"""O serviço: fica no ar entre tarefas e roda cada uma num ciclo próprio (ler a tela, decidir, agir).

Uso: python -m lmphone.service
O run.sh o sobe quando falta e manda cada tarefa por `lmphone.client`; ./run.sh --stop o encerra.

Fica entre tarefas o que não é da tarefa: o processo (imports, chave do provedor), a ligação com o Portal e a
lista de apps do aparelho. Cada pedido começa por `proxy.begin`; dentro de uma conversa (o cliente manda o id) os
valores falsos e o histórico continuam, fora dela nascem de novo. Uma tarefa por vez, porque o aparelho é um só.

O ciclo: ler a tela, pedir a próxima ação ao executor (`proxy.local_step`), fazer a ação, repetir. A tela vai ao
executor no formato de texto que o executor lê (ver device.py).

A acessibilidade e o teclado do Portal só ficam ligados durante a tarefa (access.py): ligam enquanto o plano é
pedido e desligam depois do resultado, antes de o aparelho ficar livre para a próxima. Um app de banco em primeiro
plano para a tarefa e desliga tudo na hora.
"""

import json
import os
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import access, bridge, live as live_mode, proxy
from .device import new_device, parse_call
from .executor import HOW_TO, plain

HOST, PORT = "127.0.0.1", int(os.environ.get("LMPHONE_SERVICE_PORT", "8789"))
MODEL = os.environ.get("MODEL") or "anthropic/claude-haiku-5.5"
MAX_STEPS = 60  # leituras de tela por tarefa (contam as esperas do executor)
AFTER_ACTION = 0.2  # espera entre a ação e a leitura seguinte; o executor pede mais quando a tela ainda muda
# Uma tela lida no meio da animação de troca traz os elementos em posições de passagem, e o toque seguinte cai fora
# do lugar. A tela só vale quando duas leituras seguidas saem iguais; a que nunca para (vídeo, relógio) vale no limite.
STILL_GAP, STILL_LIMIT = 0.15, 1.5
# Pelo app (LMPHONE_DEVICE=app) uma leitura leva uns 0,1 s em vez de 1,1 s: com 0,15 s entre as duas, uma pausa no meio
# do carregamento (página do Chrome, perfil do Instagram) passava por tela parada e o agente lia a página vazia.
if access.USE_APP:
    STILL_GAP, STILL_LIMIT = 0.6, 3.0
APPS_TTL = 600  # idade, em segundos, a partir da qual a lista de apps é relida no começo de uma tarefa
BUSY_WAIT = 30  # quanto um pedido espera a tarefa anterior acabar antes de ser recusado
READ_TRIES = 3
READY_LIMIT = 8  # segundos para o Portal responder depois de a acessibilidade ser ligada
BANK_MESSAGE = "Um app de banco está aberto: parei e desliguei a acessibilidade."
STOPPED_MESSAGE = "Interrompida pelo usuário."
# Erros que o app devolve quando o usuário pausou, interrompeu ou está escrevendo: a ação não foi feita, e o portão
# do live mode cuida disso na volta seguinte.
USER_BLOCKS = ("paused by the user", "stopped by the user", "the user is writing to the agent",
               "the owner is doing this step")
GUIDE_AGENT = False  # a tarefa pediu o guia com o agente tocando (a opção do app, posta pelo pedido: a suíte usa)
GUIDE_PAUSE = 2.5  # no guia, segundos entre mostrar (e dizer) o passo e fazê-lo, para o dono acompanhar
OWNER_WAIT_LIMIT = 600  # leituras de espera na vez do dono, que não contam em MAX_STEPS (cada uma ~1 s)

device = new_device()
busy = threading.Lock()
# Live mode contínuo (2026-10-24, live.py): ligado por /live ou por um pedido com "continuo", a acessibilidade fica
# ligada entre os pedidos (só o teclado volta a ser o do dono) até o app mandar "encerrar" ("finalizar" ou o X).
CONTINUOUS = False
# A senha de /task (bridge.py): o painel do assistente no celular alcança esta porta pelo `adb reverse`, e qualquer
# outro app do celular também alcançaria. Nasce em `main`; sem ela (testes), não se confere.
TOKEN = None


def read_once():
    for attempt in range(READ_TRIES):
        try:
            return device.read()
        except Exception:
            if attempt == READ_TRIES - 1:
                raise
            time.sleep(0.5)


