"""O celular: a tela é lida do Portal pelo content provider (`adb shell content query`), a digitação vai ao servidor HTTP
dele (porta trazida por `adb forward`) e os gestos vão pelo adb. Com LMPHONE_DEVICE=app, tudo vai ao app do lm_phone
(`android/`, `AppDevice`): a tela no mesmo JSON do Portal, os gestos, a digitação e as teclas pelo serviço de
acessibilidade dele.

A tela sai no mesmo texto que o Mobilerun entrega sem visão (filtro detalhado e formato indexado), porque é esse
texto que o executor, a IA local, o mascaramento e o cache já leem. `tests/test_device.py` fixa o formato.
"""

import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

from .access import APP, KEYBOARD, PORTAL, USE_APP

PORTAL_PORT = 8080  # no aparelho
GBOARD = "com.google.android.inputmethod.latin:id/"  # as teclas do teclado do Google não entram na tela
MIN_VISIBLE = 0.1  # fração do elemento que precisa estar dentro da tela
KEYS = {"back": 4, "home": 3, "enter": 66}
HEADER = "Current Clickable UI elements:\n'index. className: resourceId; checkedState, text - bounds(x1,y1,x2,y2)':\n"


def adb(*args, timeout=15):
    result = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"adb {args[0]}: {(result.stderr or result.stdout).strip()[:200]}")
    return result.stdout


def _unwrap(data):
    """O Portal embrulha a resposta em {"status", "result"}; o resultado pode vir como texto JSON."""
    if isinstance(data, dict) and data.get("status") == "error":
        raise RuntimeError(f"o Portal respondeu erro: {str(data.get('error'))[:200]}")
    inner = data.get("result", data.get("data", data)) if isinstance(data, dict) else data
    if isinstance(inner, str):
        try:
            return json.loads(inner)
        except ValueError:
            pass
    return inner


def _box(node):
    bounds = node.get("boundsInScreen") or {}
    return tuple(bounds.get(side, 0) for side in ("left", "top", "right", "bottom"))


def _visible(node, width, height):
    """Fração do elemento dentro da tela."""
    if node.get("boundsInScreen") is None:
        return 0.0
    left, top, right, bottom = _box(node)
    if right - left == 0 and bottom - top == 0:
        return 0.0
    if left <= 0 and top <= 0 and right >= width and bottom >= height:
        return 1.0
    area = (right - left) * (bottom - top)
    seen = max(0, min(right, width) - max(left, 0)) * max(0, min(bottom, height) - max(top, 0))
    return seen / area if area > 0 else 0.0


def _without_keyboard(node):
    children = [kept for kept in map(_without_keyboard, node.get("children") or []) if kept is not None]
    return None if (node.get("resourceId") or "").startswith(GBOARD) else {**node, "children": children}


def _on_screen(node, width, height):
    """Tira o que está fora da tela; um elemento fora dela fica se algum filho está dentro."""
    if node.get("ignoreBoundsFiltering") == "true":
        return node
    children = [kept for kept in (_on_screen(child, width, height) for child in node.get("children") or []) if kept is not None]
    if _visible(node, width, height) < MIN_VISIBLE and not children:
        return None
    return {**node, "children": children}


def _overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _flatten(node, counter, out):
    """Numera os elementos na ordem da árvore, a partir de 1. Um irmão clicável desenhado por cima, na mesma
    janela, fica anotado como obstáculo do toque."""
    cls = node.get("className") or ""
    element = {"index": counter[0], "id": node.get("resourceId") or "", "cls": cls.split(".")[-1] if cls else "",
               "checked": ("isChecked=True" if node.get("isChecked") else "isChecked=False") if node.get("isCheckable") else "",
               "text": node.get("text") or node.get("contentDescription") or node.get("resourceId") or cls,
               "bounds": _box(node), "blockers": []}
    out.append(element)
    counter[0] += 1
    siblings = [(child, _flatten(child, counter, out)) for child in node.get("children") or []]
    for raw, mine in siblings:
        order, window = raw.get("drawingOrder"), raw.get("windowId")
        if not isinstance(order, int) or not isinstance(window, int) or window < 0:
            continue
        for other, theirs in siblings:
            above = other.get("drawingOrder")
            if (other.get("windowId") == window and isinstance(above, int) and above > order
                    and other.get("isVisibleToUser") is not False
                    and (other.get("isClickable") or other.get("isLongClickable"))
                    and _overlap(mine["bounds"], theirs["bounds"])):
                mine["blockers"].append(theirs["bounds"])
    return element


