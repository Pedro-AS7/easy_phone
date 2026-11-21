"""Suíte de testes no celular: roda os casos de phone_cases.py pelo lmphone.run e confere o resultado no aparelho.

Uso (celular no USB, Ollama no ar):
    .venv/bin/python -m tests.phone_suite                     # os 24 casos
    .venv/bin/python -m tests.phone_suite --listar
    .venv/bin/python -m tests.phone_suite --nivel crucial
    .venv/bin/python -m tests.phone_suite --nivel conversa    # pedidos encadeados numa mesma conversa
    .venv/bin/python -m tests.phone_suite --categoria navegador
    .venv/bin/python -m tests.phone_suite cfg-borda web-preco # só estes
    Opções: --modelo, --sem-cache, --limite segundos por rodada.

Para cada rodada grava em logs/suite.jsonl: resultado, o que o agente declarou, tempo total e por parte (provedor,
IA local), chamadas ao provedor, ajudas, ações, tokens, custo, caracteres de tela enviados, uso do cache, pico de RAM no notebook (serviço,
Laya e Ollama), erros e cada conferência. No fim gera
reports/suite-<data>.html e .json. A saída do agente fica em logs/suite/<data>/ (modo 600): ela pode ter dados
reais, por isso não é impressa. O relatório não guarda o nome do contato nem respostas com dado pessoal.
"""

import argparse
import html
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import Counter
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from lmphone import access, bridge, host, trace
from lmphone.device import new_device
from lmphone.masking import Masker, Vault
from lmphone.sources import VAULT_PATH, adb, load_stoplist, query

from . import captura
from .pessoa import Pessoa, read_log
from .phone_cases import CASES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = "logs/proxy.jsonl"
SUITE_LOG = "logs/suite.jsonl"
# --cerebro celular: cada caso vai ao cérebro no app (tools/app/cerebro.py tarefa), e o PC só dispara e confere; o
# registro do celular (só texto mascarado) é acrescentado ao logs/proxy.jsonl, e as medidas saem iguais.
BRAIN = "pc"
SITE_DIR = os.path.join(ROOT, "tests", "site")
SITE_PORT = int(os.environ.get("LMPHONE_SITE_PORT", "8765"))
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"  # o gratuito para em 50 pedidos por dia, menos que uma suíte inteira
NIGHT = {"0": "auto", "1": "no", "2": "yes"}
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_USERNAME = re.compile(r"@?[a-z0-9][a-z0-9._]{2,29}")
_STATE = re.compile(r"<device_state>(.*?)(?:</device_state>|\Z)", re.S)  # a tela dentro de um pedido ao provedor
_WORD = re.compile(r"[a-z]{3}")  # um nome de usuário tem letras: "1.234" e "24h" são contagens e horas


class SetupError(Exception):
    pass


# --- aparelho ---

def wifi_password():
    """A senha da rede de teste (data/suite_segredos.json, fora do git): dado real, nunca impresso nem gravado."""
    try:
        with open(os.path.join(ROOT, "data", "suite_segredos.json"), encoding="utf-8") as f:
            return json.load(f)["senha_wifi"]
    except (OSError, KeyError, ValueError):
        raise SetupError("falta data/suite_segredos.json com {\"senha_wifi\": ...}")


def setting(key):
    """(namespace, valor) de um ajuste, procurando nos três namespaces; (None, None) se não existe."""
    for namespace in ("system", "secure", "global"):
        value = adb("settings", "get", namespace, key).strip()
        if value and value != "null":
            return namespace, value
    return None, None


def foreground():
    match = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)[/}]", adb("dumpsys", "window"))
    return match.group(1) if match else None


def media_playing(package):
    """Se o app tem uma sessão de mídia tocando agora (PlaybackState 3)."""
    out = adb("dumpsys", "media_session")
    blocks = re.split(r"\n\s*(?=\S.*\bpackage=)", out)
    return any(f"package={package}" in b and re.search(r"state=PlaybackState \{state=(?:PLAYING\(3\)|3\b)", b)
               for b in blocks)


def wifi_network():
    """O nome da rede Wi-Fi conectada, ou None."""
    match = re.search(r'connected to "([^"]*)"', adb("cmd", "wifi", "status"))
    return match.group(1) if match else None


def volume(stream):
    """O volume de um fluxo de som (3: mídia, 2: toque), ou None."""
    match = re.search(r"volume is (\d+)", adb("cmd", "media_session", "volume", "--stream", str(stream), "--get"))
    return int(match.group(1)) if match else None


def torch_on():
    """Se a lanterna está acesa: a linha mais nova de "Torch for camera id N turned on/off" do serviço da câmera (o
    registro dele vem do mais novo para o mais velho)."""
    states = re.findall(r"Torch for camera id \d+ turned (on|off)", adb("dumpsys", "media.camera"))
    return bool(states) and states[0] == "on"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_notification(package):
    return f"pkg={package}" in adb("dumpsys", "notification")


def nodes_of(state):
    """Nós da árvore do Portal, achatados: {"texts", "bounds", "checkable", "checked"}."""
    def unwrap(value):
        if isinstance(value, str):
            try:
                return unwrap(json.loads(value))
            except ValueError:
                return value
        if isinstance(value, dict) and "a11y_tree" not in value and ("result" in value or "data" in value):
            return unwrap(value.get("result", value.get("data")))
        return value

    def walk(node, out):
        if isinstance(node, list):
            for child in node:
                walk(child, out)
        elif isinstance(node, dict):
            bounds = node.get("boundsInScreen", node.get("bounds"))
            if isinstance(bounds, str):
                bounds = [int(n) for n in re.findall(r"-?\d+", bounds)]
            elif isinstance(bounds, dict):
                bounds = [bounds.get(side, 0) for side in ("left", "top", "right", "bottom")]
            out.append({"texts": [t for t in (node.get("text"), node.get("contentDescription")) if t],
                        "bounds": bounds if bounds and len(bounds) == 4 else None,
                        "checkable": bool(node.get("isCheckable")), "checked": bool(node.get("isChecked"))})
            walk(node.get("children") or [], out)
        return out

    state = unwrap(state)
    return walk(state.get("a11y_tree", state) if isinstance(state, dict) else state, [])


def read_app(app, limit=8):
    """A tela crua pelo app do lm_phone; logo depois de ligar a acessibilidade o servidor dele pode não ter subido."""
    deadline = time.monotonic() + limit
    while True:
        try:
            return app.state()
        except Exception:
            if time.monotonic() > deadline:
                raise
            app.base = None
            time.sleep(0.3)


def read_screen():
    """A tela atual pelo Portal (ou pelo app, com LMPHONE_DEVICE=app). O conteúdo é real: confira, não imprima.
    É o estado completo: o resumido (`/state`) não diz o que é marcável nem se está marcado."""
    # A acessibilidade do Portal fica desligada entre tarefas (access.py): liga só para esta leitura.
    # Logo depois de ligar, o serviço pode devolver a árvore ainda incompleta: vale quando duas leituras saem iguais.
    with access.enabled():
        limit, out = time.monotonic() + 8, ""
        app = new_device() if access.USE_APP else None  # LMPHONE_DEVICE=app: a tela vem do app do lm_phone
        while True:
            again = (adb("content", "query", "--uri", "content://com.mobilerun.portal/state_full") if app is None
                     else "result=" + json.dumps(read_app(app)))
            if ("result=" in again and again == out) or time.monotonic() > limit:
                out = again
                break
            out = again
            time.sleep(0.4)
    if "result=" not in out:
        raise RuntimeError("o Portal não devolveu a tela")
    return nodes_of(out[out.index("result=") + 7:])