def read_screen():
    """A tela parada: lê até duas leituras seguidas saírem iguais (textos, estados e posições)."""
    screen, limit = read_once(), time.monotonic() + STILL_LIMIT
    while time.monotonic() < limit:
        time.sleep(STILL_GAP)
        again = read_once()
        if again == screen:
            break
        screen = again
    return screen


def switch_on(result):
    """Liga a acessibilidade e o teclado do Portal e, se a lista de apps está velha, relê (ela vem do Portal).
    Roda junto com o pedido do plano; `result` recebe o erro que impede a tarefa, ou fica vazio."""
    started = time.monotonic()
    try:
        access.on()
    except access.BankOpen:
        result.append("bank")
        return
    except Exception as e:
        result.append(e)
        return
    try:
        device.keyboard()
    except Exception as e:
        proxy.log({"teclado": {"erro": repr(e)}})
    # A tela só serve depois de o Portal responder: o servidor dele sobe com o serviço.
    limit = time.monotonic() + READY_LIMIT
    while True:
        try:
            device.connect()
            break
        except Exception as e:
            if time.monotonic() > limit:
                result.append(e)
                return
            time.sleep(0.2)
    proxy.log({"acessibilidade": {"ligou_em": round(time.monotonic() - started, 2)}})
    if time.time() - proxy.packages_at > APPS_TTL:
        proxy.load_packages()


def switch_off():
    try:
        access.off()
    except Exception as e:
        proxy.log({"acessibilidade": {"erro_ao_desligar": repr(e)}})


def keyboard_back():
    try:
        access.keyboard_off()
    except Exception as e:
        proxy.log({"teclado": {"erro_ao_devolver": repr(e)}})


def fail(why, message):
    """Fim da tarefa por um erro do próprio ciclo, registrado como o executor registra os dele."""
    proxy.log({"exec": {"por": "código", "decisao": f"O serviço falhou: {proxy.masker.mask(why)}", "acao": "", "resultado": "falhou"},
               "arrived": round(time.time(), 3)})
    return False, message


def run(task, model, use_cache, emit, cancelled, collect=False, ask=False, conversation=None, owner=False,
        continuous=False):
    """Roda um pedido do começo ao fim. Devolve (concluída, mensagem), ou None se foi interrompido. `owner`: a tarefa
    começa na vez do dono (live mode, etapa 5), como se ele tivesse apertado ✋. `continuous`: o pedido veio do live
    mode contínuo, e a acessibilidade fica ligada depois dele."""
    bridge.choose()  # o cabo pode ter saído desde a última conferência da ponte
    # Só guia: o caminho gravado não vale (não tem as explicações do guia, e repeti-lo seria o agente agindo); o mapa dos
    # nomes vale (`proxy.cached_path` e `remember` olham `proxy.ACTS`).
    proxy.begin(task, use_cache, collect, conversation)
    proxy.ASK, proxy.OWNER = ask, owner
    emit(f"lmphone (sessão {proxy.SESSION})")
    threading.Thread(target=proxy.judge_task, daemon=True).start()
    ready = []
    starting = threading.Thread(target=switch_on, args=(ready,), daemon=True)
    starting.start()
    try:
        proxy.plan_ahead(model)
    except Exception as e:
        starting.join(30)  # senão o desligamento do fim pode vir antes de ele ligar
        return fail(repr(e), "O serviço falhou ao pedir o plano; veja logs/proxy.jsonl.")
    starting.join(30)
    if proxy.executor is not None and proxy.executor.replied is not None and (ready or starting.is_alive()):
        # Uma resposta sem nada a fazer no aparelho não precisa da acessibilidade (um banco aberto, o Portal fora do ar).
        return answer_only(model)
    if ready == ["bank"]:
        return fail("app de banco em primeiro plano no começo", BANK_MESSAGE)
    if ready or starting.is_alive():
        return fail(f"a acessibilidade do Portal não ligou: {ready[0] if ready else 'demorou demais'!r}",
                    "Não consegui ligar a acessibilidade do Portal (adb, Portal).")
    # Um "como eu faço..." já é guia antes do plano: a faixa sabe desde o começo que o toque da pessoa não pausa.
    live = live_mode.start(device, proxy.SESSION, task, continuous, guide=bool(HOW_TO.search(plain(task))))
    if live and owner:
        live.set_owner(True)
    try:
        return loop(model, emit, cancelled, live)
    except live_mode.Stopped as e:
        live.record("fim", resultado="interrompida", motivo=str(e))
        proxy.stopped_by_user(str(e))
        if str(e) == live_mode.NEW_REQUEST:
            return False, ""  # o dono já pediu outra coisa: a faixa mostra o pedido novo, não um "interrompido"
        live.show("Interrompido.")
        return False, STOPPED_MESSAGE