def elements_of(state):
    """Os elementos da tela, já filtrados e numerados, a partir do que o Portal devolve em `/state_full`."""
    screen = (state.get("device_context") or {}).get("screen_bounds") or {}
    width, height = screen.get("width", 1080), screen.get("height", 2400)
    tree = _without_keyboard(state["a11y_tree"])
    tree = _on_screen(tree, width, height) if tree is not None else None
    out = []
    if tree is not None:
        _flatten(tree, [1], out)
    return out


def one_line(text):
    """Um elemento é uma linha do texto da tela: a quebra de linha dentro do texto dele (os dois parágrafos de uma nota,
    uma mensagem) partia a linha, e o executor deixava de ver o elemento, até o campo em que ele mesmo digitou."""
    return re.sub(r"\s*[\r\n]+\s*", " ", text)


def render(state, elements):
    """A tela como texto, no formato do Mobilerun: o que vai dentro de `<device_state>`."""
    phone = state.get("phone_state") or {}
    app, package = phone.get("currentApp", ""), phone.get("packageName", "")
    focused = one_line((phone.get("focusedElement") or {}).get("text") or "")
    lines = ["**Current Phone State:**"]
    if app or package:
        lines.append(f"• **App:** {app} ({package})" if app and package else f"• **App:** {app or package}")
    lines += [f"• **Keyboard:** {'Visible' if phone.get('isEditable') else 'Hidden'}", f"• **Focused Element:** '{focused}'"]
    rows = []
    for e in elements:
        details = ", ".join(f'"{one_line(value)}"' for value in (e["id"], e["text"]) if value)
        parts = [f"{e['index']}.", e["cls"] + ":" if e["cls"] else "", details, f"; {e['checked']}" if e["checked"] else "",
                 "- ({},{},{},{})".format(*e["bounds"])]
        rows.append(" ".join(part for part in parts if part))
    return ("\n".join(lines) + "\n\n" + HEADER + ("\n".join(rows) if rows else "No UI elements found")).strip()