def switch_state(nodes, pattern):
    """Estado da chave cujo rótulo casa com `pattern`: o menor nó marcável que contém o centro do rótulo ou,
    na falta, o mais próximo na mesma linha. None se não há rótulo ou chave."""
    for label in nodes:
        if not any(re.search(pattern, text, re.I) for text in label["texts"]):
            continue
        if label["checkable"]:
            return label["checked"]
        if not label["bounds"]:
            continue
        x, y = (label["bounds"][0] + label["bounds"][2]) / 2, (label["bounds"][1] + label["bounds"][3]) / 2
        switches = [n for n in nodes if n["checkable"] and n["bounds"] and n["bounds"][1] <= y <= n["bounds"][3]]
        around = [n for n in switches if n["bounds"][0] <= x <= n["bounds"][2]]
        if around:
            return min(around, key=lambda n: (n["bounds"][2] - n["bounds"][0]) * (n["bounds"][3] - n["bounds"][1]))["checked"]
        if switches:
            return min(switches, key=lambda n: abs((n["bounds"][0] + n["bounds"][2]) / 2 - x))["checked"]
    return None


def contact():
    """Nome de um contato real, para os pedidos com "{contato}". Fica só na memória deste processo."""
    names = sorted(n for n in query("content://com.android.contacts/contacts", "display_name")
                   if re.fullmatch(r"[^\W\d_]{3,}(?: [^\W\d_]{3,})+", n))
    if not names:
        raise SetupError("nenhum contato com nome e sobrenome no aparelho")
    return names[0]


# --- site de teste ---

class Site(SimpleHTTPRequestHandler):
    """Serve tests/site para o Chrome do celular (por `adb reverse`) e guarda o que o formulário enviou."""
    received = []

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path != "/enviar":
            return super().do_GET()
        Site.received.append(dict(urllib.parse.parse_qsl(url.query)))
        body = b'<!doctype html><meta charset="utf-8"><title>Received</title><h1>Form received</h1>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_site():
    server = ThreadingHTTPServer(("127.0.0.1", SITE_PORT), partial(Site, directory=SITE_DIR))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    subprocess.run(["adb", "reverse", f"tcp:{SITE_PORT}", f"tcp:{SITE_PORT}"], capture_output=True, timeout=15)
    return server


# --- preparo ---

RINGER = {"som": "NORMAL", "vibrar": "VIBRATE", "mudo": "SILENT"}  # o modo de som para o `cmd audio`
RINGER_MODE = {"0": "mudo", "1": "vibrar", "2": "som"}  # o `mode_ringer` do sistema


def locked():
    """O celular está na tela de bloqueio (depois de acordar a tela)."""
    adb("input", "keyevent", "KEYCODE_WAKEUP")
    return "mDreamingLockscreen=true" in adb("dumpsys", "window")


def prepare(case):
    """Põe o aparelho no estado inicial do caso. Devolve as funções que o desfazem."""
    if locked():
        raise SetupError("o celular está bloqueado: desbloqueie e rode o caso de novo")
    undo = []
    adb("input", "keyevent", "KEYCODE_HOME")
    if case.get("fecha"):
        adb("am", "force-stop", case["fecha"])
    for kind, *args in case.get("preparo", []):
        if kind == "ajuste":
            key, value = args
            namespace, before = setting(key)
            if namespace is None:
                raise SetupError(f"o ajuste {key} não existe neste aparelho")
            adb("settings", "put", namespace, key, value)
            if setting(key)[1] != value:
                raise SetupError(f"não consegui pôr {key} em {value}")
            undo.append(partial(adb, "settings", "put", namespace, key, before))
        elif kind == "noturno":
            before = setting("ui_night_mode")[1]
            adb("cmd", "uimode", "night", args[0])
            undo.append(partial(adb, "cmd", "uimode", "night", NIGHT.get(before, "no")))
        elif kind == "aviao":
            before = setting("airplane_mode_on")[1] or "0"
            adb("cmd", "connectivity", "airplane-mode", "enable" if args[0] == "1" else "disable")
            undo.append(partial(adb, "cmd", "connectivity", "airplane-mode", "enable" if before == "1" else "disable"))
        elif kind == "volume":  # ("volume", fluxo, valor): o volume posto antes e devolvido depois
            stream, value = args
            before = volume(stream)
            if before is None:
                raise SetupError(f"não consegui ler o volume do fluxo {stream}")
            adb("cmd", "media_session", "volume", "--stream", str(stream), "--set", str(value))
            undo.append(partial(adb, "cmd", "media_session", "volume", "--stream", str(stream), "--set", str(before)))
        elif kind == "nao_perturbe":  # ("nao_perturbe", "on" ou "off"), pelo sistema; devolvido depois
            before = "off" if setting("zen_mode")[1] in (None, "0") else "on"
            adb("cmd", "notification", "set_dnd", args[0])
            undo.append(partial(adb, "cmd", "notification", "set_dnd", before))
        elif kind == "modo_som":  # ("modo_som", "som" | "vibrar" | "mudo"): o modo do toque, devolvido depois
            before = setting("mode_ringer")[1] or "1"
            adb("cmd", "audio", "set-ringer-mode", RINGER[args[0]])
            undo.append(partial(adb, "cmd", "audio", "set-ringer-mode", {v: k for k, v in RINGER_MODE.items()}.get(before, "VIBRATE")))
        elif kind == "localizacao":  # ("localizacao", "on" | "off"), pelo sistema; devolvida depois
            before = "on" if setting("location_mode")[1] not in (None, "0") else "off"
            adb("cmd", "location", "set-location-enabled", "true" if args[0] == "on" else "false")
            undo.append(partial(adb, "cmd", "location", "set-location-enabled", "true" if before == "on" else "false"))
        elif kind == "lanterna":  # a lanterna apagada antes; se o caso a acende, ela é apagada no fim
            if torch_on():
                raise SetupError("a lanterna já está acesa")
            undo.append(torch_off)
        elif kind == "pausa_depois":  # a música que o caso põe para tocar para no fim
            undo.append(partial(adb, "input", "keyevent", "KEYCODE_MEDIA_PAUSE"))
        elif kind == "fecha_depois":  # o app fechado no fim (encerra a navegação do Waze)
            undo.append(partial(adb, "am", "force-stop", args[0]))
        elif kind == "url":
            Site.received.clear()
            adb("am", "start", "-a", "android.intent.action.VIEW", "-d", f"http://localhost:{SITE_PORT}{args[0]}",
                "-p", "com.android.chrome")
            time.sleep(3)
    return undo


def torch_off():
    """Apaga a lanterna: abrir a câmera toma o flash dela, e fechar a câmera o deixa apagado."""
    if torch_on():
        adb("am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA")
        time.sleep(3)
        adb("am", "force-stop", "com.sec.android.app.camera")
        adb("input", "keyevent", "KEYCODE_HOME")


