"""O caminho até o provedor e o estado de uma tarefa: mascara o que sai, desmascara o que volta, registra tudo.

O serviço (service.py) fica no ar entre tarefas e chama `begin` no começo de cada uma. O executor nasce a cada pedido;
os valores falsos e o que a IA local já julgou duram a conversa (`begin` com o mesmo id, até 10 min parada): o
assistente precisa que "ela" no pedido seguinte seja o mesmo nome falso de antes. Sem conversa, nascem a cada pedido.

O pedido é julgado uma vez pela IA local (`judge_task`), em paralelo com a subida da tarefa; nada vai ao provedor
antes disso. Nos pedidos de ajuda, a IA local julga também os trechos de tela que ainda não viu (`judge_screen`).
Se o mascaramento falhar, nada é enviado.
"""

import difflib
import http.client
import itertools
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from . import access, bridge, cache, facts, local_ai, treino
from .executor import HIDDEN, SPLIT, Executor, plain, yes_no
from .masking import Masker, Vault, passwords
from .sources import VAULT_PATH, apps, load_stoplist

UPSTREAM = "https://openrouter.ai/api/v1"
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
LOG_PATH = "logs/proxy.jsonl"
JUDGE_TIMEOUT = 60
# Quem acha o controle com outro nome (laya_server.py); o run.sh o sobe.
LAYA = f"http://127.0.0.1:{os.environ.get('LMPHONE_LAYA_PORT', '8788')}"
# O Laya filtra os trechos de tela antes da Gemma: abaixo deste valor o trecho é tido como rótulo de interface.
# O menor valor medido num trecho com pessoa foi 0,20; o corte fica abaixo para errar para o lado de julgar.
GATE = 0.15
PICK_SPLIT = 0.8  # soma dos dois primeiros do modelo de escolha que indica "o controle está aqui, mas qual dos dois?"
# O aparelho é lido dele mesmo (`device_name`): depois da One UI 9 (2026-10-22) o texto fixo ainda dizia Android 16, e o
# assistente respondia a versão por ele. Este fica só para quando o adb não responde.
DEVICE = "Samsung Galaxy S23+, Android 17, One UI 9.0. Interface language: English"
MODELS = {"SM-S916B": "Galaxy S23+"}  # nome comercial dos modelos conhecidos
LANGUAGES = {"en": "English", "pt": "Portuguese", "es": "Spanish"}
_device = None
PREFERENCES_PATH = "data/preferencias.txt"
APPS_PATH = "data/apps.json"  # a última lista de apps lida do aparelho
# Nomes que o dono e o provedor usam para apps que o aparelho chama de outro jeito: o YouTube Music aparece como "YT
# Music", e "coloca uma música no YouTube Music" não abria nada (2026-10-24). Os nomes em português são do aparelho em inglês.
APP_ALIASES = {"youtube music": "yt music", "google play": "play store", "google play store": "play store",
               "configuracoes": "settings", "ajustes": "settings", "camera": "camera", "galeria": "gallery",
               "relogio": "clock", "calculadora": "calculator", "contatos": "contacts", "telefone": "phone",
               "mensagens": "messages", "agenda": "calendar", "calendario": "calendar", "notas": "notes",
               "meus arquivos": "my files", "arquivos": "my files", "loja": "play store", "tradutor": "translate",
               "fotos": "photos"}
WEB_SEARCH = "https://www.google.com/search?q="  # a pesquisa no Google do celular (executor.SEARCH_OPTION)
READ_HIDDEN = "[valor lido no aparelho]"  # o que fica no registro e na conversa no lugar do valor de um "read"


