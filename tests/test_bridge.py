import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from lmphone import bridge, service


class TokenTest(unittest.TestCase):
    """O painel do celular alcança /task pelo `adb reverse`, e qualquer app do celular também: sem a senha, nada roda."""

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        patcher = mock.patch.object(service, "TOKEN", "certa")
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, token):
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}/task",
                                         data=json.dumps({"task": "x"}).encode(),
                                         headers={"X-Lmphone-Token": token} if token is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_without_the_token_nothing_runs(self):
        with mock.patch.object(service, "run") as run:
            self.assertEqual(self.post(None), 401)
            self.assertEqual(self.post("errada"), 401)
            run.assert_not_called()


class LinkTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)  # `choose` põe ANDROID_SERIAL no ambiente
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reverse_and_token_go_to_the_phone(self):
        calls = []

        def adb(*args, input=None):
            calls.append((args, input))
            out = {"devices": "List of devices attached\nR5\tdevice\n", "reverse": ""}.get(args[0], "")
            if args[0] == "shell" and "cat files/pc_token" in args[1]:
                out = "abc123\n"  # a senha relida do app
            return mock.Mock(stdout=out, returncode=0)

        with mock.patch.object(bridge, "_adb", adb):
            self.assertTrue(bridge.link("abc123", 8789))
        self.assertIn((("reverse", "tcp:8789", "tcp:8789"), None), calls)
        # O redirecionamento vai entre aspas, para rodar dentro do run-as e não no shell de fora.
        self.assertIn((("shell", "run-as dev.pedro.lmphone sh -c 'echo abc123 > files/pc_token'"), None), calls)

    def test_no_phone_no_link(self):
        with mock.patch.object(bridge, "_adb", lambda *a, input=None: mock.Mock(stdout="List of devices attached\n", returncode=0)):
            self.assertFalse(bridge.link("abc123", 8789))


class ChooseTest(unittest.TestCase):
    """Cabo ou depuração sem fio: o adb de todo o processo vai para o aparelho escolhido (ANDROID_SERIAL)."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls, self.listed, self.mdns = [], "", ""

    def adb(self, *args, input=None):
        self.calls.append(args)
        out = {"devices": "List of devices attached\n" + self.listed, "mdns": self.mdns}.get(args[0], "")
        return mock.Mock(stdout=out, returncode=0)

    def test_cable_first(self):
        self.listed = "adb-R5-x._adb-tls-connect._tcp\tdevice\nR5\tdevice\n192.168.0.9:5555\toffline\n"
        with mock.patch.object(bridge, "_adb", self.adb):
            self.assertEqual(bridge.choose(), "R5")
            self.assertEqual(os.environ["ANDROID_SERIAL"], "R5")
            self.assertFalse(bridge.wireless())

    def test_network_when_there_is_no_cable(self):
        self.listed = "192.168.0.9:37123\tdevice\n"
        with mock.patch.object(bridge, "_adb", self.adb):
            self.assertEqual(bridge.choose(), "192.168.0.9:37123")
            self.assertTrue(bridge.wireless())

    def test_nothing_tries_the_paired_phone_again(self):
        self.mdns = "List of discovered mdns services\nadb-R5-x\t_adb-tls-connect._tcp\t192.168.0.9:37123\n"
        with mock.patch.object(bridge, "_adb", self.adb):
            self.assertIsNone(bridge.choose())
        self.assertIn(("connect", "192.168.0.9:37123"), self.calls)
        self.assertNotIn("ANDROID_SERIAL", os.environ)


class CutLinkTest(unittest.TestCase):
    """Pela rede, desligar o Wi-Fi ou ligar o modo avião cortaria a ligação com o PC: o ajuste direto recusa."""

    def test_refused_over_the_network(self):
        from lmphone import proxy
        quiet = mock.patch.object(proxy, "log", lambda entry: None)
        ran = mock.patch.object(proxy.subprocess, "run", return_value=mock.Mock(returncode=0))
        with mock.patch.object(proxy.bridge, "wireless", return_value=True), quiet, ran as run:
            self.assertEqual(proxy.set_direct("wifi", False), proxy.NO_CUT)
            self.assertEqual(proxy.set_direct("airplane_mode", True), proxy.NO_CUT)
            run.assert_not_called()
            self.assertTrue(proxy.set_direct("wifi", True))
            self.assertTrue(proxy.set_direct("bluetooth", False))
        with mock.patch.object(proxy.bridge, "wireless", return_value=False), quiet, ran:
            self.assertTrue(proxy.set_direct("wifi", False))


class ContinuousModeTest(unittest.TestCase):
    """Live mode contínuo: /live liga e desliga; um pedido contínuo deixa a acessibilidade ligada depois dele."""

    setUp = TokenTest.setUp

    def call(self, path, body):
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}{path}", data=json.dumps(body).encode(),
                                         headers={"X-Lmphone-Token": "certa"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, ""

    def patch(self, **values):
        for name, value in values.items():
            patcher = mock.patch.object(service, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_start_turns_on_and_tells_the_app(self):
        device, offs = mock.Mock(), []
        self.patch(switch_on=lambda result: None, switch_off=lambda: offs.append(1), keyboard_back=lambda: None,
                   device=device, CONTINUOUS=False)
        with mock.patch.object(service.access, "USE_APP", True), mock.patch.object(service.access, "banks", return_value=set()):
            status, _ = self.call("/live", {"acao": "iniciar"})
        self.assertEqual(status, 200)
        self.assertTrue(service.CONTINUOUS)
        self.assertTrue(device.request.call_args[0][1]["continuo"])
        self.assertEqual(offs, [])
        status, _ = self.call("/live", {"acao": "encerrar"})
        self.assertEqual(status, 200)
        self.assertFalse(service.CONTINUOUS)
        self.assertEqual(offs, [1])

    def test_continuous_request_keeps_accessibility_on(self):
        offs, backs = [], []
        self.patch(switch_off=lambda: offs.append(1), keyboard_back=lambda: backs.append(1), CONTINUOUS=False,
                   run=lambda *args: (True, "Pronto."))
        status, text = self.call("/task", {"task": "abre o youtube", "continuo": True})
        self.assertIn("Goal achieved: Pronto.", text)
        self.assertEqual((offs, backs), ([], [1]))
        status, text = self.call("/task", {"task": "abre o youtube"})
        self.assertEqual((offs, backs), ([1], [1]))