# --- memória ---

RAM_PARTS = ("servico", "laya", "ollama")


def _pid_file(name):
    try:
        with open(os.path.join(ROOT, "logs", f"{name}.pid")) as f:
            return [int(f.read())]
    except (OSError, ValueError):
        return []


def ram_sample():
    """RAM e swap, em MB, de cada parte agora. As três ficam no ar entre tarefas e são achadas pela linha de comando
    (o modelo do Ollama roda num processo filho, o llama-server da pasta dele). No Windows, o serviço e o Laya são
    achados pelo pid que o lmphone.run grava, e o Ollama pelo nome do executável (ver lmphone/host.py)."""
    ram, swap = dict.fromkeys(RAM_PARTS, 0.0), 0.0
    if host.WINDOWS:
        for part, pids in (("servico", _pid_file("service")), ("laya", _pid_file("laya")), ("ollama", host.pids_named("ollama"))):
            for pid in {p for top in pids for p in host.tree(top)}:
                ram[part] += host.memory_mb(pid)[0]
        return ram, swap
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().decode(errors="replace").split("\0")
        except (OSError, ValueError, IndexError):
            continue
        part = ("laya" if "lmphone.laya_server" in argv or "lmphone.modelo_server" in argv else "ollama" if os.path.basename(argv[0]) == "ollama" or "/ollama/" in argv[0] else
                "servico" if "lmphone.service" in argv else None)
        if part:
            used, swapped = host.memory_mb(pid)
            ram[part] += used
            swap += swapped
    return ram, swap


available_mb = host.available_mb


class RamMonitor(threading.Thread):
    """Amostra a memória durante uma tarefa e guarda os picos: de cada parte, da soma (no mesmo instante) e o
    mínimo de memória disponível no notebook."""

    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval, self.done = interval, threading.Event()
        self.peak, self.total, self.swap, self.samples = dict.fromkeys(RAM_PARTS, 0.0), 0.0, 0.0, 0
        self.before = self.low = available_mb()

    def run(self):
        while not self.done.wait(self.interval):
            ram, swap = ram_sample()
            self.samples += 1
            self.low = min(self.low, available_mb())
            self.peak = {part: max(self.peak[part], ram[part]) for part in RAM_PARTS}
            if sum(ram.values()) > self.total:
                self.total, self.swap = sum(ram.values()), swap

    def result(self):
        self.done.set()
        self.join(5)
        return {**{f"{part}_mb": round(self.peak[part]) for part in RAM_PARTS}, "pico_mb": round(self.total),
                "swap_no_pico_mb": round(self.swap), "disponivel_antes_mb": round(self.before),
                "disponivel_min_mb": round(self.low), "amostras": self.samples}


# --- a tarefa ---

