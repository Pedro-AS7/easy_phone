import json
import os
import tempfile
import time
import unittest
from unittest import mock

from lmphone import live
from lmphone.executor import USER_BLOCK, Executor

from test_executor import screen


class FakeApp:
    """O app do lm_phone: cada /events devolve o próximo estado da lista; /live guarda o que a faixa mostraria."""

    def __init__(self, *states):
        self.states, self.shown = list(states), []

    def request(self, path, body=None, timeout=10):
        if path == "/live":
            self.shown.append(body)
            return {"ok": True}
        state = self.states.pop(0) if self.states else {}
        return {"paused": False, "stopped": False, "typing": False, "events": [], **state}


class GateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(live, "LIVE_DIR", self.dir.name), mock.patch.object(live, "POLL", 0),
                   mock.patch.object(live, "USER_QUIET", 0)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.dir.cleanup)

    def rows(self):
        with open(os.path.join(self.dir.name, "s1.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_returns_instructions_and_records_everything(self):
        app = FakeApp({"events": [{"tipo": "instrucao", "texto": "não, a outra rede", "t": 1},
                                  {"tipo": "toque", "texto": "OK", "ms_desde_agente": 5000, "t": 2}]})
        self.assertEqual(live.Live(app, "s1").gate(), ["não, a outra rede"])
        kinds = [r["tipo"] for r in self.rows()]
        self.assertEqual(kinds, ["usuario_instrucao", "usuario_toque"])
        self.assertFalse(self.rows()[1]["duvidoso"])

    def test_waits_while_paused_and_stops(self):
        app = FakeApp({"paused": True}, {"paused": True}, {})
        self.assertEqual(live.Live(app, "s1").gate(), [])
        self.assertEqual(app.states, [])
        with self.assertRaises(live.Stopped):
            live.Live(FakeApp({"stopped": True}), "s1").gate()

    def test_touch_right_after_the_agent_is_doubtful(self):
        app = FakeApp({"events": [{"tipo": "toque", "texto": "X", "ms_desde_agente": 400, "t": 1}]})
        live.Live(app, "s1").gate()
        self.assertTrue(self.rows()[0]["duvidoso"])

    def test_describe(self):
        elements = [{"index": 3, "text": "Wi-Fi"}]
        self.assertEqual(live.describe("click", {"index": "3"}, elements), "Tocando em “Wi-Fi”")
        self.assertEqual(live.describe("open_app", {"text": "Waze"}, []), "Abrindo Waze")
        self.assertEqual(live.describe("type", {"text": "segredo"}, []), "Digitando")  # o texto pode ser senha


class InstructionTest(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.answers = [{"steps": [{"action": "tap", "target": ["Wi-Fi"]}, {"action": "tap", "target": ["ALAMEDA"]}],
                         "goal": {"shows": ["Connected"]}}]
        self.e = Executor("conecta no wifi", self.provider, lambda wanted, labels: None)

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def test_owner_instruction_goes_to_the_provider_without_counting_as_help(self):
        self.e.step(screen(("TextView", "Wi-Fi")))
        self.e.instructions.append("para, já está conectado")
        self.answers.append({"finish": {"success": True, "message": "Parei."}})
        why, tool = self.e.step(screen(("TextView", "ALAMEDA")))
        self.assertIn("para, já está conectado", self.asked[-1])
        self.assertIn('name="complete"', tool)
        self.assertEqual(self.e.helps, 0)
        self.assertFalse(self.e.cacheable)

    def test_action_refused_by_the_app_is_decided_again(self):
        why, tool = self.e.step(screen(("TextView", "Wi-Fi")))
        self.assertIn('name="click"', tool)
        refused = f"<function_results>\n<result>\n<error>paused by the user: {USER_BLOCK}</error>\n</result>\n</function_results>\n"
        why, tool = self.e.step(refused + screen(("TextView", "Wi-Fi")))
        self.assertIn('name="click"', tool)
        self.assertEqual(len(self.asked), 1)


class AskTest(unittest.TestCase):
    """Etapa 3: quando nem o provedor resolve, ele pergunta ao dono pela faixa; a resposta volta como um pedido de ajuda."""

    def setUp(self):
        self.asked = []
        self.answers = [{"steps": [{"action": "tap", "target": ["Rede da Ana"], "if_missing": "help"}], "goal": {"shows": ["Conectado"]}}]
        self.e = Executor("conecta na rede", self.provider, lambda wanted, labels: None)
        self.e.can_ask = True

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def test_provider_question_goes_to_the_owner_and_the_answer_back(self):
        self.answers.append({"ask": {"question": "Qual das duas redes?", "options": ["ALAMEDA", "ALAMEDA-5G"]}})
        why, tool = self.e.step(screen(("TextView", "ALAMEDA"), ("TextView", "ALAMEDA-5G")))
        while "still be changing" in why:
            why, tool = self.e.step(screen(("TextView", "ALAMEDA"), ("TextView", "ALAMEDA-5G")))
        self.assertIn('name="ask_user"', tool)
        self.assertIn("Qual das duas redes?", tool)
        self.assertIn('"ask"', self.asked[-1])
        self.e.answers.append(("Qual das duas redes?", "ALAMEDA"))
        self.answers.append({"steps": [{"action": "tap", "target": ["ALAMEDA"]}]})
        why, tool = self.e.step(screen(("TextView", "ALAMEDA"), ("TextView", "ALAMEDA-5G")))
        self.assertIn("they answered «ALAMEDA»", self.asked[-1])
        self.assertIn('name="click"', tool)

    def test_without_live_the_provider_is_not_offered_to_ask(self):
        self.e.can_ask = False
        self.answers.append({"finish": {"success": False, "message": "Não achei."}})
        why, tool = self.e.step(screen(("TextView", "ALAMEDA")))
        while "still be changing" in why:
            why, tool = self.e.step(screen(("TextView", "ALAMEDA")))
        self.assertNotIn('"ask"', self.asked[-1])

    def test_at_the_limit_it_asks_instead_of_giving_up(self):
        self.e.helps = 6
        self.answers.append({"ask": {"question": "Como sigo?"}})
        why, tool = self.e.step(screen(("TextView", "ALAMEDA")))
        while "still be changing" in why:
            why, tool = self.e.step(screen(("TextView", "ALAMEDA")))
        self.assertIn("already tried other ways", self.asked[-1])
        self.assertIn('name="ask_user"', tool)


class LiveAskTest(GateTest):
    def test_waits_for_the_answer_and_hides_secrets(self):
        app = FakeApp({}, {"events": [{"tipo": "resposta", "id": "x", "texto": "errada", "t": 1}]})
        with mock.patch.object(live.uuid, "uuid4", return_value=mock.Mock(hex="abcdef1234")):
            app.states.append({"events": [{"tipo": "resposta", "id": "abcdef12", "texto": "hunter22", "segredo": True, "t": 2}]})
            self.assertEqual(live.Live(app, "s1").ask("Qual a senha?", [], True), "hunter22")
        self.assertEqual(app.shown[0]["pergunta"]["texto"], "Qual a senha?")
        self.assertNotIn("hunter22", json.dumps(self.rows()))


class OwnerCommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for patch in (mock.patch.object(live, "LIVE_DIR", self.dir.name), mock.patch.object(live, "POLL", 0),
                      mock.patch.object(live, "USER_QUIET", 0)):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.dir.cleanup)

    def test_written_commands_pass_the_turn_and_do_not_reach_the_provider(self):
        app = FakeApp({"events": [{"tipo": "instrucao", "texto": "deixa que eu faço", "t": 1}]},
                      {"dono": True, "events": [{"tipo": "instrucao", "texto": "agora faz você", "t": 2}]})
        l = live.Live(app, "s1")
        self.assertEqual(l.gate(), [])
        self.assertTrue(l.owner)
        self.assertEqual(app.shown[-1]["vez"], "dono")
        self.assertEqual(l.gate(), [])
        self.assertFalse(l.owner)
        self.assertEqual(app.shown[-1]["vez"], "agente")

    def test_button_on_the_strip_is_read_from_the_app_state(self):
        l = live.Live(FakeApp({"dono": True}), "s1")
        l.gate()
        self.assertTrue(l.owner)


class ContinuousTest(GateTest):
    """Live mode contínuo: uma fala no meio de um pedido vira o pedido seguinte, e o app diz quando ainda está falando."""

    def test_new_request_ends_the_one_running(self):
        app = FakeApp({"events": [{"tipo": "novo_pedido", "texto": "abre o instagram", "t": 1}]})
        with self.assertRaises(live.Stopped) as stopped:
            live.Live(app, "s1").gate()
        self.assertEqual(str(stopped.exception), live.NEW_REQUEST)

    def test_poll_reads_speech_and_the_continuous_switch(self):
        session = live.Live(FakeApp({"falando": True, "events": [{"tipo": "continuo", "t": 1}]}), "s1")
        session.gate()
        self.assertTrue(session.speaking)
        self.assertTrue(session.continuous)

    def test_start_resets_the_strip_and_sends_the_banks(self):
        app = FakeApp()
        with mock.patch.object(live.access, "previous_keyboard", return_value=None), \
                mock.patch.object(live.access, "banks", return_value={"com.banco"}):
            live.Live(app, "s1").start("abre o youtube", continuous=True)
        self.assertTrue(app.shown[0]["nova_tarefa"])
        self.assertTrue(app.shown[0]["continuo"])
        self.assertEqual(app.shown[0]["bancos"], ["com.banco"])
        self.assertFalse(app.shown[0]["guia"])

    def test_the_strip_knows_a_guide_so_a_touch_does_not_pause(self):
        app = FakeApp()
        with mock.patch.object(live.access, "previous_keyboard", return_value=None), \
                mock.patch.object(live.access, "banks", return_value=set()):
            session = live.Live(app, "s1")
            session.start("como eu aumento a letra?", guide=True)
            session.guide(False)
        self.assertTrue(app.shown[0]["guia"])
        self.assertEqual(app.shown[1], {"guia": False})
        self.assertFalse(session.guiding)


class EventTimeTest(unittest.TestCase):
    def test_a_touch_counts_at_its_own_time_not_at_the_reading(self):
        # 2026-11-18: o toque do passo anterior chegou depois de o passo novo aparecer e contou para ele.
        app = FakeApp({"agora": 10_000, "events": [{"tipo": "toque", "texto": "Volume", "t": 7_000, "ms_desde_agente": 99999}]})
        session = live.Live(app, "s1")
        before = time.monotonic()
        session.gate()
        self.assertLess(session.touched_text_at, before - 2.5)  # 3 s antes da leitura
        self.assertEqual(session.touched_text, "Volume")
