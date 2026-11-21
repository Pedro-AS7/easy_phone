"""Trilhas do executor, para conferir o cérebro em Kotlin contra este (etapa 3 de docs/plano-app-android.md).

Com o gravador instalado (`install`), cada chamada de fora a um executor (`use`, `prepare`, `step`, `confirm_answer`) e
a algumas funções do módulo vira uma linha JSON: o estado inteiro do executor antes, os argumentos, tudo o que ele
pediu de fora durante a chamada (o prompt ao provedor e a resposta, o modelo de escolha, os fatos, abrir app, a
página das Configurações, o ajuste direto, a pesquisa, o relógio), o que devolveu e o estado depois. A conferência em
Kotlin (`android\\gradlew.bat :cerebro:conferir`) parte de cada estado, responde com o que foi gravado e confere que
pediu os mesmos textos, devolveu o mesmo e chegou ao mesmo estado.

O estado vai como JSON: dicionários com as chaves na ordem, listas, conjuntos em {"$set": [...]} ordenados, elementos
da tela em {"$el": [...]}, funções em {"$fn": true}. Um dicionário que aparece em dois lugares (o passo do plano que
também está em `pending`) vai uma vez, em {"$id": n, "$v": ...}, e depois em {"$ref": n}.

Os testes do executor e do proxy gravam com `tools/app/cerebro.py trilhas` (dados fictícios); o serviço grava as
tarefas de verdade com LMPHONE_TRILHA=1 em logs/trilhas/<sessão>.jsonl (telas reais, modo 600, só nesta máquina).
"""

import difflib
import functools
import itertools
import json
import os
import threading
import time as real_time

from . import executor as ex
from . import device as dv
from . import facts as fx

# Os atributos do executor, na ordem do __init__ (o Kotlin os lê e escreve com os mesmos nomes).
ATTRS = ("task", "provider", "pick", "device", "settings", "setter", "history", "assistant", "replied", "looking", "looked",
         "opening", "announce", "guide", "guide_waited", "was_met", "speaking", "searching", "searched", "searcher",
         "rolling", "rolled", "read_value", "final", "owner", "waiting", "highlight", "gesture", "owner_steps", "guide_agent", "acts", "button", "last_said", "reminded_step", "lost", "quick", "rerouting", "no_buttons", "unmet_asked", "seen", "off_names", "pressed_at", "touched_text", "touched_text_at", "touched_box", "touched_at", "nudged", "start_state", "confirming",
         "approved", "declined", "preapproved", "facts", "state", "early", "acted", "repeats", "flagged", "last_key",
         "message", "raw", "instructions", "can_ask", "may_ask", "questions", "question", "answers", "opened", "tried",
         "stuck", "launch", "plan", "goal", "i", "scrolls", "swiped", "pending", "helps", "waited", "waits", "asked",
         "torn", "elements", "labels", "now", "sign", "before", "start", "guess", "focused", "blind", "again",
         "goal_asked", "switched", "confirmed", "map", "tapped", "trail_len", "trail", "cacheable", "tool_error",
         "result", "by", "choices", "noted", "choice", "app", "cached", "reviewed", "reviews")
CALLBACKS = ("provider", "pick", "launch", "facts", "settings", "setter", "searcher")
METHODS = ("use", "prepare", "step", "confirm_answer")
FUNCTIONS = {ex: ("plain", "sensitive", "yes_no", "leaves_settings", "mentions", "matches", "signature", "parse_screen",
                  "redact", "position", "node_at", "search", "related", "render", "close_names", "call", "parse_json"),
             fx: ("describe", "speak", "network_key", "distance", "same_network", "met"),
             dv: ("elements_of", "one_line", "render", "uncovered", "point", "parse_call"),
             difflib: ("get_close_matches",)}
STATICS = ("read", "guided", "find", "control", "flips", "checked", "locate", "locator", "visible")

_local = threading.local()
_ids = itertools.count(1)
_lock = threading.Lock()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _count(value, counts):
    if isinstance(value, dict):
        counts[id(value)] = counts.get(id(value), 0) + 1
        if counts[id(value)] == 1:
            for item in value.values():
                _count(item, counts)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _count(item, counts)


