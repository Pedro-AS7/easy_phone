"""Conjuntos de treino da etapa 4 (docs/plano-modelos-pequenos.md), juntando as três fontes:

- telas: trechos com as entidades marcadas (sintéticas e reais rotuladas pelo professor);
- pedidos: texto, intenção e entidades com "precisa_pesquisa" (só sintéticos: os pedidos reais só têm o julgamento
  da Gemma, e o modelo novo herdaria os erros dela), mais cópias com uma pessoa trocada por um nome de usuário;
- escolhas: (nomes pedidos, rótulo, certo ou não). Sintéticas; reais só onde o efeito diz a verdade: o controle
  escolhido pelo Laya ou pelo provedor e conferido na tela é positivo (do provedor, só quando o professor concorda:
  ele às vezes toca outro controle do caminho), o desfeito é negativo. As escolhas do professor onde o Laya disse
  nenhum ficam de fora (erradas em 33 de 57 na revisão). E telas reais com resposta conhecida: rótulos sorteados
  com os nomes que o professor deu a eles (professor parafrasear), e o nome exato de rótulos de outras telas do mesmo
  app como casos de nenhum.

Nada do conjunto congelado (tests/base) entra: trechos iguais aos dele e escolhas com os mesmos nomes pedidos no mesmo
app saem. Cada exemplo vai para treino ou validação por um hash (da tarefa, nos reais), sempre o mesmo.

Uso (no .venv): .venv/bin/python -m tools.treino.dados
Saída: data/treino/conjunto/{telas,pedidos,escolhas}-{treino,validacao}.jsonl (modo 600: têm dados reais); o terminal
mostra só contagens.
"""

import collections
import hashlib
import json
import os
import random
import re
import sys

from lmphone.executor import MAX_LABEL
from tests.base.controles import ESCOLHAS
from tests.base.mascaramento import CASOS

SYNTHETIC = "data/treino/sintetico"
REAL = "data/treino/real"
OUT = "data/treino/conjunto"
TEACHER = "gemma4_12b"
VALIDATION = 0.1
KINDS = ("pessoa", "usuario", "email", "telefone", "documento", "negocio", "instituicao", "lugar", "app")
RELEASABLE = ("negocio", "instituicao", "lugar")  # só estes podem ser liberados para pesquisa ("negocio+")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def split(key):
    return "validacao" if int(hashlib.sha1(key.encode()).hexdigest(), 16) % 1000 < VALIDATION * 1000 else "treino"


def spans(text, entities):
    """Posições (início, fim, tipo) de cada entidade no texto: todas as ocorrências, sem sobreposição; a mais longa
    ganha quando duas se cruzam."""
    found = []
    for e in sorted(entities, key=lambda e: -len(e["texto"])):
        name = e["texto"].strip()
        if not name or e["tipo"] not in KINDS:
            continue
        kind = e["tipo"] + ("+" if e.get("precisa_pesquisa") and e["tipo"] in RELEASABLE else "")
        # Palavra inteira: "Ana" não marca o meio de "Banana".
        pattern = (r"(?<!\w)" if name[0].isalnum() else "") + re.escape(name) + (r"(?!\w)" if name[-1].isalnum() else "")
        for m in re.finditer(pattern, text, re.I):
            if not any(m.start() < end and start < m.end() for start, end, _ in found):
                found.append((m.start(), m.end(), kind))
    return sorted(found)


def frozen():
    fragments = {t.casefold() for c in CASOS for t in c.get("trechos", [])} | {c["entrada"].casefold() for c in CASOS if c["tipo"] == "pedido"}
    picks = {(c["app"].split(".")[-1].casefold(), frozenset(p.casefold() for p in c["pedidos"])) for c in ESCOLHAS}
    # (app, rótulo certo, nome pedido): um nome gerado para o mesmo controle que um caso congelado pede fica de fora.
    named = {(c["app"].split(".")[-1].casefold(), r.casefold(), p.casefold()) for c in ESCOLHAS
             for r in ((c["certo"],) if isinstance(c["certo"], str) else c["certo"] or ()) for p in c["pedidos"]}
    return fragments, picks, named


def screens(dropped):
    fragments, _, _ = frozen()
    rows = []
    for e in read(os.path.join(SYNTHETIC, "tela.jsonl")):
        rows.append(("sintetico", e["app"], e["onde"], e["trechos"], e["entidades"]))
    for e in read(os.path.join(REAL, f"rotulos-telas-{TEACHER}.jsonl")):
        failed = set(e.get("falhou", []))
        rows.append(("real", e["app"], e["chave"].split(":")[0], [t for t in e["trechos"] if t not in failed], e["entidades"]))
    rows += with_short_names([r for r in rows if r[0] == "sintetico"])
    out = []
    for source, app, key, fragments_, entities in rows:
        kept = [t for t in fragments_ if t.casefold() not in fragments]
        dropped["trechos iguais aos do conjunto congelado"] += len(fragments_) - len(kept)
        if kept:
            out.append({"fonte": source, "app": app, "chave": key, "trechos": kept,
                        "spans": [spans(t, entities) for t in kept]})
    return out


