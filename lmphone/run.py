"""Roda uma tarefa no celular: python -m lmphone.run "Turn on dark mode" (o run.sh e o run.cmd chamam isto).

O provedor escreve o plano vendo só dados mascarados; o serviço (lmphone/service.py) executa no aparelho, com o Laya
achando controles pelo nome e a IA local julgando o que mascarar: os modelos pequenos (lmphone/modelo_server.py, no
.venv-modelo) fazem os dois papéis; com LMPHONE_LOCAL_AI=gemma, o Laya e a Gemma (Ollama), como antes de 2026-10-19. A acessibilidade do Portal só fica ligada
durante a tarefa (lmphone/access.py): apps de banco bloqueiam o aparelho quando a veem ligada.
O serviço e o servidor do Laya ficam no ar entre tarefas; --stop encerra os dois, --stop-laya só o Laya.
Em Python, e não em sh, para rodar igual no Linux do notebook e no Windows da máquina da RTX.
"""

import glob
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request

from . import bridge, client, host

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYA = f"http://127.0.0.1:{os.environ.get('LMPHONE_LAYA_PORT', '8788')}"
SERVICE = f"http://127.0.0.1:{os.environ.get('LMPHONE_SERVICE_PORT', '8789')}"
OLLAMA = "http://127.0.0.1:11434"


def up(url, timeout=2):
    try:
        urllib.request.urlopen(url, timeout=timeout).close()
        return True
    except Exception:
        return False


