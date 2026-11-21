"""A pessoa simulada do app da loja (docs/plano-play-store.md): manda um pedido ao cérebro no celular (o `DebugTask` do
build de depuração) e faz o que o guia pede, lendo o registro do live mode que o app grava no próprio aparelho.

- um destaque para a pessoa ("dono": true): toca no meio dele;
- o botão da faixa ("usuario_botao_limites"): toca nele;
- um gesto ("rolar", "puxar"): faz o gesto.

Os toques são do `adb shell input`, como os de uma pessoa: o app não os distingue. No fim, confere no registro que o
agente não fez nenhuma ação ("acao" com "por" diferente de "dono" e ferramenta diferente de "wait"/"complete") e
imprime só os tipos de evento e as falas (o guia não lê dados pessoais nos casos de teste: telas das Configurações).

    .venv/bin/python -m tests.pessoa_loja "Como eu aumento a letra do celular?"
"""

import json
import re
import subprocess
import sys
import time

APP = "dev.pedro.lmphone.guia"
LIVE = "files/cerebro/logs/live"
DELAY = 1.5
LIMIT = 300


def adb(*args, timeout=30):
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout).stdout


def logs():
    return set(adb("shell", "run-as", APP, "ls", LIVE).split())


def rows(name):
    out = []
    for line in adb("exec-out", "run-as", APP, "cat", f"{LIVE}/{name}").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def rodar(request, erra=False, limit=LIMIT):
    """Manda o pedido e faz o que o guia pede até o fim (ou `limit` segundos). Com `erra`, no primeiro destaque ela
    aperta Voltar em vez de tocar (o erro mais comum de quem tem dificuldade, como em tests/pessoa.py). Devolve (as linhas
    do registro do live mode, o que ela fez, se o guia terminou)."""
    before = logs()
    adb("shell", "am", "broadcast", "-n", f"{APP}/dev.pedro.lmphone.DebugTask", "--es", "pedido", f"'{request}'")
    started, name, done, actions, kind_of, erred, current = time.monotonic(), None, 0, [], None, False, []
    active = None  # (o que está na faixa, o tipo): o guia falar de novo sem mudar a faixa é pedir de novo
    said = ""  # a última fala: ela segue a instrução (puxar pelo lado direito só se a fala disser)
    while time.monotonic() - started < limit:
        time.sleep(1.0)
        if name is None:
            new = sorted(logs() - before)
            if not new:
                continue
            name = new[-1]
        current = rows(name)
        pending = None
        for row in current[done:]:
            kind = row.get("tipo")
            # O que está pendente e de que tipo: a linha "botao" sem texto (o botão saiu da faixa) só tira um botão; ela vem
            # no mesmo instante que o destaque ou o gesto seguinte, e tirava também eles (2026-11-18: 214 s no «Som»;
            # 2026-11-19: o gesto de subir a tela, e a pessoa ficou parada).
            if kind == "destaque":
                pending, kind_of = (row.get("limites"), "destaque") if row.get("dono") else (None, None)
                active = (pending, kind_of) if pending else active if active and active[1] != "destaque" else None
            elif kind == "usuario_botao_limites":
                pending, kind_of = row.get("limites"), "botao"
                active = (pending, kind_of)
            elif kind == "botao" and not row.get("texto"):
                if kind_of == "botao":
                    pending, kind_of = None, None
                if active and active[1] == "botao":
                    active = None
            elif kind == "gesto":
                pending, kind_of = row.get("gesto"), "gesto" if row.get("gesto") else None
                active = (pending, kind_of) if pending else active if active and active[1] != "gesto" else None
            if kind == "fala":
                said = row.get("texto") or ""
                if active is None and pending is None and re.search(r"\b(voltar|volte)\b", said, re.I) and \
                        re.search(r"setinha|seta|bot[aã]o de voltar", said, re.I):
                    pending, kind_of = "voltar", "voltar"  # sem destaque: ela aperta o voltar do celular
            if kind == "fala" and pending is None and active is not None:
                # "Mais um pouco: arraste de novo", "Estou esperando você...": a faixa não mudou, e ela faz de novo.
                pending, kind_of = active
            elif kind == "fim":
                return current, actions, True
        done = len(current)
        # Só um botão sai da faixa com a linha "botao" sem texto; ela vem no mesmo instante que o destaque seguinte, e
        # tirava também o destaque (2026-11-18: a pessoa esperou 214 s no «Som»).
        if pending and kind_of == "botao" and still_gone(current, pending):
            pending = None
        if pending:
            time.sleep(DELAY)
            # O que estava na faixa pode ter saído nesse tempo (2026-11-19: o destaque saiu, a faixa voltou para cima dele,
            # e o toque repetido caiu no botão de pausa): ela olha de novo antes.
            later = rows(name)[done:]
            if any(r.get("tipo") in ("destaque", "gesto", "botao", "fim") for r in later):
                continue
            if erra and not erred and kind_of == "destaque":
                adb("shell", "input", "keyevent", "KEYCODE_BACK")
                actions.append("volta (o erro de propósito)")
                erred = True
            elif pending == "voltar":
                adb("shell", "input", "keyevent", "KEYCODE_BACK")
                actions.append("aperta voltar")
            elif isinstance(pending, str):
                # Puxar: do alto da tela abre as notificações; com elas abertas, ela puxa de novo em cima delas, que é o
                # que abre os atalhos (o mesmo gesto do alto não abre: 2026-11-19, no guia da lanterna).
                right = pending == "puxar_direita" or "direit" in said.lower()
                path = ("540", "1600", "540", "800") if not pending.startswith("puxar") else \
                    ("900", "5", "900", "1200") if right else ("540", "5", "540", "1200")
                adb("shell", "input", "swipe", *path, "500")
                actions.append(f"gesto {pending}")
            else:
                x, y = (pending[0] + pending[2]) // 2, (pending[1] + pending[3]) // 2
                adb("shell", "input", "tap", str(x), str(y))
                actions.append(f"toque em {pending}")
    return current, actions, False


def main(request):
    current, actions, finished = rodar(request)
    if not finished:
        print("passou do limite sem o fim")
        return 1
    report(current, actions)
    return 0


def still_gone(current, pending):
    """O botão de `pending` saiu da faixa depois de aparecer (a linha "botao" sem texto veio depois dos limites)."""
    last = max((i for i, r in enumerate(current) if r.get("limites") == pending), default=-1)
    return any(r.get("tipo") == "botao" and not r.get("texto") for r in current[last + 1:])


def report(current, actions):
    agent = [r for r in current if r.get("tipo") == "acao" and r.get("por") != "dono"
             and r.get("ferramenta") not in ("wait", "complete")]
    for row in current:
        kind = row.get("tipo")
        if kind in ("fala", "fim", "botao", "destaque", "gesto", "usuario_toque_tela", "usuario_botao_tocado"):
            text = row.get("texto") or row.get("mensagem") or row.get("limites") or row.get("gesto") or ""
            print(f"{kind}: {text}" if kind != "fim" else f"fim ({row.get('resultado')}): {text}")
    print(f"a pessoa fez: {actions}")
    print("ações do agente:", agent if agent else "nenhuma")


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:]) or "Como eu aumento a letra do celular?"))
