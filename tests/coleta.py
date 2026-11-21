"""Coleta noturna: roda as tarefas de coleta_cases.py com LMPHONE_COLETA=1, sem ninguém olhando.

Uso (celular no USB e desbloqueado, Ollama no ar):
    .venv/bin/python -m tests.coleta                   # todas as tarefas, uma vez
    .venv/bin/python -m tests.coleta --rodadas 3       # três vezes, cada rodada numa ordem sorteada
    .venv/bin/python -m tests.coleta --orcamento 0.50  # para quando o custo do provedor passar disto (US$)
    .venv/bin/python -m tests.coleta --rodadas 3 --de 96  # retoma de onde parou
    .venv/bin/python -m tests.coleta --listar
    Opções: --modelo, --com-cache, --limite segundos por tarefa, --apps pacote... (só estes).

Sem cache por padrão: o provedor escreve o plano toda vez, e as escolhas variam (com o cache, a tarefa repete o
caminho gravado e quase não há escolha a aprender). A tela do celular fica acesa enquanto roda (e volta ao ajuste de
antes no fim), e o computador não dorme. Antes de cada tarefa, fecha a cortina de notificações e diálogos e volta à
tela inicial. Se o adb parar de responder por 5 min, ou o celular aparecer bloqueado, a coleta para. Em logs/coleta.jsonl fica uma linha por tarefa, só com contagens (a resposta pode ter dado real).
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter

from lmphone import access, bridge, host, treino
from lmphone.sources import adb

from .coleta_cases import TASKS
from .phone_suite import DEFAULT_MODEL, ROOT, foreground, measure, run_task

COLETA_LOG = "logs/coleta.jsonl"
LAUNCHERS = ("com.sec.android.app.launcher", "terra.neo.terralauncher")
ADB_WAIT = 300  # segundos esperando o adb voltar antes de desistir


def installed():
    out = adb("pm", "list", "packages")
    return {line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("package:")}


def alive():
    """O adb responde (ele às vezes trava por minutos e volta sozinho)."""
    limit = time.monotonic() + ADB_WAIT
    while time.monotonic() < limit:
        try:
            if adb("echo", "ok").strip() == "ok":
                return True
        except Exception:
            pass
        time.sleep(10)
    return False


def locked():
    return "isKeyguardShowing=true" in adb("dumpsys", "window").replace(" ", "")


def awake():
    """Acorda a tela e põe o celular na tela inicial. Uma tarefa pode deixar a cortina de notificações ou um diálogo
    aberto: tenta fechar antes de desistir. None se está na tela inicial; senão, o que impede."""
    for _ in range(3):
        adb("input", "keyevent", "KEYCODE_WAKEUP")
        adb("cmd", "statusbar", "collapse")
        adb("input", "keyevent", "KEYCODE_BACK")
        adb("input", "keyevent", "KEYCODE_HOME")
        time.sleep(1.5)
        if foreground() in LAUNCHERS and not locked():
            return None
    return "o celular está bloqueado" if locked() else f"a tela inicial não abre (em primeiro plano: {foreground()})"


def keep_computer_awake(on):
    if host.WINDOWS:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def plan(packages, rounds, only):
    tasks = [(package, request) for package, requests in TASKS.items() for request in requests
             if (not only or package in only)]
    skipped = sorted({p for p, _ in tasks if p not in packages or access.is_bank(p)})
    tasks = [(p, r) for p, r in tasks if p not in skipped]
    order = []
    for n in range(rounds):
        batch = list(tasks)
        if n:
            random.Random(n).shuffle(batch)
        order += batch
    return order, skipped


def main():
    parser = argparse.ArgumentParser(description="Coleta noturna de dados de treino")
    parser.add_argument("--rodadas", type=int, default=1)
    parser.add_argument("--orcamento", type=float, default=1.0, help="US$ de provedor; para ao passar")
    parser.add_argument("--modelo", default=os.environ.get("MODEL") or DEFAULT_MODEL)
    parser.add_argument("--com-cache", action="store_true")
    parser.add_argument("--limite", type=int, default=180, help="segundos por tarefa")
    parser.add_argument("--apps", nargs="*", default=[])
    parser.add_argument("--de", type=int, default=1, help="retoma a partir desta tarefa (a ordem é sempre a mesma)")
    parser.add_argument("--listar", action="store_true")
    options = parser.parse_args()

    os.chdir(ROOT)
    bridge.choose()  # cabo ou depuração sem fio (com os dois, o adb sem escolha recusaria)
    order, skipped = plan(installed(), options.rodadas, set(options.apps))
    if skipped:
        print(f"fora (não instalado ou banco): {', '.join(skipped)}")
    if options.listar:
        for package, request in order:
            print(f"{package:45} {request}")
        print(f"{len(order)} tarefas")
        return 0

    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    out_dir = os.path.join("logs", "coleta", stamp)
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    stay_on = adb("settings", "get", "global", "stay_on_while_plugged_in").strip()
    adb("svc", "power", "stayon", "usb")
    keep_computer_awake(True)
    os.environ["LMPHONE_COLETA"] = "1"
    spent, results, started, stop = 0.0, Counter(), time.monotonic(), None
    try:
        for n, (package, request) in enumerate(order, 1):
            if n < options.de:
                continue
            if spent >= options.orcamento:
                stop = f"orçamento de US$ {options.orcamento:.2f} atingido"
                break
            if not alive():
                stop = "o adb não responde há 5 min"
                break
            try:
                stop = awake()
                if stop:
                    break
                adb("am", "force-stop", package)
            except subprocess.TimeoutExpired:
                continue  # o adb travou: a volta seguinte espera ele voltar
            code, seconds, rows, _ = run_task(request, options.modelo, options.com_cache, options.limite,
                                              os.path.join(out_dir, f"{n:04d}.txt"))
            numbers = measure(rows)
            spent += numbers["custo"]
            result = numbers["resultado"] or ("estourou o limite" if code is None else "sem resultado")
            results[result] += 1
            entry = {"n": n, "app": package, "segundos": round(seconds), "resultado": result, "chamadas": numbers["chamadas"],
                     "ajudas": numbers["ajudas"], "custo": numbers["custo"], "erros": len(numbers["erros"])}
            with open(COLETA_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"coleta": stamp, **entry}, ensure_ascii=False) + "\n")
            print(f"{n:4}/{len(order)}  {package:40} {result:18} {seconds:4.0f} s  US$ {spent:.4f}", flush=True)
    except KeyboardInterrupt:
        stop = "interrompida"
    finally:
        keep_computer_awake(False)
        try:
            adb("settings", "put", "global", "stay_on_while_plugged_in", stay_on or "0")
            access.off()
            adb("input", "keyevent", "KEYCODE_HOME")
        except Exception as e:
            print(f"não consegui restaurar o celular: {e!r}")
    minutes = (time.monotonic() - started) / 60
    print(f"\n{sum(results.values())} tarefas em {minutes:.0f} min · US$ {spent:.4f} · "
          + ", ".join(f"{k} {v}" for k, v in results.most_common()) + (f"\nparou: {stop}" if stop else ""))
    print()
    treino.status()
    return 1 if stop and not stop.startswith("orçamento") else 0


if __name__ == "__main__":
    sys.exit(main())
