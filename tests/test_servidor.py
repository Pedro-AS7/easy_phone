import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from servidor import servidor

INSTALL = "123e4567-e89b-42d3-a456-426614174000"
NOW = datetime.datetime(2026, 11, 16, tzinfo=datetime.timezone.utc)
BODY = json.dumps({"model": "anthropic/claude-haiku-5.5", "messages": [{"role": "user", "content": "oi"}],
                   "reasoning": {"enabled": False}, "extra": "sai"}).encode()


class Answer(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = servidor.FileStore(os.path.join(self.dir.name, "contagens.json"))
        self.sent = []

    def tearDown(self):
        self.dir.cleanup()

    def opener(self, request, timeout):
        self.sent.append(json.loads(request.data))
        return Answer(200, json.dumps({"choices": [{"message": {"content": "{}"}}], "usage": {"cost": 0.002}}).encode())

    def call(self, request="pedido1", body=BODY, install=INSTALL, now=NOW):
        headers = {"X-Lmphone-Instalacao": install, "X-Lmphone-Pedido": request}
        with mock.patch.object(servidor, "log"):
            return servidor.handle(self.store, headers, body, "chave", self.opener, now)

    def test_forwards_only_known_fields_and_counts_the_cost(self):
        status, body = self.call()
        self.assertEqual(status, 200)
        self.assertEqual(set(self.sent[0]), {"model", "messages", "reasoning", "usage"})
        self.assertEqual(self.sent[0]["usage"], {"include": True})
        self.assertAlmostEqual(servidor.spent(self.store, NOW), 0.002)
        stored = json.dumps(self.store._all())
        self.assertNotIn("oi", stored)  # nada do conteúdo fica guardado

    def test_a_request_has_many_calls_but_counts_once_in_the_month(self):
        for _ in range(3):
            self.call("pedidoA")
        value, _ = self.store.get(f"2026-11_{INSTALL}")
        self.assertEqual(value["pedidos"], {"pedidoA": 3})

    def test_the_month_limit_refuses_a_new_request_with_a_message(self):
        with mock.patch.object(servidor, "LIMIT_MONTH", 2):
            self.call("p0001")
            self.call("p0002")
            self.assertEqual(self.call("p0002")[0], 200)  # o mesmo pedido continua
            status, body = self.call("p0003")
        self.assertEqual(status, 429)
        self.assertIn("pedidos deste mês", json.loads(body)["mensagem"])
        self.assertEqual(len(self.sent), 3)
        next_month = datetime.datetime(2026, 12, 1, tzinfo=datetime.timezone.utc)
        with mock.patch.object(servidor, "LIMIT_MONTH", 2):
            self.assertEqual(self.call("p0003", now=next_month)[0], 200)

    def test_calls_per_request_are_capped(self):
        with mock.patch.object(servidor, "CALLS_PER_REQUEST", 2):
            self.call("pedidoB")
            self.call("pedidoB")
            status, _ = self.call("pedidoB")
        self.assertEqual(status, 429)

    def test_the_month_ceiling_stops_everything(self):
        servidor.add_cost(self.store, 31.0, NOW)
        status, body = self.call()
        self.assertEqual(status, 503)
        self.assertEqual(self.sent, [])

    def test_bad_identity_or_model_is_refused_before_the_provider(self):
        self.assertEqual(self.call(install="nao-e-uuid")[0], 400)
        other = json.dumps({"model": "openai/gpt-x", "messages": []}).encode()
        self.assertEqual(self.call(body=other)[0], 400)
        self.assertEqual(self.sent, [])

    def test_integrity_is_checked_once_per_request(self):
        checked = []
        with mock.patch.object(servidor, "INTEGRITY", True), \
                mock.patch.object(servidor, "genuine", lambda token, request: checked.append(request) or True):
            self.call("pedidoC")
            self.call("pedidoC")
        self.assertEqual(checked, ["pedidoC"])
        with mock.patch.object(servidor, "INTEGRITY", True), mock.patch.object(servidor, "genuine", lambda t, r: False):
            status, body = self.call("pedidoD")
        self.assertEqual(status, 403)

    def test_a_provider_error_becomes_a_message(self):
        self.opener = lambda request, timeout: Answer(500, b"{}")
        status, body = self.call()
        self.assertEqual(status, 502)
        self.assertIn("mensagem", json.loads(body))

    def test_a_report_keeps_only_the_text_the_person_sent(self):
        headers = {"X-Lmphone-Instalacao": INSTALL}
        with mock.patch.object(servidor, "log"):
            status, _ = servidor.report(self.store, headers, json.dumps({"texto": "resposta ruim"}).encode(), NOW)
            self.assertEqual(status, 200)
            value, _ = self.store.get("2026-11_denuncias")
            self.assertEqual(value["denuncias"][0]["texto"], "resposta ruim")
            self.assertNotIn(INSTALL, json.dumps(value))  # só o resumo da instalação
            with mock.patch.object(servidor, "REPORTS_MONTH", 1):
                self.assertEqual(servidor.report(self.store, headers, b'{"texto": "outra"}', NOW)[0], 429)


if __name__ == "__main__":
    unittest.main()
