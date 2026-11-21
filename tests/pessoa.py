"""Quem faz o papel da pessoa nos casos de guia da suíte (docs/plano-tutor.md, fase 1).

No guia, a faixa destaca o controle em que a pessoa deve tocar (o registro do live mode marca esse destaque com
"dono": true, `live.Live.highlight`). Este script lê o registro da tarefa em `logs/live/` enquanto ela roda e faz o que
a pessoa faria:

- "toca": toca no meio de cada destaque dela, um pouco depois de ele aparecer;
- "erra": no primeiro destaque, aperta Voltar em vez de tocar (o erro mais comum de quem tem dificuldade); depois, toca;
- "olha": não toca em nada (o agente faz, explicando).

Os toques vão pelo `adb shell input tap`: para o aparelho e para a faixa, são toques de verdade. O que ele fez fica
em `acoes`, para a conferência da suíte.
"""

import json
import os
import threading
import time

from lmphone.sources import adb

LIVE_DIR = "logs/live"
DELAY = 1.5  # segundos entre o destaque aparecer e a pessoa tocar
MODES = ("toca", "erra", "olha")


class Pessoa(threading.Thread):
    def __init__(self, mode, delay=DELAY):
        super().__init__(daemon=True)
        if mode not in MODES:
            raise ValueError(f"modo da pessoa desconhecido: {mode}")
        self.mode, self.delay = mode, delay
        self.before = set(os.listdir(LIVE_DIR)) if os.path.isdir(LIVE_DIR) else set()
        self.done = threading.Event()
        self.path = None
        self.acoes = []  # [{"tipo": "toque" | "voltar", "limites": [...], "t": segundos desde o começo}]
        self.started = time.monotonic()

    def stop(self):
        self.done.set()
        self.join(5)

    def _find(self):
        if not os.path.isdir(LIVE_DIR):
            return None
        new = [f for f in os.listdir(LIVE_DIR) if f.endswith(".jsonl") and f not in self.before]
        if not new:
            return None
        return os.path.join(LIVE_DIR, max(new, key=lambda f: os.path.getmtime(os.path.join(LIVE_DIR, f))))

    def run(self):
        offset, erred, pending = 0, False, None
        while not self.done.is_set():
            if self.path is None:
                self.path = self._find()
            if self.path:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        f.seek(offset)
                        lines = f.readlines()
                        offset = f.tell()
                except OSError:
                    lines = []
                for line in lines:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("tipo") == "destaque":
                        # Vale o último destaque: um novo (ou o fim dele) substitui o que estava para ser tocado.
                        bounds = row.get("limites")
                        pending = (bounds, time.monotonic()) if bounds and row.get("dono") else None
                    elif row.get("tipo") == "gesto":
                        # Um gesto para fazer (o painel rápido, rolar): vale como um destaque, feito com o dedo.
                        pending = (row["gesto"], time.monotonic()) if row.get("gesto") else None
            if pending and self.mode != "olha" and time.monotonic() - pending[1] >= self.delay:
                bounds, _ = pending
                pending = None
                elapsed = round(time.monotonic() - self.started, 1)
                if self.mode == "erra" and not erred:
                    erred = True
                    adb("input", "keyevent", "KEYCODE_BACK")
                    self.acoes.append({"tipo": "voltar", "limites": bounds, "t": elapsed})
                elif isinstance(bounds, str):
                    path = ("540", "5", "540", "1200") if bounds == "puxar" else ("540", "1600", "540", "800")
                    adb("input", "swipe", *path, "500")
                    self.acoes.append({"tipo": "toque", "gesto": bounds, "t": elapsed})
                else:
                    x, y = (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
                    adb("input", "tap", str(x), str(y))
                    self.acoes.append({"tipo": "toque", "limites": bounds, "t": elapsed})
            self.done.wait(0.3)


def read_log(session):
    """As linhas do registro do live mode da sessão, ou [] (valores reais: confira, não imprima)."""
    path = os.path.join(LIVE_DIR, f"{session}.jsonl")
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows
