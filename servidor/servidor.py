"""O servidor do provedor do app da loja (docs/plano-play-store.md, fase 2).

O app da loja não tem a chave do provedor: manda a este servidor o pedido ao modelo, já mascarado no aparelho, e ele o
repassa ao OpenRouter com a chave, que só existe aqui. Ele confere, antes de repassar:

- a instalação (`X-Lmphone-Instalacao`, um número sorteado pelo app) e o pedido da pessoa (`X-Lmphone-Pedido`): cada
  instalação tem LIMITE_MES pedidos por mês (decisão do Pedro, 2026-11-16: 150), e cada pedido, até
  CHAMADAS_POR_PEDIDO chamadas ao modelo (um pedido é o plano, as ajudas e a conferência);
- com INTEGRIDADE=1, o token da Play Integrity (`X-Lmphone-Integridade`): o pedido vem do app verdadeiro, instalado
  pela Play, num aparelho íntegro. Conferido uma vez por pedido;
- o teto de gasto do mês (TETO_MES_USD), somado pelo custo que o OpenRouter informa em cada resposta;
- o modelo (só os de MODELOS) e o tamanho do corpo.

Não guarda o conteúdo de nada: nem o pedido, nem a tela, nem a resposta. Guarda só, por instalação e mês, os ids dos
pedidos e quantas chamadas cada um fez, e o gasto do mês. A exceção é a denúncia (`/v1/denuncia`, exigência da política
de conteúdo gerado por IA da Play): a resposta que a pessoa decidiu denunciar, com o texto que ela leu, até
REPORTS_MONTH por instalação e mês. O registro (stdout) tem a hora, um resumo da instalação
(8 caracteres do sha256), o status e o custo.

Roda no Cloud Run (`servidor/Dockerfile`, a contagem no Firestore) ou no PC para testar (`ARMAZEM=arquivo:...`, o app
de depuração da loja o alcança por `adb reverse tcp:8792 tcp:8792`):

    OPENROUTER_API_KEY=... PORT=8792 ARMAZEM=arquivo:data/servidor.json .venv/bin/python -m servidor.servidor
"""

import base64
import datetime
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://openrouter.ai/api/v1"
LIMIT_MONTH = int(os.environ.get("LIMITE_MES", "150"))
CALLS_PER_REQUEST = int(os.environ.get("CHAMADAS_POR_PEDIDO", "25"))
CEILING_USD = float(os.environ.get("TETO_MES_USD", "30"))
MODELS = set(os.environ.get("MODELOS", "anthropic/claude-haiku-5.5").split(","))
REPORTS_MONTH = 20  # denúncias por instalação e mês
MAX_BODY = 600_000  # bytes: o plano com a tela reduzida fica bem abaixo disso
INTEGRITY = os.environ.get("INTEGRIDADE", "0") == "1"
PACKAGE = os.environ.get("PACOTE", "dev.pedro.lmphone.guia")
ALLOWED_KEYS = {"model", "messages", "reasoning", "max_tokens", "temperature"}
INSTALLATION = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
REQUEST = re.compile(r"^[A-Za-z0-9_-]{4,64}$")

# O que a pessoa lê na faixa quando o servidor recusa (o app mostra o campo "mensagem").
MONTH_FULL = (f"Você já fez os {LIMIT_MONTH} pedidos deste mês. O Guia volta a responder no dia 1º do mês que vem.")
REQUEST_FULL = "Este pedido ficou comprido demais. Tente pedir de novo, com outras palavras."
CEILING_FULL = "O Guia está com muita procura e parou por hoje. Tente de novo amanhã."
NOT_GENUINE = "Não consegui confirmar este aparelho. Atualize o Guia do Celular pela Play Store e tente de novo."
UNAVAILABLE = "O Guia não conseguiu pensar agora. Tente de novo daqui a pouco."


