"""Treino da etapa 4 (docs/plano-modelos-pequenos.md), no .venv-treino (PyTorch com CUDA), a partir dos conjuntos de
tools/treino/dados.py.

Dois modelos sobre o mesmo encoder base:
- marcação: classificação por token (BIO) das entidades nos trechos de tela e nos pedidos, mais uma cabeça de intenção
  do pedido (no primeiro token). "negocio+" é o negócio que o pedido manda pesquisar (precisa_pesquisa).
- escolha: cross-encoder (nomes pedidos, rótulo) -> nota, treinado por tela: os rótulos dela e a opção "nenhum"
  disputam um softmax. O mais provável é a resposta; um rótulo abaixo do limiar (tirado da validação) vira nenhum.

Uso:
    .venv-treino/Scripts/python.exe -m tools.treino.treinar marcacao --base intfloat/multilingual-e5-small
    .venv-treino/Scripts/python.exe -m tools.treino.treinar escolha --base intfloat/multilingual-e5-small
Saída: data/treino/modelos/<parte>-<base>/ (pesos, tokenizador, rótulos, medidas da validação). O terminal mostra só
números (os conjuntos têm dados reais).
"""

import argparse
import json
import os
import random
import re
import sys
import time

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

from lmphone.modelo import BLOCK, INTENTS, LABELS, NONE_LABEL, blocks, decode, query

DATA = "data/treino/conjunto"
OUT = "data/treino/modelos"
# Deixar passar um nome é pior que mascarar um rótulo: o erro em pessoa e usuário pesa mais.
HEAVY = {"pessoa": 3.0, "usuario": 3.0}


def read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- marcação ---

