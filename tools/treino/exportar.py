"""Etapa 5 (docs/plano-modelos-pequenos.md): corta o vocabulário, exporta para ONNX e quantiza em 8 bits, no
.venv-treino.

O e5-small tem 250 mil tokens de 100 línguas; a tabela deles é 384 dos 466 MB do modelo. Com --cortar, ficam só os
tokens que aparecem nos textos do projeto, os mais frequentes do vocabulário original e todo caractere solto (37 MB em
int8 em vez de 117), mas palavra fora dos textos passa a ser quebrada de outro jeito ("Wellington" em "Well", "ing",
"ton") e o modelo perdeu nomes no conjunto congelado; por isso o padrão é não cortar.

Quantização: a versão que vale (modelo-tabela.onnx, 173 MB) tem só a tabela de tokens em int8, que é quase todo o
tamanho; as camadas ficam em fp32. Com tudo em int8 (modelo-int8.onnx, 113 MB, dinâmica e por canal) o modelo perdeu
duas pessoas e passou de 14 toques errados no conjunto congelado; a tabela em int8 só arredonda os pesos uma vez e
empatou com o fp32.

Uso: .venv-treino/Scripts/python.exe -m tools.treino.exportar [--cortar] data/treino/modelos/marcacao-... data/treino/modelos/escolha-...
Saída, em <modelo>/onnx/: modelo.onnx (fp32), modelo-tabela.onnx, modelo-int8.onnx, tokenizer.json, modelo.json; o
limiar da escolha é recalculado na validação com modelo-tabela.onnx. O terminal mostra só números.
"""

import json
import os
import sys

import numpy as np
import torch
from tokenizers import Tokenizer

from lmphone.modelo import NONE_LABEL, SEPARATOR, query

from .treinar import DATA, Marker, Scorer, choose_threshold, pick_counts, read

TOP = 20000  # tokens mais frequentes do vocabulário original que ficam mesmo sem aparecer nos textos


def corpus():
    """Os textos que o modelo vê no projeto: conjuntos de treino e validação e tudo o que a coleta guardou."""
    texts = []
    for part in ("treino", "validacao"):
        for row in read(os.path.join(DATA, f"telas-{part}.jsonl")):
            texts += row["trechos"]
        texts += [row["texto"] for row in read(os.path.join(DATA, f"pedidos-{part}.jsonl"))]
        for row in read(os.path.join(DATA, f"escolhas-{part}.jsonl")):
            texts += row["tela"] + [query(row["pedidos"])]
    from lmphone import treino
    for e in treino.entries():
        texts += [e["texto"]] if e.get("tipo") in ("trecho", "pedido") else e.get("rotulos", [])
    return texts + [NONE_LABEL, SEPARATOR]


def trim(tokenizer_path, texts, cut):
    """Novo tokenizer.json só com os tokens que ficam (todos, sem `cut`), e os ids antigos deles (na ordem nova)."""
    spec = json.load(open(tokenizer_path, encoding="utf-8"))
    vocab = spec["model"]["vocab"]
    tokenizer = Tokenizer.from_file(tokenizer_path)
    used = set()
    for i in range(0, len(texts), 2000):
        for encoding in tokenizer.encode_batch(texts[i:i + 2000]):
            used.update(encoding.ids)
    special = {a["id"] for a in spec["added_tokens"]}
    singles = {i for i, (piece, _) in enumerate(vocab) if len(piece.replace("▁", "")) <= 1}
    frequent = set(sorted(range(len(vocab)), key=lambda i: -vocab[i][1])[:TOP])
    keep = sorted(used | special | singles | frequent) if cut else list(range(len(vocab)))
    new_id = {old: new for new, old in enumerate(keep)}
    spec["model"]["vocab"] = [vocab[i] for i in keep]
    spec["model"]["unk_id"] = new_id[spec["model"]["unk_id"]]
    for token in spec["added_tokens"]:
        token["id"] = new_id[token["id"]]
    for token in spec["post_processor"].get("special_tokens", {}).values():
        token["ids"] = [new_id[i] for i in token["ids"]]
    spec["truncation"] = None
    spec["padding"] = None
    return spec, keep, len(used)