def answer_only(model):
    """O fim de um pedido que o assistente respondeu sem precisar do aparelho (o executor não olha a tela)."""
    answer = proxy.local_step("<device_state>\n</device_state>\n", model, round(time.time(), 3))
    _, params = parse_call(answer.partition("\n\n")[2])
    return params.get("success") == "true", params.get("message", "")


def loop(model, emit, cancelled, live):
    """O ciclo ler-decidir-agir da tarefa. Com o live mode, antes de cada leitura o usuário pode pausar, interromper ou
    mandar uma instrução (`live.gate`), e a faixa mostra cada ação."""
    global CONTINUOUS
    error, steps, owner_waits, marked, gestured, offered, rerouted = None, 0, 0, None, None, None, False
    while steps < MAX_STEPS and owner_waits < OWNER_WAIT_LIMIT:
        if cancelled.is_set():
            return None
        if live:
            for instruction in live.gate():
                live.show("Entendi, mudando o plano…")
                proxy.instruct(instruction)
            if proxy.executor is not None:
                proxy.executor.owner = live.owner
                proxy.executor.speaking = live.speaking
                proxy.executor.touched_at = live.touched_at
                proxy.executor.pressed_at = live.pressed_at
                proxy.executor.touched_text, proxy.executor.touched_text_at = live.touched_text, live.touched_text_at
                proxy.executor.touched_box = live.touched_box
                proxy.executor.guide_agent = live.guide_agent or GUIDE_AGENT
            if live.continuous:
                CONTINUOUS = True  # o dono ligou o modo contínuo na faixa: depois deste pedido, tudo fica ligado
        try:
            screen = read_screen()
        except Exception as e:
            return fail(f"a tela não pôde ser lida: {e!r}", "Não consegui ler a tela do celular (adb, Portal).")
        if access.is_bank(device.package):
            CONTINUOUS = False
            switch_off()
            return fail("app de banco em primeiro plano", BANK_MESSAGE)
        results = f"<function_results>\n<result>\n<error>{error}</error>\n</result>\n</function_results>\n" if error else ""
        thinking = live.thinking() if live else None
        try:
            answer = proxy.local_step(f"{results}\n<device_state>\n{screen}\n</device_state>\n", model, round(time.time(), 3))
        finally:
            if thinking:
                thinking.cancel()
        why, _, tool = answer.partition("\n\n")
        name, params = parse_call(tool)
        waiting_owner = proxy.executor is not None and proxy.executor.waiting is not None
        rolling = proxy.executor is not None and proxy.executor.rolling is not None
        if waiting_owner or rolling:
            owner_waits += 1  # esperar o dono ou rolar sem parar ("fica rolando") não gasta os passos do agente
        else:
            steps += 1
        if live and proxy.executor is not None and proxy.executor.highlight != marked:
            marked = proxy.executor.highlight
            live.highlight(marked, owner=waiting_owner)
        if live and proxy.executor is not None and proxy.executor.gesture != gestured:
            gestured = proxy.executor.gesture
            live.gesture(gestured)
        if live and proxy.executor is not None and proxy.executor.off_names:
            # Um nome dito entre aspas que não está na tela (a conferência "nomes" da suíte).
            live.record("nome_fora_da_tela", nomes=proxy.executor.off_names)
            proxy.executor.off_names = []
        if live and proxy.executor is not None and proxy.executor.rerouting != rerouted:
            rerouted = proxy.executor.rerouting
            live.reroute(rerouted)  # a pessoa saiu do caminho: "recalculando" na faixa até a instrução nova
        if live and proxy.executor is not None and proxy.executor.button != offered:
            offered = proxy.executor.button
            live.button(proxy.button(offered))  # só guia: o botão da faixa que abre o app ou a página
        if live and proxy.executor is not None and proxy.executor.plan is not None and proxy.executor.guide != live.guiding:
            live.guide(proxy.executor.guide)  # o plano marcou guia (ou não): a faixa fica sabendo
        if name == "ask_user":
            # O provedor quer perguntar ao dono: a pergunta (escrita com valores falsos) aparece na faixa com os reais.
            question = proxy.masker.unmask(params.get("question", ""))
            options = [proxy.masker.unmask(o) for o in json.loads(params.get("options") or "[]")]
            secret = params.get("secret") == "true"
            emit(f"Pergunta ao dono: {params.get('question', '')}")
            answer = live.ask(question, options, secret)
            live.show("Entendi, continuando…")
            proxy.answered(params.get("question", ""), answer, secret)
            error = None
            continue
        if name == "confirm_user":
            # Antes de um toque que não se desfaz (enviar, comprar, apagar): a pergunta na faixa, com os valores reais.
            question = proxy.masker.unmask(params.get("question", ""))
            emit(f"Confirmação: {params.get('question', '')}")
            answer = live.ask(question, ["Sim", "Não"], False)
            if proxy.confirmed(question, answer) is not False:
                live.show("Entendi, continuando…")
            error = None
            continue
        if name == "complete":
            done, message = params.get("success") == "true", params.get("message", "")
            if live:
                live.record("fim", resultado=proxy.executor.result if proxy.executor else None, mensagem=message)
                live.show(message)  # a mensagem já é a resposta do assistente, em português
            return done, message
        emit(why)
        # O que o assistente disse que vai fazer (o "say" do plano) ou a explicação do passo (no guia), com os valores reais.
        said = proxy.executor.announce if proxy.executor else None
        if said:
            proxy.executor.announce = None
            emit(f"Assistente: {said}")
        if live:
            live.record("acao", ferramenta=name, parametros=params, por=proxy.executor.by if proxy.executor else None,
                        passo=proxy.executor.i if proxy.executor else None, **({"disse": said} if said else {}))
            if said:
                # O que o assistente diz (o plano, o passo do guia, a vez do dono) é falado; quando é a vez do dono, a
                # faixa minimizada abre, para ele ler o que fazer.
                live.show(said, speak=True, open=waiting_owner)
                if proxy.executor.guide and not waiting_owner and name != "wait":
                    time.sleep(GUIDE_PAUSE)  # o dono lê (e ouve) o passo e vê o destaque antes do toque
            elif not waiting_owner:
                live.show(live_mode.describe(name, params, device.elements))
        if cancelled.is_set():
            return None
        if name == "open_app":
            # Nome que o executor não conseguiu abrir direto: nenhum app instalado se chama assim.
            error = None if proxy.launch(params.get("text", "")) else f"Could not open the app “{params.get('text', '')}”: no installed app has this exact name"
            time.sleep(1)
        else:
            error = device.act(name, params)
        if error and any(block in error for block in USER_BLOCKS):
            # A ação não foi feita porque o usuário pausou ou está escrevendo; o executor refaz o passo na tela nova.
            error = f"{error}: the action was not done"
        if name != "wait":
            time.sleep(AFTER_ACTION)
    return fail(f"passou de {MAX_STEPS} passos", f"Não consegui terminar: passei de {MAX_STEPS} passos.")


