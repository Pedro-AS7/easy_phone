"""Dados sintéticos pelo provedor (etapa 2 de docs/plano-modelos-pequenos.md).

O provedor inventa, app por app, exemplos já rotulados das três tarefas dos modelos pequenos:
- `tela`: trechos de uma tela, como o Portal os entrega, com as entidades (pessoa, usuário, negócio...);
- `pedido`: um pedido ao assistente, com a intenção e as entidades, no formato de `local_ai.judge_request`;
- `escolha`: os nomes que o plano dá a um controle, os rótulos da tela e o certo (ou nenhum), como o `/pick`.

Nada aqui é dado real: o pedido ao provedor leva só o nome do app e nomes de pessoa e usuário tirados das listas
fictícias abaixo, e por isso não passa pelo mascaramento do proxy. Nomes que aparecem no conjunto congelado
(`tests/base`) ficam de fora das listas, e um exemplo que mesmo assim cite um deles é descartado.

Uso (no .venv, com OPENROUTER_API_KEY no .env):
    .venv/bin/python -m tools.treino.sintetico --chamadas 3            # 3 chamadas de cada tipo, apps sorteados
    .venv/bin/python -m tools.treino.sintetico --tipos escolha --chamadas 50 --orcamento 1
    .venv/bin/python -m tools.treino.sintetico --amostra 5             # só mostra exemplos já gerados
Grava em data/treino/sintetico/<tipo>.jsonl; o que o provedor mandou e foi descartado vai para descartes.jsonl.
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from lmphone.run import read_env
from tests.base import controles, mascaramento
from tests.coleta_cases import TASKS

UPSTREAM = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
DIR = "data/treino/sintetico"
KINDS = ("tela", "pedido", "escolha")
# Apps cuja interface o aparelho mostra em português (conferido na etapa 0); o resto é em inglês.
PORTUGUESE = {"com.waze", "com.netflix.mediaclient", "com.schibsted.bomnegocio.androidApp"}
APPS = sorted(set(TASKS) | {"com.google.android.gm", "com.google.android.apps.maps", "org.telegram.messenger",
                            "com.sec.android.app.camera", "com.google.android.apps.books"})
# Não há tipo "pessoa pública": todo nome de gente é "pessoa" e é mascarado, famoso ou não (decisão do Pedro,
# 2026-10-18). Um modelo pequeno não sabe quem é famoso; se aprender a soltar alguns nomes, solta nomes de pessoas
# privadas também. Mascarar um famoso custa pouco: o provedor vê um nome falso, e o aparelho digita o real.
def as_person(example):
    """Troca o que vier como pessoa pública por pessoa. Devolve quantas trocou."""
    changed = 0
    for e in example.get("entidades", []):
        if e.get("tipo") == "pessoa_publica":
            e["tipo"], changed = "pessoa", changed + 1
            if "precisa_pesquisa" in e:
                e["precisa_pesquisa"] = False
    return changed


# Nomes que o provedor não tira do pacote sozinho (sem isso, escreve "zzkko" e "officehubrow" nos pedidos).
NAMES = {"com.zzkko": "Shein", "com.microsoft.office.officehubrow": "Microsoft 365", "com.instagram.barcelona": "Threads",
         "com.zhiliaoapp.musically": "TikTok", "com.taxis99": "99", "com.schibsted.bomnegocio.androidApp": "OLX",
         "com.luizalabs.mlapp": "Magalu", "com.sirma.mobile.bible.android": "Bible (YouVersion)",
         "com.tranzmate": "Moovit", "com.ingresso.cinemas": "Ingresso.com", "com.wbd.stream": "Max",
         "com.gympass": "Wellhub", "com.amazon.avod.thirdpartyclient": "Prime Video",
         "com.memrise.android.memrisecompanion": "Memrise", "org.zwanoo.android.speedtest": "Speedtest",
         "com.sec.android.app.popupcalculator": "Samsung Calculator", "com.sec.android.app.shealth": "Samsung Health",
         "com.sec.android.app.voicenote": "Samsung Voice Recorder", "com.sec.android.app.sbrowser": "Samsung Internet",
         "com.sec.android.app.clockpackage": "Samsung Clock", "com.sec.android.gallery3d": "Samsung Gallery",
         "com.mercadolibre": "Mercado Livre", "br.com.brainweb.ifood": "iFood", "com.google.android.googlequicksearchbox": "Google"}

FIRST = """Adriana Alessandra Alexandre Alice Amanda Anderson Andréia Antônio Arthur Beatriz Benício Bernardo Bianca Breno
Camila Carla Carlos Cecília Cláudio Cristiane Daniel Daniela Davi Diego Edson Eduarda Elaine Emanuel Enzo Fabiana Felipe
Fernando Flávia Francisco Gabriel Gabriela Giovana Guilherme Heitor Helena Hugo Isabela Isadora Jaqueline Joana João
Jorge Josué Júlio Karina Larissa Laura Leandro Leonardo Letícia Lorena Luana Lucas Luciana Luís Manuela Márcia Mariana
Mateus Matheus Mirela Murilo Natália Nicolas Otávio Pietra Rafaela Raquel Ricardo Roberta Rodrigo Rogério Sabrina Samuel
Sandra Sérgio Simone Sofia Tatiane Tiago Valéria Vanessa Vinícius Vitória Wagner Yasmin Zé Neide Dona Olga Seu Tonho
Emily Jacob Olivia Ethan Chloe Mason Harper Logan Avery Ryan Grace Nathan Lily Owen Hannah Wyatt Zoe Caleb Nora Isaac""".split()
LAST = """Almeida Andrade Araújo Azevedo Barbosa Barros Batista Borges Brito Cardoso Castro Cavalcanti Correia Costa Cunha
Dias Duarte Farias Fernandes Ferreira Fonseca Freitas Gomes Gonçalves Lima Lopes Machado Magalhães Marques Martins
Medeiros Monteiro Moraes Moreira Moura Nascimento Neves Nogueira Nunes Pacheco Pinto Queiroz Ramos Reis Rezende Rios
Rodrigues Sampaio Siqueira Soares Tavares Teixeira Vasconcelos Vieira Xavier Yamamoto Tanaka Novak Schmidt Rossi
Miller Walker Hayes Turner Brooks Foster Bennett Reed Price Coleman""".split()


def fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


def frozen():
    """Palavras dos nomes de pessoa e de usuário do conjunto congelado, e as escolhas dele (para não repetir)."""
    words = set()
    for case in mascaramento.CASOS:
        for name in case["pessoas"] + case["usuarios"] + mascaramento.CONTATOS:
            words |= {w for w in re.findall(r"\w{3,}", fold(name))}
    picks = {(frozenset(fold(p) for p in e["pedidos"]), frozenset(fold(t) for t in e["tela"])) for e in controles.ESCOLHAS}
    return words, picks


FROZEN_WORDS, FROZEN_PICKS = frozen()
FIRST = [n for n in FIRST if fold(n) not in FROZEN_WORDS]
LAST = [n for n in LAST if fold(n) not in FROZEN_WORDS]


def names(rng, n):
    people = [f"{rng.choice(FIRST)} {rng.choice(LAST)}" if rng.random() < 0.6 else rng.choice(FIRST) for _ in range(n)]
    users = []
    for _ in range(n):
        first, last = fold(rng.choice(FIRST)), fold(rng.choice(LAST))
        users.append(rng.choice([f"{first}.{last}", f"{first}_{last[:4]}{rng.randint(1, 99)}", f"{first[:3]}{last}",
                                 f"{last}.{first[0]}", f"_{first}{rng.randint(80, 2009)}"]))
    return people, users


COMMON = """You write training data for small on-device models of a phone assistant. The phone is a Samsung Galaxy S23+
(Android 16, One UI 8.5) in Brazil; the owner speaks Brazilian Portuguese. Screen text is what the accessibility tree
exposes, one fragment per element, in screen order: titles, buttons, tabs, list rows, messages, times, counters,
content descriptions of icons, and sometimes internal tags (resource ids like "search_button" or Compose tags like
"HAMBURGER_BUTTON"). Make it look like the real app, with its real labels; the phone's interface language is
English, so the app's own labels are in English unless the app is said to be in Portuguese, even when the content
written by people is in Portuguese. Private people are fictitious: use only the names and usernames given below (you
may shorten them to a first name, write them in lowercase or with a typo, or use a nickname derived from them).
Famous people (athletes, artists, politicians) are real, well-known people, never the given names. Apps are given by package name: call each app by its usual name, never by the
package name. Reply with JSON only, no comments."""

PROMPTS = {
    "tela": """Write {n} different screens of the app {app} ({lang}), starting from this part of the app: {focus}.
