import json
import os
import tempfile
import unittest
from unittest import mock

from lmphone import cache
from lmphone.executor import Executor
from tests.test_executor import PLAN, screen


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        cache.PATH = os.path.join(self.dir.name, "paths.json")

    def tearDown(self):
        self.dir.cleanup()

    # O Windows não guarda o modo 600 do arquivo (máquina de treino da RTX).
    @unittest.skipIf(os.name == "nt", "sem permissões POSIX no Windows")
    def test_same_request_ignores_case_and_punctuation(self):
        cache.save("Ative as notificações!", [{"action": "back"}], {"on": ["Notificações"]})
        self.assertEqual(cache.load("ative as  notificacoes"), ([{"action": "back"}], {"on": ["Notificações"]}))
        self.assertIsNone(cache.load("Desative as notificações"))
        self.assertEqual(os.stat(cache.PATH).st_mode & 0o777, 0o600)

    def test_entries_of_an_older_format_are_ignored(self):
        with open(cache.PATH, "w", encoding="utf-8") as f:
            json.dump({"tarefa": {"steps": [{"action": "back"}], "fails": 0}}, f)
        self.assertIsNone(cache.load("tarefa"))

    def test_entry_is_dropped_after_two_failures(self):
        cache.save("tarefa", [{"action": "back"}])
        self.assertFalse(cache.failed("tarefa"))
        self.assertTrue(cache.failed("tarefa"))
        self.assertIsNone(cache.load("tarefa"))

    def test_trail_replays_without_the_provider(self):
        asked = []

        def provider(prompt):
            asked.append(prompt)
            return json.dumps({"steps": [dict(PLAN[0]), {"action": "tap", "index": 3, "expected": []},
                                         {"action": "turn_on", "target": ["Avisos", "Notificações"]}],
                               "goal": {"on": ["Avisos", "Notificações"]}})

        home = screen(("TextView", "Conversas"), ("ImageView", ""))
        row = "<device_state>\n2. View: \"android.view.View\" ; isChecked={} - (0,300,1080,400)\n3. TextView: \"Notificações\" - (40,320,400,380)\n</device_state>"

        def run(executor, state):
            tools = [executor.step(screen(("TextView", "Início")))[1], executor.step(home)[1], executor.step(row.format(state))[1]]
            while 'name="complete"' not in tools[-1]:
                tools.append(executor.step(row.format(True))[1])
            return tools

        first = Executor("tarefa", provider, lambda wanted, labels: None)
        run(first, False)
        self.assertTrue(first.result == "confirmado" and first.cacheable)
        self.assertEqual([s["action"] for s in first.trail], ["open_app", "tap", "turn_on"])
        self.assertEqual(first.trail[1]["at"]["bounds"], [0, 300, 1080, 390])
        self.assertEqual(first.trail[2]["target"], ["Notificações"])

        again = Executor("tarefa", None, lambda wanted, labels: None)
        again.use(json.loads(json.dumps(first.trail)), first.goal)
        tools = run(again, False)
        self.assertIn('<parameter name="index">3</parameter>', tools[1])
        self.assertIn('name="click"', tools[2])
        self.assertIn('<parameter name="success">true</parameter>', tools[-1])
        self.assertEqual(len(asked), 1)

    def test_map_takes_another_request_through_known_screens(self):
        cache.MAPS = os.path.join(self.dir.name, "maps.json")
        cache.learn([{"action": "open_app", "target": ["Fotos"]}, {"action": "tap", "target": ["Perfil"]},
                     {"action": "tap", "target": ["Título"], "noop": True}, {"action": "tap", "target": ["Opções"]},
                     {"action": "tap", "target": ["Privacidade"]}, {"action": "turn_on", "target": ["Conta privada"]},
                     {"action": "tap", "target": ["Confirmar"], "if_missing": "skip"}, {"action": "back"},
                     {"action": "tap", "target": ["Tema"]}])
        tree = cache.maps()
        options = tree["fotos"]["children"]["Perfil"]["children"]["Opções"]
        self.assertEqual(sorted(options["children"]), ["Privacidade", "Tema"])
        self.assertEqual(options["children"]["Privacidade"]["controls"], ["Conta privada"])
        # Abrir e fechar o mesmo menu várias vezes não vira uma fila de telas no mapa.
        cache.learn([{"action": "open_app", "target": ["Câmera"]}] + [{"action": "tap", "target": [t]} for t in ("Flash", "Ligado") * 3])
        self.assertEqual(cache.maps()["camera"]["children"]["Flash"]["children"]["Ligado"]["children"], {})

        # Outro pedido: o plano chama o menu de "Menu" e chuta textos de conferência que não existem.
        executor = Executor("outra tarefa", None, lambda wanted, labels: self.fail("não devia perguntar à IA local"))
        executor.map = tree
        executor.plan = [{"action": "open_app", "target": ["Fotos"]},
                         {"action": "tap", "target": ["Perfil"], "expected": ["Texto que não existe"]},
                         {"action": "tap", "target": ["Menu"], "expected": ["Ajustes"]},
                         {"action": "turn_off", "target": ["Conta privada"]}]
        executor.step(screen(("TextView", "Início")))
        self.assertIn('<parameter name="index">2</parameter>', executor.step(screen(("Button", "Perfil"), ("TextView", "Feed")))[1])
        why, tool = executor.step(screen(("TextView", "Nome"), ("Button", "Opções")))
        self.assertIn("app map", why)
        self.assertIn('<parameter name="index">3</parameter>', tool)
        why, tool = executor.step(screen(("Button", "Privacidade"), ("Button", "Tema")))
        self.assertIn("Privacidade", why)
        row = "<device_state>\n2. View: \"android.view.View\" ; isChecked=True - (0,300,1080,400)\n3. TextView: \"Conta privada\" - (40,320,400,380)\n</device_state>"
        self.assertIn('name="click"', executor.step(row)[1])

    def test_map_is_rendered_for_the_plan_request(self):
        from lmphone.executor import render
        tree = {"fotos": {"controls": [], "children": {"Perfil": {"controls": ["Conta privada"], "children": {"Opções": {"controls": [], "children": {}}}}}}}
        self.assertIn("App fotos:\n  Perfil\n    [switch] Conta privada\n    Opções\n", render(tree))
        self.assertEqual(render({}), "none yet.")

    def test_typing_is_not_cacheable(self):
        executor = Executor("tarefa", None, None)
        executor.plan = [{"action": "type", "text": "oi"}]
        executor.step(screen(("TextView", "Início")))
        self.assertFalse(executor.cacheable)