def uncovered(bounds, blockers):
    """Centro do maior retângulo de `bounds` que nenhum obstáculo cobre, ou None."""
    regions = [bounds] if bounds[0] < bounds[2] and bounds[1] < bounds[3] else []
    for blocker in blockers:
        remaining = []
        for left, top, right, bottom in regions:
            bl, bt, br, bb = max(left, blocker[0]), max(top, blocker[1]), min(right, blocker[2]), min(bottom, blocker[3])
            if bl >= br or bt >= bb:
                remaining.append((left, top, right, bottom))
                continue
            remaining += [r for r in ((left, top, right, bt), (left, bb, right, bottom), (left, bt, bl, bb), (br, bt, right, bb))
                          if r[0] < r[2] and r[1] < r[3]]
        regions = remaining
    if not regions:
        return None
    left, top, right, bottom = max(regions, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    return (left + right) // 2, (top + bottom) // 2


def point(element, width=None, height=None):
    """Onde tocar no elemento: o centro, ou um ponto livre se o centro está coberto por outro controle."""
    left, top, right, bottom = element["bounds"]
    x, y = (left + right) // 2, (top + bottom) // 2
    if not any(l <= x < r and t <= y < b for l, t, r, b in element["blockers"]):
        return x, y
    if width and height:
        left, top, right, bottom = max(0, left), max(0, top), min(width, right), min(height, bottom)
    clear = uncovered((left, top, right, bottom), element["blockers"])
    if clear is None:
        raise ValueError(f"No clear tap point for element {element['index']}")
    return clear


def parse_call(text):
    """(nome, parâmetros) da chamada de ferramenta que o executor escreve (ver `call` em executor.py)."""
    name = re.search(r'<invoke name="([\w-]+)">', text)
    if not name:
        return None, {}
    return name.group(1), dict(re.findall(r'<parameter name="(\w+)">(.*?)</parameter>', text[name.end():], re.S))


class Device:
    """Um aparelho ligado por adb, com o Portal instalado. O serviço de acessibilidade dele só fica ligado durante a
    tarefa (ver access.py)."""

    def __init__(self):
        self.base, self.token = None, None
        self.elements, self.size, self.package = [], (None, None), None

    def _token(self):
        out = adb("shell", "content", "query", "--uri", f"content://{PORTAL}/auth_token")
        token = _unwrap(json.loads(out[out.index("result=") + 7:])) if "result=" in out else None
        if isinstance(token, dict):
            token = token.get("token") or token.get("auth_token")
        return token if isinstance(token, str) else None

    def connect(self):
        """Pega a senha do servidor HTTP do Portal (só o adb a alcança) e a porta local que leva até ele."""
        self.token = self._token()
        forward = re.search(rf"tcp:(\d+) tcp:{PORTAL_PORT}\b", adb("forward", "--list"))
        port = forward.group(1) if forward else adb("forward", "tcp:0", f"tcp:{PORTAL_PORT}").strip()
        self.base = f"http://127.0.0.1:{port}"
        try:
            self._send("/ping", timeout=5)
        except Exception:
            # O servidor HTTP do Portal pode estar desligado: liga e tenta de novo (a senha pode mudar).
            adb("shell", "content", "insert", "--uri", f"content://{PORTAL}/toggle_socket_server", "--bind", "enabled:b:true")
            time.sleep(1)
            self.token = self._token()
            self._send("/ping", timeout=5)

    def _send(self, path, body=None, timeout=10):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _unwrap(json.load(response))

    def request(self, path, body=None, timeout=10):
        """Um pedido ao Portal. Se a ligação caiu (cabo, Portal reiniciado, senha trocada), liga de novo uma vez."""
        if self.base is None:
            self.connect()
        try:
            return self._send(path, body, timeout)
        except (urllib.error.URLError, OSError, ValueError):
            self.connect()
            return self._send(path, body, timeout)

    def state(self):
        """A tela crua, pelo content provider do Portal. Pelo servidor HTTP atrás do `adb forward` seria 0,2 s em vez de
        1,1 s, mas em telas grandes a segunda leitura seguida travava o adb inteiro por até 4 minutos (CLAUDE.md,
        "Limites conhecidos"); por aqui, 25 de 25 sem travar."""
        out = adb("shell", "content", "query", "--uri", f"content://{PORTAL}/state_full", timeout=30)
        if "result=" not in out:
            raise RuntimeError(f"o Portal não devolveu a tela: {out.strip()[:200]}")
        return _unwrap(json.loads(out[out.index("result=") + 7:]))

    def read(self):
        """Lê a tela e devolve o texto dela. Os elementos ficam guardados para os toques por índice."""
        state = self.state()
        missing = [key for key in ("a11y_tree", "phone_state", "device_context") if key not in (state if isinstance(state, dict) else {})]
        if missing:
            raise RuntimeError(f"o Portal não devolveu {', '.join(missing)}")
        screen = state["device_context"].get("screen_bounds") or {}
        self.elements, self.size = elements_of(state), (screen.get("width"), screen.get("height"))
        self.package = state["phone_state"].get("packageName")
        return render(state, self.elements)

    def keyboard(self):
        """Põe o teclado do Portal como o ativo: é por ele que o texto é digitado, e o teclado comum não cobre a tela."""
        adb("shell", f"ime enable {KEYBOARD}; ime set {KEYBOARD}")

    def tap(self, index):
        element = next((e for e in self.elements if e["index"] == index), None)
        if element is None:
            raise ValueError(f"No element with index {index} on the current screen")
        x, y = point(element, *self.size)
        adb("shell", "input", "tap", str(x), str(y))

    def type(self, text, clear=False):
        try:
            self.request("/keyboard/input", {"base64_text": base64.b64encode(text.encode()).decode(), "clear": clear})
        except RuntimeError as e:
            # O Portal digitou, mas não conseguiu reler o campo para conferir (visto no Notion). Não é falha de
            # digitação: quem confere o texto na tela é o executor, na leitura seguinte.
            if "accepted via IME" not in str(e):
                raise

    def act(self, name, params):
        """Executa uma ação do executor. Devolve None, ou o texto do erro se ela não foi feita."""
        try:
            if name == "click":
                self.tap(int(params["index"]))
            elif name == "swipe":
                (x1, y1), (x2, y2) = json.loads(params["coordinate"]), json.loads(params["coordinate2"])
                # O gesto leva `duration`; a espera pela tela parar fica com o ciclo.
                adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(int(float(params.get("duration", 1.0)) * 1000)))
            elif name == "type":
                self.type(params.get("text", ""), params.get("clear") == "true")
            elif name == "system_button" and params["button"].lower() == "quick_settings":
                adb("shell", "cmd", "statusbar", "expand-settings")
            elif name == "system_button":
                adb("shell", "input", "keyevent", str(KEYS[params["button"].lower()]))
            elif name == "wait":
                time.sleep(float(params.get("duration", 1.0)))
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Failed to {name}: {e}"
        return None


