"""Compara variantes do Laya nos casos de tests/laya_cases.py: acerto, tempo por decisão e memória.

Roda no venv do Laya, uma variante por processo (a memória medida é a do processo inteiro):
    .venv-laya/bin/python -m tests.eval_laya              # todas as variantes
    .venv-laya/bin/python -m tests.eval_laya ingles       # só uma

O codificador em 8 bits (PyTorch) foi medido e descartado: a memória não caiu e o acerto piorou.
"""
import json
import os
import subprocess
import sys
import time

from lmphone import host

VARIANTS = ["auto", "ingles", "multi"]
MIN_P = 0.5
GATE = 0.15


def rss_mb():
    return int(sum(host.memory_mb(os.getpid())))


def run(variant):
    os.environ["LMPHONE_LAYA_MODEL"] = {"auto": "auto", "ingles": "english", "multi": "multilingual"}[variant]
    from lmphone import laya_server as server
    from tests.laya_cases import FRAGMENTS, FRAGMENTS_PT, PICKS

    start = time.monotonic()
    server.pick(["Menu"], ["Options", "Back"])
    load = time.monotonic() - start

    right_present = right_absent = wrong_tap = 0
    seconds = []
    for wanted, labels, expected in PICKS:
        answer = server.pick(wanted, labels)
        seconds.append(answer["seconds"])
        if expected is None:
            right_absent += answer["label"] is None
        else:
            right_present += answer["label"] == expected
        wrong_tap += answer["label"] not in (None, expected)

    answer = server.private([text for text, _ in FRAGMENTS])
    lost = sum(1 for (_, person), p in zip(FRAGMENTS, answer["p"]) if person and p < GATE)
    dropped = sum(1 for (_, person), p in zip(FRAGMENTS, answer["p"]) if not person and p < GATE)
    pt = server.private([text for text, _ in FRAGMENTS_PT])
    lost_pt = sum(1 for (_, person), p in zip(FRAGMENTS_PT, pt["p"]) if person and p < GATE)
    dropped_pt = sum(1 for (_, person), p in zip(FRAGMENTS_PT, pt["p"]) if not person and p < GATE)
    return {
        "variante": variant, "carga_s": round(load, 1), "mb": rss_mb(),
        "pico_mb": host.peak_mb(),
        "presentes": f"{right_present}/{sum(1 for c in PICKS if c[2])}",
        "ausentes": f"{right_absent}/{sum(1 for c in PICKS if not c[2])}", "toques_errados": wrong_tap,
        "s_por_escolha": round(sum(seconds) / len(seconds), 2),
        "pessoas_perdidas": f"{lost}/{sum(1 for _, p in FRAGMENTS if p)}",
        "rotulos_descartados": f"{dropped}/{sum(1 for _, p in FRAGMENTS if not p)}",
        "s_por_trecho": round(answer["seconds"] / len(FRAGMENTS), 3),
        "pt_pessoas_perdidas": f"{lost_pt}/{sum(1 for _, p in FRAGMENTS_PT if p)}",
        "pt_rotulos_descartados": f"{dropped_pt}/{sum(1 for _, p in FRAGMENTS_PT if not p)}",
        "pesos": server.router.loaded, "mb_final": rss_mb(),
    }


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--uma":
        print(json.dumps(run(sys.argv[2]), ensure_ascii=False))
        sys.exit()
    for variant in sys.argv[1:] or VARIANTS:
        out = subprocess.run([sys.executable, "-m", "tests.eval_laya", "--uma", variant], capture_output=True, text=True)
        print(out.stdout.strip().splitlines()[-1] if out.returncode == 0 and out.stdout.strip() else f"{variant}: falhou\n{out.stderr[-1500:]}")
