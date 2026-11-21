import unittest
from unittest import mock

from lmphone import proxy
from lmphone.masking import Masker, Vault


class JudgeTaskTest(unittest.TestCase):
    def setUp(self):
        self.m = Masker(Vault())
        self.m.add_name("Arctos")
        self.logged = []
        proxy.judged.clear()
        for target, value in (("masker", self.m), ("log", self.logged.append)):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def judge(self, task, judgment):
        answer = mock.Mock(side_effect=judgment) if isinstance(judgment, Exception) else mock.Mock(
            return_value=(judgment, "", 1.0))
        with mock.patch.object(proxy, "TASK", task), mock.patch.object(proxy.local_ai, "judge_request", answer):
            proxy.judge_task()
        self.assertTrue(proxy.judged.is_set())

    def test_lowercase_name_is_masked(self):
        task = "fala pro marcos que já saí"
        self.judge(task, {"intencao": "acao", "entidades": [
            {"texto": "marcos", "tipo": "pessoa", "precisa_pesquisa": False}]})
        self.assertNotIn("marcos", self.m.mask(task))
        self.assertEqual(self.m.unmask(self.m.mask(task)), task)

    def test_business_to_search_is_released(self):
        task = "Qual o endereço da Barbearia Arctos?"
        self.judge(task, {"intencao": "pesquisa", "entidades": [
            {"texto": "Barbearia Arctos", "tipo": "negocio", "precisa_pesquisa": True}]})
        self.assertEqual(self.m.mask(task), task)

    def test_failure_keeps_fixed_rules(self):
        task = "Mande mensagem para a Barbearia Arctos"
        self.judge(task, OSError("Ollama fora do ar"))
        self.assertNotIn("Arctos", self.m.mask(task))
        self.assertIn("erro", self.logged[0]["local_ai"])

    def test_log_has_no_entity_text(self):
        self.judge("fala pro marcos que já saí", {"intencao": "acao", "entidades": [
            {"texto": "marcos", "tipo": "pessoa", "precisa_pesquisa": False}]})
        self.assertEqual(self.logged[0]["local_ai"]["decisoes"], {"mascarar": 1})
        self.assertNotIn("marcos", str(self.logged))


SCREEN = """**Current Request:**
Abra a conversa
<device_state>
**Current Phone State:**
• **App:** Mensagens (com.exemplo.mensagens)
• **Keyboard:** Hidden

Current Clickable UI elements:
'index. className: resourceId; checkedState, text - bounds(x1,y1,x2,y2)':
1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)
2. TextView: "com.exemplo.mensagens:id/title", "Conversas" - (78,800,329,882)
3. TextView: "com.exemplo.mensagens:id/name", "renato vilela" - (78,900,329,982)
4. TextView: "carol_dias: lindas" - (78,1000,329,1082)
5. Button: "12" - (78,1100,329,1182)
</device_state>"""


