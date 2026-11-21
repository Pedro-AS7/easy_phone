"""Professor local (etapa 3 de docs/plano-modelos-pequenos.md): um modelo grande no Ollama rotula as telas reais da
coleta com o mesmo esquema dos dados sintéticos, sem nada sair da máquina.

Antes de rotular, cada candidato é medido no conjunto congelado (`tests/base`, dados fictícios), com a tela inteira de
uma vez (a Gemma do serviço vê trecho por trecho). Para comparar, o mesmo teste roda com a Gemma atual.

Uso (no .venv; Ollama no ar):
    .venv/bin/python -m tools.treino.professor avaliar --modelo gemma4:12b      # mascaramento e controles
    .venv/bin/python -m tools.treino.professor avaliar --modelo qwen3:14b --parte controles
    .venv/bin/python -m tools.treino.professor rotular --modelo gemma4:12b      # dados reais; retoma de onde parou
    .venv/bin/python -m tools.treino.professor parafrasear --modelo gemma4:12b  # outros nomes de rótulos reais, para a escolha
Saída da avaliação: reports/professor-<modelo>-<data>.json, com cada caso; o terminal mostra os números e os erros.
Os rótulos dos dados reais ficam em data/treino/real/rotulos-*.jsonl (modo 600), e o terminal mostra só contagens.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

from tests.base.controles import ESCOLHAS
from tests.base.mascaramento import CASOS

OLLAMA = "http://127.0.0.1:11434"
TYPES = ["pessoa", "usuario", "email", "telefone", "documento", "negocio", "instituicao", "lugar"]

SCREEN_PROMPT = """You label the text of an Android phone screen for a privacy filter. The fragments are the
accessibility texts of the screen, in order. List every entity, copied exactly as it appears inside a fragment:
- "pessoa": the name of any person, private or famous (full name, first name, surname or nickname), also inside
  sentences, searches and titles like "Made for X" or "Playlist • X";
- "usuario": a social network username or handle (with or without @);
- "email", "telefone", "documento" (CPF, RG, card number, CEP);
- "negocio" (shop, restaurant, company), "instituicao" (university, agency, bank, newspaper), "lugar" (city,
  neighbourhood, address, country).
