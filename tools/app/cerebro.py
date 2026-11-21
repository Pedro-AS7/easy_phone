"""O cérebro no app (etapa 3 de docs/plano-app-android.md), do lado do PC.

- `exportar`: grava `android/cerebro/src/main/resources/cerebro.json` com o que o cérebro em Kotlin lê do Python em vez
  de copiar à mão: os prompts e os pedaços deles, os limites, as listas e as expressões regulares (com as opções), mais
  as tabelas do Unicode do Python que o Kotlin não tem iguais (o `casefold` e as marcas que o `plain` tira). Só o que
  está nas listas abaixo sai; nada do ambiente (a chave do provedor), do cofre ou do aparelho. `tests/test_cerebro.py`
  falha se o arquivo ficou velho.

- `trilhas`: roda os testes do executor e do proxy com o gravador de trilhas (`lmphone/trilha.py`) e grava
  `data/trilhas/testes.jsonl` (dados fictícios), que a conferência em Kotlin (`android\\gradlew.bat :cerebro:conferir`)
  refaz.

- `mascara`: a máscara e a IA local de ponta a ponta nos pedidos e telas fictícios e da coleta, com valores falsos
  determinísticos, em `data/trilhas/mascara.jsonl`, para a mesma conferência. Roda no `.venv-modelo`.

Uso: .venv/Scripts/python.exe -m tools.app.cerebro exportar | trilhas
     .venv-modelo/Scripts/python.exe -m tools.app.cerebro mascara
"""

import argparse
import json
import os
import re
import sys
import unicodedata

OUT = "android/cerebro/src/main/resources/cerebro.json"