class JudgeScreenTest(unittest.TestCase):
    def setUp(self):
        self.m = Masker(Vault())
        self.logged = []
        for target, value in (("masker", self.m), ("log", self.logged.append)):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def judge(self, text, items):
        answer = mock.Mock(side_effect=items) if isinstance(items, Exception) else mock.Mock(
            return_value=({"itens": items}, "", 1.0))
        with mock.patch.object(proxy.local_ai, "find_private", answer):
            proxy.judge_screen([{"role": "user", "content": text}])
        return answer

    def test_fragments_skip_ids_classes_and_numbers(self):
        self.assertEqual(proxy.local_ai.screen_fragments(SCREEN), ["Conversas", "renato vilela", "carol_dias: lindas"])
        self.assertEqual(proxy.local_ai.screen_fragments("fora da tela: renato vilela"), [])

    def test_fragments_of_unclassed_checkable_and_focused_elements(self):
        screen = """<device_state>
**Current Phone State:**
• **App:** Configurações (com.android.settings)
• **Keyboard:** Visible
• **Focused Element:** 'mensagem pra bia'

Current Clickable UI elements:
3. "com.android.settings:id/app_bar_viewpager", "Dark mode" - (0,0,10,10)
4. Switch: "com.android.settings:id/switch_widget", "Dark mode switch" ; isChecked=True - (0,0,10,10)
</device_state>"""
        self.assertEqual(proxy.local_ai.screen_fragments(screen), ["mensagem pra bia", "Dark mode", "Dark mode switch"])

    def test_batches_respect_size(self):
        self.assertEqual(list(proxy.local_ai.batches(["a" * 700, "b" * 700, "c"])), [["a" * 700], ["b" * 700, "c"]])

    def test_found_items_are_masked(self):
        self.judge(SCREEN, [{"texto": "Renato Vilela", "tipo": "pessoa"}, {"texto": "carol_dias", "tipo": "usuario"}])
        masked = self.m.mask(SCREEN)
        for secret in ("renato", "vilela", "carol_dias"):
            self.assertNotIn(secret, masked)
        self.assertIn("Conversas", masked)
        self.assertEqual(self.m.unmask(masked), SCREEN)
        self.assertEqual(self.logged[0]["local_ai_tela"]["trechos"], 3)
        self.assertNotIn("renato", str(self.logged).casefold())

    def test_seen_fragments_are_not_judged_again(self):
        self.judge(SCREEN, [])
        self.assertEqual(self.judge(SCREEN, []).call_count, 0)
        again = self.judge(SCREEN.replace("</device_state>", '6. TextView: "Arquivadas" - (0,0,1,1)\n</device_state>'), [])
        self.assertEqual(again.call_args[0][0], "Arquivadas")

    def test_failure_is_retried_next_step(self):
        self.judge(SCREEN, OSError("Ollama fora do ar"))
        self.assertIn("erro", self.logged[0]["local_ai_tela"])
        self.assertEqual(self.judge(SCREEN, []).call_count, 1)

    def test_released_by_request_stays_released(self):
        self.m.add_name("Trigal")
        self.m.session.release("Padaria Trigal")
        text = '<device_state>\n1. TextView: "Padaria Trigal" - (0,0,1,1)\n</device_state>'
        self.judge(text, [{"texto": "Trigal", "tipo": "pessoa"}])
        self.assertEqual(self.m.mask(text), text)


class PrimeTest(unittest.TestCase):
    def setUp(self):
        backend = mock.patch.object(proxy.local_ai, "BACKEND", "gemma")  # o preparo é coisa da Gemma no Ollama
        backend.start()
        self.addCleanup(backend.stop)

    def test_prime_call_ends_at_the_fixed_head(self):
        chat = mock.Mock(return_value='{"intencao":"acao","entidades":[]}')
        with mock.patch.object(proxy.local_ai, "_chat", chat):
            answer, _, _ = proxy.local_ai.judge_request("abre o relógio")
        self.assertEqual(answer["intencao"], "acao")
        (prime, real) = chat.call_args_list
        self.assertEqual(prime.args[1], "Pedido:")
        self.assertEqual(prime.kwargs, {"num_predict": 1})
        self.assertEqual(real.args[1], "Pedido: abre o relógio")
        self.assertEqual(real.kwargs, {})

    def test_failed_prime_does_not_stop_the_judgment(self):
        chat = mock.Mock(side_effect=[OSError("lento"), '{"itens":[]}'])
        with mock.patch.object(proxy.local_ai, "_chat", chat):
            self.assertEqual(proxy.local_ai.find_private("Conversas")[0], {"itens": []})


