"""Servidor dos modelos treinados na etapa 4, no .venv-treino (PyTorch). Tem a API do servidor do Laya (`/`, `/pick`,
`/private`) e mais as chamadas que hoje vão à Gemma:

- POST /entities {"text": "trecho • trecho • ..."} -> {"itens": [{"texto", "tipo"}], "seconds"}  (como find_private)
- POST /judge {"text": "pedido"} -> {"intencao", "entidades": [{"texto", "tipo", "precisa_pesquisa"}], "seconds"}
- POST /pick {"wanted": [...], "labels": [...]} -> {"label", "p", "ranking", "seconds"}  (como o Laya)
- POST /private {"fragments": [...]} -> {"p": [1.0, ...]}: sem filtro, todo trecho vai à marcação (ela é rápida)

É o servidor de avaliação (tests/eval_base.py --novo); o da etapa 5 roda ONNX sem PyTorch.

Uso: .venv-treino/Scripts/python.exe -m tools.treino.servidor --marcacao data/treino/modelos/marcacao-... --escolha data/treino/modelos/escolha-...
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

import torch
from transformers import AutoTokenizer

from .treinar import BLOCK, INTENTS, Marker, Scorer, blocks, decode, score_screen

PORT = 8790
LOCK = Lock()  # uma chamada por vez na GPU


class Models:
    def __init__(self, marking, picking, device):
        self.device = device
        if marking:
            self.marking_meta = json.load(open(os.path.join(marking, "modelo.json"), encoding="utf-8"))
            self.marking_tokenizer = AutoTokenizer.from_pretrained(marking)
            self.marker = Marker(self.marking_meta["base"])
            self.marker.load_state_dict(torch.load(os.path.join(marking, "pesos.pt"), map_location="cpu"))
            self.marker.to(device).eval()
        if picking:
            self.picking_meta = json.load(open(os.path.join(picking, "modelo.json"), encoding="utf-8"))
            self.picking_tokenizer = AutoTokenizer.from_pretrained(picking)
            self.scorer = Scorer(self.picking_meta["base"])
            self.scorer.load_state_dict(torch.load(os.path.join(picking, "pesos.pt"), map_location="cpu"))
            self.scorer.to(device).eval()
            self.threshold = self.picking_meta["limiar"]

    def mark(self, text):
        """Entidades de um texto (o bloco é cortado como no treino) e a intenção, se for um pedido."""
        found, intent = [], None
        fragments = text.split(" • ")
        for block, _ in blocks(fragments, [[] for _ in fragments], BLOCK):
            encoded = self.marking_tokenizer(block, truncation=True, max_length=self.marking_meta.get("max_tokens", 256),
                                             return_offsets_mapping=True, return_tensors="pt")
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                logits, intents = self.marker(encoded["input_ids"].to(self.device), encoded["attention_mask"].to(self.device))
            offsets = encoded["offset_mapping"][0].tolist()
            for s, e, k in decode(offsets, logits.argmax(-1)[0].tolist(), block):
                found.append({"texto": block[s:e].strip(), "tipo": k})
            intent = intent or INTENTS[intents.argmax(-1)[0].item()]
        return found, intent

    def pick(self, wanted, labels):
        if not labels:
            return {"label": None, "p": 0.0, "ranking": []}
        probs = score_screen(self.scorer, self.picking_tokenizer, wanted, labels, self.device,
                             self.picking_meta.get("max_tokens", 256))
        # O ranking leva a opção nenhum junto (como None), para o relatório mostrar onde ela ficou.
        ranking = sorted(zip(labels + [None], (round(p, 3) for p in probs)), key=lambda x: -x[1])
        best, p = ranking[0]
        return {"label": best if best is not None and p >= self.threshold else None, "p": p, "ranking": ranking[:10]}


def handler(models, name):
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
            self.reply({"model": name, "min_p": getattr(models, "threshold", None)})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            started = time.monotonic()
            with LOCK:
                if self.path == "/entities":
                    items, _ = models.mark(body["text"])
                    # Como a Gemma na tela: só pessoa e usuário. E-mail, telefone e documento vão como usuário (troca
                    # do texto literal), por cima das regras fixas; negócio, instituição e lugar ficam.
                    data = {"itens": [{"texto": i["texto"], "tipo": "pessoa" if i["tipo"] == "pessoa" else "usuario"}
                                      for i in items if i["tipo"] in ("pessoa", "usuario", "email", "telefone", "documento")]}
                elif self.path == "/judge":
                    items, intent = models.mark(body["text"])
                    data = {"intencao": intent, "entidades": [
                        {"texto": i["texto"], "tipo": i["tipo"].rstrip("+"), "precisa_pesquisa": i["tipo"].endswith("+")}
                        for i in items]}
                elif self.path == "/pick":
                    data = models.pick(body["wanted"], body["labels"])
                elif self.path == "/private":
                    data = {"p": [1.0] * len(body["fragments"])}
                else:
                    self.send_error(404)
                    return
            data["seconds"] = round(time.monotonic() - started, 3)
            self.reply(data)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Servidor dos modelos da etapa 4 (avaliação)")
    parser.add_argument("--marcacao")
    parser.add_argument("--escolha")
    parser.add_argument("--porta", type=int, default=PORT)
    options = parser.parse_args()
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    models = Models(options.marcacao, options.escolha, "cuda")
    name = " + ".join(os.path.basename(p) for p in (options.marcacao, options.escolha) if p)
    print(f"no ar na porta {options.porta}: {name}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", options.porta), handler(models, name)).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
