"""A acessibilidade e o teclado do Portal ficam ligados só durante uma tarefa.

Apps de banco (o Inter bloqueou o aparelho em 2026-10-13) consultam os serviços de acessibilidade ativos e o
teclado padrão quando abrem; um app de fora da loja com acessibilidade ligada é o retrato de um golpe de acesso
remoto. Fora de uma tarefa, nada do Portal fica ligado. `on` recusa ligar com um app de banco em primeiro plano, e o
ciclo do serviço desliga tudo na hora se um deles aparecer no meio da tarefa.

Com LMPHONE_DEVICE=app, o serviço e o teclado são os do app do lm_phone (android/).

Uso: python -m lmphone.access on|off|status (o serviço chama as funções direto; o run.sh usa no --stop).
"""

import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager

PORTAL = "com.mobilerun.portal"
APP = "dev.pedro.lmphone"
USE_APP = os.environ.get("LMPHONE_DEVICE", "portal") == "app"
SERVICE = f"{APP}/{APP}.AgentService" if USE_APP else f"{PORTAL}/{PORTAL}.service.MobilerunAccessibilityService"
KEYBOARD = f"{APP}/.Keyboard" if USE_APP else f"{PORTAL}/.input.MobilerunKeyboardIME"
IME_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "ime.prev")  # o teclado de antes da tarefa
BANKS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "banks.txt")  # um pacote por linha, além dos de BANKS
BANKS = {
    "br.com.intermedium",  # Inter
    "com.nu.production",  # Nubank
    "com.itau", "com.itau.iti", "br.com.itau.personnalite", "com.itaucard.activity",
    "com.bradesco", "br.com.bradesco.next",
    "br.com.bb.android",  # Banco do Brasil
    "br.com.gabba.Caixa", "br.gov.caixa.tem",
    "com.santander.app",
    "com.c6bank.app",
    "com.picpay",
    "com.mercadopago.wallet",
    "br.com.original.bank",
    "com.btg.pactual.banking",
    "br.com.sicredi.app", "br.com.sicoobnet",
}


class BankOpen(Exception):
    """Um app de banco está em primeiro plano: a acessibilidade não é ligada."""


def adb(*args, timeout=15):
    result = subprocess.run(["adb", "shell", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"adb shell {args[0]}: {(result.stderr or result.stdout).strip()[:200]}")
    return result.stdout.strip()


def banks():
    try:
        with open(BANKS_FILE, encoding="utf-8") as f:
            extra = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    except OSError:
        extra = set()
    return BANKS | extra


def is_bank(package):
    return bool(package) and package in banks()


def foreground():
    """O pacote do app em primeiro plano, pelo sistema (sem o Portal, que pode estar desligado)."""
    out = adb("dumpsys activity activities | grep -m1 -E 'topResumedActivity|mResumedActivity'; true")
    found = re.search(r"\s([\w.]+)/[\w.$]+", out)
    return found.group(1) if found else None


def services():
    value = adb("settings", "get", "secure", "enabled_accessibility_services")
    return [] if value in ("", "null") else [s for s in value.split(":") if s]


def put_services(names):
    if names:
        adb("settings", "put", "secure", "enabled_accessibility_services", ":".join(names))
        adb("settings", "put", "secure", "accessibility_enabled", "1")
    else:
        # Lista vazia: apagar em vez de gravar "" (gravado vazio, alguns sistemas leem como serviço sem nome).
        adb("settings", "delete", "secure", "enabled_accessibility_services")
        adb("settings", "put", "secure", "accessibility_enabled", "0")


def is_on():
    return SERVICE in services()


def on():
    """Liga o serviço do Portal, mantendo os outros serviços de acessibilidade que estiverem ligados.
    Guarda o teclado atual para `off` devolver. Devolve os segundos gastos."""
    started = time.monotonic()
    if not adb(f"pm path {APP if USE_APP else PORTAL}; true"):
        raise RuntimeError("o app do lm_phone não está instalado (android/build.sh)" if USE_APP
                           else "o Portal não está instalado no celular (mobilerun setup o instala)")
    package = foreground()
    if is_bank(package):
        raise BankOpen(package)
    current = adb("settings", "get", "secure", "default_input_method")
    if current and current != "null" and current != KEYBOARD:
        os.makedirs(os.path.dirname(IME_FILE), exist_ok=True)
        with open(IME_FILE, "w", encoding="utf-8") as f:
            f.write(current)
    names = services()
    if SERVICE not in names:
        put_services(names + [SERVICE])
    return time.monotonic() - started


def previous_keyboard():
    """O teclado de antes da tarefa; sem registro, o primeiro teclado ativo que não é o do Portal."""
    try:
        with open(IME_FILE, encoding="utf-8") as f:
            saved = f.read().strip()
    except OSError:
        saved = ""
    enabled = adb("ime", "list", "-s").split()
    if saved in enabled:
        return saved
    return next((ime for ime in enabled if ime != KEYBOARD), None)


def off():
    """Desliga o serviço e o teclado do Portal (devolve o teclado de antes). Não falha se já estavam desligados."""
    names = services()
    if SERVICE in names:
        put_services([s for s in names if s != SERVICE])
    keyboard_off()


def keyboard_off():
    """Devolve o teclado de antes da tarefa e desliga o do agente. No live mode contínuo, entre um pedido e outro, o
    serviço fica ligado e o dono escreve nos apps com o teclado dele."""
    if adb("settings", "get", "secure", "default_input_method") == KEYBOARD:
        other = previous_keyboard()
        if other:
            adb("ime", "set", other)
    if KEYBOARD in adb("ime", "list", "-s").split():
        adb("ime", "disable", KEYBOARD)


@contextmanager
def enabled():
    """Liga só durante o bloco (as conferências da suíte, que leem a tela pelo Portal)."""
    was_on = is_on()
    if not was_on:
        on()
    try:
        yield
    finally:
        if not was_on:
            off()


def status():
    keyboard = adb("settings", "get", "secure", "default_input_method")
    return {
        "acessibilidade_do_portal": is_on(),
        "outros_servicos": len([s for s in services() if s != SERVICE]),
        "teclado_do_portal_ativo": keyboard == KEYBOARD,
        "teclado_do_portal_habilitado": KEYBOARD in adb("ime", "list", "-s").split(),
        "depuracao_usb": adb("settings", "get", "global", "adb_enabled") == "1",
    }


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        if command == "on":
            print(f"acessibilidade do Portal ligada ({on():.1f} s)")
        elif command == "off":
            off()
            print("acessibilidade e teclado do Portal desligados")
        elif command == "status":
            for key, value in status().items():
                print(f"{key}: {value}")
        else:
            sys.exit("uso: python -m lmphone.access on|off|status")
    except BankOpen as e:
        sys.exit(f"Um app de banco está aberto ({e}): feche-o antes de rodar uma tarefa.")
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        sys.exit(f"Não consegui falar com o celular: {e}")


if __name__ == "__main__":
    from lmphone import bridge
    bridge.choose()  # cabo ou depuração sem fio (com os dois, o adb sem escolha recusaria)
    main()
