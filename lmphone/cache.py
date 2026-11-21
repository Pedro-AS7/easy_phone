"""Cache de caminhos: o que o executor fez numa tarefa concluída, para repetir sem o provedor.

Guarda só rótulos de interface. Quem grava (o proxy) recusa tarefas que digitam texto, leem um valor
ou em que o mascaramento mudaria o pedido ou algum rótulo. A chave é o texto do pedido normalizado.
"""

import json
import os
import re
import time

from .executor import SCREEN_NAMES, plain, position

PATH = os.environ.get("LMPHONE_PATHS", "data/paths.json")
MAPS = os.environ.get("LMPHONE_MAPS", "data/maps.json")
MAX_FAILS = 2  # falhas seguidas até a entrada ser apagada
VERSION = 2  # formato do que é guardado: entradas de outra versão são ignoradas (a 1 não tinha o objetivo da tarefa)


def key(task):
    return " ".join(re.findall(r"\w+", plain(task)))


def _read(path=None):
    try:
        with open(path or PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _write(entries, path=None):
    path = path or PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)


def load(task):
    """(passos, objetivo) guardados para este pedido, ou None."""
    entry = _read().get(key(task))
    if not entry or entry.get("v") != VERSION:
        return None
    return [dict(step) for step in entry["steps"]], entry.get("goal")


def save(task, steps, goal=None):
    # Toques que não mudaram a tela ficam de fora; as marcas internas do executor também.
    steps = [{k: v for k, v in step.items() if k not in ("noop", "via", "seen")} for step in steps if not step.get("noop")]
    entries = _read()
    entries[key(task)] = {"v": VERSION, "steps": steps, "goal": goal, "fails": 0, "saved": time.strftime("%Y-%m-%d")}
    _write(entries)


def worked(task):
    """Uma repetição pelo cache deu certo: as falhas anteriores deixam de contar."""
    entries = _read()
    if entries.get(key(task), {}).get("fails"):
        entries[key(task)]["fails"] = 0
        _write(entries)


def failed(task):
    """Uma tarefa que partiu do cache não concluiu. Devolve True se a entrada foi apagada."""
    entries = _read()
    entry = entries.get(key(task))
    if not entry:
        return False
    entry["fails"] = entry.get("fails", 0) + 1
    if entry["fails"] >= MAX_FAILS:
        del entries[key(task)]
    _write(entries)
    return key(task) not in entries


def maps():
    """O mapa dos apps: {app: {"children": {rótulo tocado: nó}, "controls": [chaves desta tela]}}."""
    tree = _read(MAPS)
    return tree.get("apps", {}) if tree.get("v") == VERSION else {}


def learn(trail, keep=None):
    """Acrescenta ao mapa o caminho de uma tarefa concluída. Pedidos diferentes que passam pelas mesmas telas
    reaproveitam os ramos; o mapa guarda os rótulos tocados e os nomes curtos das telas por onde o caminho passou
    ("seen", só os que `keep` aceita: os que a máscara não trocaria), nunca textos longos nem dados pessoais."""
    tree = maps()
    for n, step in enumerate(trail, 1):
        screen = position(trail[:n - 1]) if step.get("seen") else None
        if screen and len(set(screen[1])) == len(screen[1]):
            here = tree.setdefault(screen[0], {"children": {}, "controls": []})
            for label in screen[1]:
                here = here["children"].setdefault(label, {"children": {}, "controls": []})
            seen = here.setdefault("seen", [])
            for label in step["seen"]:
                if label not in seen and len(seen) < SCREEN_NAMES and (keep is None or keep(label)):
                    seen.append(label)
        place = position(trail[:n])
        # Um rótulo repetido no caminho é um laço (abrir e fechar o mesmo menu), não uma tela mais funda.
        if not place or len(set(place[1])) < len(place[1]):
            continue
        node = tree.setdefault(place[0], {"children": {}, "controls": []})
        for label in place[1]:
            node = node["children"].setdefault(label, {"children": {}, "controls": []})
        if step["action"] in ("turn_on", "turn_off") and step["target"][0] not in node["controls"]:
            node["controls"].append(step["target"][0])
    _write({"v": VERSION, "apps": tree}, MAPS)