Not entities: interface labels, app names, brands of products, titles of songs, videos, books or playlists (unless they
contain a person's name, then list only the name), times, counts, prices. If there is nothing, return an empty list."""

REQUEST_PROMPT = """You analyse a request a phone owner makes to their assistant (often informal Brazilian Portuguese).
Intent: "pesquisa" (needs public information from the internet), "acao" (done entirely on the phone: messages, calls,
apps, settings, reminders, playing media) or "mista" (both). List the proper names in it, copied exactly as written
(even in lowercase): "pessoa" (any person, private or famous), "usuario", "email", "telefone", "documento" (CPF, RG,
card), "negocio", "instituicao", "lugar", "app".
"precisa_pesquisa" is true only for a business, institution or place whose public information must be looked up."""

PICK_PROMPT = """A phone assistant wants to tap the control that a plan step names ("wanted": names for one and the
same control) on a screen whose labels are listed. Answer with the exact label that is that control (the same function
under another name, an icon description, a translation or an internal tag also count), or "(none)" when no label on
the screen is that control. A control that is only related, or does something else, is "(none)"."""

ENTITY = {"type": "object", "properties": {"texto": {"type": "string"}, "tipo": {"type": "string", "enum": TYPES}},
          "required": ["texto", "tipo"]}
SCREEN_SCHEMA = {"type": "object", "properties": {"entidades": {"type": "array", "items": ENTITY}}, "required": ["entidades"]}
REQUEST_SCHEMA = {"type": "object", "properties": {
    "intencao": {"type": "string", "enum": ["pesquisa", "acao", "mista"]},
    "entidades": {"type": "array", "items": {"type": "object", "properties": {
        "texto": {"type": "string"}, "tipo": {"type": "string", "enum": TYPES + ["app"]},
        "precisa_pesquisa": {"type": "boolean"}}, "required": ["texto", "tipo", "precisa_pesquisa"]}}},
    "required": ["intencao", "entidades"]}


NONE = "(none)"  # com null no esquema (anyOf), o Ollama nunca deixou o modelo responder "nenhum"


def pick_schema(labels):
    return {"type": "object", "properties": {"certo": {"type": "string", "enum": labels + [NONE]}}, "required": ["certo"]}


def pick(model, wanted, labels):
    data, seconds = chat(model, PICK_PROMPT, json.dumps({"wanted": wanted, "screen": labels}, ensure_ascii=False),
                         pick_schema(labels))
    got = data.get("certo")
    return (None if got in (None, NONE) else got), seconds


def chat(model, system, user, schema, timeout=600):
    body = {"model": model, "stream": False, "think": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4096},  # corta laços de repetição
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    request = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        answer = json.load(response)
    return json.loads(answer["message"]["content"]), time.monotonic() - started


def fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


def words(text):
    return [w for w in re.findall(r"\w+", fold(text)) if len(w) >= 3]


def label_screen(model, fragments):
    data, seconds = chat(model, SCREEN_PROMPT, "Fragments:\n" + json.dumps(fragments, ensure_ascii=False), SCREEN_SCHEMA)
    return data.get("entidades", []), seconds


def label_split(model, fragments):
    """Rótulos de um bloco; se a resposta sai cortada (laço de repetição), rotula as metades. Devolve as entidades e
    os trechos que nem sozinhos tiveram resposta."""
    try:
        return label_screen(model, fragments)[0], []
    except json.JSONDecodeError:
        if len(fragments) == 1:
            return [], fragments
        half = len(fragments) // 2
        first, failed_first = label_split(model, fragments[:half])
        second, failed_second = label_split(model, fragments[half:])
        return first + second, failed_first + failed_second


def score_masking(case, entities):
    """Erros do professor num caso: pessoa ou usuário que ele não marcou, contato sem marcação, texto a manter marcado."""
    people = [fold(e["texto"]) for e in entities if e["tipo"] in ("pessoa", "usuario")]
    contacts = [fold(e["texto"]) for e in entities if e["tipo"] in ("email", "telefone", "documento")]
    errors = []
    for name in case["pessoas"]:
        missing = [w for w in words(name) if not any(w in re.findall(r"\w+", p) for p in people)]
        if missing:
            errors.append(("pessoa", name))
    for user in case["usuarios"]:
        if not any(fold(user.lstrip("@")) in p for p in people):
            errors.append(("usuario", user))
    for value in case["outros"]:
        if not any(fold(value) in c or c in fold(value) for c in contacts if c):
            errors.append(("outro", value))
    for value in case["manter"] + case["liberar"]:
        if any(set(words(value)) & set(re.findall(r"\w+", p)) for p in people):
            errors.append(("manter", value))
    return errors


def evaluate_masking(model):
    totals = {k: [0, 0] for k in ("pessoa", "usuario", "outro", "manter", "intencao", "casos")}
    rows, times = [], []
    for case in CASOS:
        if case["tipo"] == "tela":
            entities, seconds = label_screen(model, case["trechos"])
            intent = None
        else:
            data, seconds = chat(model, REQUEST_PROMPT, f"Request: {case['entrada']}", REQUEST_SCHEMA)
            entities, intent = data.get("entidades", []), data.get("intencao")
        times.append(seconds)
        errors = score_masking(case, entities)
        if case["intencao"] and intent not in case["intencao"]:
            errors.append(("intencao", f"{intent} (esperado {'|'.join(case['intencao'])})"))
        for kind, n in (("pessoa", len(case["pessoas"])), ("usuario", len(case["usuarios"])), ("outro", len(case["outros"])),
                        ("manter", len(case["manter"]) + len(case["liberar"])), ("intencao", 1 if case["intencao"] else 0)):
            totals[kind][1] += n
            totals[kind][0] += n - sum(1 for k, _ in errors if k == kind)
        totals["casos"][1] += 1
        totals["casos"][0] += not errors
        rows.append({"id": case["id"], "erros": errors, "entidades": entities, "segundos": round(seconds, 1)})
        print(f"{case['id']:28} {'ok' if not errors else '; '.join(f'{k}: {v}' for k, v in errors)}", flush=True)
    return totals, rows, times


def evaluate_picks(model):
    totals = {"presentes": [0, 0], "ausentes": [0, 0], "toques_errados": [0, 0]}
    rows, times = [], []
    for case in ESCOLHAS:
        labels = list(dict.fromkeys(case["tela"]))
        got, seconds = pick(model, case["pedidos"], labels)
        times.append(seconds)
        right = case["certo"]
        rights = right if isinstance(right, tuple) else (right,)
        if right is None:
            totals["ausentes"][1] += 1
            totals["ausentes"][0] += got is None
            wrong = got is not None
        else:
            totals["presentes"][1] += 1
            totals["presentes"][0] += got in rights
            wrong = got is not None and got not in rights
        totals["toques_errados"][0] += wrong
        mark = "ok" if (got in rights) else ("TOQUE ERRADO" if wrong else "nenhum")
        rows.append({"id": case["id"], "certo": right, "obtido": got, "segundos": round(seconds, 1)})
        print(f"{case['id']:28} {mark:12} {got!r} (certo {right!r})", flush=True)
    return totals, rows, times


CHUNK = 40  # trechos por chamada: os de uma mesma tarefa, na ordem em que apareceram


def write_private(path, row):
    """Uma linha num arquivo de dados reais (modo 600, como treino.record)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def done_keys(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {json.loads(line)["chave"] for line in f if line.strip()}
    except OSError:
        return set()


def label_real(model):
    """Rotula os trechos da coleta (cada texto distinto uma vez, junto com os da mesma tarefa) e as escolhas que não
    foram por rótulo exato. Grava em data/treino/real/rotulos-*.jsonl e retoma de onde parou. Só imprime contagens."""
    from lmphone import treino
    tag = re.sub(r"[^\w.-]", "_", model)
    screens_path = os.path.join(treino.DIR, f"rotulos-telas-{tag}.jsonl")
    picks_path = os.path.join(treino.DIR, f"rotulos-escolhas-{tag}.jsonl")
    seen, tasks, choices = set(), {}, []
    for entry in treino.entries():
        if entry["tipo"] == "trecho" and entry["texto"] not in seen:
            seen.add(entry["texto"])
            tasks.setdefault(entry["session"], []).append((entry.get("app"), entry["texto"]))
        elif entry["tipo"] == "escolha" and entry["por"] != "rótulo exato" and entry["rotulos"]:
            choices.append(entry)
    jobs = [(f"{session}:{n}", items[n:n + CHUNK]) for session, items in tasks.items() for n in range(0, len(items), CHUNK)]
    done = done_keys(screens_path)
    jobs = [j for j in jobs if j[0] not in done]
    print(f"trechos distintos: {len(seen)} em {len(tasks)} tarefas; blocos a rotular: {len(jobs)} (já feitos: {len(done)})")
    kinds, started = {}, time.monotonic()
    for n, (key, items) in enumerate(jobs, 1):
        fragments = [text for _, text in items]
        entities, failed = label_split(model, fragments)
        entities = [e for e in entities if any(e["texto"] in f for f in fragments)]
        for e in entities:
            kinds[e["tipo"]] = kinds.get(e["tipo"], 0) + 1
        kinds["(sem resposta)"] = kinds.get("(sem resposta)", 0) + len(failed)
        write_private(screens_path, {"chave": key, "modelo": model, "app": items[0][0], "trechos": fragments,
                                     "entidades": entities, "falhou": failed})
        if n % 25 == 0 or n == len(jobs):
            print(f"telas {n}/{len(jobs)} · {time.monotonic() - started:.0f} s · " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())), flush=True)
    done = done_keys(picks_path)
    todo = [c for c in choices if f"{c['session']}:{c['ts']}" not in done]
    print(f"escolhas a rotular: {len(todo)} (já feitas: {len(done)})")
    agree, checked, none = 0, 0, 0
    for n, choice in enumerate(todo, 1):
        labels = list(dict.fromkeys(choice["rotulos"]))
        got, _ = pick(model, choice["passo"]["alvo"], labels)
        none += got is None
        if choice["efeito"] == "conferido":  # o executor conferiu o efeito: a escolha dele vale como certa
            checked += 1
            agree += got == choice["escolhido"]
        write_private(picks_path, {"chave": f"{choice['session']}:{choice['ts']}", "modelo": model, "certo": got})
        if n % 50 == 0 or n == len(todo):
            print(f"escolhas {n}/{len(todo)} · nenhum {none} · concorda com as conferidas {agree}/{checked}", flush=True)


NAMES_PROMPT = """A phone assistant plans steps on an Android phone before it sees the screen, so it names each control
it wants to tap without knowing the exact label. You get the app, the labels of one screen and one target label on
that screen. Write up to 3 names the planner could plausibly use for the target control: synonyms, the generic
function, the name the control has in other apps or older versions, a description of its icon. Short (1 to 5 words),
in English. Each name must be different from the target label (not only in case) and must not fit another label of
the screen better than the target."""
NAMES_SCHEMA = {"type": "object", "properties": {"nomes": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
                "required": ["nomes"]}


def paraphrase_real(model, per_screen=3, seed=1):
    """Exemplos de escolha com telas reais e resposta conhecida: sorteia rótulos das telas da coleta e pede ao
    professor outros nomes para cada um. Rótulos com pessoa, usuário ou contato (pelos rótulos de tela do professor),
    com @ ou números longos ficam de fora. Grava em data/treino/real/nomes-<modelo>.jsonl; retoma de onde parou."""
    import random
    from lmphone import treino
    from lmphone.executor import MAX_LABEL
    tag = re.sub(r"[^\w.-]", "_", model)
    path = os.path.join(treino.DIR, f"nomes-{tag}.jsonl")
    private = set()
    for row in map(json.loads, open(os.path.join(treino.DIR, f"rotulos-telas-{tag}.jsonl"), encoding="utf-8")):
        private.update(fold(e["texto"]) for e in row["entidades"] if e["tipo"] in ("pessoa", "usuario", "email", "telefone", "documento"))
    screens = {}
    for e in treino.entries():
        if e.get("tipo") == "escolha" and e["rotulos"]:
            labels = tuple(dict.fromkeys(l for l in e["rotulos"] if l.strip()))
            screens.setdefault((e["app"], frozenset(labels)), (e["app"], labels))
    rng = random.Random(seed)
    jobs = []
    for app, labels in sorted(screens.values()):
        safe = [l for l in labels if len(l) <= MAX_LABEL and re.search(r"[^\W\d_]{2}", l) and "@" not in l
                and not re.search(r"\d{3}", l) and not any(p and p in fold(l) for p in private)]
        for label in rng.sample(safe, min(per_screen, len(safe))):
            jobs.append((f"{app}|{label}|{hashlib.sha1(chr(10).join(labels).encode()).hexdigest()[:10]}", app, labels, label))
    done = done_keys(path)
    jobs = [j for j in jobs if j[0] not in done]
    print(f"telas: {len(screens)}; rótulos a parafrasear: {len(jobs)} (já feitos: {len(done)})", flush=True)
    started, made = time.monotonic(), 0
    for n, (key, app, labels, label) in enumerate(jobs, 1):
        data, _ = chat(model, NAMES_PROMPT, json.dumps({"app": app, "screen": list(labels), "target": label}, ensure_ascii=False),
                       NAMES_SCHEMA)
        on_screen = {fold(l) for l in labels}
        names = [x.strip() for x in data.get("nomes", []) if x.strip() and fold(x.strip()) not in on_screen][:3]
        made += len(names)
        write_private(path, {"chave": key, "modelo": model, "app": app, "tela": list(labels), "rotulo": label, "nomes": names})
        if n % 100 == 0 or n == len(jobs):
            print(f"rótulos {n}/{len(jobs)} · nomes {made} · {time.monotonic() - started:.0f} s", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Professor local: avaliação no conjunto congelado e rótulos dos dados reais")
    parser.add_argument("acao", choices=["avaliar", "rotular", "parafrasear"])
    parser.add_argument("--modelo", required=True)
    parser.add_argument("--parte", choices=["mascaramento", "controles"], nargs="*", default=["mascaramento", "controles"])
    options = parser.parse_args()
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    if options.acao == "rotular":
        return label_real(options.modelo)
    if options.acao == "parafrasear":
        return paraphrase_real(options.modelo)
    report = {"modelo": options.modelo, "data": time.strftime("%Y-%m-%d %H:%M")}
    summary = []
    for part in options.parte:
        totals, rows, times = (evaluate_masking if part == "mascaramento" else evaluate_picks)(options.modelo)
        report[part] = {"totais": totals, "casos": rows, "segundos_medio": round(sum(times) / len(times), 2)}
        summary.append(f"{part}: " + ", ".join(f"{k} {a}/{b}" if k != "toques_errados" else f"{k} {a}"
                                               for k, (a, b) in totals.items())
                       + f" · {sum(times) / len(times):.1f} s por chamada")
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"professor-{re.sub(r'[^\w.-]', '_', options.modelo)}-{time.strftime('%Y-%m-%d-%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\n" + "\n".join(summary) + f"\nrelatório: {path}")


if __name__ == "__main__":
    sys.exit(main())