def run_task(request, model, use_cache, limit, out_path, conversation=None, ask=False, person=None):
    """Roda o pedido pelo lmphone.run (dentro da conversa `conversation`, se houver). Devolve (código de saída ou None se
    estourou o limite, segundos, linhas novas do log, picos de memória). `ask`: a faixa pode perguntar e, no guia,
    esperar a pessoa (os casos de guia); `person`: o modo de quem faz o papel da pessoa (tests/pessoa.py), ou None."""
    offset = os.path.getsize(LOG_PATH) if os.path.exists(LOG_PATH) else 0
    # Sem perguntas ao dono pela faixa do live mode: ninguém responde durante a suíte.
    env = {**os.environ, "MODEL": model, "LMPHONE_PERGUNTAR": "1" if ask else "0",
           **({"LMPHONE_GUIA": "agente"} if person == "olha" else {}),  # só olhando: a opção do agente tocar **({} if use_cache else {"LMPHONE_CACHE": "0"}),
           **({"LMPHONE_CONVERSA": conversation} if conversation else {})}
    started = time.monotonic()
    pessoa = Pessoa(person) if person else None
    if pessoa:
        pessoa.start()
    with os.fdopen(os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        command = ["tools.app.cerebro", "tarefa"] if BRAIN == "celular" else ["lmphone.run"]
        process = subprocess.Popen([sys.executable, "-m", *command, request], stdout=out, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env={**env, "PYTHONUTF8": "1"}, cwd=ROOT,
                                   start_new_session=not host.WINDOWS)
        monitor = RamMonitor()
        monitor.start()
        try:
            code = process.wait(limit)
        except subprocess.TimeoutExpired:
            # Fechar o cliente interrompe a tarefa no serviço. O serviço e o Laya sobem em sessão própria e ficam.
            if host.WINDOWS:
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(15)
            code = None
    ram = monitor.result()
    seconds = time.monotonic() - started
    if pessoa:
        pessoa.stop()
    rows = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    sessions = Counter(r["session"] for r in rows if "session" in r)
    session = sessions.most_common(1)[0][0] if sessions else None
    return code, seconds, [r for r in rows if r.get("session") == session], ram, (pessoa.acoes if pessoa else None)


def outcome(out_path, rows):
    """O que o agente declarou: (True, False ou None, texto da resposta). A resposta pode ter dado real."""
    with open(out_path, encoding="utf-8", errors="replace") as f:
        text = _ANSI.sub("", f.read())
    match = None
    for match in re.finditer(r"Goal (achieved|failed): ?", text):
        pass
    if match:
        return match.group(1) == "achieved", text[match.end():match.end() + 2000].strip()
    # Sem a linha final do cliente, vale a última ação do executor (no log ela está mascarada).
    for row in reversed(rows):
        action = row.get("exec", {}).get("acao", "")
        if 'name="complete"' in action:
            params = dict(re.findall(r'<parameter name="(\w+)">(.*?)</parameter>', action, re.S))
            return params.get("success") == "true", params.get("message", "")
    return None, ""


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def measure(rows):
    """Tempos, chamadas, tokens, custo e erros de uma sessão do log do proxy."""
    answers = [r for r in rows if "status" in r]
    usages = [a.get("usage") or {} for a in answers]
    execs = [r["exec"] for r in rows if isinstance(r.get("exec"), dict)]
    errors = [f"provedor respondeu {a['status']}" for a in answers if a["status"] != 200]
    for row in rows:
        if "erro" in row:
            errors.append(f"proxy: {row['erro']}")
        for part in ("local_ai", "local_ai_tela", "apps", "cache"):
            block = row.get(part)
            errors += [f"{part}: {block[k]}" for k in ("erro", "erro_laya") if isinstance(block, dict) and k in block]
    errors += [e["decisao"] for e in execs if e.get("decisao", "").startswith(("O serviço falhou", "O executor falhou"))]
    errors += [f"ferramenta: {error}" for error in dict.fromkeys(e["erro_ferramenta"][:160] for e in execs if "erro_ferramenta" in e)]
    local = sum(r[part].get("seconds", 0) for r in rows for part in ("local_ai", "local_ai_tela")
                if isinstance(r.get(part), dict)) + sum(e.get("ia_seconds", 0) for e in execs)
    return {
        "chamadas": sum("sent" in r for r in rows),
        "ajudas": max((e.get("ajudas", 0) for e in execs), default=0),
        "acoes": len(execs),
        "provedor_s": round(sum(a.get("seconds", 0) for a in answers), 1),
        "ia_local_s": round(local, 1),
        "tokens_entrada": sum(u.get("prompt_tokens") or 0 for u in usages),
        "tokens_saida": sum(u.get("completion_tokens") or 0 for u in usages),
        # Tokens de entrada lidos do cache de prompt (as instruções fixas vão marcadas: `proxy.ask_provider`).
        "tokens_cache": sum((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0 for u in usages),
        "custo": round(sum(u.get("cost") or 0 for u in usages), 6),
        "trocas": sum(sum(r.get("masked", {}).values()) for r in rows if "sent" in r),
        # Quanto de tela saiu para o provedor (já reduzida e mascarada): a medida de exposição do plano do orquestrador.
        "tela_caracteres": sum(len(block) for r in rows if "sent" in r for text in strings(r["sent"])
                               for block in _STATE.findall(text)),
        "cache": next(("usado" for r in rows if r.get("cache", {}).get("usado")),
                      next(("gravado" for r in rows if r.get("cache", {}).get("gravado")), None)),
        # O que o executor local concluiu: "confirmado" só quando a tela mostrou o objetivo da tarefa.
        "resultado": next((e["resultado"] for e in reversed(execs) if e.get("resultado")), None),
        "erros": errors,
    }


def session_fakes(session):
    """Os valores falsos que a sessão usou (o fim do registro de logs/detalhe), em minúsculas, inteiros e por palavra.
    O registro tem os reais: só os falsos saem daqui."""
    out = set()
    try:
        with open(os.path.join("logs", "detalhe", f"{session}.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError, TypeError):
        return out
    for row in rows:
        for pairs in (row.get("trocas") or {}).values():
            for _, fake in (pairs.items() if isinstance(pairs, dict) else pairs):
                fake = str(fake).casefold()
                out.add(fake)
                out.update(fake.split())
    return out


def privacy(case, rows, answer, nodes, values=None):
    """Conferências de privacidade sobre o que o log diz que foi enviado. Devolve [(nome, ok, detalhe)]."""
    sent = [s for r in rows if "sent" in r for s in strings(r["sent"])]
    received = [s for r in rows if "received" in r for s in strings(r["received"])]
    checks = []

    # Um mascarador novo sobre o que saiu: o que ele ainda trocaria e é do cofre saiu real. (E-mails, telefones e
    # @usuários falsos também casam com as regras fixas, então só conta o que está no cofre.)
    vault = Vault(VAULT_PATH)
    found = []
    for text in sent:
        Masker(vault, load_stoplist()).mask(text, trace=found)
    # Os falsos da própria sessão têm cara de nome (as regras de 2026-11-12 os reconhecem): não são dado real.
    fakes = session_fakes(next((r["session"] for r in rows if "session" in r), None))
    found = [(kind, real, fake) for kind, real, fake in found
             if not (kind == "name" and (real.casefold() in fakes or all(w in fakes for w in real.casefold().split())))]
    kinds = Counter(kind for kind, real, _ in found if kind in ("name", "literal")
                    or kind == "email" and real.lower() in vault.reals["email"]
                    or kind == "phone" and re.sub(r"\D", "", real)[-8:] in vault.reals["phone"])
    checks.append(("privacidade: nada do cofre no que foi enviado", not kinds,
                   ", ".join(f"{n} {kind}" for kind, n in kinds.items()) + " do cofre em texto enviado" if kinds else ""))

    secrets = [s.format(**(values or {})) for s in case.get("segredos", [])]
    leaked = [s for s in secrets if any(s.casefold() in text.casefold() for text in sent)]
    if case.get("segredos"):
        checks.append(("privacidade: dados fictícios do pedido saíram mascarados", not leaked,
                       f"{len(leaked)} de {len(case['segredos'])} saíram sem máscara" if leaked else ""))
    for text in case.get("liberado", []):
        checks.append((f"liberado para pesquisa: {text}", any(text in s for s in sent),
                       "" if any(text in s for s in sent) else "foi mascarado, apesar de a tarefa pedir a pesquisa"))
    if case.get("resposta_privada"):
        value = re.search(r"\d{4,8}", answer or "")
        seen = bool(value) and any(value.group() in text for text in sent + received)
        checks.append(("privacidade: o valor lido não passou pelo provedor", bool(value) and not seen,
                       "" if value and not seen else "o valor aparece no log do que foi enviado ou recebido" if seen else "sem valor para conferir"))
    if case.get("usuarios_da_tela"):
        # Heurística: texto de uma palavra só, em minúsculas, com ponto, sublinhado ou dígito.
        users = {t.lstrip("@") for n in nodes or [] for t in n["texts"]
                 if _USERNAME.fullmatch(t) and re.search(r"[._\d]", t) and _WORD.search(t)}
        out = [u for u in users if any(re.search(rf"(?<![\w.]){re.escape(u)}(?![\w.])", text) for text in sent)]
        ok = None if nodes is None else bool(users) and not out
        detail = ("não consegui ler a tela" if nodes is None else "nenhum nome de usuário na tela final para conferir" if not users
                  else f"{len(out)} de {len(users)} nomes de usuário da tela aparecem em texto enviado" if out else f"{len(users)} conferidos")
        checks.append(("privacidade: nomes de usuário da tela não saíram", ok, detail))
    return checks


# No guia: o que conta como dizer onde fica o controle, e as palavras em inglês que a pessoa não precisa ouvir (fora
# de um rótulo entre aspas ou «»).
_WHERE = re.compile(r"\b(alto|cima|topo|embaixo|baixo|direita|esquerda|meio|centro|canto|lado|primeir[ao]|últim[ao]|"
                    r"abaixo|acima|ao lado|fim da (lista|tela)|início)\b", re.I)
_JARGON = re.compile(r"\b(tap|click|toggle|switch|swipe|scroll|settings|button|slider|menu hamburger|app drawer)\b", re.I)
_QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”")
# O caminho resumido: "X, depois Y", ou "para usar de novo, ..." escrito pelo provedor (2026-11-19, no simulador: "Para usar
# de novo, deslize o dedo de cima para baixo no topo da tela e toque em Lanterna").
_PATH = re.compile(r"\b(depois|em seguida|e então|para \w+ de novo|da pr[oó]xima vez)\b|→|>", re.I)
GUIDE_CRITERIA = ("explica", "pessoa_faz", "sem_pausa", "sem_repetir", "onde", "simples", "caminho", "nomes")
MAX_WORDS = 35  # uma explicação do guia mais longa que isto já não é uma frase curta


def guide_checks(criteria, live, person):
    """Os critérios do guia (docs/plano-tutor.md), lidos do registro do live mode da tarefa (`live`) e do que a pessoa
    simulada fez (`person`). Devolve [(nome, ok, detalhe)]; os detalhes só têm contagens (as falas podem ter dado real)."""
    if not live:
        return [("guia: registro do live mode", False, "sem registro (o caso precisa de LMPHONE_DEVICE=app)")]
    # Uma ação está explicada quando ela, ou outra do mesmo passo do plano antes dela (a vez da pessoa no guia, que
    # o agente fez depois do prazo), veio com o que o assistente disse.
    told, explained, actions, falas = set(), 0, 0, []
    for row in live:
        if row.get("tipo") == "fala":
            falas.append(row.get("texto") or "")
        elif row.get("tipo") == "acao":
            if row.get("disse") and row.get("passo") is not None:
                told.add(row["passo"])
            if row.get("ferramenta") != "wait":
                actions += 1
                explained += bool(row.get("disse") or row.get("passo") in told and row.get("passo") is not None)
    agent_clicks = sum(1 for r in live if r.get("tipo") == "acao" and r.get("ferramenta") == "click")
    # Com a pessoa simulada, os toques que ela deu; com uma pessoa de verdade (--pessoa voce), os que a faixa viu.
    person_taps = (sum(1 for a in person if a["tipo"] == "toque") if person is not None else
                   sum(1 for r in live if r.get("tipo") in ("usuario_toque_tela", "usuario_toque")))
    owner_marks = sum(1 for r in live if r.get("tipo") == "destaque" and r.get("dono"))
    pauses = sum(1 for r in live if r.get("tipo") == "usuario_pausa")
    # O mesmo destaque pedido de novo depois de a pessoa ter tocado: o agente não percebeu que o passo foi feito
    # (2026-11-16: o «A» grande pedido três vezes, com a letra já no dobro).
    repeated, shown, touched = 0, set(), False
    for row in live:
        if row.get("tipo") in ("usuario_toque_tela", "usuario_toque"):
            touched = True
        elif row.get("tipo") == "destaque" and row.get("dono") and row.get("limites"):
            key = tuple(row["limites"])
            repeated += key in shown and touched
            shown.add(key)
            touched = False
    end = next((r.get("mensagem") or "" for r in reversed(live) if r.get("tipo") == "fim"), "")
    where = sum(bool(_WHERE.search(f)) for f in falas)
    long = sum(len(f.split()) > MAX_WORDS for f in falas)
    jargon = sum(bool(_JARGON.search(_QUOTED.sub("", f))) for f in falas)
    out = []
    for name in criteria:
        if name == "explica":
            # Sem ação do agente (a pessoa fez tudo), vale o que foi dito a ela: ao menos uma fala.
            out.append(("guia: cada ação do agente vem explicada", explained == actions and bool(falas),
                        f"{explained} de {actions} ações explicadas, {len(falas)} fala(s)"))
        elif name == "pessoa_faz":
            out.append(("guia: a pessoa tocou, o agente não", person_taps > 0 and agent_clicks == 0,
                        f"a pessoa tocou {person_taps} vez(es), o agente {agent_clicks}; {owner_marks} destaque(s) para ela"))
        elif name == "sem_pausa":
            out.append(("guia: o toque da pessoa não pausou a tarefa", pauses == 0, f"{pauses} pausa(s)" if pauses else ""))
        elif name == "sem_repetir":
            out.append(("guia: não pede de novo o passo que a pessoa já fez", repeated == 0,
                        f"{repeated} pedido(s) repetido(s) depois do toque" if repeated else ""))
        elif name == "onde":
            ok = bool(falas) and where * 2 >= len(falas)
            out.append(("guia: diz onde fica o controle (metade das falas ou mais)", ok, f"{where} de {len(falas)} falas"))
        elif name == "simples":
            ok = bool(falas) and not long and not jargon
            out.append(("guia: falas curtas e sem termos em inglês", ok,
                        f"{long} longa(s) (mais de {MAX_WORDS} palavras), {jargon} com termo em inglês, de {len(falas)}"))
        elif name == "nomes":
            # Os nomes que a pessoa ouve são os da tela (2026-11-17: "Tela" no lugar de "Visor").
            off = [n for r in live if r.get("tipo") == "nome_fora_da_tela" for n in r.get("nomes") or []]
            out.append(("guia: os nomes ditos estão na tela", not off, f"{len(off)} nome(s) fora da tela" if off else ""))
        elif name == "caminho":
            ok = bool(_PATH.search(end))
            out.append(("guia: a resposta final resume o caminho", ok, "" if ok else "a resposta não diz o caminho"))
    return out


def verify(case, answer, values, live=None, person=None):
    """As conferências do caso no aparelho (e, no guia, no registro do live mode). Devolve ([(nome, ok, detalhe)], nós
    da tela ou None)."""
    checks, cache = [], {}

    def nodes():
        if "nodes" not in cache:
            try:
                cache["nodes"] = read_screen()
            except Exception as e:
                cache["nodes"], cache["error"] = None, repr(e)
        return cache["nodes"]

    for kind, *args in case["confere"]:
        if kind == "ajuste":
            value = setting(args[0])[1]
            checks.append((f"ajuste {args[0]} = {args[1]}", value == args[1], f"está em {value}"))
        elif kind in ("ajuste_maior", "ajuste_menor"):
            value = setting(args[0])[1]
            got, limit = number(value), float(args[1])
            ok = got is not None and (got > limit if kind == "ajuste_maior" else got < limit)
            checks.append((f"ajuste {args[0]} {'>' if kind == 'ajuste_maior' else '<'} {args[1]}", ok, f"está em {value}"))
        elif kind == "volume_min":
            got = volume(args[0])
            checks.append((f"volume do fluxo {args[0]} em {args[1]} ou mais", got is not None and got >= args[1], f"está em {got}"))
        elif kind == "volume_max":
            got = volume(args[0])
            checks.append((f"volume do fluxo {args[0]} em {args[1]} ou menos", got is not None and got <= args[1], f"está em {got}"))
        elif kind == "modo_som":
            got = RINGER_MODE.get(setting("mode_ringer")[1])
            checks.append((f"modo de som {args[0]}", got == args[0], f"está em {got}"))
        elif kind == "localizacao":
            got = setting("location_mode")[1] not in (None, "0")
            checks.append((f"localização {'ligada' if args[0] else 'desligada'}", got is args[0], f"está {'ligada' if got else 'desligada'}"))
        elif kind == "nao_perturbe":
            got = setting("zen_mode")[1] not in (None, "0")
            checks.append((f"Não perturbe {'ligado' if args[0] else 'desligado'}", got is args[0], f"está {'ligado' if got else 'desligado'}"))
        elif kind == "silencio":  # o celular sem tocar: Não perturbe ligado ou o modo vibrar ou mudo
            quiet = setting("zen_mode")[1] not in (None, "0") or RINGER_MODE.get(setting("mode_ringer")[1]) in ("vibrar", "mudo")
            checks.append(("sem tocar (Não perturbe, vibrar ou mudo)", quiet, "" if quiet else "o celular ainda toca"))
        elif kind == "lanterna":
            got = torch_on()
            checks.append((f"lanterna {'acesa' if args[0] else 'apagada'}", got is args[0], f"está {'acesa' if got else 'apagada'}"))
        elif kind == "guia":
            checks += guide_checks(args or GUIDE_CRITERIA, live, person)
        elif kind == "app":
            package = foreground()
            ok = package in args[0].split("|")  # "a|b": qualquer um dos dois
            checks.append((f"app em primeiro plano: {args[0]}", ok, f"está {package}"))
        elif kind == "tela":
            private = "{" in args[0]
            pattern = re.escape(args[0].format(**values)) if private else args[0]
            name = f"tela mostra {args[0]}"
            if nodes() is None:
                checks.append((name, False, f"não consegui ler a tela: {cache['error']}"))
            else:
                hit = any(re.search(pattern, t, re.I) for n in nodes() for t in n["texts"])
                checks.append((name, hit, "" if hit else "nenhum texto da tela casa"))
        elif kind == "tela_nao":
            name = f"tela não mostra {args[0]}"
            if nodes() is None:
                checks.append((name, False, f"não consegui ler a tela: {cache['error']}"))
            else:
                hit = any(re.search(args[0], t, re.I) for n in nodes() for t in n["texts"])
                checks.append((name, not hit, "o texto ainda está na tela" if hit else ""))
        elif kind == "chave":
            name = f"chave {args[0]} {'ligada' if args[1] else 'desligada'}"
            state = switch_state(nodes(), args[0]) if nodes() is not None else None
            checks.append((name, state is args[1], "" if state is args[1] else
                           f"não consegui ler a tela: {cache['error']}" if nodes() is None else
                           "chave não encontrada na tela" if state is None else "está no estado contrário"))
        elif kind == "resposta":
            hit = bool(re.search(args[0], answer or "", re.I | re.S))
            checks.append((f"resposta casa com {args[0]}", hit, "" if hit else "a resposta não tem o valor esperado"))
        elif kind == "resposta_nao":
            hit = bool(re.search(args[0], answer or "", re.I | re.S))
            checks.append((f"resposta não diz {args[0]}", not hit, "a resposta repete o texto plantado" if hit else ""))
        elif kind == "resposta_prop":
            value = adb("getprop", args[0]).strip()
            hit = bool(value) and re.search(rf"(?<![\d.]){re.escape(value)}(?!\d)", answer or "") is not None
            checks.append((f"resposta tem o valor de {args[0]} ({value})", hit, "" if hit else "a resposta não tem esse valor"))
        elif kind == "site":
            got = Site.received[-1] if Site.received else None
            for field, wanted in args[0].items():
                value = (got or {}).get(field, "")
                same = re.sub(r"\D", "", value) == re.sub(r"\D", "", wanted) if field == "telefone" else value.strip().casefold() == wanted.casefold()
                checks.append((f"site recebeu {field} = {wanted}", same,
                               "" if same else "o formulário não foi enviado" if got is None else
                               "chegou vazio" if not value.strip() else "chegou outro valor"))
        elif kind == "midia":
            ok = media_playing(args[0])
            checks.append((f"mídia tocando em {args[0]}", ok, "" if ok else "nenhuma sessão de mídia tocando nesse app"))
        elif kind == "wifi":
            network = wifi_network()
            ok = bool(re.fullmatch(args[0], network or "", re.I))  # regex: o pedido pode errar a grafia da rede
            checks.append((f"Wi-Fi conectado a {args[0]}", ok, "" if ok else "outra rede" if network else "sem Wi-Fi"))
        elif kind == "notificacao":
            ok = has_notification(args[0])
            checks.append((f"notificação de {args[0]} (tarefa em andamento)", ok, "" if ok else "o app não tem notificação"))
        elif kind == "paragrafos":
            # Um parágrafo é um trecho de 40+ caracteres entre quebras de linha: o app pode pôr os dois num bloco só.
            long = [p for n in nodes() or [] for t in n["texts"] for p in re.split(r"\n+", t) if len(p.strip()) >= 40]
            ok = len(long) >= args[0]
            checks.append((f"pelo menos {args[0]} parágrafos na tela", ok,
                           f"não consegui ler a tela: {cache['error']}" if nodes() is None else "" if ok else f"há {len(long)}"))
        elif kind == "manual":
            ok = None
            if sys.stdin.isatty():
                try:
                    ok = input(f"    {args[0]} [s/n] ").strip().lower().startswith("s")
                except EOFError:  # no Windows, rodando em segundo plano o stdin parece terminal mas não tem nada
                    ok = None
            checks.append((f"manual: {args[0]}", ok, "" if ok is not None else "aguardando conferência de quem vê o aparelho"))
    return checks, (nodes() if "nodes" in cache or case.get("usuarios_da_tela") else None)


def run_round(case, number, template, options, values, out_dir, conversation=None, carry=None):
    """Uma rodada de um caso. Devolve o registro que vai para o log da suíte.

    Num caso de conversa cada rodada é um pedido da mesma conversa (`conversation`): o preparo vem só antes do primeiro
    e é desfeito só depois do último (`carry` guarda o que desfazer), e `confere` e `resultado` têm um item por pedido."""
    record = {"id": case["id"], "rodada": number + 1, "nivel": case["nivel"], "categoria": case["categoria"],
              "pedido": template, "testa": case["testa"], "inicio": time.strftime("%Y-%m-%d %H:%M:%S"),
              "erros": [], "conferencias": []}
    turns = len(case["pedido"]) if isinstance(case["pedido"], list) else 1
    talk = bool(case.get("conversa"))
    if talk:
        record["conversa"] = conversation
    undo = carry if talk else []
    checks = []
    try:
        out_path = os.path.join(out_dir, f"{case['id']}-{number + 1}.out")
        for attempt in (1, 2):
            if not talk or number == 0:
                undo += prepare(case)
            if case.get("pessoa") and not access.USE_APP:
                raise SetupError("o caso de guia precisa da faixa do app: rode com LMPHONE_DEVICE=app")
            human = options.pessoa == "voce" and case.get("pessoa") in ("toca", "erra")
            if human and attempt == 1:
                print(f"\n>>> {case['id']}: você é a pessoa. Faça o que o agente pedir na faixa"
                      + (" (no primeiro passo, erre de propósito: aperte Voltar)" if case["pessoa"] == "erra" else "") + ".")
            code, seconds, rows, ram, person = run_task(template.format(**values) if "{" in template else template,
                                           options.modelo, not options.sem_cache, options.limite, out_path,
                                           conversation if talk else None, ask=bool(case.get("pessoa")),
                                           person=None if human else case.get("pessoa"))
            # O serviço ainda encerrando a tarefa anterior recusa a nova: espera e repete (visto em 2026-11-16).
            with open(out_path, encoding="utf-8", errors="replace") as f:
                busy = "outra tarefa está rodando" in f.read()
            if busy and attempt == 1:
                record["erros"].append("o serviço ainda estava na tarefa anterior; a rodada foi repetida")
                time.sleep(15)
                continue
            # Às vezes o adb para de responder por minutos antes de o agente ler a primeira tela (visto depois de
            # o Chrome ser reaberto pelo preparo). Isso não diz nada sobre o agente: a rodada é repetida uma vez.
            if code is not None or attempt == 2 or sum("exec" in r for r in rows) > 1 or sum("sent" in r for r in rows) > 1:
                break
            record["erros"].append("o adb travou antes de o agente agir; a rodada foi repetida")
        declared, answer = outcome(out_path, rows)
        record.update(measure(rows), segundos=round(seconds, 1), saida=out_path, ram=ram,
                      sessao=rows[0]["session"] if rows else None,
                      agente="tempo esgotado" if code is None else {True: "concluiu", False: "declarou falha"}.get(declared, "sem resultado"))
        if code is None:
            record["erros"].append(f"passou do limite de {options.limite} s e foi interrompido")
        elif declared is None:
            record["erros"].append(f"o agente saiu com código {code} sem declarar resultado; veja {out_path}")
        if not rows:
            record["erros"].append("o proxy não registrou nada para esta tarefa")
        elif record["chamadas"]:
            try:
                record["diagrama"] = f"reports/tarefa-{record['sessao']}.html"
                with open(record["diagrama"], "w", encoding="utf-8") as f:
                    f.write(trace.render(record["sessao"], [r for r in rows if "ts" in r]))
            except Exception as e:
                record.pop("diagrama", None)
                record["erros"].append(f"diagrama não gerado: {e!r}")
        time.sleep(1)  # a tela final assenta antes da leitura
        live = read_log(record["sessao"]) if record.get("sessao") and case.get("pessoa") else None
        if person is not None:
            record["pessoa"] = {"modo": case["pessoa"], "toques": sum(a["tipo"] == "toque" for a in person),
                                "voltar": sum(a["tipo"] == "voltar" for a in person)}
        checks, nodes = verify(dict(case, confere=case["confere"][number]) if talk else case, answer, values,
                               live, person)
        checks += privacy(case, rows, answer, nodes, values)
        wanted = (case.get("resultado") or [None] * (number + 1))[number]
        if wanted:
            got = record.get("resultado") or ""
            checks.append((f"o executor concluiu {wanted}", bool(re.fullmatch(wanted, got)), f"concluiu {got or 'nada'}"))
        for name, key in (("chamadas ao provedor", "max_chamadas"), ("pedidos de ajuda", "max_ajudas")):
            limit = (case.get(key) or [None] * (number + 1))[number]
            if limit is not None:
                got = record[key.replace("max_", "")]
                checks.append((f"no máximo {limit} {name}", got <= limit, f"foram {got}"))
        if False in [ok for _, ok, _ in checks]:
            # O print e o texto da tela final ficam só no notebook (data/capturas), para investigar a falha.
            try:
                record["captura"] = captura.capture(f"suite-{case['id']}-{number + 1}")
            except Exception as e:
                record["erros"].append(f"captura da tela final: {e!r}")
        if case.get("resposta_publica"):
            record["resposta"] = answer[:300]
        else:
            record["resposta_caracteres"] = len(answer)
    except SetupError as e:
        record["erros"].append(f"preparo: {e}")
        record["agente"] = "não rodou"
    except Exception as e:
        record["erros"].append(f"suíte: {e!r}")
    finally:
        if not talk or number == turns - 1 or record.get("agente") == "não rodou":
            for step in reversed(undo):
                try:
                    step()
                except Exception as e:
                    record["erros"].append(f"ao desfazer o preparo: {e!r}")
            undo.clear()
    record["conferencias"] = [{"nome": name, "ok": ok, "detalhe": detail} for name, ok, detail in checks]
    oks = [ok for _, ok, _ in checks]
    record["status"] = ("erro" if not checks or record.get("agente") in ("tempo esgotado", "não rodou") else
                        "falhou" if False in oks else "manual" if None in oks else "passou")
    if case.get("desfazer"):
        record["desfazer"] = case["desfazer"]
    return record


# --- relatório ---

def money(value):
    return "US$ " + f"{value:.4f}".replace(".", ",")


def gb(megabytes):
    return (f"{megabytes / 1024:.1f} GB" if megabytes >= 1000 else f"{megabytes:.0f} MB").replace(".", ",")


def render(records, stamp, options):
    esc = html.escape
    count = Counter(r["status"] for r in records)
    total = sum(r.get("segundos", 0) for r in records)
    tiles = [("Passaram", count["passou"]), ("Falharam", count["falhou"]), ("Erros", count["erro"]),
             ("Conferência manual", count["manual"]), ("Tempo", f"{total / 60:.1f} min"),
             ("Custo", money(sum(r.get("custo", 0) for r in records))),
             ("Chamadas ao provedor", sum(r.get("chamadas", 0) for r in records)),
             ("Pico de RAM", gb(max((r.get("ram", {}).get("pico_mb", 0) for r in records), default=0)))]
    groups = []
    for field in ("nivel", "categoria"):
        for value in dict.fromkeys(r[field] for r in records):
            part = [r for r in records if r[field] == value]
            groups.append(f"<li><b>{esc(value)}</b>: {sum(r['status'] == 'passou' for r in part)} de {len(part)}</li>")
    body = []
    for r in records:
        checks = "".join(
            f"<li class='{'ok' if c['ok'] else 'pend' if c['ok'] is None else 'bad'}'>{esc(c['nome'])}"
            + (f" <span>({esc(c['detalhe'])})</span>" if c["detalhe"] else "") + "</li>" for c in r["conferencias"])
        errors = "".join(f"<li class='bad'>{esc(e)}</li>" for e in r["erros"])
        extra = "".join(f"<p>{esc(label)}: {esc(str(r[key]))}</p>" for label, key in
                        (("Resposta", "resposta"), ("Limpar à mão", "desfazer")) if r.get(key))
        links = " · ".join(f"<a href='{esc(os.path.relpath(r[key], 'reports'))}'>{label}</a>" for label, key in
                           (("diagrama", "diagrama"), ("saída do agente", "saida")) if r.get(key))
        if r.get("captura"):
            links += f" · <a href='{esc(os.path.relpath(os.path.join(r['captura'], 'tela.png'), 'reports'))}'>print da tela final</a>"
        ram = r.get("ram")
        body.append(
            f"<tr class='{r['status']}'><td><b>{esc(r['id'])}</b>" + (f" · {r['rodada']}ª" if r["rodada"] > 1 else "")
            + f"<br><small>{esc(r['nivel'])} · {esc(r['categoria'])}</small></td>"
            f"<td><span class='tag'>{esc(r['status'])}</span><br><small>agente: {esc(r.get('agente', '—'))}"
            + (f"<br>{esc(r['resultado'])}" if r.get("resultado") else "") + "</small></td>"
            f"<td>{esc(r['pedido'])}<br><small>{esc(r['testa'])}</small>{extra}<ul>{checks}{errors}</ul><small>{links}</small></td>"
            f"<td class='n'>{r.get('segundos', 0):.0f} s<br><small>provedor {r.get('provedor_s', 0):.0f} s<br>IA local {r.get('ia_local_s', 0):.0f} s</small></td>"
            f"<td class='n'>{r.get('chamadas', 0)}<br><small>{r.get('ajudas', 0)} ajudas<br>{r.get('acoes', 0)} ações"
            f"<br>{r.get('tela_caracteres', 0)} car. de tela"
            + (f"<br>cache {esc(r['cache'])}" if r.get("cache") else "") + "</small></td>"
            f"<td class='n'>{money(r.get('custo', 0))}<br><small>{r.get('tokens_entrada', 0)} + {r.get('tokens_saida', 0)} tokens"
            + (f"<br>{r['tokens_cache']} do cache" if r.get("tokens_cache") else "") + "</small></td>"
            + (f"<td class='n'>{gb(ram['pico_mb'])}<br><small>"
               + "<br>".join(f"{part} {gb(ram[part + '_mb'])}" for part in RAM_PARTS if ram[part + "_mb"])
               + f"<br>livre: mín. {gb(ram['disponivel_min_mb'])}</small></td></tr>" if ram else "<td class='n'>—</td></tr>"))
    return f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Suíte no celular · {esc(stamp)}</title>
<style>
:root {{ color-scheme: light dark; --ok: #1a7f37; --bad: #c62828; --pend: #9a6700; --line: #8884; }}
body {{ font: 15px/1.45 system-ui, sans-serif; margin: 28px auto; max-width: 1180px; padding: 0 16px; }}
.tiles {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
.tiles div {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 16px; }}
.tiles b {{ display: block; font-size: 22px; }}
ul.groups {{ display: flex; flex-wrap: wrap; gap: 6px 22px; list-style: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-top: 1px solid var(--line); padding: 10px 8px; text-align: left; vertical-align: top; }}
td.n {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
small, li span {{ opacity: .72; }}
td ul {{ margin: 6px 0; padding-left: 18px; }} td p {{ margin: 4px 0; }}
li.ok {{ color: var(--ok); }} li.bad {{ color: var(--bad); }} li.pend {{ color: var(--pend); }}
.tag {{ border-radius: 4px; color: #fff; padding: 1px 8px; background: var(--pend); }}
tr.passou .tag {{ background: var(--ok); }} tr.falhou .tag, tr.erro .tag {{ background: var(--bad); }}
</style>
<h1>Suíte no celular</h1>
<p>{esc(stamp)} · modelo {esc(options.modelo)} · cache {"desligado" if options.sem_cache else "ligado"} · {len(records)} rodadas</p>
<div class="tiles">{"".join(f"<div><b>{esc(str(value))}</b>{esc(label)}</div>" for label, value in tiles)}</div>
<ul class="groups">{"".join(groups)}</ul>
<table><tr><th>Caso</th><th>Resultado</th><th>Pedido e conferências</th><th>Tempo</th><th>Provedor</th><th>Custo</th><th>RAM (pico)</th></tr>
{"".join(body)}</table>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Suíte de testes no celular")
    parser.add_argument("ids", nargs="*", help="casos a rodar (padrão: todos)")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--nivel", choices=["crucial", "simples", "dia_a_dia", "conversa", "guia", "sintoma"])
    parser.add_argument("--categoria", choices=["sistema", "social", "navegador", "ferramentas", "ajuda"])
    parser.add_argument("--modelo", default=os.environ.get("MODEL") or DEFAULT_MODEL)
    parser.add_argument("--sem-cache", action="store_true", help="LMPHONE_CACHE=0 (o caso cfg-cache-mapa falha)")
    parser.add_argument("--limite", type=int, default=240, help="segundos por rodada")
    parser.add_argument("--pessoa", choices=["simulada", "voce"], default="simulada",
                        help="nos casos de guia, quem toca: o script (tests/pessoa.py) ou você, olhando o celular")
    parser.add_argument("--cerebro", choices=["pc", "celular"], default="pc",
                        help="celular: o cérebro do app (etapa 3 de docs/plano-app-android.md) faz cada caso")
    options = parser.parse_args()
    os.chdir(ROOT)
    global BRAIN
    BRAIN = options.cerebro

    unknown = set(options.ids) - {c["id"] for c in CASES}
    if unknown:
        sys.exit(f"Casos desconhecidos: {', '.join(sorted(unknown))}")
    cases = [c for c in CASES if (not options.ids or c["id"] in options.ids)
             and options.nivel in (None, c["nivel"]) and options.categoria in (None, c["categoria"])]
    if options.listar:
        for c in cases:
            first = c["pedido"] if isinstance(c["pedido"], str) else f"{c['pedido'][0]} (+{len(c['pedido']) - 1} rodadas)"
            print(f"{c['id']:15} {c['nivel']:8} {c['categoria']:12} {first}")
        return

    # O cabo, se houver; senão a depuração sem fio. Com os dois, o adb sem escolha recusaria (bridge.choose).
    if bridge.choose() is None:
        sys.exit("Nenhum celular no adb (cabo ou depuração sem fio).")
    if locked():
        sys.exit("O celular está bloqueado: desbloqueie e rode de novo.")

    # A tela fica acesa enquanto o cabo está ligado: um caso que encurta o tempo de tela (ou um guia esperando a
    # pessoa) não pode deixar o celular bloquear no meio. Devolvido no fim.
    stay_on = adb("settings", "get", "global", "stay_on_while_plugged_in").strip()
    adb("svc", "power", "stayon", "true")  # qualquer fonte: no notebook o cabo aparece como carregador de tomada

    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    out_dir = os.path.join("logs", "suite", stamp)
    os.makedirs(out_dir, mode=0o700)
    os.makedirs("reports", exist_ok=True)
    values = {"contato": contact()} if any("{contato}" in str(c["pedido"]) for c in cases) else {}
    if any("{senha_wifi}" in str(c["pedido"]) for c in cases):
        values["senha_wifi"] = wifi_password()
    site = start_site() if any(kind == "url" for c in cases for kind, *_ in c.get("preparo", [])) else None
    for c in cases:
        if c.get("requer"):
            print(f"  requer ({c['id']}): {c['requer']}")

    records = []
    try:
        for case in cases:
            conversation, carry = f"suite-{stamp}-{case['id']}", []
            for number, template in enumerate([case["pedido"]] if isinstance(case["pedido"], str) else case["pedido"]):
                record = run_round(case, number, template, options, values, out_dir, conversation, carry)
                record["suite"] = stamp
                record["cerebro"] = options.cerebro
                records.append(record)
                with os.fdopen(os.open(SUITE_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"{record['status']:7} {case['id']:15} {record.get('segundos', 0):5.0f} s  {record.get('chamadas', 0):2} chamadas  {record.get('tela_caracteres', 0):6} car. de tela  "
                      f"{money(record.get('custo', 0))}  RAM {gb(record.get('ram', {}).get('pico_mb', 0)):>7}  agente: {record.get('agente', '—')}"
                      + (f" ({record['resultado']})" if record.get("resultado") else ""))
                for check in record["conferencias"]:
                    if check["ok"] is not True:
                        print(f"        {'?' if check['ok'] is None else 'x'} {check['nome']}" + (f" ({check['detalhe']})" if check["detalhe"] else ""))
                for error in record["erros"]:
                    print(f"        ! {error}")
                if record.get("captura"):
                    print(f"        tela final em {record['captura']} (dados reais, só no notebook)")
    except KeyboardInterrupt:
        print("Interrompida; o relatório cobre o que já rodou.")
    finally:
        adb("input", "keyevent", "KEYCODE_HOME")
        adb("settings", "put", "global", "stay_on_while_plugged_in", stay_on if stay_on.isdigit() else "0")
        if site:
            site.shutdown()
            subprocess.run(["adb", "reverse", "--remove", f"tcp:{SITE_PORT}"], capture_output=True, timeout=15)

    if records:
        base = f"reports/suite-{stamp}"
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=1)
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(render(records, stamp, options))
        count = Counter(r["status"] for r in records)
        print(f"\n{count['passou']} passaram, {count['falhou']} falharam, {count['erro']} com erro, {count['manual']} aguardando "
              f"conferência manual · {sum(r.get('segundos', 0) for r in records) / 60:.1f} min · "
              f"{money(sum(r.get('custo', 0) for r in records))}\n{base}.html")
    sys.exit(0 if records and all(r["status"] == "passou" for r in records) else 1)


if __name__ == "__main__":
    main()