Exactly {empty} of them have no private person and no username at all (settings, menus, players, product pages,
empty states). The others have people: chats, comments, feeds, contact lists, notifications, search results, shared
files. Content written by people (messages, posts, comments) is mostly in Portuguese. Add traps that fit this app:
interface labels, product names and titles that contain a word that is also a first name, businesses, places and
famous people next to private people, names inside sentences, usernames with dots and numbers, emails and phones.

For each screen list every entity, copied exactly as it appears inside a fragment:
- "pessoa": any person, private or famous (full name, first name, nickname), also inside sentences;
- "usuario": a social network username or handle;
- "negocio": a shop, restaurant, company; "instituicao": a university, agency, bank, newspaper; "lugar": a city,
  neighbourhood, address, country;
- "email": an email address; "telefone": a phone number; "documento": a CPF, RG, card or postal code (CEP).
App names, brands of the app itself and interface labels are not entities.

Names: {people}
Usernames: {users}

{{"telas": [{{"onde": "app › screen", "trechos": ["...", "..."], "entidades": [{{"texto": "...", "tipo": "pessoa"}}]}}]}}""",

    "pedido": """Write {n} different requests that the phone owner could say to the assistant, mostly about the app {app}
and what is done in it ({focus}), some about other apps.
About two thirds in Brazilian Portuguese (informal, often lowercase, with abbreviations like "pra", "vc", "tbm"), the
rest in English. Mix intents:
- "acao": everything is done on the phone (send a message, call, open a screen, change a setting, set a reminder);
- "pesquisa": the answer needs public information from the internet (opening hours, prices, news, how to do something);
- "mista": needs both.
List the proper names of the request as entities, copied exactly as written (even in lowercase): "pessoa" (any
person, private or famous), "negocio", "instituicao", "lugar", "app", "outro". "precisa_pesquisa" is true only when the
request needs public information about that entity from the internet, and is always false for a person (a business
whose opening hours are asked: true; a business that will receive a message: false). Do not list common words,
emails, phones or documents. Include requests with no entities, with two people, with a person and a business, with
famous people, and with lowercase names.