def device_description():
    """O aparelho, como vai ao provedor, com os apps preferidos do dono: sem eles, "coloque uma música" abria o
    Spotify, e o dono usa o YouTube Music. Só nomes de apps (não é dado pessoal)."""
    try:
        with open(PREFERENCES_PATH, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except OSError:
        lines = []
    return device_name() + (". The owner's preferred apps (use them when the task does not name one): " + "; ".join(lines) if lines else "")


def device_name():
    """Modelo, versão do Android e da One UI e idioma da interface, lidos do aparelho uma vez por subida do serviço."""
    global _device
    if _device is None:
        try:
            out = subprocess.run(["adb", "shell", "getprop ro.product.model; getprop ro.build.version.release; "
                                  "getprop ro.build.version.oneui; getprop persist.sys.locale"],
                                 capture_output=True, text=True, timeout=10).stdout.split("\n")
            model, android, oneui, locale = (line.strip() for line in (out + ["", "", "", ""])[:4])
            if not model or not android:
                return DEVICE
            name = f"Samsung {MODELS.get(model, model)}, Android {android}"
            if oneui.isdigit():  # 90000 = 9.0, 85000 = 8.5
                name += f", One UI {int(oneui) // 10000}.{int(oneui) // 100 % 100 // 10}"
            _device = f"{name}. Interface language: {LANGUAGES.get(locale.split('-')[0], locale or 'English')}"
        except Exception:
            return DEVICE
    return _device

TASK, SESSION, CACHE = "", secrets.token_hex(4), True
COLLECT = False  # grava dados de treino desta tarefa (treino.py)
ASK = False  # o agente pode perguntar ao dono pela faixa do live mode (o serviço põe, por tarefa)
OWNER = False  # a tarefa começou na vez do dono (live mode, etapa 5): o app do pedido não é aberto por ele
ACTS = True  # False: só guia, como o app da loja (docs/plano-play-store.md); o agente nunca age, nem abre o app antes
CONVERSATION = None  # {"id", "turnos": [{"dono", "assistente", "feito", "resultado"}], "at"}: valores reais, só na memória
HISTORY = []  # os turnos da conversa antes do pedido em curso
CONVERSATION_TTL = 600  # segundos parada depois dos quais a conversa acaba (e os valores falsos com ela)
MAX_TURNS = 6  # turnos anteriores que vão ao provedor
DETAIL = os.environ.get("LMPHONE_DETALHE", "1") != "0"
DETAIL_DIR = "logs/detalhe"
_APP = re.compile(r"• \*\*App:\*\* .*?\(?([\w.]+)\)?$", re.M)


def new_masker():
    masker = Masker(Vault(VAULT_PATH), load_stoplist())
    masker.session.seen.add(HIDDEN)  # marca de texto escondido nos pedidos de ajuda: não é texto de tela
    return masker


masker = new_masker()
# Fica fechado até a IA local terminar de julgar o pedido (ou falhar): antes disso nada é enviado ao provedor.
# O que se resolve no aparelho (caminho do cache, pacote do app) não espera.
judged = threading.Event()
screen_lock = threading.Lock()
requests = itertools.count(1)
executor = None  # criado no primeiro passo do modo local
executor_lock = threading.Lock()
packages = {}  # nome do app -> pacote, lido do aparelho na subida (modo local)
rivals = {}  # nome que mais de um app tem -> pacotes
packages_ready = threading.Event()
packages_at = 0.0  # quando a lista de apps foi lida
began = 0.0  # quando a tarefa começou
opened = None  # app citado no pedido que o proxy abriu antes de o plano existir
collected = set()  # trechos de tela já gravados nesta tarefa (coleta)
sent = 0  # escolhas do executor já gravadas (coleta)


def begin(task, use_cache=True, collect=False, conversation=None):
    """Começa outro pedido. O executor nasce aqui. Com o id da conversa em curso (`conversation`, ainda viva), os
    valores falsos, o que a IA local já julgou e o histórico continuam; senão nascem aqui, e o cofre é relido.
    A lista de apps fica: ela vem do aparelho."""
    global TASK, SESSION, CACHE, COLLECT, masker, judged, requests, executor, opened, began, collected, sent
    global CONVERSATION, HISTORY
    with executor_lock:
        collect_choices(final=True)  # as da tarefa anterior, se ela foi interrompida
        alive = (conversation and CONVERSATION and CONVERSATION["id"] == conversation
                 and time.time() - CONVERSATION["at"] < CONVERSATION_TTL)
        if not alive:
            CONVERSATION = {"id": conversation or None, "turnos": [], "at": time.time()}
            masker = new_masker()
        HISTORY = CONVERSATION["turnos"][-MAX_TURNS:]
        TASK, SESSION, CACHE, COLLECT = task, secrets.token_hex(4), use_cache, collect
        collected, sent = set(), 0
        judged, requests = threading.Event(), itertools.count(1)
        executor, opened, began = None, None, time.time()
        for password in passwords(task):  # regra fixa: vale mesmo sem a IA local
            masker.session.protect_literal(password)


def load_packages():
    """Lê a lista de apps do Portal (cerca de 3 s); o serviço a relê quando fica velha."""
    global packages, rivals, packages_at
    started, found, same, fresh = time.monotonic(), {}, {}, True
    try:
        listed = apps()
        os.makedirs(os.path.dirname(APPS_PATH), exist_ok=True)
        with open(APPS_PATH, "w", encoding="utf-8") as f:
            json.dump(listed, f, ensure_ascii=False)
    except Exception as e:
        # Com o app do lm_phone, a lista só vem com o serviço dele ligado, e o pedido pode chegar antes (o app do
        # pedido é aberto enquanto o plano é escrito): vale a última lista lida, sem contar como lida agora.
        log({"apps": {"erro": repr(e)}})
        fresh = False
        try:
            with open(APPS_PATH, encoding="utf-8") as f:
                listed = json.load(f)
        except (OSError, ValueError):
            listed = []
    for app in listed:
        name = plain(app.get("label", ""))
        same.setdefault(name, []).append(app["packageName"])
        found[name] = None if name in found else app["packageName"]
    if found:
        packages, rivals = found, {name: pkgs for name, pkgs in same.items() if len(pkgs) > 1}
        packages_at = time.time() if fresh else packages_at
    packages_ready.set()
    log({"apps": {"seconds": round(time.monotonic() - started, 1), "total": len(packages)}})


def pick_rival(candidates):
    """Entre apps de mesmo nome ("Messages" do Google e da Samsung), o que o aparelho usa como app de SMS padrão;
    se nenhum é, o último da lista."""
    try:
        default = subprocess.run(["adb", "shell", "settings", "get", "secure", "sms_default_application"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        default = ""
    return default if default in candidates else candidates[-1]


def find_package(name):
    """O pacote do app com esse nome. O provedor costuma dizer "Google Maps" para o app que se chama "Maps" (e
    "Samsung Notes" para "Notes"): sem achar o nome inteiro, tenta sem o nome da empresa na frente, pelos apelidos de
    APP_ALIASES, sem espaços ("sofa score") e, por fim, pelo nome mais parecido (uma letra trocada)."""
    wanted = plain(name)
    short = re.sub(r"^(google|samsung|galaxy|microsoft)\s+", "", wanted)
    for candidate in dict.fromkeys([wanted, short, APP_ALIASES.get(wanted), APP_ALIASES.get(short)]):
        if not candidate:
            continue
        package = packages.get(candidate) or (pick_rival(rivals[candidate]) if candidate in rivals else None)
        if package:
            return package
    squeezed = {re.sub(r"\W", "", label): label for label in packages}
    label = squeezed.get(re.sub(r"\W", "", wanted))
    close = difflib.get_close_matches(wanted, list(packages), n=1, cutoff=0.85) if not label and len(wanted) >= 5 else []
    label = label or (close[0] if close else None)
    if label:
        return packages.get(label) or (pick_rival(rivals[label]) if label in rivals else None)
    return None


def web_search(query):
    """Abre no Chrome do celular a pesquisa do Google por `query` (escrita pelo provedor, com valores falsos: no
    aparelho vai a real, como numa digitação). False se não abriu."""
    real = masker.unmask(str(query)).strip()
    if not real:
        return False
    url = WEB_SEARCH + urllib.parse.quote_plus(real)
    try:
        result = subprocess.run(["adb", "shell", f"am start -W -a android.intent.action.VIEW -d '{url}' -p com.android.chrome"],
                                capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    log({"pesquisa": {"ok": result.returncode == 0 and "Error" not in result.stdout + result.stderr}})
    return result.returncode == 0 and "Error" not in result.stdout + result.stderr


# As páginas de `executor.SETTINGS_PAGES` e o atalho do Android que abre cada uma (conferidos no S23+, One UI 9:
# o do modo escuro e o do filtro de luz azul caem na tela de Tela, onde eles ficam).
SETTINGS = {"wifi": "android.settings.WIFI_SETTINGS", "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
            "airplane_mode": "android.settings.AIRPLANE_MODE_SETTINGS", "connections": "android.settings.WIRELESS_SETTINGS",
            "nfc": "android.settings.NFC_SETTINGS", "data_usage": "android.settings.DATA_USAGE_SETTINGS",
            "display": "android.settings.DISPLAY_SETTINGS", "dark_mode": "android.settings.DISPLAY_SETTINGS",
            "eye_comfort": "android.settings.DISPLAY_SETTINGS", "sound": "android.settings.SOUND_SETTINGS",
            "do_not_disturb": "android.settings.ZEN_MODE_SETTINGS", "location": "android.settings.LOCATION_SOURCE_SETTINGS",
            "battery": "android.intent.action.POWER_USAGE_SUMMARY", "apps": "android.settings.APPLICATION_SETTINGS",
            "accessibility": "android.settings.ACCESSIBILITY_SETTINGS", "date_time": "android.settings.DATE_SETTINGS",
            "security": "android.settings.SECURITY_SETTINGS", "about_phone": "android.settings.DEVICE_INFO_SETTINGS"}


# Os ajustes de `executor.DIRECT` e os comandos que os ligam e desligam (os mesmos que a suíte usa para preparar e
# desfazer; na One UI 9 o de modo escuro deixa "Dark" marcado na tela de Tela).
DIRECT = {"dark_mode": ("cmd uimode night yes", "cmd uimode night no"),
          "airplane_mode": ("cmd connectivity airplane-mode enable", "cmd connectivity airplane-mode disable"),
          "wifi": ("cmd wifi set-wifi-enabled enabled", "cmd wifi set-wifi-enabled disabled"),
          "bluetooth": ("cmd bluetooth_manager enable", "cmd bluetooth_manager disable"),
          "do_not_disturb": ("cmd notification set_dnd on", "cmd notification set_dnd off"),
          "location": ("cmd location set-location-enabled true", "cmd location set-location-enabled false")}
# Com o celular ligado ao PC pela rede (depuração sem fio), estes cortariam a ligação no meio da tarefa.
CUTS_LINK = {("wifi", False), ("airplane_mode", True)}
NO_CUT = ("O celular está ligado ao PC pelo Wi-Fi: desligar o Wi-Fi ou ligar o modo avião cortaria a ligação. "
          "Faça isso no celular, ou ligue o cabo e me peça de novo.")


# Os níveis (docs/plano-tutor.md): o volume pelo fluxo de som (3: mídia, 2: toque) e o brilho, de 0 a 100 %.
STREAMS = {"media_volume": 3, "ring_volume": 2}


def set_level(name, value):
    """Põe um nível (facts.LEVELS) em `value` por cento, pelo sistema. False se o comando falhou."""
    percent = max(0, min(100, round(float(value))))
    try:
        if name in STREAMS:
            out = subprocess.run(["adb", "shell", f"cmd media_session volume --stream {STREAMS[name]} --get"],
                                 capture_output=True, text=True, timeout=15).stdout
            found = re.search(r"in range \[(\d+)\.\.(\d+)\]", out)
            if not found:
                return False
            low, high = int(found.group(1)), int(found.group(2))
            command = f"cmd media_session volume --stream {STREAMS[name]} --set {low + round(percent * (high - low) / 100)}"
        else:  # o brilho fixo: o automático o mudaria de novo
            command = (f"settings put system screen_brightness_mode 0; settings put system screen_brightness "
                       f"{round(percent * facts.BRIGHTNESS_MAX / 100)}")
        result = subprocess.run(["adb", "shell", command], capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    log({"ajuste_direto": {"ajuste": name, "valor": percent, "ok": result.returncode == 0}})
    return result.returncode == 0


def set_direct(name, value):
    """Liga (`value`) ou desliga um ajuste de DIRECT pelo sistema; um nível vai a `value` por cento. False se o ajuste
    não existe ou o comando falhou; a mensagem ao dono (NO_CUT) se a mudança cortaria a ligação com o PC."""
    name = str(name).strip().lower()
    if name in facts.LEVELS:
        return set_level(name, value)
    commands = DIRECT.get(name)
    if not commands:
        return False
    if (name, bool(value)) in CUTS_LINK and bridge.wireless():
        log({"ajuste_direto": {"ajuste": name, "valor": bool(value), "recusado": "ligação sem fio"}})
        return NO_CUT
    try:
        result = subprocess.run(["adb", "shell", commands[0 if value else 1]], capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    log({"ajuste_direto": {"ajuste": name, "valor": bool(value), "ok": result.returncode == 0}})
    return result.returncode == 0


def open_settings(page):
    """Abre uma página das Configurações pelo atalho do Android. False se a página não existe ou não abriu."""
    action = SETTINGS.get(str(page).strip().lower().replace(" ", "_"))
    if not action:
        return False
    try:
        result = subprocess.run(["adb", "shell", "am", "start", "-W", "-a", action], capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    return result.returncode == 0 and "Error" not in result.stdout + result.stderr


def button(offer):
    """O botão da faixa no só guia (`executor.button`), com o que o app abre quando a pessoa o toca: a ação do Android
    da página das Configurações, ou o pacote do app. None se não há o que abrir."""
    if not offer:
        return None
    if offer.get("open_settings") is not None:
        action = SETTINGS.get(str(offer["open_settings"]).strip().lower().replace(" ", "_"))
        return {"texto": offer["text"], "acao": action} if action else None
    packages_ready.wait(10)
    package = find_package(str(offer.get("open_app") or ""))
    return {"texto": offer["text"], "pacote": package} if package else None


def launch(name):
    """Abre o app pelo pacote. False se nenhum app tem esse nome."""
    packages_ready.wait(10)
    package = find_package(name)
    if not package and packages_at < began:
        # A lista é de antes da tarefa: o app pode ter sido instalado depois.
        load_packages()
        package = find_package(name)
    if not package:
        return False
    if access.is_bank(package):
        # Com a acessibilidade do Portal ligada, o app do banco bloqueia o aparelho (ver access.py).
        log({"banco": "abertura recusada"})
        return False
    try:
        result = subprocess.run(["adb", "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
                                capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    return result.returncode == 0 and "No activities found" not in result.stdout + result.stderr


def judge_task():
    """Julga o pedido da tarefa e aplica as decisões à sessão. Se a IA local falhar, valem só as regras fixas."""
    # A tarefa em que este julgamento começou: se ele terminar depois de outra tarefa ter começado
    # (a anterior foi interrompida), o resultado não pode cair na sessão nova.
    task, session, mine, done, collect = TASK, SESSION, masker, judged, COLLECT
    judgment = None
    try:
        if task:
            judgment, _, seconds = local_ai.judge_request(task, JUDGE_TIMEOUT)
            if session != SESSION:
                return
            decisions = local_ai.apply_request(judgment, mine, task)
            detail(session, "pedido", texto=task, julgamento=judgment, decisoes=decisions, segundos=round(seconds, 2))
            # Só contagens: os textos das entidades são dados reais.
            log({"local_ai": {"intencao": judgment["intencao"], "seconds": round(seconds, 1),
                              "decisoes": Counter(d["decisao"] for d in decisions)}})
            prelaunch(judgment)
    except Exception as e:
        if session == SESSION:
            log({"local_ai": {"erro": repr(e)}})
    finally:
        done.set()
        if collect and task:
            treino.record(session, "pedido", texto=task, gemma=judgment)
    try:
        if session == SESSION:
            log({"task": mine.mask(task)})
    except Exception:
        pass


def prelaunch(judgment):
    """Se o pedido cita um único app, abre-o já, enquanto o plano é pedido.
    Se o plano começar por outro app, ele é aberto normalmente; o custo do erro é um app aberto à toa."""
    global opened
    names = [e["texto"] for e in judgment.get("entidades", []) if e["tipo"] == "app"]
    started = time.monotonic()
    # Uma tarefa do cache pode já estar andando sem ter esperado o julgamento: aí não se abre mais nada. Na vez do
    # dono, abrir o app é o primeiro passo dele.
    if OWNER or not ACTS or len(names) != 1 or not executor_lock.acquire(blocking=False):
        return
    try:
        if executor is None and launch(names[0]):
            opened = names[0]
            log({"abriu_antes": {"seconds": round(time.monotonic() - started, 1)}})
    finally:
        executor_lock.release()


def judge_screen(messages):
    """Julga com a IA local só os trechos de tela que ela ainda não viu nesta tarefa.

    Um bloco que falha não entra em `seen`: vale só a regra fixa agora e ele é tentado de novo no próximo passo.
    """
    texts = []
    masker.walk(messages, texts.append)
    with screen_lock:
        seen = masker.session.seen
        new = [f for f in dict.fromkeys(f for text in texts for f in local_ai.screen_fragments(text)) if f not in seen]
        if not new:
            return
        entry = {"trechos": len(new), "seconds": 0.0, "mascarar": 0}
        judgment = {"trechos": new, "laya": None, "gemma": []}
        try:
            answer = laya("/private", {"fragments": new})
            judgment["laya"] = answer["p"]
            dropped = [f for f, p in zip(new, answer["p"]) if p < GATE]
            seen.update(dropped)
            new = [f for f in new if f not in seen]
            entry.update(filtrados=len(dropped), laya_seconds=answer["seconds"])
        except Exception as e:
            # Sem o filtro, a Gemma julga tudo.
            entry["erro_laya"] = repr(e)
        for batch in local_ai.batches(new):
            source = " • ".join(batch)
            try:
                found, _, seconds = local_ai.find_private(source, JUDGE_TIMEOUT)
                judgment["gemma"].append({"trechos": batch, "achou": found})
                applied = local_ai.apply_screen(found, masker, source)
                judgment["gemma"][-1]["mascarados"] = applied
                entry["mascarar"] += len(applied)
                entry["seconds"] = round(entry["seconds"] + seconds, 1)
                seen.update(batch)
            except Exception as e:
                entry["erro"] = repr(e)
        # Só contagens: os trechos são texto real da tela.
        log({"local_ai_tela": entry})
        detail(SESSION, "tela", **entry, julgamento=judgment)
        if COLLECT:
            treino.record(SESSION, "julgamento", **judgment)


def laya(path, body):
    request = urllib.request.Request(LAYA + path, data=json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=JUDGE_TIMEOUT) as response:
        return json.load(response)


def log(entry):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": round(time.time(), 3), "session": SESSION, **entry}, ensure_ascii=False) + "\n")


def detail(session, kind, **fields):
    """O que os modelos locais geraram, com os valores reais, para o painel (lmphone/painel.py). Fica só na máquina
    (logs/detalhe/<sessão>.jsonl, modo 600); LMPHONE_DETALHE=0 desliga."""
    if not DETAIL:
        return
    try:
        os.makedirs(DETAIL_DIR, mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(DETAIL_DIR, session + ".jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "tipo": kind, **fields}, ensure_ascii=False, default=list) + "\n")
    except OSError:
        pass


def upstream(path, method, body=None):
    """Um pedido ao provedor. A chave só existe no processo do serviço."""
    request = urllib.request.Request(
        UPSTREAM + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, http.client.RemoteDisconnected, ConnectionError):
            # Conexão caída antes da resposta (visto com o OpenRouter): tenta mais uma vez.
            if attempt:
                raise
            time.sleep(1)


def ask_provider(model, prompt, reasoning=True):
    """Uma pergunta ao provedor (plano ou ajuda): mascara, envia, registra e desmascara."""
    number, arrived = next(requests), round(time.time(), 3)
    # As instruções fixas (antes de SPLIT) vão como mensagem de sistema com marca de cache: elas se repetem iguais em
    # todo pedido, e o provedor as lê do cache (no orquestrador, 2026-10-21, 74% da entrada veio de lá).
    fixed, split, situation = prompt.partition(SPLIT)
    parts = [fixed, situation] if split else [prompt]
    judged.wait()
    judge_screen([{"content": part} for part in parts])
    counts = {}
    # As instruções fixas passam só pelo cofre e pelas regras de sempre: as regras de nome (`Masker.learn`) trocariam
    # uma palavra delas a cada sessão, e o provedor deixaria de ler essa parte do cache.
    parts = [masker.mask(part, counts, learn=not (split and i == 0)) for i, part in enumerate(parts)]
    messages = ([{"role": "system", "content": [{"type": "text", "text": parts[0], "cache_control": {"type": "ephemeral"}}]},
                 {"role": "user", "content": parts[1]}] if split else [{"role": "user", "content": parts[0]}])
    log({"request": number, "arrived": arrived, "model": model, "messages": len(messages), "masked": counts, "sent": messages})
    started = time.monotonic()
    body = {"model": model, "messages": messages}
    if not reasoning:
        body["reasoning"] = {"enabled": False}
    status, data = upstream("/chat/completions", "POST", body)
    answered = {"request": number, "status": status, "seconds": round(time.monotonic() - started, 1)}
    if status != 200:
        log({**answered, "received": data.decode(errors="replace")[:2000]})
        raise RuntimeError(f"o provedor respondeu {status}")
    answer = json.loads(data)
    log({**answered, "usage": answer.get("usage"), "received": [c.get("message") for c in answer.get("choices", [])]})
    return masker.unmask(answer["choices"][0]["message"]["content"])


def cached_path():
    # No meio de uma conversa o pedido depende do que veio antes ("desliga de novo"): o cache não vale.
    return CACHE and ACTS and not HISTORY and masker.mask(TASK) == TASK and cache.load(TASK) is not None


def history_text():
    """Os turnos anteriores da conversa, para o provedor (com valores reais: `ask_provider` mascara tudo)."""
    lines = []
    for turn in HISTORY:
        lines.append(f"Owner: {turn['dono']}")
        lines.append(f"You: {turn['assistente']}")
        if turn["feito"]:
            lines.append(f"  (on the phone: {'; '.join(turn['feito'])}; result: {turn['resultado']})")
    return "\n" + "\n".join(lines) if lines else ""


def remember_turn(message, result):
    """Guarda o pedido em curso e a resposta na conversa. O que foi feito vai resumido, sem as telas."""
    done = []
    for step in executor.trail if executor else []:
        target = (step.get("target") or [""])[0]
        done.append(" ".join(part for part in (step["action"], f"“{target}”" if target else "",
                                               f"text “{step['text']}”" if step.get("text") else "") if part))
    CONVERSATION["turnos"].append({"dono": TASK, "assistente": message, "feito": done[-12:], "resultado": result})
    CONVERSATION["at"] = time.time()


def make_executor(model):
    """Cria o executor da tarefa, se ainda não existe, e lhe dá o caminho ao provedor. Chamar com `executor_lock`."""
    global executor
    if executor is None:
        executor = Executor(TASK, None, None, device_description(), launch, opened, facts=read_facts, history=history_text(),
                            settings=open_settings)
        executor.assistant = True
        executor.acts = ACTS
        executor.setter = set_direct
        executor.searcher = web_search
        executor.can_ask = ASK and access.USE_APP  # perguntas ao dono só com a faixa do live mode
        executor.may_ask = ASK  # sem ninguém para responder (a suíte), o turno não oferece a pergunta
        if HISTORY and HISTORY[-1].get("resultado") == "a confirmar" and yes_no(TASK):
            # O pedido anterior parou para o dono confirmar um toque que não se desfaz, e ele disse que sim.
            executor.preapproved = True
        saved = cache.load(TASK) if cached_path() else None
        executor.cached = saved is not None
        if saved:
            executor.use(*saved)
        executor.map = cache.maps() if CACHE else {}
        if executor.cached:
            log({"cache": {"usado": True, "passos": len(executor.plan)}})
    # O plano é escrito sem raciocínio (2 a 3 s em vez de 5 a 7, planos equivalentes); os pedidos de ajuda, com.
    executor.provider = lambda prompt: ask_provider(model, prompt, reasoning=executor.plan is not None and not executor.quick)


def instruct(text):
    """Uma instrução escrita pelo dono na faixa do live mode, no meio da tarefa. É julgada como o pedido (o que ela
    traz de pessoal passa a ser mascarado) e vai para o executor, que pede ao provedor o resto do plano com ela."""
    for password in passwords(text):
        masker.session.protect_literal(password)
    try:
        judgment, _, seconds = local_ai.judge_request(text, JUDGE_TIMEOUT)
        decisions = local_ai.apply_request(judgment, masker, text)
        detail(SESSION, "instrucao", texto=text, julgamento=judgment, decisoes=decisions, segundos=round(seconds, 2))
    except Exception as e:
        log({"local_ai": {"erro_instrucao": repr(e)}})
    with executor_lock:
        if executor is not None:
            executor.instructions.append(text)
    log({"instrucao": {"texto": masker.mask(text)}})


def answered(question, answer, secret):
    """A resposta do dono a uma pergunta do agente (live mode). Uma senha ou código fica protegida como valor literal
    (vai mascarada ao provedor e só volta ao real na digitação no aparelho); o resto é julgado como o pedido."""
    if secret:
        masker.session.protect_literal(answer)
        detail(SESSION, "resposta", pergunta=question, resposta="[segredo]")
    else:
        for password in passwords(answer):
            masker.session.protect_literal(password)
        try:
            judgment, _, seconds = local_ai.judge_request(answer, JUDGE_TIMEOUT)
            decisions = local_ai.apply_request(judgment, masker, answer)
            detail(SESSION, "resposta", pergunta=question, resposta=answer, julgamento=judgment, decisoes=decisions)
        except Exception as e:
            log({"local_ai": {"erro_resposta": repr(e)}})
    with executor_lock:
        if executor is not None:
            executor.answers.append((question, answer))
    # A pergunta chega com os valores reais (`ask_provider` os devolve): o registro só leva texto mascarado.
    log({"resposta": {"pergunta": masker.mask(question), "texto": masker.mask(answer)}})


def confirmed(question, answer):
    """A resposta do dono à confirmação de um toque que não se desfaz (live mode). Sim libera o toque, não encerra;
    outra coisa vale como a resposta a uma pergunta (julgada e levada ao provedor). Devolve True, False ou None."""
    with executor_lock:
        verdict = executor.confirm_answer(answer) if executor is not None else None
    detail(SESSION, "confirmacao", pergunta=question, resposta=answer, liberou=verdict)
    log({"confirmacao": {"pergunta": masker.mask(question), "resposta": masker.mask(answer), "liberou": verdict}})
    if verdict is None:
        answered(question, answer, False)
    return verdict


def stopped_by_user(why):
    """O dono interrompeu a tarefa pela faixa: registrada como as outras, sem ensinar o cache."""
    with executor_lock:
        if executor is not None:
            executor.result = "interrompida"
        remember_turn("(o dono interrompeu)", "interrompida")
        collect_choices(final=True)
    log({"exec": {"por": "usuário", "decisao": f"Tarefa interrompida pelo usuário ({why}).", "acao": "", "resultado": "interrompida"},
         "arrived": round(time.time(), 3)})


def read_facts():
    """O estado do aparelho (facts.py), com o nome do app no lugar do pacote do que está tocando."""
    names = {package: name for name, package in packages.items() if package}
    state = facts.read(lambda package: names.get(package, package))
    detail(SESSION, "estado", estado=state)
    return state


def plan_ahead(model):
    """Pede o plano antes de a tela ser lida (ele não depende dela). A leitura sai em décimos de segundo: sem isto,
    o primeiro passo seria decidido numa tela lida antes de o plano chegar e de o app do pedido abrir."""
    if executor is None and not cached_path():
        judged.wait()
    with executor_lock:
        make_executor(model)
        executor.prepare()


def local_step(message, model, arrived):
    """A próxima ação para a tela em `message`: explicação e chamada de ferramenta, em texto."""
    # Com o caminho no cache, o provedor não é chamado e a execução começa sem esperar o julgamento;
    # se um passo falhar, o pedido de ajuda espera em `ask_provider`. Sem cache, espera aqui, para o
    # app aberto antes do plano (`opened`) já estar decidido.
    if executor is None and not cached_path():
        judged.wait()
    with executor_lock:
        seconds, picks = [0.0], []

        def pick(wanted, labels):
            answer = laya("/pick", {"wanted": wanted, "labels": labels})
            label = answer["label"]
            seconds[0] += answer["seconds"]
            detail(SESSION, "escolha_ia", pedido=wanted, rotulos=labels, resposta=answer)
            picks.append(label is not None)
            # Sem um rótulo acima do corte, mas com os dois primeiros juntos acima dele: o controle está na tela e o
            # modelo ficou dividido. O executor pede ajuda nesta tela em vez de rolar (executor.ask).
            ranked = [(l, p) for l, p in answer.get("ranking") or [] if l is not None]
            if label is None and len(ranked) >= 2 and ranked[0][1] + ranked[1][1] >= PICK_SPLIT:
                return ("dividido", (ranked[0][0], ranked[1][0]))
            return label

        make_executor(model)
        executor.pick = pick
        app = _APP.search(message)
        executor.app = app.group(1) if app else None  # o app da tela, para a coleta
        try:
            why, tool = executor.step(message)
        except Exception as e:
            why, tool = f"O executor falhou: {e!r}", (
                '<function_calls>\n<invoke name="complete">\n<parameter name="success">false</parameter>\n'
                '<parameter name="message">O executor falhou; veja logs/proxy.jsonl.</parameter>\n</invoke>\n</function_calls>')
        if 'name="complete"' in tool and CACHE:
            remember()
        # O valor de um "read" (um código, um preço) fica só no aparelho: nem o registro nem a conversa, que vai ao
        # provedor no pedido seguinte, o levam (em 2026-10-24 um código de verificação estava no proxy.jsonl).
        public =(lambda text: text.replace(executor.read_value, READ_HIDDEN)) if executor.read_value else (lambda text: text)
        if 'name="complete"' in tool:
            remember_turn(public(executor.final or ""), executor.result)
            session = masker.session
            detail(SESSION, "fim", resultado=executor.result, ajudas=executor.helps, escolhas=executor.choices,
                   trocas={kind: pairs for kind, pairs in session.forward.items() if pairs},
                   nomes_extra=sorted(session.extra_names), usuarios_extra=sorted(session.extra_literals),
                   liberados=sorted(session.released))
        if COLLECT:
            collect_screen(message, executor.app)
            collect_choices(final='name="complete"' in tool)
            if 'name="complete"' in tool:
                treino.record(SESSION, "fim", resultado=executor.result, ajudas=executor.helps)
        # Só texto mascarado no log: a explicação cita rótulos da tela.
        log({"exec": {"por": executor.by, "passo": executor.i, "de": len(executor.plan or []), "ajudas": executor.helps,
                      "ia_seconds": round(seconds[0], 2),
                      "ia": "laya" if picks else None, "ia_achou": any(picks), "decisao": masker.mask(public(why)),
                      "acao": masker.mask(public(tool)),
                      # O aparelho não conseguiu fazer a ação anterior (o texto pode citar a tela).
                      **({"erro_ferramenta": masker.mask(executor.tool_error)} if executor.tool_error else {}),
                      # Só no fim: "confirmado" quando a tela mostrou o objetivo da tarefa.
                      **({"resultado": executor.result} if 'name="complete"' in tool else {})},
             "arrived": arrived})
    return f"{why}\n\n{tool}"


def collect_screen(message, app):
    """Grava os trechos da tela que esta tarefa ainda não gravou, com o app em primeiro plano."""
    for fragment in local_ai.screen_fragments(message):
        if fragment not in collected:
            collected.add(fragment)
            treino.record(SESSION, "trecho", app=app, texto=fragment)


def collect_choices(final=False):
    """Grava as escolhas de controle cujo efeito já foi conferido; no fim da tarefa, todas. Chamar com `executor_lock`."""
    global sent
    if not COLLECT or executor is None:
        return
    for choice in executor.choices[sent:]:
        if choice["efeito"] is None and not final:
            break
        treino.record(SESSION, "escolha", **choice)
        sent += 1


def remember():
    """Fim da tarefa: guarda o caminho executado, ou conta a falha de um caminho que veio do cache.
    Só aprende de tarefa cujo objetivo a tela confirmou: o que o plano ou o provedor declaram não basta."""
    try:
        # Nada que o mascaramento trocaria entra no cache nem no mapa: eles guardam só rótulos de interface.
        texts = [t for step in executor.trail for t in step.get("target") or []]
        texts += [str(t) for labels in (executor.goal or {}).values() for t in (labels.values() if isinstance(labels, dict) else labels)]
        clean = all(masker.mask(t) == t for t in texts)
        if executor.result in ("confirmado", "já estava") and clean and executor.trail:
            # O mapa aprende também com os guias (os toques da pessoa) e no só guia: os nomes das telas são os do aparelho.
            cache.learn(executor.trail, keep=lambda label: masker.mask(label) == label)
        if executor.result in ("confirmado", "já estava") and executor.cacheable and clean and executor.trail and ACTS:
            # Uma repetição sem desvios não regrava o caminho: ela pode ter achado tudo já feito.
            replay = executor.cached and not executor.helps
            # Chave que já estava certa sem nenhum toque: pode ser a chave errada; o pedido não fica gravado.
            if executor.result == "já estava" and not executor.cached:
                log({"cache": {"gravado": False, "passos": len(executor.trail)}})
            elif masker.mask(TASK) == TASK and not replay and not HISTORY:
                cache.save(TASK, executor.trail, executor.goal)
                log({"cache": {"gravado": True, "passos": len(executor.trail)}})
            elif replay:
                cache.worked(TASK)
        elif executor.cached:
            log({"cache": {"falhou": True, "apagado": cache.failed(TASK)}})
    except Exception as e:
        log({"cache": {"erro": repr(e)}})