def month(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m")


def short(installation):
    return hashlib.sha256(installation.encode()).hexdigest()[:8]


def log(**fields):
    print(json.dumps({"t": round(time.time(), 3), **fields}, ensure_ascii=False), flush=True)


# --- onde as contagens ficam ---

class Conflict(Exception):
    """O documento mudou entre a leitura e a escrita (outra instância do servidor): lê de novo e tenta outra vez."""


class FileStore:
    """As contagens num arquivo JSON (o PC, os testes). Uma instância só: a trava basta."""

    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()

    def _all(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def get(self, key):
        with self.lock:
            value = self._all().get(key)
        return (value, json.dumps(value, sort_keys=True)) if value is not None else (None, None)

    def put(self, key, value, version):
        with self.lock:
            data = self._all()
            current = data.get(key)
            if (json.dumps(current, sort_keys=True) if current is not None else None) != version:
                raise Conflict(key)
            data[key] = value
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(temporary, self.path)


class Firestore:
    """As contagens no Firestore pela API REST, com a credencial do Cloud Run (servidor de metadados). Cada valor vai
    como texto JSON num campo só; a escrita exige que o documento não tenha mudado desde a leitura (`updateTime`)."""

    def __init__(self, project):
        self.base = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/contagens"

    def _call(self, method, url, body=None):
        request = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Authorization": f"Bearer {google_token()}",
                                                  "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as answer:
                return json.loads(answer.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (409, 412) or (e.code == 400 and b"FAILED_PRECONDITION" in e.read()):
                raise Conflict(url)
            raise

    def get(self, key):
        doc = self._call("GET", f"{self.base}/{key}")
        if not doc:
            return None, None
        return json.loads(doc["fields"]["dados"]["stringValue"]), doc["updateTime"]

    def put(self, key, value, version):
        precondition = (f"currentDocument.updateTime={urllib.parse.quote(version)}" if version
                        else "currentDocument.exists=false")
        self._call("PATCH", f"{self.base}/{key}?{precondition}",
                   {"fields": {"dados": {"stringValue": json.dumps(value)}}})


_token = {"value": None, "until": 0.0}


def google_token():
    """A credencial da conta de serviço do Cloud Run, pelo servidor de metadados (guardada até perto de vencer)."""
    if _token["value"] and time.time() < _token["until"] - 60:
        return _token["value"]
    request = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(request, timeout=5) as answer:
        data = json.loads(answer.read())
    _token.update(value=data["access_token"], until=time.time() + data.get("expires_in", 300))
    return _token["value"]


def store_from(spec):
    kind, _, where = spec.partition(":")
    if kind == "arquivo":
        return FileStore(where or "data/servidor.json")
    if kind == "firestore":
        return Firestore(where)
    raise ValueError(f"ARMAZEM desconhecido: {spec}")


def change(store, key, update, tries=5):
    """Lê, muda e grava um documento, de novo se outra instância o mudou no meio. `update(valor)` devolve o novo valor,
    ou levanta para desistir sem gravar."""
    for _ in range(tries):
        value, version = store.get(key)
        new = update(json.loads(json.dumps(value)) if value is not None else None)
        try:
            store.put(key, new, version)
            return new
        except Conflict:
            continue
    raise Conflict(key)


# --- as regras ---

class Refused(Exception):
    def __init__(self, status, message, reason):
        super().__init__(reason)
        self.status, self.message, self.reason = status, message, reason


def admit(store, installation, request, now=None):
    """Conta a chamada: um pedido novo gasta um dos LIMIT_MONTH do mês; cada pedido tem até CALLS_PER_REQUEST
    chamadas. Levanta Refused se passou. Devolve se o pedido é novo (para conferir a integridade uma vez)."""
    key = f"{month(now)}_{installation}"
    seen = {"new": False}

    def update(doc):
        doc = doc or {"pedidos": {}}
        calls = doc["pedidos"].get(request)
        if calls is None:
            if len(doc["pedidos"]) >= LIMIT_MONTH:
                raise Refused(429, MONTH_FULL, "limite do mês")
            seen["new"] = True
            calls = 0
        if calls >= CALLS_PER_REQUEST:
            raise Refused(429, REQUEST_FULL, "chamadas do pedido")
        doc["pedidos"][request] = calls + 1
        return doc

    change(store, key, update)
    return seen["new"]


def spent(store, now=None):
    value, _ = store.get(f"{month(now)}_gasto")
    return float((value or {}).get("usd", 0.0))


def add_cost(store, usd, now=None):
    if usd <= 0:
        return
    change(store, f"{month(now)}_gasto", lambda doc: {"usd": round(float((doc or {}).get("usd", 0.0)) + usd, 6)})


def genuine(token, request):
    """A Play Integrity diz que o pedido vem do app verdadeiro, instalado pela Play, num aparelho íntegro, e que o token
    foi feito para este pedido (`requestHash` = sha256 do id do pedido, em base64url)."""
    if not token:
        return False
    body = json.dumps({"integrity_token": token}).encode()
    call = urllib.request.Request(f"https://playintegrity.googleapis.com/v1/{PACKAGE}:decodeIntegrityToken", data=body,
                                  headers={"Authorization": f"Bearer {google_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(call, timeout=10) as answer:
            payload = json.loads(answer.read()).get("tokenPayloadExternal", {})
    except (urllib.error.URLError, ValueError):
        return False
    details = payload.get("requestDetails", {})
    wanted = base64.urlsafe_b64encode(hashlib.sha256(request.encode()).digest()).decode().rstrip("=")
    return (details.get("requestPackageName") == PACKAGE
            and details.get("requestHash", "").rstrip("=") == wanted
            and payload.get("appIntegrity", {}).get("appRecognitionVerdict") == "PLAY_RECOGNIZED"
            and "MEETS_DEVICE_INTEGRITY" in payload.get("deviceIntegrity", {}).get("deviceRecognitionVerdict", []))


def forward(body, key, opener=urllib.request.urlopen):
    """O pedido ao OpenRouter, com a chave. Devolve (status, bytes)."""
    request = urllib.request.Request(UPSTREAM + "/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with opener(request, timeout=300) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def clean(raw):
    """O corpo que vai ao OpenRouter: só os campos conhecidos, o modelo da lista, e o custo na resposta."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list) or data.get("model") not in MODELS:
        raise ValueError("corpo inválido ou modelo fora da lista")
    out = {k: v for k, v in data.items() if k in ALLOWED_KEYS}
    out["usage"] = {"include": True}
    return json.dumps(out).encode()


def handle(store, headers, raw, key, opener=urllib.request.urlopen, now=None):
    """Um pedido do app, do começo ao fim. Devolve (status, corpo em bytes)."""
    installation = headers.get("X-Lmphone-Instalacao", "")
    request = headers.get("X-Lmphone-Pedido", "")
    if not INSTALLATION.match(installation) or not REQUEST.match(request):
        return 400, json.dumps({"mensagem": UNAVAILABLE, "erro": "instalação ou pedido sem formato"}).encode()
    try:
        body = clean(raw)
    except ValueError as e:
        return 400, json.dumps({"mensagem": UNAVAILABLE, "erro": str(e)}).encode()
    try:
        if spent(store, now) >= CEILING_USD:
            raise Refused(503, CEILING_FULL, "teto do mês")
        new = admit(store, installation, request, now)
        if INTEGRITY and new and not genuine(headers.get("X-Lmphone-Integridade", ""), request):
            raise Refused(403, NOT_GENUINE, "integridade")
    except Refused as e:
        log(instalacao=short(installation), status=e.status, recusa=e.reason)
        return e.status, json.dumps({"mensagem": e.message}).encode()
    status, answer = forward(body, key, opener)
    cost = 0.0
    if status == 200:
        try:
            cost = float(json.loads(answer).get("usage", {}).get("cost") or 0.0)
        except (ValueError, AttributeError):
            pass
        add_cost(store, cost, now)
    log(instalacao=short(installation), status=status, usd=round(cost, 6))
    if status != 200:
        return 502, json.dumps({"mensagem": UNAVAILABLE, "erro": f"o provedor respondeu {status}"}).encode()
    return 200, answer


def report(store, headers, raw, now=None):
    """Guarda a denúncia de uma resposta (o texto que a pessoa leu e decidiu enviar). Devolve (status, corpo)."""
    installation = headers.get("X-Lmphone-Instalacao", "")
    try:
        text = str(json.loads(raw).get("texto") or "").strip()[:4000]
    except (ValueError, AttributeError):
        text = ""
    if not INSTALLATION.match(installation) or not text:
        return 400, b'{"ok": false}'
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds")

    def update(doc):
        doc = doc or {"denuncias": []}
        if sum(1 for r in doc["denuncias"] if r["instalacao"] == short(installation)) >= REPORTS_MONTH:
            raise Refused(429, "", "denúncias do mês")
        doc["denuncias"].append({"em": stamp, "instalacao": short(installation), "texto": text})
        return doc

    try:
        change(store, f"{month(now)}_denuncias", update)
    except Refused:
        return 429, b'{"ok": false}'
    log(instalacao=short(installation), denuncia=True)
    return 200, b'{"ok": true}'


def serve(port, store, key):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # o registro é o de `log`, sem o caminho nem o corpo

        def reply(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(200 if self.path == "/saude" else 404, b'{"ok": true}' if self.path == "/saude" else b"{}")

        def do_POST(self):
            if self.path not in ("/v1/chat/completions", "/v1/denuncia"):
                return self.reply(404, b"{}")
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self.reply(413, json.dumps({"mensagem": REQUEST_FULL}).encode())
            raw = self.rfile.read(length)
            if self.path == "/v1/denuncia":
                return self.reply(*report(store, self.headers, raw))
            status, body = handle(store, self.headers, raw, key)
            self.reply(status, body)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log(inicio=True, porta=port, integridade=INTEGRITY, limite_mes=LIMIT_MONTH, teto_usd=CEILING_USD)
    server.serve_forever()


def main():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            name, _, value = line.strip().partition("=")
            if name == "OPENROUTER_API_KEY":
                key = value.strip().strip('"')
    if not key:
        sys.exit("falta OPENROUTER_API_KEY")
    serve(int(os.environ.get("PORT", "8080")), store_from(os.environ.get("ARMAZEM", "arquivo:data/servidor.json")), key)


if __name__ == "__main__":
    main()