def with_short_names(rows, share=0.3, seed=1):
    """Nas telas, nomes aparecem encurtados ("Duda T.", o motorista "Wellington" sozinho), e os sintéticos quase só
    têm nome e sobrenome: numa parte das telas, uma pessoa de nome composto vira "Nome S." ou só "Nome"."""
    rng = random.Random(seed)
    out = []
    for source, app, key, fragments, entities in rows:
        full = [e for e in entities if e["tipo"] == "pessoa" and len(e["texto"].split()) >= 2]
        if not full or rng.random() >= share:
            continue
        name = rng.choice(full)["texto"]
        words = name.split()
        short = f"{words[0]} {words[-1][0]}." if rng.random() < 0.5 else words[0]
        changed = [f.replace(name, short) for f in fragments]
        kept = [e for e in entities if e["texto"] != name] + [{"texto": short, "tipo": "pessoa"}]
        out.append(("sintetico-curto", app, key + "|curto", changed, kept))
    return out


def requests(dropped):
    fragments, _, _ = frozen()
    out = []
    for e in read(os.path.join(SYNTHETIC, "pedido.jsonl")):
        if e["texto"].casefold() in fragments:
            dropped["pedidos iguais aos do conjunto congelado"] += 1
            continue
        out.append({"fonte": "sintetico", "app": e["app"], "chave": e["texto"], "texto": e["texto"],
                    "intencao": e["intencao"], "spans": spans(e["texto"], e["entidades"])})
    return out + with_handles(out)


def with_handles(rows, share=0.2, seed=1):
    """Os pedidos sintéticos não têm nome de usuário ("abre o perfil do joao.vitor.silva"): numa parte dos que citam
    uma pessoa, o nome dela vira um usuário fictício (dos mesmos nomes do gerador, sem os do conjunto congelado)."""
    from tools.treino.sintetico import names
    rng = random.Random(seed)
    out = []
    for row in rows:
        people = [s for s in row["spans"] if s[2] == "pessoa"]
        if not people or rng.random() >= share:
            continue
        start, end, _ = rng.choice(people)
        handle = names(rng, 1)[1][0]
        handle = "@" + handle if rng.random() < 0.3 else handle
        text = row["texto"][:start] + handle + row["texto"][end:]
        shift = len(handle) - (end - start)
        moved = [(s, e, k) if e <= start else (s + shift, e + shift, k) for s, e, k in row["spans"] if (s, e) != (start, end)]
        out.append({**row, "fonte": "sintetico-usuario", "chave": text, "texto": text,
                    "spans": sorted(moved + [(start, start + len(handle), "usuario")])})
    return out


def picks(dropped):
    _, frozen_picks, frozen_names = frozen()
    out = []

    def add(source, app, key, wanted, labels, positive, negatives, none=False):
        # Como o executor: rótulos acima de MAX_LABEL nunca são oferecidos à escolha.
        labels = [l for l in labels if len(l) <= MAX_LABEL]
        negatives = [l for l in negatives if len(l) <= MAX_LABEL]
        if positive is not None and len(positive) > MAX_LABEL:
            dropped["escolhas com o rótulo certo acima de MAX_LABEL"] += 1
            return
        if (app.split(".")[-1].casefold(), frozenset(w.casefold() for w in wanted)) in frozen_picks:
            dropped["escolhas iguais às do conjunto congelado"] += 1
            return
        # nenhum: sabe-se que o controle não está na tela (nas reais desfeitas, só que o escolhido não era ele).
        out.append({"fonte": source, "app": app, "chave": key, "pedidos": wanted, "tela": labels,
                    "certo": positive, "errados": negatives, "nenhum": none})

    for e in read(os.path.join(SYNTHETIC, "escolha.jsonl")):
        add("sintetico", e["app"], e["onde"] + "|" + "|".join(e["pedidos"]), e["pedidos"], e["tela"], e["certo"],
            [l for l in e["tela"] if l != e["certo"]], none=e["certo"] is None)
    named_picks(add, frozen_names, dropped)
    teacher = {r["chave"]: r["certo"] for r in read(os.path.join(REAL, f"rotulos-escolhas-{TEACHER}.jsonl"))}
    from lmphone import treino
    for e in treino.entries():
        if e.get("tipo") != "escolha" or e["por"] == "rótulo exato" or not e["escolhido"] or not e["rotulos"]:
            continue
        key, labels = f"{e['session']}:{e['ts']}", list(dict.fromkeys(e["rotulos"]))
        wanted = e["passo"]["alvo"]
        if e["efeito"] == "conferido" and (e["por"] == "IA local" or teacher.get(key) == e["escolhido"]):
            # Os outros rótulos da tela não são o controle (o escolhido mudou a tela como o passo pedia).
            add("real", e["app"], e["session"], wanted, labels, e["escolhido"], [l for l in labels if l != e["escolhido"]])
        elif e["efeito"] == "desfeito":
            add("real", e["app"], e["session"], wanted, labels, None, [e["escolhido"]])  # só se sabe que este não é
        else:
            dropped["escolhas reais sem efeito que diga a verdade"] += 1
    return out


