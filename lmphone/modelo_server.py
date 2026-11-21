"""Servidor dos modelos pequenos (etapa 5 de docs/plano-modelos-pequenos.md): ONNX na CPU, sem PyTorch. Roda no
.venv-modelo (onnxruntime, tokenizers, numpy) e tem a API do servidor do Laya, mais as chamadas que hoje vão à Gemma:

- GET / -> {"model", "min_p"}
- POST /entities {"text": "trecho • trecho • ..."} -> {"itens": [{"texto", "tipo"}]}  (como local_ai.find_private)
- POST /judge {"text": "pedido"} -> {"intencao", "entidades": [{"texto", "tipo", "precisa_pesquisa"}]}
- POST /pick {"wanted": [...], "labels": [...]} -> {"label", "p", "ranking"}  (como o Laya)
- POST /private {"fragments": [...]} -> {"p": [1.0, ...]}: sem filtro, todo trecho vai à marcação

Toda resposta leva "seconds".

Uso: .venv-modelo/bin/python -m lmphone.modelo_server [--marcacao DIR] [--escolha DIR] [--variante tabela] [--porta 8788]
(DIR é a pasta onnx/ que tools/treino/exportar.py grava; o padrão é data/modelos/marcacao e data/modelos/escolha, que o
lmphone.run usa).
"""

import argparse
import hashlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

# O numpy aqui só faz contas pequenas; com uma thread o OpenBLAS não reserva um buffer por núcleo (490 MB no Windows).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import onnxruntime  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402

from .modelo import BLOCK, INTENTS, NONE_LABEL, SEPARATOR, blocks, decode, query  # noqa: E402

PORT = int(os.environ.get("LMPHONE_LAYA_PORT", "8788"))
# Os modelos em uso: cópia das pastas onnx/ de tools/treino/exportar.py (fora do git, como todo data/).
MODELS = "data/modelos"
LOCK = Lock()  # uma chamada por vez: cada sessão já usa os núcleos da CPU


