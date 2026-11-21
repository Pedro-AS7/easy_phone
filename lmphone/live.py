"""O live mode do lado do cérebro (docs/plano-live-mode.md), com o app do lm_phone (LMPHONE_DEVICE=app).

A faixa flutuante do app mostra o que o agente está fazendo e recebe do usuário: pausar, interromper, uma instrução
escrita, e os toques que ele dá na tela durante a tarefa. Antes de cada ação o serviço chama `gate`: ele pede ao app
o que o usuário fez (`/events`), espera enquanto está pausado ou o usuário escreve ou toca, e devolve as instruções
novas; `show` muda o texto da faixa.

Etapa 5 (docs/plano-assistente.md): a faixa também narra (o "say" e, no guia, a explicação de cada passo, lidos em
voz alta pelo app), destaca o controle em que o agente vai tocar, e passa a vez ao dono: com "✋" na faixa, ou escrevendo
"deixa que eu faço", o agente para de agir, mostra cada passo ao dono e espera ele fazer (executor.owner_turn); "🤖" ou
"faz você" devolve a vez. Esses dois comandos ficam aqui: não vão ao provedor.

Live mode contínuo (2026-10-24): o dono liga pela faixa ou pelo painel, o microfone do app fica aberto e cada fala é um
pedido novo da mesma conversa, até ele dizer "finalizar" ou tocar no X. Uma fala no meio de um pedido vira o pedido
seguinte: o app manda "novo_pedido", e `gate` encerra o pedido em curso (`Stopped(NEW_REQUEST)`). Entre os pedidos o
serviço deixa a acessibilidade ligada (service.CONTINUOUS); o app se desliga sozinho se um app de banco vier para a
frente (a lista vai em `start`).

Tudo vai para logs/live/<sessão>.jsonl (modo 600, valores reais, só na máquina): o pedido, cada status mostrado, cada
ação do agente, cada evento do usuário e o fim. É para analisar os erros do agente e treinar os modelos; não vai ao
provedor nem ao proxy.jsonl.
"""

import json
import os
import re
import threading
import time
import uuid

from . import access

LIVE_DIR = "logs/live"
POLL = 0.5  # segundos entre pedidos ao app enquanto espera (pausa, usuário escrevendo ou tocando)
PAUSE_LIMIT = 600  # pausa mais longa que isto encerra a tarefa
TYPING_LIMIT = 180  # o usuário escrevendo na faixa
ASK_LIMIT = 300  # espera pela resposta a uma pergunta do agente
USER_QUIET = 1.5  # depois de um toque do usuário, o agente espera a tela ficar este tempo sem toques dele
AGENT_WINDOW_MS = 1500  # toque até este tempo depois de um gesto do agente pode ser efeito do gesto (duvidoso)
THINKING_AFTER = 0.8  # decisão mais longa que isto (o provedor pensando) mostra "Pensando…"
# O dono pede a vez, ou a devolve, escrevendo na faixa.
OWNER_ON = re.compile(r"\b(deixa que eu fa[cç]o|eu fa[cç]o|deixa comigo|pode deixar que eu)\b", re.I)
OWNER_OFF = re.compile(r"\b(faz voc[eê]|pode fazer|continua voc[eê]|faz pra mim|faz para mim)\b", re.I)

NEW_REQUEST = "novo pedido"  # o motivo de `Stopped` quando, no modo contínuo, o dono já pediu outra coisa


class Stopped(Exception):
    """O usuário interrompeu a tarefa (ou a pausa passou do limite)."""