def encode(value, memo=None, counts=None):
    memo = {} if memo is None else memo
    if isinstance(value, ex.Element):
        return {"$el": [value.index, value.cls, list(value.texts), value.checked, list(value.bounds), list(value.ids)]}
    if isinstance(value, dict):
        if id(value) in memo:
            return {"$ref": memo[id(value)]}
        shared = counts is not None and counts.get(id(value), 0) > 1
        if shared:
            memo[id(value)] = len(memo)
        body = {str(k): encode(v, memo, counts) for k, v in value.items()}
        return {"$id": memo[id(value)], "$v": body} if shared else body
    if isinstance(value, (list, tuple)):
        return [encode(v, memo, counts) for v in value]
    if isinstance(value, (set, frozenset)):
        return {"$set": sorted((encode(v, memo, counts) for v in value), key=canonical)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if callable(value):
        return {"$fn": True}
    return {"$repr": repr(value)}


def snapshot(executor):
    values = [getattr(executor, name, None) for name in ATTRS]
    counts = {}
    for value in values:
        _count(value, counts)
    memo = {}
    return {name: encode(value, memo, counts) for name, value in zip(ATTRS, values)}


class Recorder:
    """Grava as trilhas num arquivo JSONL (modo 600)."""

    def __init__(self, path):
        self.path = path  # o arquivo, ou uma função que o dá (no serviço, um por sessão)

    def write(self, entry):
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        path = self.path() if callable(self.path) else self.path
        os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
        with _lock:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)


def _depth():
    return getattr(_local, "depth", 0)


def _event(entry):
    events = getattr(_local, "events", None)
    if events is not None:
        events.append(entry)


class _Clock:
    """O `time` do módulo do executor: o `monotonic` lido vai para a trilha."""

    def __getattr__(self, name):
        return getattr(real_time, name)

    @staticmethod
    def monotonic():
        value = real_time.monotonic()
        _event({"cb": "clock", "ret": value})
        return value


def _wrap_callback(name, original):
    @functools.wraps(original)
    def recorded(*args):
        try:
            value = original(*args)
        except Exception as e:
            _event({"cb": name, "args": encode(list(args)), "raise": type(e).__name__})
            raise
        _event({"cb": name, "args": encode(list(args)), "ret": encode(value)})
        return value
    return recorded


def _function(qualified, original, recorder):
    @functools.wraps(original)
    def recorded(*args, **kwargs):
        if _depth():
            return original(*args, **kwargs)
        _local.depth = 1
        try:
            try:
                value = original(*args, **kwargs)
            except Exception as e:
                recorder.write({"fn": qualified, "args": encode(list(args)), "kwargs": encode(kwargs), "raise": type(e).__name__})
                raise
        finally:
            _local.depth = 0
        recorder.write({"fn": qualified, "args": encode(list(args)), "kwargs": encode(kwargs), "ret": encode(value)})
        return value
    return recorded


def install(path):
    """Instala o gravador no executor (e nas funções de fatos que ele usa). Devolve uma função que o desinstala."""
    recorder = Recorder(path)
    undo = []

    def patch(owner, name, new):
        old = owner.__dict__[name] if isinstance(owner, type) else getattr(owner, name)
        undo.append((owner, name, old))
        setattr(owner, name, new)

    for name in METHODS:
        original = ex.Executor.__dict__[name]
        patch(ex.Executor, name, _method_value(name, original, recorder))
    for name in STATICS:
        raw = ex.Executor.__dict__[name]
        # Um classmethod recebe a classe: ela fica fora dos argumentos gravados.
        function = raw.__func__ if isinstance(raw, staticmethod) else functools.partial(raw.__func__, ex.Executor)
        patch(ex.Executor, name, staticmethod(_function(f"Executor.{name}", function, recorder)))
    for module, names in FUNCTIONS.items():
        prefix = {ex: "executor", fx: "facts", dv: "device", difflib: "difflib"}[module]
        for name in names:
            patch(module, name, _function(f"{prefix}.{name}", getattr(module, name), recorder))
    patch(ex, "time", _Clock())

    def uninstall():
        for owner, name, old in reversed(undo):
            setattr(owner, name, old)
    return uninstall


def _method_value(name, original, recorder):
    """O método gravado, devolvendo o mesmo valor (e levantando a mesma exceção) que o original."""
    @functools.wraps(original)
    def recorded(self, *args, **kwargs):
        if _depth():
            return original(self, *args, **kwargs)
        if not hasattr(self, "_trilha"):
            self._trilha = next(_ids)
        entry = {"exec": self._trilha, "call": name, "args": encode(list(args)), "kwargs": encode(kwargs),
                 "before": snapshot(self)}
        saved = {cb: getattr(self, cb, None) for cb in CALLBACKS}
        for cb, fn in saved.items():
            if fn is not None:
                setattr(self, cb, _wrap_callback(cb, fn))
        _local.depth, _local.events = 1, []
        error, value = None, None
        try:
            value = original(self, *args, **kwargs)
        except Exception as e:
            error = e
        finally:
            entry["events"], _local.depth, _local.events = _local.events, 0, None
            for cb, fn in saved.items():
                if fn is not None:
                    setattr(self, cb, fn)
        if error is not None:
            entry["raise"] = type(error).__name__
        else:
            entry["ret"] = encode(value)
        entry["after"] = snapshot(self)
        recorder.write(entry)
        if error is not None:
            raise error
        return value
    return recorded
