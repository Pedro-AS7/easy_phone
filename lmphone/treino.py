"""Coleta de dados de treino para os modelos pequenos (etapa 1 de docs/plano-modelos-pequenos.md).

Com LMPHONE_COLETA=1 no ambiente de quem pede a tarefa, o serviço grava em data/treino/real/, um arquivo por dia:
o pedido (com o julgamento da Gemma), os trechos novos de cada tela com o app em primeiro plano, o que o Laya e a
Gemma acharam dos trechos que julgaram, e cada escolha de controle, com quem decidiu e o efeito conferido na tela.
São dados reais: ficam na máquina (modo 600) e o `status` mostra só contagens.

Uso: python -m lmphone.treino status
"""

import glob
import json
import os
import sys
import time
from collections import Counter

DIR = "data/treino/real"


def record(session, kind, **fields):
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    path = os.path.join(DIR, time.strftime("%Y-%m-%d") + ".jsonl")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "session": session, "tipo": kind, **fields}, ensure_ascii=False) + "\n")


def entries():
    for path in sorted(glob.glob(os.path.join(DIR, "*.jsonl"))):
        if not os.path.basename(path)[:4].isdigit():  # só a coleta (AAAA-MM-DD.jsonl); o resto é do professor
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def status():
    """Contagens por tipo, por app e por fonte, sem conteúdo."""
    kinds, sessions, apps, unique = Counter(), set(), Counter(), set()
    choices, outcomes = Counter(), Counter()
    for entry in entries():
        kinds[entry["tipo"]] += 1
        sessions.add(entry["session"])
        if entry["tipo"] == "trecho":
            apps[entry.get("app") or "?"] += 1
            unique.add(entry["texto"])
        elif entry["tipo"] == "escolha":
            choices[entry["por"]] += 1
            outcomes[(entry["por"], entry["efeito"])] += 1
    print(f"{len(sessions)} tarefas · {kinds['pedido']} pedidos · {kinds['trecho']} trechos ({len(unique)} distintos) · "
          f"{kinds['escolha']} escolhas de controle · {kinds['julgamento']} julgamentos de tela")
    if apps:
        print("\ntrechos por app:")
        for app, n in apps.most_common():
            print(f"  {n:6}  {app}")
    if choices:
        print("\nescolhas por fonte e efeito:")
        for by, n in choices.most_common():
            detail = ", ".join(f"{effect or 'sem efeito'} {count}" for (who, effect), count in sorted(
                outcomes.items(), key=lambda item: -item[1]) if who == by)
            print(f"  {n:6}  {by} ({detail})")


if __name__ == "__main__":
    if sys.argv[1:] != ["status"]:
        sys.exit(__doc__.strip().splitlines()[-1])
    status()