class Live:
    def __init__(self, device, session):
        self.device, self.session = device, session
        self.lock = threading.Lock()
        self.last_status = None
        self.owner = False  # a vez é do dono: o agente mostra os passos e espera (executor.owner)
        self.speaking = False  # o app ainda está lendo algo em voz alta (o prazo do dono no guia espera)
        self.continuous = False  # o dono ligou o modo contínuo na faixa durante este pedido
        self.touched_at = 0.0  # quando o dono tocou na tela pela última vez (time.monotonic); o guia conta o passo dele por isso
        self.guide_agent = False  # opção do app: no guia, o agente toca (depois de um prazo) em vez de esperar a pessoa
        self.guiding = False  # a faixa sabe que o pedido é um guia (o toque da pessoa não pausa)
        self.pressed_at = None  # quando a pessoa tocou no botão da faixa
        self.touched_text = None  # o texto do último controle em que ela tocou no app de baixo
        self.touched_text_at = None
        self.touched_box = None  # os limites desse controle

    def record(self, kind, **fields):
        try:
            os.makedirs(LIVE_DIR, mode=0o700, exist_ok=True)
            fd = os.open(os.path.join(LIVE_DIR, self.session + ".jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(time.time(), 3), "tipo": kind, **fields}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _send(self, path, body=None):
        with self.lock:
            return self.device.request(path, body, timeout=5)

    def start(self, task, continuous=False, guide=False):
        """O começo do pedido: a faixa zera pausa e interrupção (no modo contínuo ela fica de um pedido para o outro),
        recebe o teclado do dono e a lista dos apps de banco. `guide`: o pedido é um guia ("como eu faço..."), e um
        toque da pessoa na tela não pausa a tarefa."""
        self.record("pedido", texto=task, **({"continuo": True} if continuous else {}))
        self.continuous = continuous
        self.guiding = guide
        try:
            keyboard = access.previous_keyboard()
        except Exception:
            keyboard = None
        try:
            self._send("/live", {"status": "Entendendo o pedido…", "nova_tarefa": True, "guia": guide,
                                 "bancos": sorted(access.banks()),
                                 **({"teclado": keyboard} if keyboard else {}), **({"continuo": True} if continuous else {})})
        except Exception as e:
            self.record("erro", onde="start", erro=repr(e))

    def show(self, text, speak=False, open=False):
        """Muda o texto da faixa; com `speak`, o app também o lê em voz alta (se o dono deixou a voz ligada); com
        `open`, a faixa minimizada abre (o guia e a vez do dono: o dono lê o que fazer)."""
        if text == self.last_status and not speak:
            return
        self.last_status = text
        self.record("fala" if speak else "status", texto=text)
        try:
            self._send("/live", {"status": text, **({"fala": text} if speak else {}), **({"abrir": True} if open else {})})
        except Exception as e:
            self.record("erro", onde="show", erro=repr(e))

    def highlight(self, bounds, owner=False):
        """Destaca na tela o controle de limites (x1, y1, x2, y2); None tira o destaque. `owner`: é o dono quem deve
        tocar nele (a vez do dono, ou o prazo dele no guia); o toque dele ali não pausa a tarefa."""
        self.record("destaque", limites=list(bounds) if bounds else None, **({"dono": True} if bounds and owner else {}))
        try:
            self._send("/live", {"destaque": list(bounds) if bounds else None, "destaque_dono": bool(bounds and owner)})
        except Exception as e:
            self.record("erro", onde="highlight", erro=repr(e))

    def button(self, offer):
        """O botão que a pessoa toca na faixa para abrir algo (só guia): {"texto", "acao" | "pacote"}; None o tira."""
        self.record("botao", **({"texto": offer["texto"]} if offer else {"texto": None}))
        try:
            self._send("/live", {"botao": offer})
        except Exception as e:
            self.record("erro", onde="botao", erro=repr(e))

    def reroute(self, on):
        """A pessoa saiu do caminho e o agente está achando a volta: a faixa mostra "recalculando" até a instrução nova."""
        self.record("recalculando", ligado=on)
        try:
            self._send("/live", {"recalculando": on})
        except Exception as e:
            self.record("erro", onde="recalculando", erro=repr(e))

    def guide(self, on):
        """O pedido virou guia (ou deixou de ser): no guia em que a pessoa toca, o toque dela na tela não pausa."""
        self.guiding = on
        self.record("guia", ligado=on)
        try:
            self._send("/live", {"guia": on})
        except Exception as e:
            self.record("erro", onde="guia", erro=repr(e))

    def gesture(self, kind):
        """Mostra animado o gesto que o dono deve fazer ("puxar": o painel rápido, do alto da tela; "rolar"); None tira."""
        self.record("gesto", gesto=kind)
        try:
            self._send("/live", {"gesto": kind})
        except Exception as e:
            self.record("erro", onde="gesto", erro=repr(e))

    def set_owner(self, owner):
        """Passa a vez ao dono (True) ou ao agente; a faixa mostra o botão do jeito certo."""
        self.owner = owner
        self.record("vez", dono=owner)
        try:
            self._send("/live", {"vez": "dono" if owner else "agente", "status": "Sua vez: eu acompanho." if owner else "Deixa comigo."})
        except Exception as e:
            self.record("erro", onde="vez", erro=repr(e))

    def thinking(self):
        """Um temporizador: se a decisão demorar (o provedor pensando), a faixa diz isso. Chamar .cancel() no fim."""
        timer = threading.Timer(THINKING_AFTER, self.show, args=("Pensando…",))
        timer.daemon = True
        timer.start()
        return timer

    def poll(self):
        try:
            state = self._send("/events")
        except Exception as e:
            self.record("erro", onde="events", erro=repr(e))
            return {"paused": False, "stopped": False, "typing": False, "events": []}
        for event in state.get("events") or []:
            kind = event.get("tipo", "?")
            if kind in ("toque", "toque_longo"):
                event["duvidoso"] = event.get("ms_desde_agente", AGENT_WINDOW_MS) < AGENT_WINDOW_MS
            # A hora do toque, não a da leitura: o aviso do toque do passo anterior chegava depois de o passo novo
            # aparecer e contava para ele (2026-11-18: "Esse foi o «Volume»" sem toque novo nenhum).
            when = event_time(state, event)
            if kind == "toque_tela" or kind in ("toque", "toque_longo") and not event["duvidoso"]:
                self.touched_at = max(self.touched_at or 0.0, when)
            if kind in ("toque", "toque_longo") and not event["duvidoso"] and event.get("texto"):
                self.touched_text, self.touched_text_at = str(event["texto"]), when
                self.touched_box = event.get("limites")
            if kind == "botao_tocado":
                self.pressed_at = when  # o botão da faixa (só guia): abrir o app ou a página
            fields = {k: v for k, v in event.items() if k != "tipo"}
            if fields.get("segredo"):
                fields["texto"] = "[segredo]"  # a senha ou o código não vai para o registro
            self.record("usuario_" + kind, **fields)
        if "dono" in state:
            self.owner = bool(state["dono"])  # o botão da faixa vale na hora, no app
        self.speaking = bool(state.get("falando"))
        self.guide_agent = state.get("guia") == "agente"
        if any(event.get("tipo") == "continuo" for event in state.get("events") or []):
            self.continuous = True
        return state

    def ask(self, question, options, secret):
        """Mostra na faixa a pergunta do agente e espera a resposta (um botão ou o campo). Devolve o texto da resposta.
        Levanta `Stopped` se o usuário interromper ou não responder a tempo."""
        qid = uuid.uuid4().hex[:8]
        self.record("pergunta", id=qid, texto=question, opcoes=options, segredo=secret)
        self._send("/live", {"pergunta": {"id": qid, "texto": question, "opcoes": options, "segredo": secret}})
        started = time.monotonic()
        while True:
            state = self.poll()
            for event in state.get("events") or []:
                if event.get("tipo") == "resposta" and event.get("id") == qid and event.get("texto"):
                    return event["texto"]
            if state.get("stopped"):
                raise Stopped("interrompida pelo usuário")
            if time.monotonic() - started > ASK_LIMIT:
                self._send("/live", {"pergunta": None, "status": "Sem resposta: parei."})
                raise Stopped("sem resposta à pergunta")
            time.sleep(POLL)

    def gate(self):
        """Antes de cada ação: espera enquanto o usuário pausou, escreve ou toca; devolve as instruções que ele mandou.
        Levanta `Stopped` se ele interrompeu."""
        instructions, started, touched = [], time.monotonic(), None
        while True:
            state = self.poll()
            for event in state.get("events") or []:
                if event.get("tipo") == "instrucao" and event.get("texto"):
                    if OWNER_ON.search(event["texto"]):
                        self.set_owner(True)
                    elif OWNER_OFF.search(event["texto"]) and self.owner:
                        self.set_owner(False)
                    else:
                        instructions.append(event["texto"])
                elif event.get("tipo") in ("toque", "toque_longo") and not event.get("duvidoso"):
                    touched = time.monotonic()
                elif event.get("tipo") == "novo_pedido":
                    raise Stopped(NEW_REQUEST)
            if state.get("stopped"):
                raise Stopped("interrompida pelo usuário")
            waiting = state.get("paused") or state.get("typing") or (touched and time.monotonic() - touched < USER_QUIET)
            if not waiting:
                return instructions
            limit = PAUSE_LIMIT if state.get("paused") else TYPING_LIMIT
            if time.monotonic() - started > limit:
                raise Stopped("pausa longa demais")
            time.sleep(POLL)


def describe(name, params, elements):
    """O que a faixa mostra para uma ação do agente, em português."""
    if name == "open_app":
        return f"Abrindo {params.get('text', 'o app')}"
    if name == "click":
        try:
            index = int(params.get("index", -1))
        except ValueError:
            index = -1
        element = next((e for e in elements if e.get("index") == index), None)
        label = (element or {}).get("text") or ""
        return f"Tocando em “{label[:40]}”" if label else "Tocando na tela"
    if name == "type":
        return "Digitando"
    if name == "swipe":
        return "Rolando a tela"
    if name == "wait":
        return "Esperando a tela carregar"
    if name == "system_button":
        return {"back": "Voltando", "home": "Indo para a tela inicial", "enter": "Confirmando",
                "quick_settings": "Abrindo o painel rápido"}.get(params.get("button", "").lower(), "Apertando um botão")
    return "Trabalhando…"


def event_time(state, event):
    """A hora de um evento do app no relógio do PC (time.monotonic): a leitura menos a idade dele, pelo relógio do
    celular ("agora" da leitura e "t" do evento). Sem as duas horas, a da leitura."""
    now = time.monotonic()
    if isinstance(state.get("agora"), (int, float)) and isinstance(event.get("t"), (int, float)):
        return now - max(0.0, (state["agora"] - event["t"]) / 1000)
    return now


def start(device, session, task, continuous=False, guide=False):
    """O live mode da tarefa, ou None sem o app do lm_phone (pelo Portal não há faixa)."""
    if not access.USE_APP:
        return None
    live = Live(device, session)
    live.start(task, continuous, guide)
    return live