Names: {people}

{{"pedidos": [{{"texto": "...", "intencao": "acao", "entidades": [{{"texto": "...", "tipo": "pessoa", "precisa_pesquisa": false}}]}}]}}""",

    "escolha": """Write {n} different control choices in the app {app} ({lang}), on screens from this part of the app:
{focus}, and the screens around it. In each one, a plan step names the control it wants to tap ("pedidos": 1 to 3
names an AI planner would use for that one control, in English; all of them mean the same control), and "tela" is the
list of labels of one real screen of the app, in screen order (8 to 25 labels, as the accessibility tree shows them).
"certo" is the label of the screen that is that control, or null when it is not on this screen.
Rules:
- No name in "pedidos" may be equal to a label of the screen (ignoring case): the easy cases are solved without AI.
- Exactly {present} have the control under another name: a synonym, a longer or shorter label, the content
  description of an icon, a Portuguese label when the app is in Portuguese, an internal resource id or Compose tag.
- Exactly {absent} have certo null: the control is not on this screen, but the screen has a control with a similar
  word or topic that a careless reader would tap. These traps matter most; vary them, do not reuse the same trap.
- Screens may contain people names and usernames as labels; take them from: {people}; {users}

{{"escolhas": [{{"onde": "app › screen", "pedidos": ["..."], "tela": ["...", "..."], "certo": "..." }}]}}""",
}

SIZE = {"tela": 6, "pedido": 15, "escolha": 12}  # exemplos por chamada
# Por onde começar, sorteado por chamada: sem isso, chamadas do mesmo app repetem as mesmas telas.
FOCUS = ["the home screen or main feed", "search and its results", "the settings and their sub-screens",
         "the user's profile or account", "notifications and messages", "a detail page of one item",
         "lists the user saved or created (library, favourites, history)", "dialogs, menus and bottom sheets",
         "a player, viewer or editor", "onboarding, empty states and errors", "sharing and inviting other people",
         "orders, bookings, payments history or activity"]


VERIFY = """For each case below, a phone assistant wants to tap the control that a plan step names ("wanted": names
for one and the same control) on a screen whose labels are listed. Answer with the exact label that is that control
(the same function under another name, an icon description, a translation or an internal tag also count), or null
when no label on the screen is that control. A control that is only related, or does something else, is null.
Reply with JSON only: {"respostas": [{"caso": 1, "certo": "label or null"}]}