class PrelaunchTest(unittest.TestCase):
    JUDGMENT = {"entidades": [{"texto": "Relógio", "tipo": "app", "precisa_pesquisa": False}]}

    def run_prelaunch(self, executor):
        launch = mock.Mock(return_value=True)
        with mock.patch.object(proxy, "launch", launch), \
                mock.patch.object(proxy, "executor", executor), mock.patch.object(proxy, "opened", None), \
                mock.patch.object(proxy, "log", mock.Mock()):
            proxy.prelaunch(self.JUDGMENT)
            return launch.call_count, proxy.opened

    def test_opens_the_app_before_the_executor_exists(self):
        self.assertEqual(self.run_prelaunch(None), (1, "Relógio"))

    def test_does_not_open_an_app_under_a_running_task(self):
        # Tarefa do cache que começou sem esperar o julgamento.
        self.assertEqual(self.run_prelaunch(object()), (0, None))
        proxy.executor_lock.acquire()
        self.addCleanup(proxy.executor_lock.release)
        self.assertEqual(self.run_prelaunch(None), (0, None))


if __name__ == "__main__":
    unittest.main()


class UpstreamRetryTest(unittest.TestCase):
    def test_a_dropped_connection_is_tried_once_more(self):
        import http.client
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.return_value = b"{}"
        calls = [http.client.RemoteDisconnected("closed"), response]
        with mock.patch.object(proxy.urllib.request, "urlopen", side_effect=calls), mock.patch.object(proxy.time, "sleep"):
            self.assertEqual(proxy.upstream("/x", "POST", {}), (200, b"{}"))

    def test_two_drops_are_an_error(self):
        import http.client
        drops = [http.client.RemoteDisconnected("closed")] * 2
        with mock.patch.object(proxy.urllib.request, "urlopen", side_effect=drops), mock.patch.object(proxy.time, "sleep"):
            with self.assertRaises(http.client.RemoteDisconnected):
                proxy.upstream("/x", "POST", {})


class ConversationTest(unittest.TestCase):
    """Dentro de uma conversa, os valores falsos e o histórico passam de um pedido ao seguinte."""

    def setUp(self):
        for target, value in (("new_masker", lambda: Masker(Vault())), ("masker", proxy.masker), ("TASK", ""),
                              ("SESSION", ""), ("CONVERSATION", None), ("HISTORY", []), ("executor", None)):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def turn(self, task, conversation, reply="Feito.", trail=()):
        proxy.begin(task, conversation=conversation)
        proxy.executor = mock.Mock(trail=list(trail))
        proxy.remember_turn(reply, "confirmado")

    def test_same_conversation_keeps_the_fakes_and_the_history(self):
        self.turn("liga pra Arctos", "c1", "Ligando.", [{"action": "open_app", "target": ["Telefone"]}])
        first = proxy.masker
        proxy.begin("de novo", conversation="c1")
        self.assertIs(proxy.masker, first)
        history = proxy.history_text()
        self.assertIn("Owner: liga pra Arctos", history)
        self.assertIn("You: Ligando.", history)
        self.assertIn("open_app “Telefone”", history)

    def test_other_or_expired_conversation_starts_fresh(self):
        self.turn("liga pra Arctos", "c1")
        first = proxy.masker
        proxy.begin("oi", conversation="c2")
        self.assertIsNot(proxy.masker, first)
        self.assertEqual(proxy.history_text(), "")
        self.turn("liga pra Arctos", "c3")
        proxy.CONVERSATION["at"] -= proxy.CONVERSATION_TTL + 1
        proxy.begin("de novo", conversation="c3")
        self.assertEqual(proxy.history_text(), "")

    def test_without_an_id_every_request_is_alone(self):
        self.turn("liga pra Arctos", None)
        proxy.begin("de novo")
        self.assertEqual(proxy.history_text(), "")

    def test_cache_is_not_used_in_the_middle_of_a_conversation(self):
        with mock.patch.object(proxy.cache, "load", return_value=([], None)):
            proxy.begin("liga o wifi", conversation="c1")
            self.assertTrue(proxy.cached_path())
            proxy.executor = mock.Mock(trail=[])
            proxy.remember_turn("Pronto.", "confirmado")
            proxy.begin("liga o wifi", conversation="c1")
            self.assertFalse(proxy.cached_path())

    def test_yes_after_a_confirmation_question_lets_the_action_go(self):
        with mock.patch.object(proxy, "device_description", lambda: "x"), mock.patch.object(proxy.cache, "maps", dict):
            proxy.begin("manda oi pra Arctos", conversation="c1")
            proxy.executor = mock.Mock(trail=[])
            proxy.remember_turn("Posso tocar em «Send»? (sim / não)", "a confirmar")
            proxy.begin("sim", conversation="c1")
            proxy.make_executor("m")
            self.assertTrue(proxy.executor.preapproved)
            proxy.remember_turn("Enviei.", "confirmado")
            proxy.begin("sim", conversation="c1")
            proxy.executor = None
            proxy.make_executor("m")
            self.assertFalse(proxy.executor.preapproved)