def named_picks(add, frozen_names, dropped, seed=1):
    """Telas reais com resposta conhecida (professor parafrasear): o rótulo sorteado e os nomes que o professor deu a
    ele. Cada rótulo vira uma escolha com todos os nomes e outra com um só; e cada tela ganha uma escolha sem resposta,
    com os nomes de um rótulo de outra tela do mesmo app que não está nela."""
    rng = random.Random(seed)
    rows = [r for r in read(os.path.join(REAL, f"nomes-{TEACHER}.jsonl")) if r["nomes"]]
    by_app = collections.defaultdict(list)
    for r in rows:
        app = r["app"].split(".")[-1].casefold()
        names = [n for n in r["nomes"] if (app, r["rotulo"].casefold(), n.casefold()) not in frozen_names]
        dropped["nomes iguais aos do conjunto congelado"] += len(r["nomes"]) - len(names)
        if names:
            by_app[r["app"]].append((r, names))
    for app, items in by_app.items():
        for r, names in items:
            screen = r["chave"].rsplit("|", 1)[-1]
            others = [l for l in r["tela"] if l != r["rotulo"]]
            add("nomes", app, screen, names, r["tela"], r["rotulo"], others)
            if len(names) > 1:
                add("nomes", app, screen, [rng.choice(names)], r["tela"], r["rotulo"], others)
            on_screen = {l.casefold() for l in r["tela"]}
            away = [(o, n) for o, n in items if o["rotulo"].casefold() not in on_screen]
            if away:
                _, names_away = rng.choice(away)
                add("nomes", app, screen, names_away, r["tela"], None, list(r["tela"]), none=True)
            # O plano costuma pedir o controle pelo nome exato, e ele está no app mas fora da parte visível (mais
            # abaixo, em outra tela): "Edge panels" na tela Display virou "Eye comfort shield" na suíte. Pelo nome
            # exato de rótulos de outras telas do mesmo app, a resposta é nenhum.
            labels_away = list(dict.fromkeys(o["rotulo"] for o, _ in away))
            for label in rng.sample(labels_away, min(2, len(labels_away))):
                add("fora", app, screen, [label], r["tela"], None, list(r["tela"]), none=True)


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    parts = collections.defaultdict(list)
    for row in rows:
        parts[split(row["fonte"] + "|" + row["chave"])].append(row)
    for part in ("treino", "validacao"):
        path = os.path.join(OUT, f"{name}-{part}.jsonl")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in parts[part]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {part: len(parts[part]) for part in ("treino", "validacao")}


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    dropped = collections.Counter()
    built = {"telas": screens(dropped), "pedidos": requests(dropped), "escolhas": picks(dropped)}
    for name, rows in built.items():
        sizes = write(name, rows)
        by_source = collections.Counter(r["fonte"] for r in rows)
        print(f"{name}: treino {sizes['treino']}, validação {sizes['validacao']} · " + ", ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    kinds = collections.Counter(s[2] for r in built["telas"] for spans_ in r["spans"] for s in spans_)
    print("entidades nas telas: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    print("trechos: " + ", ".join(f"{src} {sum(len(r['trechos']) for r in built['telas'] if r['fonte'] == src)}" for src in ("sintetico", "real")))
    kinds = collections.Counter(s[2] for r in built["pedidos"] for s in r["spans"])
    print("entidades nos pedidos: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    picks_ = built["escolhas"]
    print("escolhas: com o controle certo " + str(sum(r["certo"] is not None for r in picks_))
          + f", sem o controle na tela {sum(r['nenhum'] for r in picks_)}, só com um errado conhecido "
          + str(sum(r["certo"] is None and not r["nenhum"] for r in picks_)))
    for reason, n in dropped.items():
        print(f"fora: {reason}: {n}")


if __name__ == "__main__":
    sys.exit(main())