"""


def ask(key, model, prompt, system=COMMON, reasoning=False):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "reasoning": {"enabled": reasoning}, "usage": {"include": True}}
    if not reasoning:
        body["temperature"] = 1.0
    request = urllib.request.Request(UPSTREAM, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=300) as response:
        answer = json.load(response)
    text = answer["choices"][0]["message"]["content"]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text), (answer.get("usage") or {}).get("cost") or 0.0


def cites_frozen(texts):
    return any(w in FROZEN_WORDS for t in texts for w in re.findall(r"\w{3,}", fold(t)))


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![#\w])\+?\(?\d[\d ()-]{6,}\d")  # 8 dígitos ou mais; "#8831204577" é número de pedido
CONTACT = {"email", "telefone", "documento"}


def digits(text):
    return sum(c.isdigit() for c in text)


def contact_problem(fragments, entities):
    """E-mails e telefones se conferem por código: o tipo tem de ter a forma, e nenhum pode ficar sem marcação."""
    for e in entities:
        if e["tipo"] == "email" and not EMAIL.search(e["texto"]) or e["tipo"] == "telefone" and digits(e["texto"]) < 8:
            return f"{e['tipo']} sem a forma"
    marked = [e["texto"] for e in entities if e["tipo"] in CONTACT | {"lugar"}]
    for fragment in fragments:
        found = EMAIL.findall(fragment) + [m for m in PHONE.findall(fragment) if digits(m) >= 8]
        if any(not any(m.strip() in t or t in m for t in marked) for m in found):
            return "e-mail ou telefone sem marcação"
    return None


def check(kind, item):
    """O exemplo limpo, ou (None, motivo)."""
    if kind == "tela":
        fragments = [str(t) for t in item.get("trechos", []) if str(t).strip()]
        entities = [e for e in item.get("entidades", []) if isinstance(e, dict) and e.get("texto")]
        if len(fragments) < 3:
            return None, "tela curta"
        if any(not any(e["texto"] in f for f in fragments) for e in entities):
            return None, "entidade fora dos trechos"
        as_person({"entidades": entities})
        if cites_frozen(e["texto"] for e in entities if e.get("tipo") in ("pessoa", "usuario")):
            return None, "nome do conjunto congelado"
        unique = [{"texto": t, "tipo": k} for t, k in {(e["texto"], e.get("tipo", "documento")): None for e in entities}]
        problem = contact_problem(fragments, unique)
        if problem:
            return None, problem
        return {"onde": item.get("onde", ""), "trechos": fragments, "entidades": unique}, None
    if kind == "pedido":
        text, entities = str(item.get("texto", "")), item.get("entidades", [])
        if item.get("intencao") not in ("pesquisa", "acao", "mista") or not text:
            return None, "intenção inválida"
        for e in entities:  # o gerador às vezes escreve com maiúscula o que o pedido tem em minúscula
            at = text.casefold().find(str(e.get("texto", "")).casefold())
            if not e.get("texto") or at < 0:
                return None, "entidade fora do texto"
            e["texto"] = text[at:at + len(e["texto"])]
        as_person({"entidades": entities})
        if cites_frozen(e["texto"] for e in entities if e.get("tipo") == "pessoa"):
            return None, "nome do conjunto congelado"
        return {"texto": text, "intencao": item["intencao"], "entidades": [
            {"texto": e["texto"], "tipo": e.get("tipo", "outro"),
             "precisa_pesquisa": bool(e.get("precisa_pesquisa")) and e.get("tipo") != "pessoa"}
            for e in entities]}, None
    wanted, labels, right = [str(p) for p in item.get("pedidos", [])], [str(t) for t in item.get("tela", [])], item.get("certo")
    if not wanted or len(labels) < 3:
        return None, "escolha incompleta"
    if right is not None and right not in labels:
        return None, "certo fora da tela"
    if {fold(w) for w in wanted} & {fold(t) for t in labels}:
        return None, "pedido igual a rótulo"
    if (frozenset(map(fold, wanted)), frozenset(map(fold, labels))) in FROZEN_PICKS:
        return None, "igual ao conjunto congelado"
    return {"onde": item.get("onde", ""), "pedidos": wanted, "tela": labels, "certo": right}, None


VERIFY_SCREEN = """For each phone screen below (its text fragments, in order), list every person's name, private or
famous (full name, first name or nickname, also inside sentences), and every social network username, copied exactly
as they appear. Not: businesses, brands, apps, places, interface labels, titles of books, songs or products.
Reply with JSON only: {"respostas": [{"caso": 1, "pessoas": ["..."], "usuarios": ["..."]}]}