class ConfirmedTest(unittest.TestCase):
    """A resposta à confirmação de um toque que não se desfaz: sim libera, não encerra, outra coisa vai ao provedor."""

    def setUp(self):
        self.answered = []
        for target, value in (("log", lambda entry: None), ("detail", lambda *a, **k: None),
                              ("answered", lambda question, answer, secret: self.answered.append(answer))):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        executor = proxy.Executor("t", None, None)
        executor.confirming = {"i": 2, "label": "Send", "question": "Posso tocar em «Send»?"}
        patcher = mock.patch.object(proxy, "executor", executor)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_yes(self):
        self.assertTrue(proxy.confirmed("Posso tocar em «Send»?", "Sim"))
        self.assertEqual(proxy.executor.approved, (2, "Send"))
        self.assertEqual(self.answered, [])

    def test_no(self):
        self.assertFalse(proxy.confirmed("Posso tocar em «Send»?", "não"))
        self.assertEqual(proxy.executor.declined, "Send")

    def test_anything_else_goes_to_the_provider(self):
        self.assertIsNone(proxy.confirmed("Posso tocar em «Send»?", "manda pro outro contato"))
        self.assertEqual(self.answered, ["manda pro outro contato"])
        self.assertIsNone(proxy.executor.approved)


class CachedPromptTest(unittest.TestCase):
    """As instruções fixas vão como mensagem de sistema com marca de cache; a situação vai depois, mascarada."""

    def test_fixed_part_is_a_cached_system_message(self):
        from lmphone.executor import SPLIT
        masker = Masker(Vault())
        masker.add_name("Arctos")
        sent = []

        def upstream(path, method, body):
            sent.append(body)
            return 200, b'{"choices": [{"message": {"content": "{}"}}], "usage": {}}'

        proxy.judged.set()
        with mock.patch.object(proxy, "masker", masker), mock.patch.object(proxy, "upstream", upstream), \
                mock.patch.object(proxy, "judge_screen", lambda messages: None), mock.patch.object(proxy, "log", lambda entry: None):
            proxy.ask_provider("m", f"Fixed rules.{SPLIT}The owner says: liga pro Arctos")
        system, user = sent[0]["messages"]
        self.assertEqual(system["role"], "system")
        self.assertEqual(system["content"][0], {"type": "text", "text": "Fixed rules.", "cache_control": {"type": "ephemeral"}})
        self.assertEqual(user["role"], "user")
        self.assertNotIn("Arctos", user["content"])
        self.assertNotIn(SPLIT.strip(), str(sent))


class DeviceNameTest(unittest.TestCase):
    def test_read_from_the_phone_with_a_fallback(self):
        with mock.patch.object(proxy, "_device", None), mock.patch.object(proxy.subprocess, "run",
                return_value=mock.Mock(stdout="SM-S916B\n17\n90000\npt-BR\n")):
            self.assertEqual(proxy.device_name(), "Samsung Galaxy S23+, Android 17, One UI 9.0. Interface language: Portuguese")
        with mock.patch.object(proxy, "_device", None), mock.patch.object(proxy.subprocess, "run",
                return_value=mock.Mock(stdout="SM-X\n16\n85000\nen-US\n")):
            self.assertEqual(proxy.device_name(), "Samsung SM-X, Android 16, One UI 8.5. Interface language: English")
        with mock.patch.object(proxy, "_device", None), mock.patch.object(proxy.subprocess, "run", side_effect=OSError):
            self.assertEqual(proxy.device_name(), proxy.DEVICE)