def export(directory, cut):
    meta = json.load(open(os.path.join(directory, "modelo.json"), encoding="utf-8"))
    out = os.path.join(directory, "onnx")
    os.makedirs(out, exist_ok=True)
    texts = corpus()
    spec, keep, used = trim(os.path.join(directory, "tokenizer.json"), texts, cut)
    with open(os.path.join(out, "tokenizer.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    # O corte não pode mudar como os textos do projeto viram tokens.
    old, new = Tokenizer.from_file(os.path.join(directory, "tokenizer.json")), Tokenizer.from_file(os.path.join(out, "tokenizer.json"))
    old.no_padding()  # o tokenizador salvo pelo treino pode ter ficado com o preenchimento do lote ligado
    old.no_truncation()
    sample = texts[::7]
    remap = {o: n for n, o in enumerate(keep)}
    differ = sum([remap.get(i) for i in a.ids] != b.ids for a, b in zip(old.encode_batch(sample), new.encode_batch(sample)))
    print(f"{os.path.basename(directory)}: vocabulário {len(spec['model']['vocab'])} de 250002 ({used} usados nos textos); "
          f"tokenização diferente em {differ} de {len(sample)} textos", flush=True)

    model = Marker(meta["base"]) if meta["parte"] == "marcacao" else Scorer(meta["base"])
    model.load_state_dict(torch.load(os.path.join(directory, "pesos.pt"), map_location="cpu"))
    embeddings = model.encoder.embeddings.word_embeddings
    model.encoder.embeddings.word_embeddings = torch.nn.Embedding.from_pretrained(
        embeddings.weight.data[keep].clone(), freeze=True, padding_idx=remap[1])
    model.encoder.config.vocab_size = len(keep)
    model.eval()
    ids = torch.tensor([new.encode("Ana Souza • Settings").ids])
    names = ["tokens", "intencao"] if meta["parte"] == "marcacao" else ["nota"]
    axes = {"input_ids": {0: "lote", 1: "seq"}, "attention_mask": {0: "lote", 1: "seq"}}
    axes.update({name: ({0: "lote", 1: "seq"} if name == "tokens" else {0: "lote"}) for name in names})
    fp32 = os.path.join(out, "modelo.onnx")
    torch.onnx.export(model, (ids, torch.ones_like(ids)), fp32, input_names=["input_ids", "attention_mask"],
                      output_names=names, dynamic_axes=axes, opset_version=17, dynamo=False)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = os.path.join(out, "modelo-int8.onnx")
    quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8, per_channel=True)
    table = os.path.join(out, "modelo-tabela.onnx")
    quantize_dynamic(fp32, table, weight_type=QuantType.QInt8, op_types_to_quantize=["Gather"])
    sizes = {os.path.basename(p): round(os.path.getsize(p) / 2**20) for p in (fp32, table, int8)}
    meta_out = {"parte": meta["parte"], "base": meta["base"], "max_tokens": meta.get("max_tokens", 256),
                "rotulos": meta.get("rotulos"), "intencoes": meta.get("intencoes"), "bloco": meta.get("bloco"),
                "limiar": meta.get("limiar"), "vocabulario": len(keep), "tamanho_mb": sizes}
    if meta["parte"] == "escolha":
        meta_out["limiar"] = recalibrate(table, os.path.join(out, "tokenizer.json"), meta.get("max_tokens", 256))
    with open(os.path.join(out, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=1)
    print(f"  tamanhos (MB): {sizes}; limiar {meta_out['limiar']}", flush=True)


def recalibrate(path, tokenizer_path, max_tokens):
    """O limiar da escolha, de novo na validação, agora com o modelo exportado."""
    from lmphone.modelo_server import Picker
    picker = Picker(path, tokenizer_path, max_tokens, threshold=0.0)
    scored = []
    for row in read(os.path.join(DATA, "escolhas-validacao.jsonl")):
        labels = list(dict.fromkeys(row["tela"]))
        if not labels:
            continue
        probs = picker.probabilities(row["pedidos"], labels)
        best = int(np.argmax(probs))
        scored.append({"p": float(probs[best]) if best < len(labels) else 0.0, "rotulo": labels[best] if best < len(labels) else None,
                       "certo": row["certo"], "nenhum": row["nenhum"], "errados": set(row["errados"])})
    threshold = choose_threshold(scored)
    print(f"  validação do modelo exportado com limiar {threshold}: {pick_counts(scored, threshold)}", flush=True)
    return threshold


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    cut = "--cortar" in sys.argv
    for directory in [a for a in sys.argv[1:] if a != "--cortar"]:
        export(directory, cut)


if __name__ == "__main__":
    sys.exit(main())
