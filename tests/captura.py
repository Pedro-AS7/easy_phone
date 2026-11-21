"""Guarda a tela atual do celular para investigar um erro: o print e o texto que o agente leria dela.

Uso: .venv/bin/python -m tests.captura [nome]
Saída: data/capturas/<nome>-<hora>/ com tela.png (print), tela.txt (a tela como o executor a lê), trechos.json (os
trechos que a IA local julgaria) e app.txt (o pacote em primeiro plano). A pasta fica só no notebook (modo 700) e o
comando não imprime nada da tela, só onde gravou e contagens: o conteúdo é real.

Serve para comparar um caso do conjunto congelado (tests/base) com a tela de verdade que ele imita, e para ver a tela
final de uma rodada da suíte que falhou (phone_suite.py grava uma captura dessas sozinho). Com app de banco em
primeiro plano, não captura nada.
"""

import json
import os
import subprocess
import sys
import time

from lmphone import access, local_ai
from lmphone.device import new_device

OUT_DIR = os.path.join("data", "capturas")


def screenshot(path):
    with open(path, "wb") as f:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=True, timeout=20)
    os.chmod(path, 0o600)


def stable_read(device, limit=8):
    """A tela vale quando duas leituras seguidas saem iguais (logo depois de ligar a acessibilidade, a árvore pode vir
    incompleta)."""
    end, last = time.monotonic() + limit, None
    while True:
        text = device.read()
        if text == last or time.monotonic() > end:
            return text
        last = text
        time.sleep(0.4)


def capture(name):
    """Grava a captura e devolve a pasta. Levanta `access.BankOpen` com app de banco em primeiro plano."""
    package = access.foreground()
    if access.is_bank(package):
        raise access.BankOpen(package)
    folder = os.path.join(OUT_DIR, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.chmod(OUT_DIR, 0o700)
    screenshot(os.path.join(folder, "tela.png"))
    text = ""
    try:
        with access.enabled():
            text = stable_read(new_device())
    except Exception as e:
        text = f"(a tela não pôde ser lida pelo Portal: {e!r})"
    files = {"tela.txt": text, "app.txt": package or "",
             "trechos.json": json.dumps(local_ai.screen_fragments(f"<device_state>\n{text}\n</device_state>"), ensure_ascii=False, indent=1)}
    for file, content in files.items():
        path = os.path.join(folder, file)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    return folder


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "tela"
    try:
        folder = capture(name)
    except access.BankOpen as e:
        sys.exit(f"app de banco em primeiro plano ({e}): nada foi capturado")
    with open(os.path.join(folder, "trechos.json"), encoding="utf-8") as f:
        count = len(json.load(f))
    print(f"captura em {folder}: tela.png, tela.txt ({count} trechos de texto), app.txt")
    print("O conteúdo é real: confira você mesmo; só mostre a um assistente se a tela não tiver dados pessoais.")


if __name__ == "__main__":
    from lmphone import bridge
    bridge.choose()  # cabo ou depuração sem fio (com os dois, o adb sem escolha recusaria)
    main()