def info(url):
    """O que o servidor responde em GET /, ou None se ele não está no ar."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.load(response)
    except Exception:
        return None


def wait(url, seconds):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit and not up(url):
        time.sleep(0.25)


def stop(name):
    path = f"logs/{name}.pid"
    try:
        with open(path) as f:
            host.stop(int(f.read()))
    except (OSError, ValueError):
        pass
    if os.path.exists(path):
        os.remove(path)


def start(name, argv, env=None):
    with open(f"logs/{name}.pid", "w") as f:
        f.write(str(host.spawn(argv, f"logs/{name}.out", env)))


def read_env():
    values = {}
    try:
        with open(".env", encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return values


def ollama_model():
    """Cria no Ollama a gemma4:e2b-it-qat só com o arquivo de texto (o primeiro FROM), sem o projetor de imagem e áudio."""
    if subprocess.run(["ollama", "show", "gemma4-e2b-texto"], capture_output=True).returncode == 0:
        return
    shown = subprocess.run(["ollama", "show", "gemma4:e2b-it-qat", "--modelfile"], capture_output=True, text=True)
    source = next((line for line in shown.stdout.splitlines()
                   if line.startswith("FROM ") and os.path.isabs(line[5:].strip())), None)
    if source:
        with open("logs/gemma-texto.Modelfile", "w", encoding="utf-8") as f:
            f.write(f"{source}\nTEMPLATE {{{{ .Prompt }}}}\nRENDERER gemma4\nPARSER gemma4\n")
        if subprocess.run(["ollama", "create", "gemma4-e2b-texto", "-f", "logs/gemma-texto.Modelfile"],
                          capture_output=True).returncode == 0:
            return
    print("Aviso: não consegui criar gemma4-e2b-texto no Ollama (falta 'ollama pull gemma4:e2b-it-qat'?).", file=sys.stderr)


def main():
    os.chdir(ROOT)
    # O aparelho dos comandos adb, aqui e nos processos que este sobe: o cabo, se houver; senão a depuração sem fio.
    bridge.choose()
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "--stop-laya":
        stop("laya")
        return 0
    if command == "--stop":
        stop("laya")
        stop("service")
        return subprocess.run([sys.executable, "-m", "lmphone.access", "off"]).returncode
    if not command or (command.startswith("-") and command not in ("--conversa", "--celular")):
        print('uso: run "instrução" | --conversa | --celular | --stop | --stop-laya', file=sys.stderr)
        return 1
    if command == "--celular":
        # O painel do assistente fala com o serviço pelo app do lm_phone: o serviço tem de estar no modo do app.
        os.environ["LMPHONE_DEVICE"] = "app"
    env = read_env()
    if not env.get("OPENROUTER_API_KEY"):
        print("Defina OPENROUTER_API_KEY em .env", file=sys.stderr)
        return 1
    os.makedirs("logs", exist_ok=True)

    # Na porta do Laya ficam os modelos pequenos (lmphone/modelo_server.py), que fazem o papel do Laya e da Gemma,
    # ou, com LMPHONE_LOCAL_AI=gemma, o Laya (e a Gemma no Ollama). Fica no ar entre tarefas; se o que está no ar é o do
    # outro modo, é trocado, e o serviço sobe de novo (ele lê o modo ao subir).
    mode = os.environ.get("LMPHONE_LOCAL_AI", "novo")
    small = mode == "novo"
    running = info(LAYA + "/")
    if running is not None and str(running.get("model", "")).startswith("modelos pequenos") != small:
        stop("laya")
        stop("service")
        time.sleep(0.5)
        running = None
    if running is None:
        argv = ([host.venv_python(".venv-modelo"), "-u", "-m", "lmphone.modelo_server"] if small
                else [host.venv_python(".venv-laya"), "-u", "-m", "lmphone.laya_server"])
        start("laya", argv)
        wait(LAYA + "/", 60)

    if not small:  # os modelos pequenos não usam o Ollama
        if not up(OLLAMA + "/api/version"):
            print("Aviso: Ollama fora do ar (ollama serve). O pedido não será julgado pela IA local; valem só as regras fixas.",
                  file=sys.stderr)
        else:
            ollama_model()

    # O serviço guarda o código, o .env e os modos de quando subiu: se algum mudou, sobe de novo.
    pid_file, mode_file = "logs/service.pid", "logs/service.modo"
    device = os.environ.get("LMPHONE_DEVICE", "portal")
    modes = f"{mode} {device}"
    if os.path.exists(pid_file):
        started = os.path.getmtime(pid_file)
        try:
            with open(mode_file, encoding="utf-8") as f:
                same = f.read().strip() == modes
        except OSError:
            same = False
        if not same or any(os.path.getmtime(p) > started for p in glob.glob("lmphone/*.py") + [".env"]):
            stop("service")
            time.sleep(0.3)
    if not up(SERVICE + "/health"):
        # A chave do provedor fica só no processo do serviço.
        start("service", [sys.executable, "-u", "-m", "lmphone.service"],
              {**os.environ, **env, "LMPHONE_LOCAL_AI": mode, "LMPHONE_DEVICE": device})
        with open(mode_file, "w", encoding="utf-8") as f:
            f.write(modes)
        wait(SERVICE + "/health", 10)
    # MODEL (no ambiente) troca o modelo do provedor nesta tarefa; LMPHONE_CACHE=0 ignora o cache e o mapa.
    if command == "--conversa":
        return conversation()
    if command == "--celular":
        return phone()
    return client.main()


def phone():
    """Deixa o assistente pronto para ser chamado pelo celular (etapa 3 de docs/plano-assistente.md)."""
    token = bridge.read_token()
    if not token or not bridge.link(token, int(SERVICE.rsplit(":", 1)[1])):
        print("Não consegui ligar o celular ao serviço (adb no cabo ou na depuração sem fio? app do lm_phone "
              "instalado?).", file=sys.stderr)
        return 1
    if bridge.wireless():
        print("Ligado pela depuração sem fio: o PC e o celular precisam ficar na mesma rede.")
    print("Pronto: o assistente atende pelo celular. Toque longo na tecla lateral (com o lm_phone como assistente "
          "digital: Configurações > Apps > Apps padrão > Assistente digital). A IA local e o serviço ficam no ar; "
          "run --stop encerra.")
    return 0


def conversation():
    """Conversa com o assistente pelo terminal: cada linha é um pedido, e ele lembra os anteriores (o mesmo id)."""
    print("Conversa com o assistente. Linha vazia ou Ctrl+C encerra.", flush=True)
    conversation_id = secrets.token_hex(4)
    while True:
        try:
            said = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not said:
            return 0
        try:
            client.main(said, conversation_id)
        except KeyboardInterrupt:
            print("(pedido interrompido)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
