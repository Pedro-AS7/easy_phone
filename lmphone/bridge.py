"""A ponte do celular ao serviço (etapa 3 de docs/plano-assistente.md): o painel do assistente no app manda o pedido
para 127.0.0.1:8789 do celular, e o `adb reverse` o leva à mesma porta do PC.

Qualquer app do celular alcança essa porta. Por isso o serviço só aceita `/task` com a senha dele
(`logs/service.token`, nova a cada subida do serviço): o cliente do PC a lê do arquivo, e o app de `files/pc_token`,
que só o adb grava (`run-as`). O `adb reverse` some quando o celular desconecta: o serviço o refaz sozinho.

O celular pode estar no cabo ou na depuração sem fio do Android (pareado uma vez com `adb pair`; o adb volta a se ligar
sozinho a ele pela rede, e `reconnect` tenta de novo). Com os dois ao mesmo tempo, todo `adb` sem escolha recusa
("more than one device"): `choose` põe em ANDROID_SERIAL, que o adb lê, o do cabo se houver.
"""

import os
import re
import secrets
import subprocess
import threading
import time

from .access import APP

TOKEN_PATH = "logs/service.token"
CHECK = 10  # segundos entre as conferências da ponte


def new_token():
    token = secrets.token_hex(16)
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    return token


def read_token():
    try:
        with open(TOKEN_PATH) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _adb(*args, input=None):
    return subprocess.run(["adb", *args], input=input, capture_output=True, text=True, timeout=15)


def is_wireless(serial):
    """Serial de uma ligação pela rede: "192.168.0.10:37123" ou o nome do mDNS ("adb-XXXX._adb-tls-connect._tcp")."""
    return ":" in serial or "._adb-tls-connect." in serial


def devices():
    """Os seriais dos aparelhos prontos no adb, o do cabo primeiro."""
    ready = [line.split("\t")[0] for line in _adb("devices").stdout.splitlines() if line.endswith("\tdevice")]
    return sorted(ready, key=is_wireless)


def reconnect():
    """Liga de novo, pela rede, um aparelho já pareado que o mDNS anuncia. O adb costuma fazer isso sozinho."""
    for line in _adb("mdns", "services").stdout.splitlines():
        if "_adb-tls-connect." in line and (address := re.search(r"(\d+\.\d+\.\d+\.\d+:\d+)\s*$", line)):
            _adb("connect", address.group(1))


def choose():
    """Escolhe o aparelho dos comandos adb deste processo e dos que ele abrir (ANDROID_SERIAL): o do cabo, se houver;
    senão o da rede. Sem nenhum, tenta religar pela rede. Devolve o serial ou None."""
    found = devices()
    if not found:
        reconnect()
        found = devices()
    if found:
        os.environ["ANDROID_SERIAL"] = found[0]
    else:
        os.environ.pop("ANDROID_SERIAL", None)
    return found[0] if found else None


def wireless():
    """O aparelho em uso está ligado pela rede: desligar o Wi-Fi cortaria a ligação com o PC."""
    serial = os.environ.get("ANDROID_SERIAL") or next(iter(devices()), "")
    return is_wireless(serial)


def connected():
    return choose() is not None


def link(token, port):
    """Põe o `adb reverse` da porta e grava a senha no app. Devolve True se o celular ficou ligado ao serviço."""
    if not connected():
        return False
    if f"tcp:{port}" not in _adb("reverse", "--list").stdout and _adb("reverse", f"tcp:{port}", f"tcp:{port}").returncode:
        return False
    # O `adb shell` junta os argumentos num comando só: o redirecionamento vai entre aspas, para rodar dentro do
    # `run-as` (no app) e não no shell de fora. A senha é hexadecimal: não precisa de escape.
    if not all(c in "0123456789abcdef" for c in token):
        return False
    done = _adb("shell", f"run-as {APP} sh -c 'echo {token} > files/pc_token'")
    return done.returncode == 0 and _adb("shell", f"run-as {APP} cat files/pc_token").stdout.strip() == token


def keep(token, port, log, app=True):
    """Mantém a ponte enquanto o serviço está no ar: escolhe de novo o aparelho (o cabo saiu, voltou, ou a rede
    caiu) e, com o app (`app`), refaz o reverse e a senha quando ele volta."""
    def loop():
        linked, serial = False, None
        while True:
            try:
                now = choose()
                if now != serial:
                    log({"ponte": {"aparelho": None if now is None else "rede" if is_wireless(now) else "cabo"}})
                    linked, serial = False, now
                if now is None or not app:
                    linked = False
                elif not linked or f"tcp:{port}" not in _adb("reverse", "--list").stdout:
                    linked = link(token, port)
                    log({"ponte": {"ligada": linked}})
            except Exception as e:
                log({"ponte": {"erro": repr(e)}})
            time.sleep(CHECK)

    threading.Thread(target=loop, name="ponte", daemon=True).start()