# Por módulo, os nomes exportados. Só constantes: nada que venha do ambiente ou mude durante uma tarefa.
NAMES = {
    "executor": [
        "MAX_SCROLLS", "MAX_HELP", "MAX_SAME_HELP", "MAX_QUESTIONS", "MAX_REVIEWS", "OWNER_LIMIT", "GUIDE_LIMIT",
        "GUIDE_REMIND", "GUIDE_REMINDER", "_POSITION", "CUT_OFF", "COVERED", "SLIDER", "SLIDER_DOWN", "SLIDER_DOWN_AT", "_BAR_SAID", "SLIDER_GAP", "OWNER_QUIET", "TOUCH_LATE", "TOUCH_READS", "TOUCH_GAP", "SETTINGS_WAY", "ONLY_GUIDE", "ONLY_GUIDE_HELP", "BUTTON_SETTINGS", "BUTTON_APP",
        "SCROLL_FOR", "KEEP_SCROLLING_GUIDE", "AGAIN_SCROLL", "LOST_WAIT", "BUTTON_DEAD", "DEAD_TOUCH", "BUTTON_DEAD_SAY", "GUIDE_REMINDER_BUTTON", "GUIDE_REMINDER_GESTURE", "SPLIT_SHADE", "SYSTEM_PANEL", "GUIDE_WORDS", "_SENTENCE", "FLIP_SLACK", "EXPANDERS", "PULL_RIGHT", "SHADE_ONLY_SAY", "WRONG_SPOT", "WRONG_SPOT_BLIND", "UNDO", "UNDONE", "STATE_WORDS", "BACK_NAMES", "_SWITCH_WORDS", "SEEN_MAX", "SCREEN_NAMES", "_QUOTED_NAME", "GUIDE_REMINDER_ONLY",
        "KEEP_SCROLLING", "KEEP_SCROLLING_LIMIT", "SEARCH_LABEL", "LOOKAHEAD", "MAX_DEPTH", "MAX_WAITS", "FEW_LABELS",
        "MAX_LABEL", "HIDDEN", "USER_BLOCK", "CONFIRM", "CONFIRM_START", "SENSITIVE", "YES_WORDS", "NO_WORDS",
        "PLAIN_WORDS", "_NUMBER", "EDITABLE", "ACTIONS", "DIRECT", "SCREENS", "SET_SCREENS", "SET_SCREENS_OFF", "SET_ROUTES", "SOUND_MODES", "QUOTES", "SOUND_MODE_WORDS", "HOW_TO", "PROMISE", "PROMISED", "SOUND_SYMPTOM", "NEAR_PREFIX", "NEAR_TAIL", "SETTINGS_PAGES",
        "_TOOL_ERROR", "_STATE", "_ELEMENT", "FORMAT", "GOAL", "SPLIT", "PLAN_PROMPT", "ASK_OPTION", "NO_ASK_OPTION",
        "NO_HISTORY", "SEARCH_OPTION", "SEARCHED", "GUIDE_HELP", "NO_SCREEN", "HELP_PROMPT", "ASK", "ASK_NOW", "REVIEW",
        "KNOWN_HELP", "MAX_KNOWN",
    ],
    "masking": ["EMAIL", "CARD", "CPF", "HANDLE", "PHONE", "CNPJ", "CEP", "CARD16", "CPF11", "CNPJ14", "PLATE", "LABELED",
                "_PLATE_SHAPE", "MIN_CODE_DIGITS", "STREET", "_STREET_WORD", "_STREET_NUMBER", "MAX_STREET_WORDS",
                "PASSWORD_IS", "PASSWORD_TO", "PASSWORD_NEXT", "_NOT_PASSWORD", "STOPLIST", "_PREFIXES", "_SUFFIXES",
                "_CONNECTIVES", "MAX_SURNAMES"],
    "nomes": ["FIRST_NAMES", "SURNAMES", "AMBIGUOUS"],
    "local_ai": ["_STATE", "_ELEMENT", "_HEADERS", "_FOCUSED", "HANDLE", "SOCIAL", "URLISH"],
    "facts": ["GOAL_KEYS", "SPOKEN", "SPOKEN_SOUND", "SOUND_MODES", "_BAND", "LEVELS", "LEVEL_SLACK", "SPOKEN_LEVELS", "BRIGHTNESS_MAX", "CHANGES", "SCALES", "AUDIBLE", "VOLUMES",
              "SPOKEN_CHANGE"],
    "cache": ["MAX_FAILS", "VERSION"],
    "proxy": ["JUDGE_TIMEOUT", "PICK_SPLIT", "DEVICE", "MODELS", "LANGUAGES", "APP_ALIASES", "WEB_SEARCH", "READ_HIDDEN",
              "CONVERSATION_TTL", "MAX_TURNS", "SETTINGS", "CUTS_LINK", "NO_CUT", "UPSTREAM"],
    "service": ["MAX_STEPS", "AFTER_ACTION", "APPS_TTL", "READ_TRIES", "READY_LIMIT", "BANK_MESSAGE", "STOPPED_MESSAGE",
                "USER_BLOCKS", "GUIDE_PAUSE", "OWNER_WAIT_LIMIT"],
    "access": ["BANKS"],
    "live": ["POLL", "PAUSE_LIMIT", "TYPING_LIMIT", "ASK_LIMIT", "USER_QUIET", "AGENT_WINDOW_MS", "THINKING_AFTER",
             "OWNER_ON", "OWNER_OFF", "NEW_REQUEST"],
    "device": ["GBOARD", "MIN_VISIBLE", "KEYS", "HEADER"],
}
# O serviço lê a tela com estes intervalos quando o aparelho é o app (os do Portal são outros).
APP_STILL = {"STILL_GAP": 0.6, "STILL_LIMIT": 3.0}


def value(item):
    """Um valor do Python em JSON: expressões regulares com as opções, conjuntos ordenados, tuplas como listas."""
    if isinstance(item, re.Pattern):
        flags = "".join(letter for letter, flag in (("i", re.I), ("m", re.M), ("s", re.S)) if item.flags & flag)
        return {"$re": item.pattern, "flags": flags}
    if isinstance(item, (set, frozenset)):
        return sorted(value(x) for x in item)
    if isinstance(item, (list, tuple)):
        return [value(x) for x in item]
    if isinstance(item, dict):
        return {str(k): value(v) for k, v in item.items()}
    if isinstance(item, (str, int, float, bool)) or item is None:
        return item
    raise TypeError(f"não sei exportar {type(item).__name__}")