if __name__ == "__main__":
    unittest.main()


class ScreenNamesTest(unittest.TestCase):
    """O mapa guarda os nomes das telas do caminho (2026-11-17: o guia mandou procurar "Tela"; aqui é "Visor")."""

    def test_names_of_the_screens_go_to_the_map_and_to_the_provider(self):
        import tempfile
        from lmphone import executor
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(cache, "MAPS", os.path.join(folder, "maps.json")):
            trail = [{"action": "open_settings", "target": ["display"]},
                     {"action": "tap", "target": ["Tamanho e estilo da fonte"],
                      "seen": ["Modo escuro", "Tamanho e estilo da fonte", "Ana Souza"]}]
            cache.learn(trail, keep=lambda label: label != "Ana Souza")
            tree = cache.maps()
            visor = tree["settings"]["children"]["Visor"]
            self.assertEqual(visor["seen"], ["Modo escuro", "Tamanho e estilo da fonte"])
            self.assertIn("Tamanho e estilo da fonte", visor["children"])
            text = executor.render(executor.related(tree, "como deixo a letra maior? tamanho da fonte"))
            self.assertIn("Visor", text)
            self.assertIn("(also on this screen: Modo escuro; Tamanho e estilo da fonte)", text)

    def test_the_path_cache_does_not_keep_the_names(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(cache, "PATH", os.path.join(folder, "p.json")):
            cache.save("liga o modo escuro", [{"action": "tap", "target": ["Modo escuro"], "seen": ["Modo escuro"]}])
            self.assertEqual(cache.load("liga o modo escuro")[0], [{"action": "tap", "target": ["Modo escuro"]}])