class UsernameShapeTest(unittest.TestCase):
    """Um "usuário" que o modelo acha no pedido só é mascarado com forma de usuário ou num pedido de rede social."""

    setUp, judge = JudgeTaskTest.setUp, JudgeTaskTest.judge

    def test_loose_word_outside_social_is_kept(self):
        # 2026-10-24: o Hyrox, ouvido como "rayrox", foi marcado como usuário e o provedor só viu um nome falso.
        task = "O que é o esporte rayrox"
        self.judge(task, {"intencao": "pesquisa", "entidades": [{"texto": "rayrox", "tipo": "usuario", "precisa_pesquisa": False}]})
        self.assertEqual(self.m.mask(task), task)

    def test_username_in_a_social_request_is_masked(self):
        task = "segue o rosiro no instagram"
        self.judge(task, {"intencao": "acao", "entidades": [{"texto": "rosiro", "tipo": "usuario", "precisa_pesquisa": False}]})
        self.assertNotIn("rosiro", self.m.mask(task))

    def test_username_shape_is_masked_anywhere(self):
        task = "o que o joao.silva92 postou"
        self.judge(task, {"intencao": "pesquisa", "entidades": [{"texto": "joao.silva92", "tipo": "usuario", "precisa_pesquisa": False}]})
        self.assertNotIn("joao.silva92", self.m.mask(task))


class FindPackageTest(unittest.TestCase):
    """O app pelo nome que o dono ou o provedor usa, mesmo quando o aparelho o chama de outro jeito."""

    def setUp(self):
        packages = {"yt music": "com.google.android.apps.youtube.music", "sofascore": "com.sofascore.results",
                    "instagram": "com.instagram.android", "maps": "com.google.android.apps.maps"}
        for target, value in (("packages", packages), ("rivals", {})):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_names_the_phone_calls_otherwise(self):
        self.assertEqual(proxy.find_package("YouTube Music"), "com.google.android.apps.youtube.music")
        self.assertEqual(proxy.find_package("Google Maps"), "com.google.android.apps.maps")
        self.assertEqual(proxy.find_package("Sofa Score"), "com.sofascore.results")
        self.assertEqual(proxy.find_package("Instagran"), "com.instagram.android")
        self.assertIsNone(proxy.find_package("Netflix"))


class ReadValueTest(unittest.TestCase):
    """O valor que um "read" leu no aparelho não vai ao registro nem à conversa (que o provedor recebe depois)."""

    def test_value_stays_out_of_the_log_and_the_history(self):
        logged = []
        executor = proxy.Executor("qual o código", None, None)
        executor.plan = [{"action": "read", "target": ["código"], "pattern": "[0-9]{6}", "answer": "O código é {value}."}]
        for target, value in (("log", logged.append), ("detail", lambda *a, **k: None), ("executor", executor),
                              ("masker", Masker(Vault())), ("CACHE", False), ("COLLECT", False), ("TASK", "qual o código"),
                              ("CONVERSATION", {"turnos": [], "at": 0})):
            patcher = mock.patch.object(proxy, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        screen = ('<device_state>\n1. TextView: "Seu código" - (0,100,1080,190)\n2. TextView: "482913" - (0,200,1080,290)\n'
                  '3. TextView: "Mensagens" - (0,300,1080,390)\n</device_state>')
        answer = proxy.local_step(screen, "m", 0)
        self.assertIn("482913", answer)  # o dono recebe o valor
        self.assertNotIn("482913", str(logged))
        self.assertNotIn("482913", str(proxy.CONVERSATION))
        self.assertIn(proxy.READ_HIDDEN, str(proxy.CONVERSATION))