"""


def private_set(names):
    return {fold(n).lstrip("@") for n in names if n}


def verify_screens(key, model, screens):
    """Como `verify`, para as pessoas e os nomes de usuário das telas: o exemplo fica se os conjuntos batem."""
    cases = "\n".join(json.dumps({"caso": n, "fragments": t["trechos"]}, ensure_ascii=False) for n, t in enumerate(screens, 1))
    data, cost = ask(key, model, VERIFY_SCREEN + cases, system="You check training data. Be strict.", reasoning=True)
    answers = {a.get("caso"): private_set((a.get("pessoas") or []) + (a.get("usuarios") or []))
               for a in data.get("respostas", []) if isinstance(a, dict)}
    return [answers.get(n) for n in range(1, len(screens) + 1)], cost


VERIFY_REQUEST = """For each request a phone owner made to their assistant, classify the intent:
- "pesquisa": the answer needs public information from the internet;
- "acao": everything is done on the phone (messages, calls, apps, settings, reminders, reading what is on the phone);
- "mista": needs both.
List the people named in it, private or famous (copied exactly as written), and the other names (business, place,
institution, app) whose public information must be looked up on the internet to answer.
Reply with JSON only: {"respostas": [{"caso": 1, "intencao": "acao", "pessoas": ["..."], "pesquisar": ["..."]}]}