def gone(connection):
    """O cliente fechou a ligação (o run.sh foi interrompido)."""
    try:
        readable, _, _ = select.select([connection], [], [], 0)
        return bool(readable) and connection.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(200 if self.path == "/health" else 404, {"status": "ok", "busy": busy.locked()})

    def do_POST(self):
        global CONTINUOUS
        if self.path not in ("/task", "/live"):
            return self.reply(404, {"error": "só existem /task e /live"})
        # O corpo é lido antes da recusa: respondido sem ler, o cliente que ainda manda o corpo vê a conexão cair.
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if TOKEN and self.headers.get("X-Lmphone-Token") != TOKEN:
            return self.reply(401, {"error": "senha errada ou ausente (logs/service.token)"})
        if self.path == "/live":
            return self.live_mode(data)
        try:
            body = json.loads(data)
            task = body["task"]
        except (ValueError, KeyError):
            return self.reply(400, {"error": "esperado: {\"task\": \"...\"}"})
        if not busy.acquire(timeout=BUSY_WAIT):
            return self.reply(409, {"error": "outra tarefa está rodando no celular"})
        # Cada pedido diz se é do modo contínuo; um pedido comum (o painel) depois de o app ter se desligado sozinho
        # (um app de banco na frente) não deixa a acessibilidade ligada.
        CONTINUOUS = bool(body.get("continuo"))
        try:
            # O andamento vai linha a linha, até a ligação fechar. As linhas citam rótulos da tela: ficam no terminal de quem pediu.
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            cancelled, outcome, started = threading.Event(), [], time.monotonic()

            def emit(line):
                try:
                    self.wfile.write((line + "\n").encode())
                    self.wfile.flush()
                except OSError:
                    cancelled.set()

            def work():
                global GUIDE_AGENT
                GUIDE_AGENT = bool(body.get("guia_agente"))  # uma tarefa por vez: vale para esta
                proxy.ACTS = body.get("agir", True) is not False  # só guia, como o app da loja
                try:
                    outcome.append(run(task, body.get("model") or MODEL, body.get("cache", True), emit, cancelled,
                                       body.get("coleta", False), body.get("perguntar", False), body.get("conversa"),
                                       body.get("dono", False), bool(body.get("continuo"))))
                except Exception as e:
                    outcome.append(fail(repr(e), "O serviço falhou; veja logs/proxy.jsonl."))

            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            while worker.is_alive():
                worker.join(0.3)
                if gone(self.connection):
                    cancelled.set()
            # Só depois de a tarefa parar de fato o aparelho fica livre para a próxima.
            if outcome and outcome[0] is not None:
                done, message = outcome[0]
                emit(f"({time.monotonic() - started:.1f} s)")
                emit(f"Goal {'achieved' if done else 'failed'}: {message}")
            else:
                proxy.log({"interrompida": True})
        finally:
            # Depois do resultado (quem pediu não espera isto), e antes de o aparelho ficar livre. No modo contínuo a
            # acessibilidade fica para o pedido seguinte; só o teclado volta a ser o do dono.
            if CONTINUOUS:
                keyboard_back()
            else:
                switch_off()
            busy.release()

    def live_mode(self, data):
        """POST /live {"acao": "iniciar" | "encerrar"}: o modo contínuo, pedido pelo painel ou pela faixa do app.
        Iniciar liga a acessibilidade (a faixa aparece, como um círculo, já ouvindo) e a deixa ligada; encerrar a
        desliga, ou deixa para o fim do pedido em curso."""
        global CONTINUOUS
        try:
            action = json.loads(data).get("acao")
        except (ValueError, AttributeError):
            action = None
        if action == "encerrar":
            CONTINUOUS = False
            if busy.acquire(blocking=False):  # sem pedido em curso; com um, o fim dele desliga tudo
                try:
                    switch_off()
                finally:
                    busy.release()
            return self.reply(200, {"ok": True})
        if action != "iniciar":
            return self.reply(400, {"error": "esperado: {\"acao\": \"iniciar\" ou \"encerrar\"}"})
        if not access.USE_APP:
            return self.reply(400, {"error": "o modo contínuo precisa do app (LMPHONE_DEVICE=app)"})
        if not busy.acquire(timeout=BUSY_WAIT):
            return self.reply(409, {"error": "outra tarefa está rodando no celular"})
        try:
            ready = []
            switch_on(ready)
            if ready:
                switch_off()
                message = BANK_MESSAGE if ready == ["bank"] else "Não consegui ligar a acessibilidade do app."
                proxy.log({"continuo": {"iniciou": False, "motivo": "banco" if ready == ["bank"] else repr(ready[0])}})
                return self.reply(500, {"error": message})
            CONTINUOUS = True
            device.request("/live", {"continuo": True, "nova_tarefa": True, "bancos": sorted(access.banks()),
                                     "status": "Modo contínuo: pode ir pedindo. Diga «finalizar» para encerrar."})
            keyboard_back()
            proxy.log({"continuo": {"iniciou": True}})
            return self.reply(200, {"ok": True})
        except Exception as e:
            CONTINUOUS = False
            switch_off()
            return self.reply(500, {"error": repr(e)})
        finally:
            busy.release()


def main():
    global TOKEN
    TOKEN = bridge.new_token()
    print(f"lmphone serviço em http://{HOST}:{PORT}", flush=True)
    bridge.choose()
    # O aparelho dos comandos adb é escolhido de novo a cada 10 s (cabo ou rede). Com o app, o painel do assistente
    # manda os pedidos por aqui (etapa 3 de docs/plano-assistente.md), e a ponte é refeita quando ele volta.
    bridge.keep(TOKEN, PORT, proxy.log, app=access.USE_APP)
    # A ligação com o Portal e a lista de apps ficam para a primeira tarefa: fora dela a acessibilidade fica desligada.
    # Uma tarefa interrompida por queda do serviço pode tê-la deixado ligada.
    switch_off()
    if os.environ.get("LMPHONE_TRILHA") == "1":
        # As trilhas do executor (lmphone/trilha.py), uma por sessão, para conferir o cérebro em Kotlin com tarefas de
        # verdade. Têm as telas reais: ficam em logs/trilhas/ (modo 600), nesta máquina.
        from . import trilha
        trilha.install(lambda: f"logs/trilhas/{proxy.SESSION}.jsonl")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
