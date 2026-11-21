"""Servidor local do Laya (modelo de decisão, sem geração de texto).

Roda no ambiente próprio, porque precisa do PyTorch: .venv-laya/bin/python -m lmphone.laya_server
POST /pick {"wanted": [...], "labels": [...]} -> {"label": rótulo ou null, "p": probabilidade, "ranking": todas as
    opções em [rótulo, probabilidade], da mais provável à menos, "seconds": tempo}
GET / -> {"status": "ok", "model": peso fixo, "min_p": MIN_P}
POST /private {"fragments": [...]} -> {"p": [probabilidade de cada trecho citar uma pessoa], "seconds": tempo}

A pergunta é feita como um roteamento, que é para o que o modelo foi treinado: o controle que o
plano pede é o pedido, os rótulos da tela são os destinos e "(none)" é um destino a mais.
Abaixo de MIN_P a resposta é "nenhum": errar para o lado do pedido de ajuda custa menos que um toque errado.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from laya import Router

PORT = int(os.environ.get("LMPHONE_LAYA_PORT", "8788"))
MIN_P = 0.5
NONE = "(none)"
# Peso fixo em inglês. Com "auto" o Router escolhe pelo idioma de cada texto e mantém dois pesos na memória (3,4 GB
# em vez de 2,1 GB); nos casos de tests/laya_cases.py o inglês deu as mesmas respostas, inclusive em português.
# Outro valor só serve para comparar (tests/eval_laya.py).
MODEL = os.environ.get("LMPHONE_LAYA_MODEL", "english")
MODEL = "" if MODEL == "auto" else MODEL

router = Router(max_loaded=1, default=MODEL) if MODEL else Router()
FIXED = {"model": MODEL} if MODEL else {}


def pick(wanted, labels):
    state = "I want to tap the control called " + " or ".join(f'"{w}"' for w in wanted) + "."
    criteria = {label: f'the button or item labelled "{label}"' for label in labels}
    criteria[NONE] = "no control on this screen matches; it is not here"
    question = {"type": "choice", "instructions": "Which control on the screen is the one the user wants?", "criteria": criteria}
    start = time.monotonic()
    answer = router.predict(state, {"which": question}, **FIXED)["answers"]["which"]
    choice, p = answer["choice"], answer["probabilities"][answer["choice"]]
    # O ranking serve ao diagnóstico (tests/eval_base.py); o proxy não o registra, porque são rótulos de tela.
    ranking = sorted(answer["probabilities"].items(), key=lambda item: -item[1])
    return {"label": None if choice == NONE or p < MIN_P else choice, "p": round(p, 3),
            "ranking": [[label, round(q, 3)] for label, q in ranking], "seconds": round(time.monotonic() - start, 2)}


REVIEW = {"type": "choice", "instructions": "Who should review this text?", "criteria": {
    "mentions_person": "privacy review: the text has a person's name, nickname or a social network username in it",
    "interface": "no review needed: it is only an interface label, setting, button, app or company name, number or generic sentence"}}


def private(fragments):
    """Probabilidade de cada trecho de tela citar uma pessoa. Serve de filtro: quem acha os nomes é a Gemma."""
    start = time.monotonic()
    answers = router.predict_batch([{"state": f'Text on a phone screen: "{f}"', "questions": {"q": REVIEW}, **FIXED} for f in fragments])
    return {"p": [round(a["answers"]["q"]["probabilities"]["mentions_person"], 3) for a in answers],
            "seconds": round(time.monotonic() - start, 2)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"status": "ok", "model": MODEL or "auto", "min_p": MIN_P})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path == "/private":
            return self.reply(private(body["fragments"]))
        self.reply(pick(body["wanted"], body["labels"]) if body.get("labels") else {"label": None, "p": 0.0, "seconds": 0.0})


if __name__ == "__main__":
    pick(["Menu"], ["Options", "Back"])  # carrega o modelo antes de aceitar pedidos
    print(f"laya em http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