class AppDevice(Device):
    """O aparelho pelo app do lm_phone (`android/`): o serviço de acessibilidade dele atende num servidor local e só
    responde com a senha que o app guarda no próprio armazenamento (lida por `run-as`). A tela vem no mesmo JSON do
    `state_full` do Portal; as ações vão pelo serviço, sem `input` do adb nem teclado próprio.

    O pedido não vai pelo `adb forward`: com ele (2026-10-19), o adb inteiro travou por até 5 minutos em casos que
    digitam e leem telas grandes, como com o servidor do Portal na pv1. Vai por um `adb exec-out` que passa o pedido ao
    `nc` do aparelho, um canal de shell comum como o do content provider, que nunca travou. Uma tela de 63 KB leva uns
    0,1 s por aqui (o content provider do Portal, 1,1 s)."""

    PORT = 8081  # no aparelho (AgentService.PORT)
    TOKEN = None  # a senha não muda: lida uma vez por processo

    def connect(self):
        if AppDevice.TOKEN is None:
            AppDevice.TOKEN = adb("shell", "run-as", APP, "cat", "files/token").strip() or None
        self.token, self.base = AppDevice.TOKEN, "exec-out"
        self._send("/ping", timeout=5)

    def _send(self, path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else b""
        head = (f"{'POST' if body is not None else 'GET'} {path} HTTP/1.1\r\nHost: lmphone\r\n"
                f"Authorization: Bearer {self.token}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode()
        packed = base64.b64encode(head + data).decode()
        result = subprocess.run(["adb", "exec-out", f"echo {packed} | base64 -d | nc -w {int(timeout)} 127.0.0.1 {self.PORT}"],
                                capture_output=True, timeout=timeout + 5)
        raw = result.stdout
        if b"\r\n\r\n" not in raw:
            raise OSError(f"o app não respondeu a {path} (o serviço de acessibilidade dele está ligado?)")
        head, payload = raw.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 200 " not in status + " ":
            if " 401 " in status + " ":
                AppDevice.TOKEN = None  # app reinstalado: a senha mudou
            raise OSError(f"o app respondeu {status} a {path}: {payload[:200].decode(errors='replace')}")
        return _unwrap(json.loads(payload))

    def _do(self, path, body):
        answer = self.request(path, body, timeout=15)
        if isinstance(answer, dict) and answer.get("ok") is False:
            raise RuntimeError(answer.get("error") or "o app recusou")

    def state(self):
        return self.request("/state", timeout=15)

    def tap(self, index):
        element = next((e for e in self.elements if e["index"] == index), None)
        if element is None:
            raise ValueError(f"No element with index {index} on the current screen")
        x, y = point(element, *self.size)
        self._do("/tap", {"x": x, "y": y})

    def type(self, text, clear=False):
        self._do("/type", {"text": text, "clear": clear})

    def act(self, name, params):
        try:
            if name == "swipe":
                (x1, y1), (x2, y2) = json.loads(params["coordinate"]), json.loads(params["coordinate2"])
                self._do("/swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": int(float(params.get("duration", 1.0)) * 1000)})
            elif name == "system_button":
                self._do("/key", {"name": params["button"].lower()})
            else:
                return super().act(name, params)
        except Exception as e:
            return f"Failed to {name}: {e}"
        return None


def new_device():
    """O aparelho do modo em uso: o app do lm_phone (LMPHONE_DEVICE=app) ou o Portal."""
    return AppDevice() if USE_APP else Device()