class Marker(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.tokens = nn.Linear(hidden, len(LABELS))
        self.intent = nn.Linear(hidden, len(INTENTS))

    def forward(self, input_ids, attention_mask):
        states = self.dropout(self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state)
        return self.tokens(states), self.intent(states[:, 0])


def token_labels(offsets, spans):
    labels, previous = [], None
    for start, end in offsets:
        if start == end:  # token especial
            labels.append(-100)
            previous = None
            continue
        span = next((s for s in spans if start < s[1] and end > s[0]), None)
        if span is None:
            labels.append(0)
        else:
            labels.append(LABELS.index(("I-" if previous == span else "B-") + span[2]))
        previous = span
    return labels


def marking_examples(tokenizer, rows_screens, rows_requests, max_length):
    examples = []
    for row in rows_screens:
        for text, spans in blocks(row["trechos"], row["spans"]):
            examples.append((text, spans, -100, row["fonte"]))
    for row in rows_requests:
        examples.append((row["texto"], row["spans"], INTENTS.index(row["intencao"]), "pedido"))
    out = []
    for text, spans, intent, source in examples:
        encoded = tokenizer(text, truncation=True, max_length=max_length, return_offsets_mapping=True)
        out.append({"input_ids": encoded["input_ids"], "labels": token_labels(encoded["offset_mapping"], spans),
                    "intent": intent, "fonte": source, "texto": text, "offsets": encoded["offset_mapping"], "spans": spans})
    return out


def pad(batch, key, value):
    width = max(len(b[key]) for b in batch)
    return torch.tensor([b[key] + [value] * (width - len(b[key])) for b in batch])


def collate_marking(batch, pad_id):
    ids = pad(batch, "input_ids", pad_id)
    return {"input_ids": ids, "attention_mask": (ids != pad_id).long(), "labels": pad(batch, "labels", -100),
            "intent": torch.tensor([b["intent"] for b in batch])}


def evaluate_marking(model, examples, device, pad_id, batch_size=32):
    """Recall e precisão por entidade (a entidade conta como achada se algum pedaço dela foi marcado com o tipo
    certo, sem o "+"; pessoa e usuário contam juntos, como a máscara trata os dois), e acerto da intenção."""
    model.eval()
    stats = {"achadas": {}, "total": {}, "marcadas": 0, "marcadas_certas": 0, "intencao": [0, 0]}
    with torch.no_grad():
        for i in range(0, len(examples), batch_size):
            batch = examples[i:i + batch_size]
            inputs = collate_marking(batch, pad_id)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits, intent = model(inputs["input_ids"].to(device), inputs["attention_mask"].to(device))
            predicted, intents = logits.argmax(-1).tolist(), intent.argmax(-1).tolist()
            for b, labels, guess in zip(batch, predicted, intents):
                got = decode(b["offsets"], labels, b["texto"])
                for s, e, k in b["spans"]:
                    kind = group(k)
                    stats["total"][kind] = stats["total"].get(kind, 0) + 1
                    if any(gs < e and ge > s and group(gk) == kind for gs, ge, gk in got):
                        stats["achadas"][kind] = stats["achadas"].get(kind, 0) + 1
                for gs, ge, gk in got:
                    stats["marcadas"] += 1
                    stats["marcadas_certas"] += any(gs < e and ge > s and group(k) == group(gk) for s, e, k in b["spans"])
                if b["intent"] != -100:
                    stats["intencao"][0] += guess == b["intent"]
                    stats["intencao"][1] += 1
    model.train()
    return stats


def group(kind):
    kind = kind.rstrip("+")
    return "pessoa/usuario" if kind in ("pessoa", "usuario") else kind


def train_marking(options, tokenizer, device, out):
    screens = {p: read(os.path.join(DATA, f"telas-{p}.jsonl")) for p in ("treino", "validacao")}
    requests = {p: read(os.path.join(DATA, f"pedidos-{p}.jsonl")) for p in ("treino", "validacao")}
    train = marking_examples(tokenizer, screens["treino"], requests["treino"], options.max_tokens)
    valid = marking_examples(tokenizer, screens["validacao"], requests["validacao"], options.max_tokens)
    print(f"exemplos: treino {len(train)}, validação {len(valid)}", flush=True)
    model = Marker(options.base).to(device)
    weights = torch.ones(len(LABELS))
    for i, name in enumerate(LABELS[1:], 1):
        weights[i] = HEAVY.get(name.split("-", 1)[1], 1.0)
    token_loss = nn.CrossEntropyLoss(weight=weights.to(device), ignore_index=-100)
    intent_loss = nn.CrossEntropyLoss(ignore_index=-100)
    pad_id = tokenizer.pad_token_id

    def step_loss(batch):
        logits, intent = model(batch["input_ids"].to(device), batch["attention_mask"].to(device))
        loss = token_loss(logits.float().view(-1, len(LABELS)), batch["labels"].to(device).view(-1))
        if (batch["intent"] != -100).any():
            loss = loss + intent_loss(intent.float(), batch["intent"].to(device))
        return loss

    history = run_training(model, train, lambda b: collate_marking(b, pad_id), step_loss, options,
                           lambda: summarize_marking(evaluate_marking(model, valid, device, pad_id)))
    os.makedirs(out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(out, "pesos.pt"))
    return {"rotulos": LABELS, "intencoes": INTENTS, "bloco": BLOCK, "historico": history}


def summarize_marking(stats):
    found = {k: f"{stats['achadas'].get(k, 0)}/{n}" for k, n in sorted(stats["total"].items())}
    precision = stats["marcadas_certas"] / max(1, stats["marcadas"])
    intent = stats["intencao"]
    return {"recall": found, "precisao": round(precision, 3), "intencao": f"{intent[0]}/{intent[1]}"}


# --- escolha ---

class Scorer(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        self.dropout = nn.Dropout(0.1)
        self.score = nn.Linear(self.encoder.config.hidden_size, 1)

    def forward(self, input_ids, attention_mask):
        states = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        return self.score(self.dropout(states[:, 0])).squeeze(-1)


def list_examples(rows, negatives, rng):
    """Uma tela por exemplo: o certo (se houver) e até `negatives` errados, embaralhados, mais a opção nenhum no fim.
    Das reais desfeitas só se sabe que um rótulo não é o certo, e elas ficam de fora (sem "nenhum")."""
    out = []
    for row in rows:
        if row["certo"] is None and not row["nenhum"]:
            continue
        labels = [l for l in dict.fromkeys(row["errados"]) if l != row["certo"]]
        rng.shuffle(labels)
        labels = labels[:negatives] + ([row["certo"]] if row["certo"] is not None else [])
        rng.shuffle(labels)
        target = labels.index(row["certo"]) if row["certo"] is not None else len(labels)
        out.append({"pedidos": row["pedidos"], "labels": labels, "target": target})
    return out


def encode_screen(tokenizer, wanted, labels, max_length):
    return tokenizer([query(wanted)] * (len(labels) + 1), labels + [NONE_LABEL], truncation=True, max_length=max_length,
                     padding=True, return_tensors="pt")


def score_screen(model, tokenizer, wanted, labels, device, max_length):
    """Probabilidade de cada rótulo ser o controle pedido e, por último, a de nenhum."""
    encoded = encode_screen(tokenizer, wanted, labels, max_length)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        logits = model(encoded["input_ids"].to(device), encoded["attention_mask"].to(device)).float()
    return torch.softmax(logits, -1).tolist()


def evaluate_picks(model, tokenizer, rows, device, max_length):
    """Para cada tela: o rótulo mais provável (ou nenhum) e se ele é o certo. A escolha final depende do limiar."""
    model.eval()
    scored = []
    for row in rows:
        labels = list(dict.fromkeys(row["tela"]))
        if not labels:
            continue
        probs = score_screen(model, tokenizer, row["pedidos"], labels, device, max_length)
        best = max(range(len(probs)), key=probs.__getitem__)
        # Real desfeita: só se sabe que aquele rótulo não é o certo.
        known_none = row["nenhum"]
        scored.append({"p": probs[best] if best < len(labels) else 0.0, "rotulo": labels[best] if best < len(labels) else None,
                       "certo": row["certo"], "nenhum": known_none, "errados": set(row["errados"])})
    model.train()
    return scored


def pick_counts(scored, threshold):
    c = {"presentes": 0, "achados": 0, "toques_errados": 0, "ausentes": 0, "nenhum_certo": 0}
    for s in scored:
        chosen = s["rotulo"] if s["rotulo"] is not None and s["p"] >= threshold else None
        if s["certo"] is not None:
            c["presentes"] += 1
            c["achados"] += chosen == s["certo"]
            c["toques_errados"] += chosen is not None and chosen != s["certo"]
        elif s["nenhum"]:
            c["ausentes"] += 1
            c["nenhum_certo"] += chosen is None
            c["toques_errados"] += chosen is not None
        else:
            c["toques_errados"] += chosen in s["errados"]
    return c


def choose_threshold(scored):
    """O menor limiar com no máximo 5% de toques errados (a meta é achar mais que o Laya sem tocar mais errado)."""
    for t in [i / 100 for i in range(0, 100, 5)]:
        if pick_counts(scored, t)["toques_errados"] <= 0.05 * len(scored):
            return t
    return 0.95


def collate_lists(batch, tokenizer, max_length):
    texts = [(query(b["pedidos"]), label) for b in batch for label in b["labels"] + [NONE_LABEL]]
    encoded = tokenizer([a for a, _ in texts], [b for _, b in texts], truncation=True, max_length=max_length,
                        padding=True, return_tensors="pt")
    return {"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"],
            "sizes": [len(b["labels"]) + 1 for b in batch], "target": torch.tensor([b["target"] for b in batch])}


def train_picks(options, tokenizer, device, out):
    rows = {p: read(os.path.join(DATA, f"escolhas-{p}.jsonl")) for p in ("treino", "validacao")}
    rng = random.Random(options.semente)
    train = list_examples(rows["treino"], options.negativos, rng)
    print(f"telas: treino {len(train)}; validação {len(rows['validacao'])}", flush=True)
    model = Scorer(options.base).to(device)

    def step_loss(batch):
        logits = model(batch["input_ids"].to(device), batch["attention_mask"].to(device)).float()
        width = max(batch["sizes"])
        rows_ = torch.full((len(batch["sizes"]), width), float("-inf"), device=device)
        at = 0
        for i, n in enumerate(batch["sizes"]):
            rows_[i, :n] = logits[at:at + n]
            at += n
        return nn.functional.cross_entropy(rows_, batch["target"].to(device))

    def report():
        scored = evaluate_picks(model, tokenizer, rows["validacao"], device, options.max_tokens)
        t = choose_threshold(scored)
        return {"limiar": t, **pick_counts(scored, t)}

    history = run_training(model, train, lambda b: collate_lists(b, tokenizer, options.max_tokens), step_loss, options, report)
    os.makedirs(out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(out, "pesos.pt"))
    return {"limiar": history[-1]["validacao"]["limiar"], "nenhum": NONE_LABEL, "historico": history}


# --- comum ---

def run_training(model, examples, collate, step_loss, options, report):
    rng = random.Random(options.semente)
    optimizer = torch.optim.AdamW(model.parameters(), lr=options.lr, weight_decay=0.01)
    steps = options.epocas * ((len(examples) + options.lote - 1) // options.lote)
    schedule = get_linear_schedule_with_warmup(optimizer, int(0.06 * steps), steps)
    history, started = [], time.monotonic()
    model.train()
    for epoch in range(1, options.epocas + 1):
        order = list(range(len(examples)))
        rng.shuffle(order)
        total = 0.0
        for i in range(0, len(order), options.lote):
            batch = collate([examples[j] for j in order[i:i + options.lote]])
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = step_loss(batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
            total += loss.item()
        measured = report()
        history.append({"epoca": epoch, "perda": round(total / max(1, len(order) / options.lote), 4), "validacao": measured,
                        "segundos": round(time.monotonic() - started)})
        print(json.dumps(history[-1], ensure_ascii=False), flush=True)
    return history


def main():
    parser = argparse.ArgumentParser(description="Treino dos modelos pequenos (etapa 4)")
    parser.add_argument("parte", choices=["marcacao", "escolha"])
    parser.add_argument("--base", default="intfloat/multilingual-e5-small")
    parser.add_argument("--epocas", type=int, default=4)
    parser.add_argument("--lote", type=int, default=16)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--negativos", type=int, default=15, help="escolha: rótulos errados por tela no treino")
    parser.add_argument("--semente", type=int, default=1)
    options = parser.parse_args()
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    torch.manual_seed(options.semente)
    device = "cuda"
    tokenizer = AutoTokenizer.from_pretrained(options.base)
    out = os.path.join(OUT, f"{options.parte}-{re.sub(r'[^\w.-]', '_', options.base.split('/')[-1])}")
    started = time.monotonic()
    meta = (train_marking if options.parte == "marcacao" else train_picks)(options, tokenizer, device, out)
    tokenizer.save_pretrained(out)
    meta.update(base=options.base, parte=options.parte, max_tokens=options.max_tokens, opcoes=vars(options),
                minutos=round((time.monotonic() - started) / 60, 1), data=time.strftime("%Y-%m-%d %H:%M"))
    with open(os.path.join(out, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"gravado: {out} · {meta['minutos']} min")


if __name__ == "__main__":
    sys.exit(main())