def unicode_tables():
    """O `casefold` do Python por caractere (só os que mudam) e as marcas combinantes (as que `plain` tira), em
    intervalos. O Kotlin não tem `casefold`, e as categorias do Java não dizem a classe combinante."""
    folds, marks, start = {}, [], None
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        char = chr(cp)
        if char.casefold() != char:
            folds[str(cp)] = char.casefold()
        mark = unicodedata.combining(char) != 0
        if mark and start is None:
            start = cp
        elif not mark and start is not None:
            marks.append([start, cp - 1])
            start = None
    return {"versao": unicodedata.unidata_version, "casefold": folds, "combinantes": marks}


def build():
    sys.path.insert(0, os.getcwd())
    import importlib
    out = {"aviso": "Gerado por tools/app/cerebro.py exportar a partir do Python; não edite à mão."}
    for module, names in NAMES.items():
        loaded = importlib.import_module(f"lmphone.{module}")
        out[module] = {name: value(getattr(loaded, name)) for name in names}
    out["service"].update(APP_STILL)
    out["unicode"] = unicode_tables()
    return out


def export():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{OUT}: {sum(len(v) for k, v in data.items() if isinstance(v, dict) and k != 'unicode')} constantes, "
          f"{os.path.getsize(OUT) / 1000:.0f} KB")


TRAILS = "data/trilhas/testes.jsonl"