"""


def request_key(intent, people, search):
    return intent, private_set(people), private_set(search)


def verify_requests(key, model, requests):
    cases = "\n".join(json.dumps({"caso": n, "request": r["texto"]}, ensure_ascii=False) for n, r in enumerate(requests, 1))
    data, cost = ask(key, model, VERIFY_REQUEST + cases, system="You check training data. Be strict.", reasoning=True)
    answers = {a.get("caso"): request_key(a.get("intencao"), a.get("pessoas") or [], a.get("pesquisar") or [])
               for a in data.get("respostas", []) if isinstance(a, dict)}
    return [answers.get(n) for n in range(1, len(requests) + 1)], cost


def verify(key, model, choices):
    """Outra chamada, com raciocínio e sem ver a resposta do gerador, resolve cada escolha. Devolve as respostas
    dela (None onde não respondeu) e o custo. Um exemplo só fica se as duas concordam."""
    cases = "\n".join(json.dumps({"caso": n, "wanted": c["pedidos"], "screen": c["tela"]}, ensure_ascii=False)
                      for n, c in enumerate(choices, 1))
    data, cost = ask(key, model, VERIFY + cases, system="You check training data. Be strict.", reasoning=True)
    answers = {a.get("caso"): a.get("certo") for a in data.get("respostas", []) if isinstance(a, dict)}
    return [answers.get(n, "?") for n in range(1, len(choices) + 1)], cost


lock = threading.Lock()


def save(name, row):
    os.makedirs(DIR, exist_ok=True)
    with lock, open(os.path.join(DIR, name), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate(key, model, kind, app, seed):
    rng = random.Random(seed)
    people, users = names(rng, 12)
    lang = "interface in Portuguese" if app in PORTUGUESE else "interface in English"
    absent = rng.choice((3, 4, 4, 5))
    named = f"{NAMES[app]} ({app})" if app in NAMES else app
    prompt = PROMPTS[kind].format(n=SIZE[kind], app=named, lang=lang, people=", ".join(people), users=", ".join(users),
                                  focus=rng.choice(FOCUS), empty=rng.choice((2, 3)), present=SIZE[kind] - absent,
                                  absent=absent)
    started = time.monotonic()
    try:
        data, cost = ask(key, model, prompt)
    except json.JSONDecodeError:  # resposta cortada ou com aspas sem escape: uma segunda tentativa
        data, cost = ask(key, model, prompt)
    items = next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) else []
    kept, dropped, cleaned = 0, Counter(), []
    for item in items:
        clean, why = check(kind, item) if isinstance(item, dict) else (None, "não é objeto")
        cleaned.append((item, clean, why))
    if any(clean for _, clean, _ in cleaned):
        check_with = {"escolha": verify, "tela": verify_screens, "pedido": verify_requests}[kind]
        answers, extra = check_with(key, model, [c for _, c, _ in cleaned if c])
        cost += extra
        answers = iter(answers)
        for n, (item, clean, why) in enumerate(cleaned):
            if not clean:
                continue
            second = next(answers)
            if kind == "escolha":
                second = None if second in (None, "null", "") else second
                agree = second == clean["certo"]
            elif kind == "tela":
                agree = second == private_set(e["texto"] for e in clean["entidades"] if e["tipo"] in ("pessoa", "usuario"))
                second = sorted(second) if second is not None else None
            else:
                entities = clean["entidades"]
                # Intenção e pessoas batem exatamente; a pesquisa, por sobreposição: a conferência corta o trecho de
                # outro jeito ("shopping iguatemi") e lista produtos, que nunca são mascarados.
                agree = second is not None and second[:2] == request_key(
                    clean["intencao"], [e["texto"] for e in entities if e["tipo"] == "pessoa"], [])[:2] and all(
                    e["precisa_pesquisa"] == any(fold(e["texto"]) in s or s in fold(e["texto"]) for s in second[2])
                    for e in entities if e["tipo"] != "pessoa")
                second = [second[0], sorted(second[1]), sorted(second[2])] if second is not None else None
            if not agree:
                cleaned[n] = ({**item, "conferencia": second}, None, "conferência discordou")
    for item, clean, why in cleaned:
        if clean:
            save(f"{kind}.jsonl", {"app": app, "modelo": model, **clean})
            kept += 1
        else:
            dropped[why] += 1
            save("descartes.jsonl", {"tipo": kind, "app": app, "motivo": why, "item": item})
    return kept, dropped, cost, time.monotonic() - started


def sample(n):
    for kind in KINDS:
        try:
            with open(os.path.join(DIR, f"{kind}.jsonl"), encoding="utf-8") as f:
                rows = [json.loads(line) for line in f]
        except OSError:
            continue
        print(f"\n== {kind}: {len(rows)} exemplos")
        for row in random.sample(rows, min(n, len(rows))):
            name = NAMES.get(row["app"], row["app"])
            if kind == "tela":
                print(f"\n[{name}] {row['onde']}\n  " + " · ".join(row["trechos"]) + "\n  -> "
                      + (", ".join(f"{e['texto']} ({e['tipo']})" for e in row["entidades"]) or "nenhuma entidade"))
            elif kind == "pedido":
                print(f"\n[{name}] {row['texto']}\n  -> {row['intencao']}; " + (", ".join(
                    f"{e['texto']} ({e['tipo']}{', pesquisar' if e['precisa_pesquisa'] else ''})" for e in row["entidades"])
                    or "sem entidades"))
            else:
                print(f"\n[{name}] {row['onde']}: quer {' / '.join(row['pedidos'])}\n  tela: " + " · ".join(row["tela"])
                      + f"\n  -> {row['certo'] if row['certo'] is not None else 'NENHUM (não está na tela)'}")


def main():
    parser = argparse.ArgumentParser(description="Dados sintéticos pelo provedor")
    parser.add_argument("--tipos", nargs="*", default=list(KINDS), choices=KINDS)
    parser.add_argument("--chamadas", type=int, default=3, help="chamadas de cada tipo")
    parser.add_argument("--orcamento", type=float, default=0.10, help="US$; não começa chamada nova depois disto")
    parser.add_argument("--modelo", default=os.environ.get("MODEL") or DEFAULT_MODEL)
    parser.add_argument("--paralelas", type=int, default=4)
    parser.add_argument("--semente", type=int, default=int(time.time()))
    parser.add_argument("--amostra", type=int, default=0, help="só mostra N exemplos de cada tipo e sai")
    options = parser.parse_args()
    os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))
    if options.amostra:
        return sample(options.amostra)
    key = os.environ.get("OPENROUTER_API_KEY") or read_env().get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("Defina OPENROUTER_API_KEY em .env")

    rng = random.Random(options.semente)
    jobs = [(kind, rng.choice(APPS), rng.randrange(1 << 30)) for _ in range(options.chamadas) for kind in options.tipos]
    spent, kept, dropped, failures = 0.0, Counter(), Counter(), 0
    with ThreadPoolExecutor(options.paralelas) as pool:
        pending = []
        for kind, app, seed in jobs:
            if spent >= options.orcamento:
                break
            pending.append((kind, app, pool.submit(generate, key, options.modelo, kind, app, seed)))
            if len(pending) >= options.paralelas:
                kind_, app_, future = pending.pop(0)
                spent, failures = collect(kind_, app_, future, spent, kept, dropped, failures)
        for kind_, app_, future in pending:
            spent, failures = collect(kind_, app_, future, spent, kept, dropped, failures)
    print(f"\nUS$ {spent:.4f} · guardados: " + ", ".join(f"{k} {v}" for k, v in kept.items())
          + (" · descartados: " + ", ".join(f"{k} {v}" for k, v in dropped.most_common()) if dropped else "")
          + (f" · chamadas que falharam: {failures}" if failures else ""))


def collect(kind, app, future, spent, kept, dropped, failures):
    try:
        n, why, cost, seconds = future.result()
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
        print(f"{kind:8} {app:42} falhou: {type(e).__name__}", flush=True)
        return spent, failures + 1
    kept[kind] += n
    dropped.update(why)
    spent += cost
    print(f"{kind:8} {app:42} {n:3} guardados, {sum(why.values())} descartados, {seconds:4.0f} s  US$ {spent:.4f}", flush=True)
    return spent, failures


if __name__ == "__main__":
    main()