def session(path):
    options = onnxruntime.SessionOptions()
    options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Sem a reserva de memória do onnxruntime: com entradas de tamanhos variados ela cresce sem voltar (1,3 GB depois
    # do conjunto congelado, contra uns 300 MB sem ela) e o tempo não muda.
    options.enable_cpu_mem_arena = False
    return onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"])


TOKENIZERS = {}


def tokenizer(path):
    """Os dois modelos têm o mesmo vocabulário (250 mil tokens, 256 MB carregado): um tokenizador só por conteúdo.
    Cada modelo põe o seu limite de tokens antes de usar (as chamadas são uma por vez, ver LOCK)."""
    key = hashlib.sha1(open(path, "rb").read()).hexdigest()
    if key not in TOKENIZERS:
        TOKENIZERS[key] = Tokenizer.from_file(path)
    return TOKENIZERS[key]


def batch(encodings, pad_id=1):
    width = max(len(e.ids) for e in encodings)
    ids = np.full((len(encodings), width), pad_id, dtype=np.int64)
    mask = np.zeros((len(encodings), width), dtype=np.int64)
    for i, e in enumerate(encodings):
        ids[i, :len(e.ids)] = e.ids
        mask[i, :len(e.ids)] = 1
    return {"input_ids": ids, "attention_mask": mask}


class Marker:
    def __init__(self, path, tokenizer_path, max_tokens):
        self.session = session(path)
        self.tokenizer, self.max_tokens = tokenizer(tokenizer_path), max_tokens

    def mark(self, text):
        """Entidades de um texto (cortado em blocos como no treino) e a intenção, se for um pedido."""
        found, intent = [], None
        fragments = text.split(SEPARATOR)
        for block, _ in blocks(fragments, [[] for _ in fragments], BLOCK):
            self.tokenizer.enable_truncation(self.max_tokens)
            encoding = self.tokenizer.encode(block)
            tokens, intents = self.session.run(None, batch([encoding]))
            for s, e, k in decode(encoding.offsets, tokens[0].argmax(-1).tolist(), block):
                found.append({"texto": block[s:e].strip(), "tipo": k})
            intent = intent or INTENTS[int(intents[0].argmax())]
        return found, intent


class Picker:
    def __init__(self, path, tokenizer_path, max_tokens, threshold):
        self.session = session(path)
        self.tokenizer, self.max_tokens = tokenizer(tokenizer_path), max_tokens
        self.threshold = threshold

    def probabilities(self, wanted, labels):
        """Probabilidade de cada rótulo ser o controle pedido e, por último, a de nenhum."""
        q = query(wanted)
        self.tokenizer.enable_truncation(self.max_tokens)
        encodings = self.tokenizer.encode_batch([(q, label) for label in labels + [NONE_LABEL]])
        scores = self.session.run(None, batch(encodings))[0].astype(np.float64)
        scores = np.exp(scores - scores.max())
        return scores / scores.sum()

    def pick(self, wanted, labels):
        if not labels:
            return {"label": None, "p": 0.0, "ranking": []}
        probs = self.probabilities(wanted, labels)
        # O ranking leva a opção nenhum junto (como None), para o relatório mostrar onde ela ficou.
        ranking = sorted(zip(labels + [None], (round(float(p), 3) for p in probs)), key=lambda x: -x[1])
        best, p = ranking[0]
        return {"label": best if best is not None and p >= self.threshold else None, "p": p, "ranking": ranking[:10]}


VARIANTS = {"tabela": "modelo-tabela.onnx", "int8": "modelo-int8.onnx", "fp32": "modelo.onnx"}


def load(directory, variant):
    meta = json.load(open(os.path.join(directory, "modelo.json"), encoding="utf-8"))
    path = os.path.join(directory, VARIANTS[variant])
    tokenizer = os.path.join(directory, "tokenizer.json")
    if meta["parte"] == "marcacao":
        return Marker(path, tokenizer, meta["max_tokens"])
    return Picker(path, tokenizer, meta["max_tokens"], meta["limiar"])


def handler(marker, picker, name):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply({"model": name, "min_p": picker.threshold if picker else None})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            started = time.monotonic()
            with LOCK:
                if self.path == "/entities":
                    items, _ = marker.mark(body["text"])
                    # Como a Gemma na tela: só pessoa e usuário. E-mail, telefone e documento vão como usuário (troca
                    # do texto literal), por cima das regras fixas; negócio, instituição e lugar ficam.
                    data = {"itens": [{"texto": i["texto"], "tipo": "pessoa" if i["tipo"] == "pessoa" else "usuario"}
                                      for i in items if i["tipo"] in ("pessoa", "usuario", "email", "telefone", "documento")]}
                elif self.path == "/judge":
                    items, intent = marker.mark(body["text"])
                    data = {"intencao": intent, "entidades": [
                        {"texto": i["texto"], "tipo": i["tipo"].rstrip("+"), "precisa_pesquisa": i["tipo"].endswith("+")}
                        for i in items]}
                elif self.path == "/pick":
                    data = picker.pick(body["wanted"], body["labels"])
                elif self.path == "/private":
                    data = {"p": [1.0] * len(body["fragments"])}
                else:
                    self.send_error(404)
                    return
            data["seconds"] = round(time.monotonic() - started, 3)
            self.reply(data)

    return Handler


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser = argparse.ArgumentParser(description="Servidor dos modelos pequenos (ONNX, CPU)")
    parser.add_argument("--marcacao", default=MODELS + "/marcacao", help="pasta onnx/ do modelo de marcação")
    parser.add_argument("--escolha", default=MODELS + "/escolha", help="pasta onnx/ do modelo de escolha")
    parser.add_argument("--variante", choices=list(VARIANTS), default="tabela",
                        help="tabela: só a tabela de tokens em int8 (padrão); int8: tudo; fp32: nada")
    parser.add_argument("--porta", type=int, default=PORT)
    options = parser.parse_args()
    marker, picker = load(options.marcacao, options.variante), load(options.escolha, options.variante)
    name = f"modelos pequenos ({options.variante})"
    print(f"no ar na porta {options.porta}: {name}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", options.porta), handler(marker, picker, name)).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