def trails():
    """Roda os testes do executor, do proxy e do simulador (guias inteiros) com o gravador de trilhas (lmphone/trilha.py) e grava data/trilhas/testes.jsonl.
    O gravador entra antes de os testes importarem o executor, para as funções que eles chamam direto também irem."""
    import unittest

    sys.path.insert(0, os.getcwd())
    from lmphone import trilha
    if os.path.exists(TRAILS):
        os.remove(TRAILS)
    uninstall = trilha.install(TRAILS)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(["tests.test_executor", "tests.test_proxy", "tests.test_device",
                                                                "tests.test_simulado"])
        outcome = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
        # Nomes de apps (fictícios) ditos errado, para o difflib do find_package.
        import difflib
        names = ["youtube music", "yt music", "sofascore", "instagram", "whatsapp", "waze", "spotify", "settings",
                 "calculator", "camera", "gallery", "clock", "chrome", "gmail", "maps", "notes", "play store",
                 "netflix", "ifood", "uber", "my files", "samsung notes", "google maps", "messages", "phone"]
        said = ["sofa score", "instagran", "wase", "spotfy", "galery", "calculater", "yotube music", "play stor",
                "neflix", "ifod", "setings", "crome", "whats app", "my file", "mesages", "fone", "x", ""]
        for word in said:
            difflib.get_close_matches(word, names, n=1, cutoff=0.85)
            difflib.get_close_matches(word, names)
    finally:
        uninstall()
    map_reference()
    calls = functions = 0
    with open(TRAILS, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            calls += "call" in entry
            functions += "fn" in entry
    print(f"{TRAILS}: {calls} chamadas ao executor e {functions} a funções, de {outcome.testsRun} testes "
          f"({len(outcome.failures) + len(outcome.errors)} falharam com o gravador)")


MAP = "data/trilhas/mapa.json"


def map_reference():
    """O mapa dos nomes do aparelho num caso fictício (o que o Python aprende e o texto que vai ao provedor), para a
    conferência do `Cache.learn` em Kotlin, que as trilhas do executor não cobrem."""
    import tempfile
    from unittest import mock
    from lmphone import cache, executor
    trail = [{"action": "open_settings", "target": ["display"]},
             {"action": "tap", "target": ["Tamanho e estilo da fonte"], "seen": ["Modo escuro", "Tamanho e estilo da fonte", "Ana Souza"]},
             {"action": "back"},
             {"action": "tap", "target": ["Zoom da tela"], "seen": ["Modo escuro", "Zoom da tela"]},
             {"action": "turn_on", "target": ["Negrito"], "seen": ["Negrito", "Estilo da fonte"]}]
    task, out = "como deixo a letra maior? tamanho da fonte", ["Ana Souza"]
    with tempfile.TemporaryDirectory() as folder, mock.patch.object(cache, "MAPS", os.path.join(folder, "maps.json")):
        cache.learn(trail, keep=lambda label: label not in out)
        tree = cache.maps()
    with open(MAP, "w", encoding="utf-8") as f:
        json.dump({"trail": trail, "fora": out, "task": task, "tree": tree,
                   "text": executor.render(executor.related(tree, task))}, f, ensure_ascii=False)


MASKING = "data/trilhas/mascara.jsonl"
SEPARATOR = " • "


def stub_fake(session, kind, real):
    """Valores falsos determinísticos, iguais aos do Kotlin na conferência (o sorteio de verdade não se compara)."""
    n = len(session.reverse[kind]) + 1
    letters = "".join(chr(97 + (n // 26 ** k) % 26) for k in range(3))
    fakes = {"name": "fake" + letters, "email": f"contato{1000 + n}@exemplo.com", "literal": f"usuario{1000 + n}",
             "handle": f"@usuario{1000 + n}"}
    return fakes.get(kind) or "".join(str((n * 7 + k * 3) % 10) for k in range(len(real)))


def masking():
    """A máscara e a IA local de ponta a ponta, como o proxy faz, nos pedidos e nas telas do conjunto congelado e dos
    casos da IA (fictícios) e da coleta (reais): julgar com os modelos pequenos, aplicar as decisões, mascarar e
    desmascarar. Grava data/trilhas/mascara.jsonl. Roda no .venv-modelo (usa o modelo_server)."""
    sys.path.insert(0, os.getcwd())
    from lmphone import local_ai, masking as mk, modelo_server
    from lmphone.sources import load_stoplist
    from tests import ia_cases, regras_cases
    from tests.base import mascaramento as base
    from tools.app.modelos import collection

    marker = modelo_server.load("data/modelos/marcacao", "tabela")

    def judge(text):
        items, intent = marker.mark(text)
        return {"intencao": intent, "entidades": [{"texto": i["texto"], "tipo": i["tipo"].rstrip("+"),
                                                   "precisa_pesquisa": i["tipo"].endswith("+")} for i in items]}

    def private(text):
        items, _ = marker.mark(text)
        return {"itens": [{"texto": i["texto"], "tipo": "pessoa" if i["tipo"] == "pessoa" else "usuario"}
                          for i in items if i["tipo"] in ("pessoa", "usuario", "email", "telefone", "documento")]}

    vault = mk.Vault()
    stoplist = load_stoplist()
    builder = mk.Masker(vault, stoplist)
    for name in base.CONTATOS + ia_cases.CONTATOS:
        builder.add_name(name)
    for email in base.EMAILS + ia_cases.EMAILS:
        vault.add("email", email.lower())
    for phone in base.TELEFONES + ia_cases.TELEFONES:
        builder.add_phone(phone)
    mk.Session._new_fake = stub_fake

    def session_state(masker):
        session = masker.session
        return {"extra_names": sorted(session.extra_names), "cap_names": sorted(session.cap_names),
                "extra_literals": sorted(session.extra_literals),
                "released": sorted(session.released), "forward": {k: v for k, v in session.forward.items() if v}}

    def request(text):
        masker = mk.Masker(vault, stoplist)
        for password in mk.passwords(text):
            masker.session.protect_literal(password)
        decisions = local_ai.apply_request(judge(text), masker, text)
        counts, trace = {}, []
        masked = masker.mask(text, counts, trace)
        return {"decisoes": decisions, "mascarado": masked, "volta": masker.unmask(masked), "trocas": trace,
                "contagem": counts, "sessao": session_state(masker)}

    def screen(fragments):
        masker = mk.Masker(vault, stoplist)
        applied = []
        for batch in local_ai.batches(fragments):
            source = SEPARATOR.join(batch)
            applied.append(local_ai.apply_screen(private(source), masker, source))
        masked = [masker.mask(f) for f in fragments]
        return {"decisoes": applied, "mascarado": masked, "volta": [masker.unmask(m) for m in masked],
                "sessao": session_state(masker)}

    real_requests, _, real_screens, _ = collection()
    cases = ([("pedido", c["entrada"], False) for c in base.CASOS if c["tipo"] == "pedido"]
             + [("pedido", c["entrada"], False) for c in ia_cases.CASOS if c["tipo"] == "pedido"]
             + [("pedido", c["entrada"], False) for c in regras_cases.CASOS]  # as regras que valem sem a IA local
             + [("tela", c["trechos"], False) for c in base.CASOS if c["tipo"] == "tela"]
             + [("tela", c["entrada"].split(SEPARATOR), False) for c in ia_cases.CASOS if c["tipo"] == "tela"]
             + [("pedido", t, True) for t in real_requests] + [("tela", s, True) for s in real_screens])
    screens = []  # telas inteiras (fictícias) das trilhas dos testes, para screen_fragments e redact
    if os.path.exists(TRAILS):
        with open(TRAILS, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("call") == "step":
                    screens.append(entry["args"][0])
    with open(MASKING, "w", encoding="utf-8") as f:
        f.write(json.dumps({"cofre": {k: sorted(v) for k, v in vault.reals.items()}, "stoplist": stoplist}, ensure_ascii=False) + "\n")
        for kind, value, real in cases:
            out = request(value) if kind == "pedido" else screen(value)
            f.write(json.dumps({"tipo": kind, "entrada": value, "real": real, **out}, ensure_ascii=False) + "\n")
        for text in dict.fromkeys(screens):
            f.write(json.dumps({"tipo": "trechos", "entrada": text, "real": False,
                                "trechos": local_ai.screen_fragments(text)}, ensure_ascii=False) + "\n")
    print(f"{MASKING}: {len(cases)} casos ({sum(r for _, _, r in cases)} reais), {len(set(screens))} telas para os trechos")


# --- o celular ---

APP = "dev.pedro.lmphone"
BRAIN = f"{APP}/.BrainService"
APP_DIR = "files/cerebro"  # o que o cérebro no celular grava (logs/, data/), no armazenamento do app
DATA_FILES = ("vault.json", "stoplist.txt", "preferencias.txt", "banks.txt", "paths.json", "maps.json")
PERMISSIONS = ("android.permission.WRITE_SECURE_SETTINGS", "android.permission.READ_CONTACTS",
               "android.permission.ACCESS_FINE_LOCATION")


def adb(*args, data=None, check=True, timeout=60):
    import subprocess
    result = subprocess.run(["adb", *args], input=data, capture_output=True, timeout=timeout)
    if check and result.returncode != 0:
        sys.exit(f"adb {args[0]} falhou: {(result.stderr or result.stdout).decode(errors='replace').strip()[:200]}")
    return result.stdout


def to_app(path, data):
    """Grava `data` em `path` (relativo ao armazenamento do app) pela entrada padrão do adb: o conteúdo não passa por
    arquivo temporário nem por linha de comando (o cofre e a chave são dados reais)."""
    folder = os.path.dirname(path)
    adb("exec-in", f"run-as {APP} sh -c 'mkdir -p {folder} && cat > {path}'", data=data)


def provider_key():
    """A chave do provedor, lida do .env (nunca impressa)."""
    with open(".env", encoding="utf-8") as f:
        for line in f:
            name, _, value = line.strip().partition("=")
            if name.strip() == "OPENROUTER_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    sys.exit("o .env não tem OPENROUTER_API_KEY")


def send_all():
    """Prepara o celular para o cérebro: as permissões que só o adb dá, os arquivos de data/ (cofre, stoplist,
    preferências, bancos, cache e mapa), a chave do provedor (cifrada pelo app no Keystore assim que ele a lê) e os
    modelos pequenos. O terminal mostra só o que foi feito."""
    for permission in PERMISSIONS:
        adb("shell", "pm", "grant", APP, permission)
    adb("shell", "cmd", "appops", "set", APP, "GET_USAGE_STATS", "allow")
    # O teclado do agente fica ativado (não o padrão): o app só o põe como padrão durante a tarefa.
    adb("shell", "ime", "enable", f"{APP}/.Keyboard")
    print("permissões: dadas; teclado do agente: ativado")
    for name in DATA_FILES:
        path = os.path.join("data", name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                to_app(f"{APP_DIR}/data/{name}", f.read())
            print(f"data/{name}: enviado")
    to_app("files/chave.txt", provider_key().encode())
    # A tela do app lê a chave na hora, cifra pelo Keystore e apaga o texto claro.
    adb("shell", "am", "start", "-n", f"{APP}/.MainActivity")
    print("chave do provedor: enviada (o app a cifra e apaga o texto claro)")
    from tools.app.modelos import send
    send()


def brain_device():
    sys.path.insert(0, os.getcwd())
    from lmphone.device import AppDevice

    class BrainDevice(AppDevice):
        PORT = 8083  # BrainService.PORT

    return BrainDevice()


def task(request):
    """Um pedido ao cérebro no celular, como `lmphone.run` faz com o do PC: imprime o andamento e a linha final
    ("Goal achieved: ..."), e acrescenta ao logs/proxy.jsonl do PC as linhas que o celular gravou (só texto mascarado),
    para a suíte medir igual. MODEL, LMPHONE_PERGUNTAR, LMPHONE_CACHE e LMPHONE_CONVERSA valem como no lmphone.run."""
    import time
    device = brain_device()
    log = f"{APP_DIR}/logs/proxy.jsonl"
    try:
        device.request("/ping", timeout=5)
    except Exception:
        adb("shell", "am", "start-foreground-service", "-n", BRAIN)
        for _ in range(20):
            time.sleep(0.5)
            try:
                device.request("/ping", timeout=5)
                break
            except Exception:
                pass
        else:
            sys.exit("o BrainService do app não respondeu (o app está instalado?)")
    size = adb("shell", f"run-as {APP} stat -c %s {log} 2>/dev/null || echo 0", check=False).decode().strip()
    offset = int(size) if size.isdigit() else 0
    body = {"task": request, "cache": os.environ.get("LMPHONE_CACHE", "1") != "0",
            "perguntar": os.environ.get("LMPHONE_PERGUNTAR", "1") != "0", "conversa": os.environ.get("LMPHONE_CONVERSA", ""),
            **({"modelo": os.environ["MODEL"]} if os.environ.get("MODEL") else {})}
    started = time.monotonic()
    answer = device._send("/tarefa", body, timeout=900)
    for line in answer.get("linhas", []):
        print(line, flush=True)
    new = adb("exec-out", f"run-as {APP} tail -c +{offset + 1} {log}", check=False)
    if new:
        os.makedirs("logs", exist_ok=True)
        with open("logs/proxy.jsonl", "ab") as f:
            f.write(new)
    print(f"({time.monotonic() - started:.1f} s)")
    print(f"Goal {'achieved' if answer.get('ok') else 'failed'}: {answer.get('mensagem', '')}")


def pull():
    """Traz do celular o registro do cérebro (detalhe/ e live/, com valores reais, ficam nesta máquina com modo 600)."""
    import tarfile
    import io
    data = adb("exec-out", f"run-as {APP} tar -cf - -C {APP_DIR} logs", check=False)
    if not data:
        sys.exit("o celular não tem registro do cérebro")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall("logs/celular", filter="data")
    print("logs/celular/: registro do cérebro no celular")


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parser = argparse.ArgumentParser(description="O cérebro no app: exportar, trilhas, máscara, enviar, tarefa, puxar")
    parser.add_argument("acao", choices=["exportar", "trilhas", "mascara", "enviar", "tarefa", "puxar"])
    parser.add_argument("pedido", nargs="?", help="o pedido, com tarefa")
    options = parser.parse_args()
    if options.acao == "tarefa":
        task(options.pedido or "")
    else:
        {"exportar": export, "trilhas": trails, "mascara": masking, "enviar": send_all, "puxar": pull}[options.acao]()


if __name__ == "__main__":
    main()
