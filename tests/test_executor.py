import json
import os
import unittest
import time

from lmphone.executor import GUIDE_LIMIT, GUIDE_REMIND, GUIDE_REMINDER, MAX_SCROLLS, SLIDER, SLIDER_DOWN, Executor, parse_screen, redact, related


def screen(*rows):
    """Monta uma tela no formato do Mobilerun. Cada linha: (classe, texto) ou (classe, texto, marcado)."""
    lines = ['1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)']
    for i, row in enumerate(rows, 2):
        cls, text = row[0], row[1]
        body = f'"{text}"' if text else f'"android.view.{cls}"'
        checked = f" ; isChecked={row[2]}" if len(row) > 2 else ""
        lines.append(f"{i}. {cls}: {body}{checked} - (0,{i * 100},1080,{i * 100 + 90})")
    return "<device_state>\n**Current Phone State:**\n" + "\n".join(lines) + "\n</device_state>"


PLAN = [
    {"action": "open_app", "target": ["Mensagens"], "if_missing": "help", "expected": ["Conversas"]},
    {"action": "tap", "target": ["Ajustes", "Configurações"], "if_missing": "scroll", "expected": ["Notificações"]},
    {"action": "turn_on", "target": ["Notificações"], "if_missing": "help", "expected": ["Notificações"]},
]
GOAL = {"on": ["Notificações"]}


def switch(label, state, *more):
    """Uma tela com uma linha de chave (o controle marcável envolve o rótulo) e, abaixo, outros elementos."""
    lines = [f'2. View: "android.view.View" ; isChecked={state} - (0,300,1080,400)', f'3. TextView: "{label}" - (40,320,400,380)']
    lines += [f'{i}. {cls}: "{text}" - (0,{i * 100 + 200},1080,{i * 100 + 290})' for i, (cls, text) in enumerate(more, 4)]
    return "<device_state>\n" + "\n".join(lines) + "\n</device_state>"


# Trecho da tela Display das Configurações do aparelho: opções com o botão embaixo do rótulo e chave ao lado do título.
DISPLAY = """<device_state>
• **App:** Settings (com.android.settings)
1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)
2. LinearLayout: "com.android.settings:id/item1", "com.android.settings:id/item1" - (28,297,540,838)
3. TextView: "com.android.settings:id/icon_title", "Light" - (50,656,529,715)
4. RadioButton: "com.android.settings:id/radio_button", "com.android.settings:id/radio_button" ; isChecked={light} - (244,726,334,816)
5. LinearLayout: "com.android.settings:id/item2", "com.android.settings:id/item2" - (540,297,1052,838)
6. TextView: "com.android.settings:id/icon_title", "Dark" - (551,656,1030,715)
7. RadioButton: "com.android.settings:id/radio_button", "com.android.settings:id/radio_button" ; isChecked={dark} - (745,726,835,816)
8. LinearLayout: "android.widget.LinearLayout" - (28,1753,1052,1911)
9. TextView: "android:id/title", "Eye comfort shield" - (79,1799,512,1865)
10. Switch: "android:id/switch_widget", "Eye comfort shield" ; isChecked={shield} - (863,1753,990,1911)
</device_state>"""


class ExecutorTest(unittest.TestCase):
    def setUp(self):
        self.asked, self.answers, self.picked = [], [{"steps": [dict(s) for s in PLAN], "goal": dict(GOAL)}], None
        self.e = Executor("tarefa", self.provider, lambda wanted, labels: self.picked)

    def provider(self, prompt):
        self.asked.append(prompt)
        return "```json\n" + json.dumps(self.answers.pop(0), ensure_ascii=False) + "\n```"

    def tool(self, text):
        why, tool = self.e.step(text)
        # A espera única para a tela assentar: o Mobilerun devolve a mesma tela.
        while "still be changing" in why:
            why, tool = self.e.step(text)
        return tool

    def test_waits_once_before_giving_up_on_a_screen(self):
        self.e.step(screen(("TextView", "Início")))
        why, tool = self.e.step(screen(("TextView", "Carregando")))
        self.assertIn("still be changing", why)
        self.assertIn('name="wait"', tool)
        self.assertIn('name="click"', self.e.step(screen(("TextView", "Conversas"), ("Button", "Ajustes")))[1])
        self.assertEqual(self.asked, self.asked[:1])

    def test_parse_screen(self):
        elements, _ = parse_screen(screen(("TextView", "Conversas"), ("View", "", False)))
        self.assertEqual([(e.index, e.text, e.checked) for e in elements], [(1, "", None), (2, "Conversas", None), (3, "", False)])

    def test_follows_plan_by_exact_label(self):
        self.assertIn('name="open_app"', self.tool(screen(("TextView", "Início"))))
        self.assertIn('<parameter name="index">3</parameter>', self.tool(screen(("TextView", "Conversas"), ("Button", "Ajustes"))))
        self.assertIn('<parameter name="index">2</parameter>', self.tool(switch("Notificações", False)))
        done = self.tool(switch("Notificações", True))
        self.assertIn('name="complete"', done)
        self.assertIn('"success">true', done)
        self.assertEqual(self.e.result, "confirmado")
        self.assertEqual(len(self.asked), 1)
        self.assertIn('"goal"', self.asked[0])

    def test_opens_app_directly_when_it_can(self):
        launched = []
        self.e.launch = lambda name: launched.append(name) or True
        self.assertIn('name="wait"', self.tool(screen(("TextView", "Início"))))
        self.assertEqual(launched, ["Mensagens"])
        self.e = Executor("tarefa", self.provider, None, launch=lambda name: False)
        self.answers = [{"steps": [dict(s) for s in PLAN], "goal": dict(GOAL)}]
        self.assertIn('name="open_app"', self.tool(screen(("TextView", "Início"))))

    def test_help_hides_long_texts_and_numbers(self):
        long = "Seu código de verificação é 482913. Não compartilhe com ninguém, nem com atendentes."
        raw = parse_screen(screen(("TextView", long), ("TextView", "Código 482913"), ("Button", "Wi-Fi 5"), ("View", "")))[1]
        hidden = redact(raw)
        self.assertNotIn("482913", hidden)
        self.assertNotIn("compartilhe", hidden)
        self.assertIn('2. TextView: "[hidden text]" - (0,200,1080,290)', hidden)
        self.assertIn('"Código ######"', hidden)
        self.assertIn('"Wi-Fi 5"', hidden)
        self.assertIn('"android.view.View" - (0,500,1080,590)', hidden)
        self.assertEqual(len(hidden.splitlines()), len(raw.splitlines()))

    def test_skips_opening_an_app_already_opened(self):
        self.e = Executor("tarefa", self.provider, None, opened="mensagens")
        self.assertIn('name="click"', self.tool(screen(("TextView", "Conversas"), ("Button", "Ajustes"))))

    def test_stops_when_stuck_on_the_same_step(self):
        again = {"steps": [dict(PLAN[1], if_missing="help")]}
        self.answers = [{"steps": [dict(PLAN[0])] + again["steps"]}, again, again]
        self.e.pick = lambda wanted, labels: None
        self.tool(screen(("TextView", "Início")))
        done = self.tool(screen(("TextView", "Conversas"), ("Button", "Outra coisa")))
        self.assertIn('name="complete"', done)
        self.assertIn("preso no mesmo passo", done)
        self.assertEqual(len(self.asked), 3)
        self.assertIn('did NOT work', self.asked[2])
        self.assertNotIn(": none", self.asked[2].split("did NOT work")[1].split("\n")[0])

    def test_scrolls_when_target_is_further_down(self):
        self.tool(screen(("TextView", "Início")))
        page = screen(("TextView", "Conversas"), ("Button", "Arquivadas"))
        self.assertIn('name="swipe"', self.tool(page))
        self.assertEqual(self.e.by, "código")
        # A tela não mudou com a rolagem: a lista chegou ao fim, e rolar de novo não adianta.
        self.answers = [{"finish": {"success": False, "message": "Não achei."}}]
        self.assertIn('name="complete"', self.tool(page))
        self.assertIn("none of the target labels is on screen", self.asked[1])

    def test_local_ai_matches_other_label(self):
        self.e.plan, self.e.i, self.e.scrolls = [dict(s) for s in PLAN], 1, MAX_SCROLLS
        self.picked = "Opções"
        self.assertIn('<parameter name="index">3</parameter>', self.tool(screen(("TextView", "Conversas"), ("Button", "Opções"), ("Button", "Arquivadas"))))
        self.assertEqual(self.e.by, "IA local")
        # O toque foi um palpite da IA local: a tela mudou, mas sem nenhum dos textos esperados o provedor confere.
        self.answers = [{"finish": {"success": False, "message": "Tela errada."}}]
        self.assertIn('"success">false', self.tool(screen(("TextView", "Arquivo morto"))))
        self.assertIn("the local model guessed", self.asked[0])

    def test_records_each_choice_with_who_chose_and_the_effect(self):
        # Coleta para o treino: o toque por rótulo exato que mudou a tela foi conferido; o palpite da IA local que
        # terminou num pedido de ajuda foi desfeito; uma pergunta sem resposta vira "nenhum".
        self.e.plan = [{"action": "tap", "target": ["Sobre"]}, {"action": "tap", "target": ["Versão"], "expected": ["Android"]}]
        self.tool(screen(("Button", "Sobre")))
        self.picked = "Modelo"
        self.tool(screen(("TextView", "Sobre o telefone"), ("TextView", "Modelo")))
        self.answers = [{"finish": {"success": False, "message": "Tela errada."}}]
        self.tool(screen(("TextView", "Galaxy S23+")))
        self.assertEqual([(c["por"], c["escolhido"], c["efeito"]) for c in self.e.choices],
                         [("rótulo exato", "Sobre", "conferido"), ("IA local", "Modelo", "desfeito")])
        self.assertEqual(self.e.choices[1]["passo"], {"acao": "tap", "alvo": ["Versão"]})
        self.assertEqual(self.e.choices[1]["rotulos"], ["Sobre o telefone", "Modelo"])
        self.e.plan, self.e.i, self.e.scrolls, self.e.asked, self.picked = [{"action": "tap", "target": ["Versão"]}], 0, MAX_SCROLLS, None, None
        self.answers = [{"finish": {"success": False, "message": "Não achei."}}]
        self.tool(screen(("TextView", "Modelo"), ("TextView", "Bateria")))
        self.assertEqual((self.e.choices[-1]["escolhido"], self.e.choices[-1]["efeito"]), (None, "nenhum"))

    def test_step_counts_by_its_effect_not_by_the_guessed_texts(self):
        self.e.plan = [{"action": "tap", "target": ["Sobre"], "expected": ["Texto que o plano chutou"]},
                       {"action": "tap", "target": ["Versão"], "if_missing": "scroll"}]
        self.assertIn('name="click"', self.tool(screen(("Button", "Sobre"))))
        self.assertIn('name="swipe"', self.tool(screen(("TextView", "Sobre o telefone"), ("TextView", "Modelo"))))
        self.assertEqual(self.asked, [])

    def test_tap_that_changes_nothing_asks_for_help(self):
        self.e.plan = [{"action": "tap", "target": ["Sobre"]}, {"action": "tap", "target": ["Versão"], "if_missing": "help"}]
        self.e.pick = lambda wanted, labels: None
        page = screen(("Button", "Sobre"))
        self.assertIn('name="click"', self.tool(page))
        self.answers = [{"finish": {"success": False, "message": "O botão não responde."}}]
        self.assertIn('"success">false', self.tool(page))
        self.assertIn("nothing changed on screen", self.asked[0])
        self.assertEqual(self.e.result, "falhou")

    def test_turn_taps_the_switch_and_tap_goes_to_the_title(self):
        page = DISPLAY.format(light=True, dark=False, shield=False)
        self.e.plan = [{"action": "turn_on", "target": ["Eye comfort shield"]}]
        self.assertIn('<parameter name="index">10</parameter>', self.e.step(page)[1])
        self.e = Executor("tarefa", None, None)
        self.e.plan = [{"action": "tap", "target": ["Eye comfort shield"]}]
        self.assertIn('<parameter name="index">9</parameter>', self.e.step(page)[1])

    def test_option_with_the_button_under_the_label_has_a_state(self):
        self.e.use([{"action": "open_app", "target": ["Settings"]}, {"action": "turn_on", "target": ["Dark"]}], {"on": ["Dark"]})
        self.e.opened = "settings"
        self.assertIn('<parameter name="index">7</parameter>', self.e.step(DISPLAY.format(light=True, dark=False, shield=False))[1])
        self.assertIn('"success">true', self.e.step(DISPLAY.format(light=False, dark=True, shield=False))[1])
        self.assertEqual(self.e.result, "confirmado")
        self.assertEqual(self.asked, [])

    def test_tap_on_the_goal_switch_becomes_a_turn(self):
        # O plano manda tocar às cegas na chave do objetivo, que já está ligada: nada é tocado.
        self.answers = [{"steps": [{"action": "tap", "target": ["Notificações"]}, {"action": "check", "target": ["Notificações"]}],
                         "goal": {"on": "Notificações"}}]
        self.assertIn('"success">true', self.tool(switch("Notificações", True)))
        self.assertEqual([s["action"] for s in self.e.trail], ["turn_on"])
        self.assertEqual(self.e.result, "já estava")

    def test_plan_is_adjusted_to_what_the_executor_does(self):
        steps = self.e.adopt([{"action": "tap", "target": ["Search or type URL", "Address bar"]},
                              {"action": "type", "target": ["Address bar"], "text": "example.com"},
                              {"action": "scroll", "target": ["Dark"]}, {"action": "check", "target": ["Dark"]},
                              {"action": "tap", "target": ["Dark", "Dark mode"]}], {"on": "Dark mode"}, complete=True)
        self.assertEqual([s["action"] for s in steps], ["type", "turn_on"])
        self.assertEqual(self.e.goal, {"on": ["Dark mode", "Dark"]})  # "Dark" veio do passo do próprio provedor
        twice = self.e.adopt([{"action": "tap", "target": ["Dark mode"]}, {"action": "turn_on", "target": ["Dark mode"]}])
        self.assertEqual(len(twice), 1)

    def test_local_ai_label_for_the_goal_switch_is_checked_by_the_provider(self):
        # O plano chama a opção de "Dark mode"; na tela ela é "Dark". A IA local acha, o estado é lido no controle
        # tocado, e quem confirma que é mesmo o objetivo é o provedor, corrigindo o rótulo.
        self.e.use([{"action": "turn_on", "target": ["Dark mode"], "if_missing": "help"}], {"on": ["Dark mode"]})
        self.picked = "Dark"
        self.assertIn('<parameter name="index">7</parameter>', self.tool(DISPLAY.format(light=True, dark=False, shield=False)))
        self.answers = [{"goal": {"on": ["Dark"]}, "finish": {"success": True, "message": "Dark is selected."}}]
        done = self.tool(DISPLAY.format(light=False, dark=True, shield=False))
        self.assertEqual(len(self.asked), 1)
        self.assertIn("Dark is selected.", done)
        self.assertEqual(self.e.result, "confirmado")

    def test_plan_that_forgets_the_goal_switch_gets_the_step(self):
        self.answers = [{"steps": [{"action": "tap", "target": ["Ajustes"]}], "goal": {"off": ["Notificações"]}}]
        self.assertIn('<parameter name="index">2</parameter>', self.tool(screen(("Button", "Ajustes"))))
        self.assertIn('<parameter name="index">2</parameter>', self.tool(switch("Notificações", True)))
        self.assertIn("conferido na tela", self.tool(switch("Notificações", False)))

    def test_goal_switch_on_screen_skips_the_steps_before_it(self):
        self.e.use([{"action": "tap", "target": ["Tela que não existe"], "if_missing": "help"},
                    {"action": "turn_on", "target": ["Notificações"]}], dict(GOAL))
        self.assertIn('<parameter name="index">2</parameter>', self.e.step(switch("Notificações", False))[1])
        self.assertEqual(self.asked, [])

    def test_switch_that_loads_after_its_title_is_waited_for(self):
        self.e.use([{"action": "turn_on", "target": ["Eye comfort shield"]}], {"on": ["Eye comfort shield"]})
        loading = "<device_state>\n9. TextView: \"android:id/title\", \"Eye comfort shield\" - (79,1799,512,1865)\n</device_state>"
        self.assertIn('name="wait"', self.e.step(loading)[1])
        self.assertIn('<parameter name="index">10</parameter>', self.e.step(DISPLAY.format(light=True, dark=False, shield=False))[1])

    def test_label_without_a_switch_is_the_way_to_it(self):
        # "Dark mode" aqui é uma linha que leva à tela da opção (um resultado de busca): o passo é refeito lá.
        self.e.use([{"action": "turn_on", "target": ["Dark mode", "Dark"]}], {"on": ["Dark mode", "Dark"]})
        self.assertIn('<parameter name="index">3</parameter>', self.tool(screen(("TextView", "Results"), ("TextView", "Dark mode"))))
        self.assertIn('<parameter name="index">7</parameter>', self.tool(DISPLAY.format(light=True, dark=False, shield=False)))
        self.assertIn("conferido na tela", self.tool(DISPLAY.format(light=False, dark=True, shield=False)))
        self.assertEqual(self.asked, [])

    def test_unreadable_goal_switch_asks_the_provider_once(self):
        self.e.use([{"action": "turn_on", "target": ["Flash"]}], {"on": ["Flash"]})
        camera = screen(("FrameLayout", "Flash"), ("FrameLayout", "Take picture"))
        self.assertIn('name="click"', self.tool(camera))
        self.answers = [{"finish": {"success": True, "message": "The flash menu was tapped."}}]
        done = self.tool(screen(("FrameLayout", "Flash"), ("FrameLayout", "Take picture"), ("FrameLayout", "On")))
        self.assertIn("cannot be read", self.asked[0])
        self.assertIn("Não consegui conferir", done)
        self.assertEqual(self.e.result, "sem confirmação")

    def test_tap_on_a_row_that_is_the_switch_is_not_blind(self):
        # A linha inteira é a chave (como no Instagram): o toque do plano a inverteria. O provedor diz o estado.
        self.e.use([{"action": "tap", "target": ["Conta privada"]}], {"shows": ["Sua conta é privada"]})
        self.answers = [{"steps": [{"action": "turn_on", "target": ["Conta privada"]}], "goal": {"on": ["Conta privada"]}}]
        self.assertIn('"success">true', self.tool(switch("Conta privada", True)))
        self.assertIn("which is a switch that is now ON", self.asked[0])
        self.assertEqual(self.e.result, "já estava")
        self.assertEqual([s["action"] for s in self.e.trail], ["turn_on"])
        # Com a chave ao lado do título (Configurações), o toque no título é navegação e segue valendo.
        self.e = Executor("tarefa", self.provider, None)
        self.e.plan = [{"action": "tap", "target": ["Eye comfort shield"]}]
        self.assertIn('<parameter name="index">9</parameter>', self.e.step(DISPLAY.format(light=True, dark=False, shield=True))[1])

    def test_provider_cannot_turn_what_it_sees_into_the_goal(self):
        self.e.use([{"action": "tap", "target": ["Ajustes"]}], {"shows": ["Conta privada ativada"]})
        self.tool(screen(("Button", "Ajustes")))
        self.answers = [{"finish": {"success": True, "message": "A dialog is open."}, "goal": {"shows": ["Tornar a conta pública?"]}}]
        done = self.tool(screen(("TextView", "Tornar a conta pública?"), ("Button", "Cancelar")))
        self.assertIn("Não consegui conferir", done)
        self.assertEqual(self.e.result, "sem confirmação")
        self.assertEqual(self.e.goal, {"shows": ["Conta privada ativada"]})

    def test_plan_request_only_gets_the_map_of_what_the_task_is_about(self):
        tree = {"settings": {"controls": [], "children": {"Display": {"controls": ["Eye comfort shield"], "children": {}}}},
                "instagram": {"controls": [], "children": {"Profile": {"controls": [], "children": {}}}}}
        self.assertEqual(related(tree, "Remove the yellow bar that shows up on the edge of the screen"), {})
        self.assertEqual(list(related(tree, "Turn on the eye comfort shield")), ["settings"])
        self.assertEqual(list(related(tree, "Open my Instagram and go to the feed")), ["instagram"])

    def test_goal_text_only_counts_when_it_is_new(self):
        self.e.use([{"action": "tap", "target": ["Ajustes"]}], {"shows": ["Ajustes", "Conta e privacidade"]})
        self.assertIn('name="click"', self.tool(screen(("Button", "Ajustes"))))
        done = self.tool(screen(("TextView", "Ajustes"), ("TextView", "Ajustes gerais")))
        self.assertIn("Não consegui conferir", done)
        self.assertEqual(self.e.result, "sem confirmação")
        self.e = Executor("tarefa", self.provider, None)
        self.e.use([{"action": "tap", "target": ["Ajustes"]}], {"shows": ["Ajustes", "Conta e privacidade"]})
        self.tool(screen(("Button", "Ajustes")))
        self.tool(screen(("TextView", "Ajustes"), ("TextView", "Conta e privacidade do app")))
        self.assertEqual(self.e.result, "confirmado")

    def test_goal_not_met_asks_the_provider(self):
        self.e.use([{"action": "tap", "target": ["Ajustes"]}], {"shows": ["Tela de ajustes"]})
        self.tool(screen(("Button", "Ajustes")))
        # O provedor diz que está feito, mas a tela não mostra o objetivo: o resultado fica sem confirmação.
        self.answers = [{"finish": {"success": True, "message": "The settings screen is open."}}]
        done = self.tool(screen(("TextView", "Configurações"), ("TextView", "Geral")))
        self.assertIn("the goal is not met", self.asked[0])
        self.assertIn('"success">true', done)
        self.assertIn("The settings screen is open. (Não consegui conferir", done)
        self.assertEqual(self.e.result, "sem confirmação")

    def test_switch_already_on_is_skipped(self):
        self.e.plan, self.e.i = [dict(s) for s in PLAN], 2
        self.e.goal = dict(GOAL)
        done = self.tool(switch("Notificações", True))
        # Nada foi tocado: o usuário fica sabendo qual chave já estava certa, e o resultado não vale como mudança feita.
        self.assertIn("“Notificações” já estava ligado; não mudei nada.", done)
        self.assertEqual(self.e.result, "já estava")

    def test_switch_confirms_dialog_and_checks_by_state(self):
        self.e.plan, self.e.i, self.e.goal = [dict(s) for s in PLAN], 2, dict(GOAL)
        row = "<device_state>\n2. View: \"android.view.View\" ; isChecked={} - (0,300,1080,400)\n3. TextView: \"Notificações\" - (40,320,400,380)\n</device_state>"
        self.assertIn('name="click"', self.e.step(row.format(False))[1])
        dialog = screen(("TextView", "Ativar notificações?"), ("Button", "Turn on notifications"), ("Button", "Cancel"))
        self.assertIn('name="wait"', self.e.step(dialog)[1])
        why, tool = self.e.step(dialog)
        self.assertIn("Turn on notifications", why)
        self.assertIn('<parameter name="index">3</parameter>', tool)
        done = self.e.step(row.format(True))[1]
        self.assertIn('<parameter name="success">true</parameter>', done)
        self.assertEqual(self.asked, [])

    def test_blind_tap_on_a_switch_is_left_to_the_turn_step(self):
        self.e.plan = [{"action": "tap", "target": ["Notificações"]}, {"action": "turn_on", "target": ["Notificações"]}]
        self.e.reviewed = True  # a conferência final pelo provedor tem testes próprios (ReviewTest)
        row = "<device_state>\n2. View: \"android.view.View\" ; isChecked=True - (0,300,1080,400)\n3. TextView: \"Notificações\" - (40,320,400,380)\n</device_state>"
        self.assertIn('name="complete"', self.tool(row))
        self.assertEqual([s["action"] for s in self.e.trail], ["turn_on"])
        self.assertEqual(self.e.result, "sem confirmação")  # este plano veio sem objetivo
        self.assertEqual(self.asked, [])

    def test_textless_screen_asks_provider_for_index(self):
        self.e.plan, self.e.i = [dict(s) for s in PLAN], 1
        self.answers = [{"steps": [{"action": "tap", "index": 3, "expected": ["Notificações"]}] + PLAN[2:]}]
        tool = self.tool(screen(("Button", "Voltar"), ("View", "")))
        self.assertIn('<parameter name="index">3</parameter>', tool)
        self.assertIn("almost no text", self.asked[0])
        self.assertIn("<device_state>", self.asked[0])

    def test_identifier_label_matches_plain_target(self):
        self.e.plan = [{"action": "tap", "target": ["On", "Flash on"], "if_missing": "help", "expected": []}]
        tool = self.tool(screen(("FrameLayout", "MOTION_PHOTO_OFF"), ("FrameLayout", "BACK_FLASH_AUTO"), ("FrameLayout", "BACK_FLASH_ON")))
        self.assertIn('<parameter name="index">4</parameter>', tool)
        self.assertEqual(self.asked, [])

    def test_reads_value_on_device(self):
        self.e.plan = [{"action": "read", "target": ["verification code", "code"], "pattern": r"\b\d{6}\b", "if_missing": "help"}]
        done = self.tool(screen(("TextView", "Entrega prevista para 12/10"), ("TextView", "Your verification code is 482913")))
        self.assertIn('<parameter name="message">482913</parameter>', done)
        self.assertEqual(self.asked, [])

    def test_reads_the_most_specific_match_and_the_value_under_a_title(self):
        labels = ["Red backpack: R$ 149,90", "Blue backpack: R$ 189,90", "Android version", "16", "One UI version", "8.5"]
        price = {"action": "read", "target": ["blue backpack", "backpack"], "pattern": r"\d+,\d{2}"}
        self.assertEqual(Executor.read(price, labels), "189,90")
        # O plano pôs a moeda antes do item: vale o trecho que tem mais palavras do alvo, não o primeiro que tem uma.
        self.assertEqual(Executor.read(dict(price, target=["price", "R$", "Blue backpack", "backpack"]), labels), "189,90")
        self.assertEqual(Executor.read({"action": "read", "target": ["Android version"], "pattern": r"\d+(?:\.\d+)*"}, labels), "16")
        # O padrão também casa com o título ("open" em "Opening hours"): vale a linha de baixo.
        hours = ["Opening hours", "Monday to Friday, from 9:00 to 18:00.", "Closed on weekends."]
        step = {"action": "read", "target": ["opening hours", "hours", "open"], "pattern": r"(?i)(mon|open|closed).*"}
        self.assertEqual(Executor.read(step, hours), "Monday to Friday, from 9:00 to 18:00.")

    def test_types_into_the_named_field_and_presses_enter(self):
        self.e.use([{"action": "type", "target": ["Search YouTube"], "text": "lofi music", "expected": ["Results"]},
                    {"action": "enter"}], {"shows": ["Filters"]})
        # Primeiro o toque que dá o foco ao campo; a digitação vem na leitura seguinte, sem índice.
        search = screen(("ImageView", "Voice search"), ("EditText", "Search YouTube"))
        tool = self.e.step(search)[1]
        self.assertIn('<invoke name="click">', tool)
        self.assertIn('<parameter name="index">3</parameter>', tool)
        tool = self.e.step(search)[1]
        self.assertIn('<invoke name="type">', tool)
        self.assertIn('<parameter name="text">lofi music</parameter>', tool)
        self.assertNotIn('name="index"', tool)
        self.assertNotIn("clear", tool)
        # O texto digitado aparece no campo: basta, mesmo sem nenhum dos textos que o plano chutou em `expected`.
        tool = self.e.step(screen(("ImageView", "Voice search"), ("EditText", "lofi music")))[1]
        self.assertIn('<invoke name="system_button">', tool)
        self.assertIn('<parameter name="button">enter</parameter>', tool)
        self.assertIn('"success">true', self.e.step(screen(("Button", "Filters")))[1])
        self.assertEqual(self.asked, [])
        self.assertFalse(self.e.cacheable)

    def test_types_into_the_only_field_or_the_focused_one(self):
        self.e.plan = [{"action": "type", "text": "abc", "clear": True}]
        page = screen(("TextView", "Título"), ("EditText", ""))
        self.assertIn('<parameter name="index">3</parameter>', self.e.step(page)[1])
        tool = self.e.step(page)[1]
        self.assertIn('<invoke name="type">', tool)
        self.assertIn('<parameter name="clear">true</parameter>', tool)
        self.e = Executor("tarefa", self.provider, None)
        self.e.plan = [{"action": "type", "text": "abc"}]
        tool = self.e.step(screen(("EditText", ""), ("EditText", "")))[1]
        self.assertIn('<invoke name="type">', tool)
        self.assertNotIn('name="index"', tool)

    def test_does_not_type_over_what_an_earlier_step_typed(self):
        self.e.use([{"action": "type", "target": ["Untitled"], "text": "lmphone test", "clear": True},
                    {"action": "type", "target": ["Start writing"], "text": "corpo", "clear": True}], {"shows": ["lmphone test"]})
        self.assertIn('<invoke name="click">', self.e.step(screen(("EditText", "Untitled")))[1])
        self.assertIn('<parameter name="text">lmphone test</parameter>', self.e.step(screen(("EditText", "Untitled")))[1])
        # O campo do corpo não existe, e o único campo da tela é o título recém-digitado: não é ali que se digita.
        self.answers = [{"steps": [{"action": "enter"}, {"action": "type", "text": "corpo"}]}]
        tool = self.tool(screen(("EditText", "lmphone test")))
        self.assertIn('<parameter name="button">enter</parameter>', tool)
        self.assertIn("the only text field holds the text typed by an earlier step", self.asked[0])
        tool = self.tool(screen(("EditText", "lmphone test"), ("EditText", "Write something")))
        self.assertIn('<parameter name="text">corpo</parameter>', tool)
        self.assertNotIn("clear", tool)

    def test_waits_for_the_typed_text_to_arrive(self):
        self.e.use([{"action": "type", "target": ["Search"], "text": "lofi music"}, {"action": "enter"}], {"shows": ["Filters"]})
        self.e.step(screen(("EditText", "Search")))
        self.assertIn('<invoke name="type">', self.e.step(screen(("EditText", "Search")))[1])
        why, tool = self.e.step(screen(("EditText", "lofi mu")))
        self.assertIn("still be changing", why)
        self.assertIn('<parameter name="button">enter</parameter>', self.e.step(screen(("EditText", "lofi music")))[1])
        self.assertEqual(self.asked, [])

    def test_tool_error_goes_straight_to_help(self):
        self.e.plan = [{"action": "type", "text": "abc", "expected": ["abc"]}]
        self.e.step(screen(("EditText", "")))
        self.assertIn('<invoke name="type">', self.e.step(screen(("EditText", "")))[1])
        self.answers = [{"finish": {"success": False, "message": "Não consegui digitar."}}]
        failed = "<function_results>\n<result>\n<name>type</name>\n<error>Failed to type text: input failed</error>\n</result>\n</function_results>\n"
        why, tool = self.e.step(failed + screen(("EditText", "")))
        self.assertIn('name="complete"', tool)
        self.assertIn("the tool reported an error: Failed to type text: input failed", self.asked[0])
        self.assertEqual(self.e.tool_error, "Failed to type text: input failed")

    def test_provider_can_end_the_task(self):
        self.e.plan, self.e.i = [dict(PLAN[0]), dict(PLAN[1], if_missing="help")], 1
        self.e.pick = lambda wanted, labels: None
        self.answers = [{"finish": {"success": False, "message": "O app pediu login."}}]
        done = self.tool(screen(("TextView", "Entrar"), ("Button", "Criar conta")))
        self.assertIn('"success">false', done)
        self.assertIn("O app pediu login.", done)
        self.assertEqual(self.e.result, "falhou")


if __name__ == "__main__":
    unittest.main()


class ReviewTest(unittest.TestCase):
    """No fim do plano, o provedor confere a tela final contra o pedido, uma vez (o objetivo que ele chutou pode estar
    cumprido sem o pedido estar: a lista de farmácias mostra "farmácia")."""

    def setUp(self):
        self.asked, self.answers = [], []
        self.e = Executor("procura a farmácia mais próxima", self.provider, lambda wanted, labels: None)
        self.e.plan, self.e.goal, self.e.start = [], {"shows": ["Farmácias"]}, set()

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def run_until_action(self, text):
        why, tool = self.e.step(text)
        while "still be changing" in why:
            why, tool = self.e.step(text)
        return why, tool

    def test_review_finishes_when_the_provider_agrees(self):
        self.answers = [{"finish": {"success": True, "message": "Aberta."}}]
        why, tool = self.run_until_action(screen(("TextView", "Farmácias"), ("Button", "Rotas")))
        self.assertEqual(len(self.asked), 1)
        self.assertIn("check this final screen", self.asked[0])
        self.assertIn('name="complete"', tool)

    def test_review_adds_the_missing_steps(self):
        self.answers = [{"steps": [{"action": "tap", "target": ["Farmácia Central"]}]}]
        why, tool = self.run_until_action(screen(("TextView", "Farmácias"), ("TextView", "Farmácia Central")))
        self.assertIn('name="click"', tool)
        self.assertIn("Farmácia Central", why)
        self.assertTrue(self.e.reviewed)

    def test_no_review_for_a_cached_path_or_a_switch_goal(self):
        self.e.cached = True
        self.assertIn('name="complete"', self.run_until_action(screen(("TextView", "Farmácias")))[1])
        other = Executor("liga as notificações", self.provider, lambda wanted, labels: None)
        other.plan, other.goal = [], {"on": ["Notificações"]}
        why, tool = other.step(switch("Notificações", True))
        while "still be changing" in why:
            why, tool = other.step(switch("Notificações", True))
        self.assertIn('name="complete"', tool)
        self.assertEqual(self.asked, [])


class StateTest(unittest.TestCase):
    """O estado do aparelho (facts.py) vai no pedido do plano; um objetivo por fato é conferido antes do primeiro passo
    e depois de cada um, e a mesma ação na mesma tela não é repetida sem o provedor olhar (o celular já estava na rede
    pedida e o agente tocava nela de novo até desistir)."""

    def setUp(self):
        self.asked, self.answers = [], []
        self.state = {"wifi": "ALAMEDA", "airplane_mode": False}
        self.e = Executor("conecta na alamada 2g", self.provider, lambda wanted, labels: None, facts=lambda: dict(self.state))

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def run_until_action(self, text):
        why, tool = self.e.step(text)
        while "still be changing" in why:
            why, tool = self.e.step(text)
        return why, tool

    def test_plan_prompt_has_the_state(self):
        self.answers = [{"finish": {"success": True, "message": "Já conectado."}, "goal": {"fact": {"wifi": "ALAMEDA"}}}]
        why, tool = self.run_until_action(screen(("TextView", "Início")))
        self.assertIn("wifi: ALAMEDA; airplane_mode: off", self.asked[0])
        self.assertIn('name="complete"', tool)
        self.assertEqual(self.e.result, "já estava")
        self.assertEqual(len(self.asked), 1)

    def test_fact_goal_stops_the_plan_as_soon_as_it_holds(self):
        self.state["wifi"] = "on, not connected"
        self.answers = [{"steps": [{"action": "tap", "target": ["Wi-Fi"]}, {"action": "tap", "target": ["ALAMEDA"]},
                                   {"action": "tap", "target": ["Conectar"]}], "goal": {"fact": {"wifi": "ALAMEDA"}}}]
        self.assertIn('name="click"', self.run_until_action(screen(("TextView", "Wi-Fi")))[1])
        self.assertIn('name="click"', self.run_until_action(screen(("TextView", "ALAMEDA")))[1])
        self.state["wifi"] = "ALAMEDA"  # conectou sem precisar do terceiro passo
        why, tool = self.run_until_action(screen(("TextView", "ALAMEDA"), ("TextView", "Connected")))
        self.assertIn('name="complete"', tool)
        self.assertEqual(self.e.result, "confirmado")

    def test_fact_goal_with_another_network_is_not_met(self):
        self.state["wifi"] = "VIZINHO_2G_EXT"
        self.answers = [{"steps": [{"action": "tap", "target": ["ALAMEDA"]}], "goal": {"fact": {"wifi": "ALAMEDA"}}}]
        self.assertIn('name="click"', self.run_until_action(screen(("TextView", "ALAMEDA"), ("TextView", "VIZINHO_2G_EXT")))[1])

    def test_network_said_from_memory_is_the_one_the_phone_is_on(self):
        # O dono disse "Alamada 2g"; o provedor pôs a grafia dele no objetivo e o aparelho já está na ALAMEDA-5G.
        self.state["wifi"] = "ALAMEDA-5G"
        self.answers = [{"steps": [{"action": "tap", "target": ["Alamada 2g"]}], "goal": {"fact": {"wifi": "Alamada 2g"}}}]
        why, tool = self.run_until_action(screen(("TextView", "Wi-Fi")))
        self.assertEqual(self.e.result, "já estava")
        self.assertIn("Wi-Fi na rede ALAMEDA-5G", tool)  # a rede como o aparelho a chama

    def test_same_action_on_the_same_screen_goes_to_the_provider_first(self):
        self.state = {}
        same = screen(("TextView", "Redes"), ("TextView", "ALAMEDA"))
        self.answers = [{"steps": [{"action": "tap", "target": ["ALAMEDA"]}, {"action": "tap", "target": ["ALAMEDA"]}],
                         "goal": {"shows": ["Conectado"]}},
                        {"finish": {"success": True, "message": "Já está nessa rede."}}]
        self.assertIn('name="click"', self.run_until_action(same)[1])
        why, tool = self.run_until_action(same)
        self.assertEqual(len(self.asked), 2)
        self.assertIn("already done on this same screen", self.asked[1])
        self.assertIn('name="complete"', tool)

    def test_no_local_guess_before_typing(self):
        self.state = {}
        guesses = []
        self.e.pick = lambda wanted, labels: guesses.append(wanted) or "VIZINHA_2G"
        self.answers = [{"steps": [{"action": "tap", "target": ["Alamada 2G"]}, {"action": "type", "target": ["Password"], "text": "x"}],
                         "goal": {"shows": ["Connected"]}},
                        {"finish": {"success": False, "message": "Rede não encontrada."}}]
        why, tool = self.run_until_action(screen(("TextView", "Redes"), ("TextView", "VIZINHA_2G")))
        self.assertEqual(guesses, [])
        self.assertNotIn('name="click"', tool)


class AssistantTest(unittest.TestCase):
    """O turno do assistente: responder, ver a tela, perguntar, agir (dizendo o que vai fazer) ou guiar."""

    def setUp(self):
        self.asked, self.answers = [], []
        self.e = Executor("tarefa", self.provider, lambda wanted, labels: None, history="\nOwner: oi\nYou: Oi!")
        self.e.assistant = True

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0), ensure_ascii=False)

    def act(self, text):
        why, tool = self.e.step(text)
        while "still be changing" in why:
            why, tool = self.e.step(text)
        return why, tool

    def test_reply_ends_without_touching_the_phone(self):
        self.answers = [{"reply": "Modo avião desliga as conexões sem fio."}]
        why, tool = self.act(screen(("TextView", "Início")))
        self.assertIn("Modo avião desliga", tool)
        self.assertEqual(self.e.result, "respondido")
        self.assertFalse(self.e.acted)
        self.assertIn("Owner: oi", self.asked[0])  # a conversa vai no turno
        self.assertIn("not shown", self.asked[0])

    def test_look_sends_the_screen_and_decides_again(self):
        self.answers = [{"look": True}, {"reply": "É a tela de Ajustes."}]
        why, tool = self.act(screen(("TextView", "Ajustes"), ("TextView", "x" * 80)))
        self.assertEqual(len(self.asked), 2)
        self.assertIn("Ajustes", self.asked[1])
        self.assertIn("[hidden text]", self.asked[1])  # a tela vai reduzida, como nas ajudas
        self.assertIn("É a tela de Ajustes.", tool)

    def test_question_without_the_panel_is_the_answer(self):
        self.answers = [{"ask": {"question": "Qual das duas redes?", "options": ["Casa", "Casa 5G"]}}]
        why, tool = self.act(screen(("TextView", "Início")))
        self.assertIn("Qual das duas redes? (Casa / Casa 5G)", tool)
        self.assertEqual(self.e.result, "pergunta")

    def test_question_with_the_panel_goes_to_the_owner(self):
        self.e.can_ask = True
        self.answers = [{"ask": {"question": "Qual das duas redes?", "options": ["Casa", "Casa 5G"]}}]
        why, tool = self.act(screen(("TextView", "Início")))
        self.assertIn('name="ask_user"', tool)
        self.assertEqual(self.e.questions, 1)

    def test_say_and_explain_are_announced(self):
        self.answers = [{"say": "Vou abrir os Ajustes.", "guide": True,
                         "steps": [{"action": "tap", "target": ["Ajustes"], "explain": "Toco em Ajustes, no alto."}],
                         "goal": {"shows": ["Conta"]}}]
        self.e.prepare()
        self.assertEqual(self.e.announce, "Vou abrir os Ajustes.")
        self.assertTrue(self.e.guide)
        why, tool = self.act(screen(("TextView", "Início"), ("Button", "Ajustes")))
        self.assertIn('name="click"', tool)
        self.assertEqual(self.e.announce, "Vou abrir os Ajustes. Toco em Ajustes, no alto.")

    def test_review_runs_even_for_a_switch_goal_and_its_message_is_the_answer(self):
        self.e.plan, self.e.goal = [], {"on": ["Notificações"]}
        self.e.switched = True
        self.answers = [{"finish": {"success": True, "message": "Liguei as notificações do app."}}]
        why, tool = self.act(switch("Notificações", True))
        self.assertIn("check this final screen", self.asked[0])
        self.assertIn("Liguei as notificações do app.", tool)
        self.assertEqual(self.e.result, "confirmado")

    def test_provider_check_without_the_goal_on_screen_is_conferido(self):
        self.e.plan, self.e.goal, self.e.start = [], {"shows": ["Rota iniciada"]}, set()
        self.answers = [{"finish": {"success": True, "message": "A rota começou, chegada às 14h32."}}]
        why, tool = self.act(screen(("TextView", "14h32"), ("Button", "Encerrar")))
        self.assertEqual(self.e.result, "conferido")
        self.assertIn("chegada às 14h32", tool)
        self.assertEqual(self.e.final, "A rota começou, chegada às 14h32.")


class SpeakTest(unittest.TestCase):
    def test_facts_in_portuguese(self):
        from lmphone.facts import speak
        self.assertEqual(speak({"wifi": "CASA"}), "Wi-Fi na rede CASA")
        self.assertEqual(speak({"airplane_mode": False, "location": True}), "modo avião desligado, localização ligada")
        self.assertEqual(speak({"wifi": "off"}), "Wi-Fi desligado")


class NetworkTest(unittest.TestCase):
    def test_same_network(self):
        from lmphone.facts import same_network
        self.assertTrue(same_network("Alamada 2g", "ALAMEDA-5G"))  # uma letra trocada e outro sufixo de faixa
        self.assertTrue(same_network("alameda", "ALAMEDA"))
        self.assertTrue(same_network("Casa 2.4GHz", "casa_5G"))
        self.assertFalse(same_network("ALAMEDA", "BRUTUS_2G_EXT"))
        self.assertFalse(same_network("Casa", "Cama"))  # nome curto: só igual
        self.assertFalse(same_network("ALAMEDA", "ALAMEDA_EXT"))  # repetidor é outra rede
        self.assertFalse(same_network("off", "ALAMEDA"))


class WaitTest(unittest.TestCase):
    """Logo depois de a acessibilidade ligar, o Chrome mostra só a barra de endereço: o executor espera a página."""

    def setUp(self):
        self.answers = []
        self.asked = []
        self.e = Executor("tarefa", self.provider, lambda wanted, labels: None)

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def test_named_field_missing_waits_before_using_the_only_field(self):
        self.answers = [{"steps": [{"action": "type", "target": ["E-mail"], "text": "a@b.c"}], "goal": {"shows": ["Enviado"]}}]
        why, tool = self.e.step(screen(("EditText", "Search or type URL")))
        self.assertIn('name="wait"', tool)

    def test_look_waits_once_before_sending_the_screen(self):
        self.answers = [{"look": True}, {"reply": "Uma loja."}]
        why, tool = self.e.step(screen(("EditText", "localhost")))
        self.assertIn('name="wait"', tool)
        self.assertEqual(len(self.asked), 1)
        loaded = screen(("EditText", "localhost"), ("TextView", "Blue backpack"))
        self.assertIn('name="wait"', self.e.step(loaded)[1])  # a tela mudou durante a espera: espera ela parar
        why, tool = self.e.step(loaded)
        self.assertIn("Blue backpack", self.asked[1])
        self.assertIn("Uma loja.", tool)

    def test_review_says_whether_the_long_typed_text_is_on_screen(self):
        text = "Primeiro parágrafo da nota, com bem mais de sessenta caracteres para ficar escondido."
        self.e.plan, self.e.goal, self.e.start, self.e.assistant = [], {"shows": ["Nota"]}, set(), True
        self.e.trail = [{"action": "type", "text": text}]
        self.answers = [{"finish": {"success": True, "message": "Feito."}}]
        why, tool = self.e.step(screen(("TextView", "Nota"), ("EditText", text)))
        while "still be changing" in why:
            why, tool = self.e.step(screen(("TextView", "Nota"), ("EditText", text)))
        self.assertIn("1 of the 1 long texts", self.asked[0])
        self.assertEqual(self.e.helps, 0)  # a conferência não conta como ajuda


class ParagraphTest(unittest.TestCase):
    def test_text_with_paragraphs_stays_one_element(self):
        from lmphone import device
        state = {"a11y_tree": {"className": "android.widget.EditText", "text": "Primeiro parágrafo.\n\nSegundo parágrafo.",
                               "boundsInScreen": {"left": 0, "top": 200, "right": 1080, "bottom": 600}, "children": []},
                 "phone_state": {}, "device_context": {"screen_bounds": {"width": 1080, "height": 2340}}}
        text = device.render(state, device.elements_of(state))
        elements, _ = parse_screen(f"<device_state>\n{text}\n</device_state>")
        self.assertEqual([e.text for e in elements], ["Primeiro parágrafo. Segundo parágrafo."])
        from lmphone.executor import mentions
        self.assertTrue(mentions("Primeiro parágrafo.\n\nSegundo parágrafo.", elements[0].text))


class ReadAnswerTest(unittest.TestCase):
    def test_read_value_goes_into_the_sentence(self):
        answers = [{"steps": [{"action": "read", "target": ["blue backpack"], "pattern": r"R\$ ?[\d.,]+",
                               "answer": "A mochila azul custa {value}."}]}]
        e = Executor("quanto custa a mochila azul?", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None)
        why, tool = e.step(screen(("TextView", "Blue backpack: R$ 189,90")))
        self.assertIn("A mochila azul custa R$ 189,90.", tool)
        self.assertEqual(e.result, "lido")


class CloseNamesTest(unittest.TestCase):
    def test_help_lists_names_said_with_another_spelling(self):
        asked = []
        answers = [{"steps": [{"action": "tap", "target": ["Alamada 2g"], "if_missing": "help"}], "goal": {"shows": ["Connected"]}},
                   {"finish": {"success": False, "message": "x"}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("Coloca o wifi na rede Alamada 2g", provider, lambda w, l: None)
        why, tool = e.step(screen(("TextView", "Wi-Fi"), ("TextView", "ALAMEDA-5G")))
        while "still be changing" in why:
            why, tool = e.step(screen(("TextView", "Wi-Fi"), ("TextView", "ALAMEDA-5G")))
        self.assertIn("«Alamada 2g» is «ALAMEDA-5G»", asked[-1])


class SecondReviewTest(unittest.TestCase):
    def test_review_runs_again_after_the_steps_it_gave(self):
        asked = []
        answers = [{"steps": [{"action": "tap", "target": ["Ver rotas"]}]},
                   {"finish": {"success": True, "message": "A rota começou, chegada às 14h32."}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("bota o shopping no waze", provider, lambda w, l: None)
        e.assistant, e.plan, e.goal, e.start = True, [], {"shows": ["Ver rotas"]}, set()
        why, tool = e.step(screen(("TextView", "Shopping"), ("Button", "Ver rotas")))
        while "still be changing" in why:
            why, tool = e.step(screen(("TextView", "Shopping"), ("Button", "Ver rotas")))
        self.assertIn('name="click"', tool)
        route = screen(("TextView", "14h32"), ("Button", "Encerrar"))
        why, tool = e.step(route)
        while "still be changing" in why:
            why, tool = e.step(route)
        self.assertEqual(sum("check this final screen" in p for p in asked), 2)
        self.assertIn("A rota começou", tool)


class OwnerTurnTest(unittest.TestCase):
    """Live mode, etapa 5: na vez do dono ("eu faço"), o agente mostra o passo, espera e confere o que o dono fez."""

    def setUp(self):
        self.answers = [{"steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "O Wi-Fi fica aqui."}],
                         "goal": {"shows": ["Redes disponíveis"]}}]
        self.e = Executor("me ensina a abrir o wifi", lambda prompt: json.dumps(self.answers.pop(0)), lambda w, l: None)
        self.e.owner = True
        self.e.reviewed = True  # a conferência final tem testes próprios

    def test_owner_does_the_step_and_it_is_checked(self):
        start = screen(("TextView", "Configurações"), ("TextView", "Wi-Fi"))
        why, tool = self.e.step(start)
        self.assertIn('name="wait"', tool)
        self.assertEqual(self.e.announce, "O Wi-Fi fica aqui. Sua vez: toque em «Wi-Fi».")
        self.assertEqual(self.e.highlight, (0, 300, 1080, 390))
        why, tool = self.e.step(start)  # o dono ainda não tocou
        self.assertIn('name="wait"', tool)
        self.assertEqual(self.e.highlight, (0, 300, 1080, 390))
        why, tool = self.e.step(screen(("TextView", "Redes disponíveis"), ("TextView", "Adicionar rede")))  # o dono tocou
        self.assertIn('name="complete"', tool)
        self.assertEqual(self.e.result, "confirmado")
        self.assertFalse(self.e.cacheable)

    def test_giving_the_turn_back_makes_the_agent_act(self):
        start = screen(("TextView", "Configurações"), ("TextView", "Wi-Fi"))
        self.e.step(start)
        self.e.owner = False
        why, tool = self.e.step(start)
        self.assertIn('<parameter name="index">3</parameter>', tool)


class GuideHighlightTest(unittest.TestCase):
    def test_guide_highlights_where_the_agent_taps(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "Toco no Wi-Fi."}],
                    "goal": {"shows": ["Redes"]}}]
        e = Executor("como abro o wifi?", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None)
        why, tool = e.step(screen(("TextView", "Configurações"), ("TextView", "Wi-Fi")))
        self.assertIn('name="click"', tool)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))
        self.assertEqual(e.announce, "Toco no Wi-Fi.")


class GuideNarrationTest(unittest.TestCase):
    def test_step_without_explanation_is_still_narrated_and_help_asks_for_it(self):
        asked = []
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Sobre"], "if_missing": "help"}], "goal": {"shows": ["X"]}},
                   {"steps": [{"action": "tap", "target": ["Sobre o telefone"]}]}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("como vejo a versão?", provider, lambda w, l: None)
        page = screen(("TextView", "Configurações"), ("TextView", "Sobre o telefone"))
        why, tool = e.step(page)
        while "still be changing" in why:
            why, tool = e.step(page)
        self.assertIn('give every step an "explain"', asked[-1])
        self.assertIn('name="click"', tool)
        self.assertEqual(e.announce, "Agora toco em «Sobre o telefone».")


class TornPickTest(unittest.TestCase):
    def test_split_pick_asks_the_provider_on_this_screen_instead_of_scrolling(self):
        asked = []
        answers = [{"steps": [{"action": "turn_on", "target": ["Dark mode"], "if_missing": "scroll"}], "goal": {"fact": {"dark_mode": True}}},
                   {"steps": [{"action": "tap", "target": ["Dark"]}]}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("liga o modo escuro", provider, lambda wanted, labels: ("dividido", ("Dark", "Dark mode schedule")))
        page = screen(("TextView", "Light"), ("TextView", "Dark"), ("TextView", "Dark mode schedule"))
        why, tool = e.step(page)
        while "still be changing" in why:
            why, tool = e.step(page)
        self.assertIn("hesitated between «Dark» and «Dark mode schedule»", asked[-1])
        self.assertIn('name="click"', tool)
        self.assertNotIn("swipe", tool)


class OpenSettingsTest(unittest.TestCase):
    def setUp(self):
        self.opened, self.asked = [], []
        self.answers = [{"steps": [{"action": "open_settings", "target": ["airplane_mode"]},
                                   {"action": "turn_on", "target": ["Airplane mode"]}], "goal": {"fact": {"airplane_mode": True}}}]

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0))

    def executor(self, works=True):
        def settings(page):
            self.opened.append(page)
            return works
        return Executor("liga o modo avião", self.provider, lambda w, l: None, settings=settings)

    def test_page_opens_directly(self):
        e = self.executor()
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(self.opened, ["airplane_mode"])
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.trail[0], {"action": "open_settings", "target": ["airplane_mode"]})

    def test_page_that_does_not_open_goes_to_help(self):
        e = self.executor(works=False)
        self.answers.append({"finish": {"success": False, "message": "x"}})
        e.step(screen(("TextView", "Início"), ("TextView", "Settings")))
        self.assertIn("cannot be opened directly", self.asked[-1])

    def test_owner_turn_asks_the_owner_to_open_it(self):
        e = self.executor()
        e.owner = True
        e.step(screen(("TextView", "Início")))
        self.assertEqual(self.opened, [])
        self.assertIn("Sua vez: abra as Configurações na página airplane_mode.", e.announce)


class DirectSettingTest(unittest.TestCase):
    """Modo escuro e modo avião mudam direto pelo sistema; quem confere é o estado do aparelho."""

    def test_set_changes_the_setting_and_the_state_confirms(self):
        state, changed = {"dark_mode": False}, []
        answers = [{"say": "Vou ligar o modo escuro.", "steps": [{"action": "set", "target": ["dark_mode"], "value": True}],
                    "goal": {"fact": {"dark_mode": True}}}]
        e = Executor("liga o modo escuro", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: dict(state))
        e.setter = lambda name, value: changed.append((name, value)) or state.update({name: value}) or True
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(changed, [("dark_mode", True)])
        self.assertIn('name="wait"', tool)
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn('name="complete"', tool)
        self.assertEqual(e.result, "confirmado")
        self.assertIn("Pronto: modo escuro ligado.", tool)

    def test_a_level_is_set_with_a_number_and_the_state_confirms(self):
        state, changed = {"media_volume": 0}, []
        answers = [{"say": "Vou aumentar o volume.", "steps": [{"action": "set", "target": ["media_volume"], "value": "70"}],
                    "goal": {"fact": {"media_volume": 70}}}]
        e = Executor("o celular tá mudo", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: dict(state))
        e.setter = lambda name, value: changed.append((name, value)) or state.update({name: 67}) or True
        e.step(screen(("TextView", "Início")))
        self.assertEqual(changed, [("media_volume", 70)])  # um número, não True
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn('name="complete"', tool)  # 67 vale como 70: a tela arredonda
        self.assertIn("volume da mídia em 67%", tool)  # o valor lido do aparelho

    def test_turning_dark_mode_off_through_the_screens_picks_light(self):
        route = Executor.guided([{"action": "set", "target": ["dark_mode"], "value": False}])
        self.assertEqual(route[1]["action"], "turn_on")
        self.assertEqual(route[1]["target"][:2], ["Light", "Claro"])
        route = Executor.guided([{"action": "set", "target": ["dark_mode"], "value": True}])
        self.assertEqual((route[1]["action"], route[1]["target"][-1]), ("turn_on", "Escuro"))

    def test_unknown_setting_goes_to_help(self):
        asked = []
        answers = [{"steps": [{"action": "set", "target": ["nfc"], "value": True}]},
                   {"finish": {"success": False, "message": "x"}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("liga o nfc", provider, lambda w, l: None, facts=lambda: {"bluetooth": False})
        e.setter = lambda name, value: True
        e.step(screen(("TextView", "Início"), ("TextView", "Settings")))
        self.assertIn("cannot be changed directly", asked[-1])

    def test_wifi_on_is_any_network(self):
        state = {"wifi": "off"}
        answers = [{"steps": [{"action": "set", "target": ["wifi"], "value": True}], "goal": {"fact": {"wifi": "on"}}}]
        e = Executor("liga o wifi", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None, facts=lambda: dict(state))
        e.setter = lambda name, value: state.update({"wifi": "on, not connected"}) or True
        e.step(screen(("TextView", "Início")))
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(e.result, "confirmado")
        self.assertIn("Wi-Fi ligado", tool)

    def test_a_change_that_would_cut_the_link_ends_the_task(self):
        answers = [{"steps": [{"action": "set", "target": ["wifi"], "value": False}], "goal": {"fact": {"wifi": "off"}}}]
        e = Executor("desliga o wifi", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None, facts=lambda: {"wifi": "CASA"})
        e.setter = lambda name, value: "Ligue o cabo."
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn('name="complete"', tool)
        self.assertIn("Ligue o cabo.", tool)
        self.assertEqual(e.result, "falhou")


class ConfirmTest(unittest.TestCase):
    """Toques que não se desfazem (enviar, comprar, apagar) esperam o dono confirmar."""

    SCREEN = screen(("EditText", "Mensagem"), ("ImageButton", "Send"))

    def setUp(self):
        self.asked, self.answers = [], [{"say": "Vou enviar.", "steps": [{"action": "tap", "target": ["Send"]}],
                                         "goal": {"shows": ["Enviada"]}}]
        self.e = Executor("manda oi", self.provider, lambda wanted, labels: None)
        self.e.can_ask = True

    def provider(self, prompt):
        self.asked.append(prompt)
        return json.dumps(self.answers.pop(0), ensure_ascii=False)

    def test_yes_lets_the_tap_go(self):
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="confirm_user"', tool)
        self.assertIn("Posso tocar em «Send»?", tool)
        self.assertEqual(self.e.trail, [])  # o toque ainda não saiu
        self.assertTrue(self.e.confirm_answer("Pode mandar"))
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="click"', tool)
        self.assertIn('<parameter name="index">3</parameter>', tool)
        self.assertEqual(self.e.trail, [{"action": "tap", "target": ["Send"], "seen": ["Mensagem", "Send"]}])

    def test_no_ends_the_task(self):
        self.e.step(self.SCREEN)
        self.assertFalse(self.e.confirm_answer("Não"))
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="complete"', tool)
        self.assertIn("parei antes de tocar em «Send»", tool)
        self.assertEqual(self.e.result, "cancelada")

    def test_other_answer_is_left_to_the_provider(self):
        self.e.step(self.SCREEN)
        self.assertIsNone(self.e.confirm_answer("não, manda para a outra Ana"))
        self.assertIsNone(self.e.confirming)
        self.assertIsNone(self.e.approved)

    def test_plan_question_is_asked(self):
        self.answers[0]["steps"][0]["confirm"] = "Envio a mensagem para Ana?"
        why, tool = self.e.step(self.SCREEN)
        self.assertIn("Envio a mensagem para Ana?", tool)

    def test_without_the_strip_the_question_is_the_answer(self):
        self.e.can_ask = False
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="complete"', tool)
        self.assertIn("(sim / não)", tool)
        self.assertEqual(self.e.result, "a confirmar")

    def test_yes_in_the_next_request_lets_it_go(self):
        self.e.can_ask, self.e.preapproved = False, True
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="click"', tool)

    def test_ordinary_taps_do_not_ask(self):
        self.answers[0]["steps"][0]["target"] = ["Settings"]
        why, tool = self.e.step(screen(("TextView", "Call log"), ("Button", "Settings")))
        self.assertIn('name="click"', tool)

    def test_a_tap_pointed_by_index_keeps_it_for_after_the_yes(self):
        self.e.plan, self.e.goal = [{"action": "tap", "index": 3}], {"shows": ["Enviada"]}
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="confirm_user"', tool)
        self.e.confirm_answer("sim")
        why, tool = self.e.step(self.SCREEN)
        self.assertIn('name="click"', tool)
        self.assertIn('<parameter name="index">3</parameter>', tool)

    def test_switches_do_not_ask(self):
        self.e.plan, self.e.goal = [{"action": "turn_on", "target": ["Remove animations"]}], {"on": ["Remove animations"]}
        why, tool = self.e.step(switch("Remove animations", False))
        self.assertIn('name="click"', tool)

    def test_words(self):
        from lmphone.executor import sensitive, yes_no
        self.assertTrue(all(map(sensitive, ["Send", "Enviar", "Buy now", "Delete", "Chamada de vídeo", "Call"])))
        self.assertFalse(any(map(sensitive, ["Call log", "Posts", "Dark", "Settings", "Send feedback about this app now"])))
        self.assertEqual([yes_no(a) for a in ["Sim", "pode mandar", "com certeza", "Não", "pode não", "não precisa", "cancela",
                                              "e o outro contato?", "manda pro outro contato", "não manda pro outro"]],
                         [True, True, True, False, False, False, False, None, None, None])


class GoneGoalTest(unittest.TestCase):
    """O botão que começa o que foi pedido ("Ir agora") tem de sair da tela: o destino já aparece na prévia da rota."""

    def state(self, e, *rows):
        elements, raw = parse_screen(screen(*rows))
        return e.goal_state(elements, [x.text for x in elements if x.text])

    def test_button_still_there_is_not_done(self):
        e = Executor("t", None, None)
        e.adopt([], {"shows": "Park Shopping", "gone": ["Ir agora", "Go now"]})
        e.start = set()
        self.assertFalse(self.state(e, ("TextView", "Park Shopping"), ("Button", "Ir agora")))
        self.assertTrue(self.state(e, ("TextView", "Park Shopping"), ("TextView", "18 min")))

    def test_correction_with_only_gone_adds_to_the_goal(self):
        e = Executor("t", None, None)
        e.adopt([], {"shows": ["Park Shopping"]})
        e.correct({"gone": "Ir agora"})
        self.assertEqual(e.goal, {"shows": ["Park Shopping"], "gone": ["Ir agora"]})


class FactGoalScopeTest(unittest.TestCase):
    """Um fato do sistema só encerra o pedido quando o resto do plano é ajuste: o pedido que vai a outro app segue."""

    def test_fact_goal_unrelated_to_a_plan_in_apps_is_dropped(self):
        # 2026-10-24: "coloca uma música no YouTube Music e volta pro Waze" veio com o objetivo "Wi-Fi na rede X", que já
        # valia, e terminou como "já estava" sem fazer nada.
        answers = [{"steps": [{"action": "open_app", "target": ["YouTube Music"]}, {"action": "open_app", "target": ["Waze"]}],
                    "goal": {"fact": {"wifi": "CASA"}}}]
        e = Executor("coloca uma música no youtube music e volta pro waze", lambda p: json.dumps(answers.pop(0)),
                     lambda w, l: None, facts=lambda: {"wifi": "CASA"}, launch=lambda name: True)
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertNotIn('name="complete"', tool)
        self.assertIsNone(e.goal)
        self.assertEqual(e.trail[-1]["target"], ["YouTube Music"])

    def test_setting_then_another_app_does_both(self):
        state, opened = {"bluetooth": True}, []
        answers = [{"steps": [{"action": "set", "target": ["bluetooth"], "value": False},
                              {"action": "open_app", "target": ["Waze"]}], "goal": {"fact": {"bluetooth": False}}}]
        e = Executor("desliga o bluetooth e volta pro waze", lambda p: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: dict(state), launch=lambda name: opened.append(name) or True)
        e.setter = lambda name, value: state.update({name: value}) or True
        e.step(screen(("TextView", "Início")))
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(opened, ["Waze"])
        self.assertNotIn('name="complete"', tool)
        self.assertEqual(e.goal, {"fact": {"bluetooth": False}})


class GuideByRequestTest(unittest.TestCase):
    """"Como eu ligo..." é um guia mesmo sem "guide" no plano; no guia, o dono tem uns segundos para tocar no alvo."""

    def test_how_to_request_is_a_guide_and_a_setting_goes_through_the_screens(self):
        answers = [{"steps": [{"action": "set", "target": ["airplane_mode"], "value": True}],
                    "goal": {"fact": {"airplane_mode": True}}}]
        pages = []
        e = Executor("como ligar o modo avião", lambda p: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: {"airplane_mode": False}, settings=lambda page: pages.append(page) or True)
        e.setter = lambda name, value: self.fail("no guia, nada muda direto")
        e.step(screen(("TextView", "Início")))
        self.assertTrue(e.guide)
        self.assertEqual(pages, ["airplane_mode"])
        self.assertEqual([s["action"] for s in e.plan], ["open_settings", "turn_on"])

    def test_with_the_agent_option_the_owner_has_a_few_seconds_then_the_agent_taps(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "O Wi-Fi fica aqui."}],
                    "goal": {"shows": ["Redes"]}}]
        e = Executor("como abro o wifi?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask, e.guide_agent = True, True
        start = screen(("TextView", "Configurações"), ("TextView", "Wi-Fi"))
        why, tool = e.step(start)
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))
        self.assertEqual(e.announce, "O Wi-Fi fica aqui. Toque em «Wi-Fi», ou eu toco daqui a pouco.")
        e.speaking = True  # o prazo só conta depois de a explicação ser dita
        e.waiting["since"] -= GUIDE_LIMIT + 1
        why, tool = e.step(start)
        self.assertIn('name="wait"', tool)
        e.speaking = False
        e.waiting["since"] -= GUIDE_LIMIT + 1
        why, tool = e.step(start)
        self.assertIn('<parameter name="index">3</parameter>', tool)

    def test_by_default_the_person_taps_and_the_agent_waits_without_a_countdown(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "Toque em Wi-Fi."}],
                    "goal": {"shows": ["Redes"]}}]
        e = Executor("como abro o wifi?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask = True
        start = screen(("TextView", "Configurações"), ("TextView", "Wi-Fi"))
        why, tool = e.step(start)
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))
        self.assertEqual(e.announce, "Toque em Wi-Fi. Fica no alto da tela.")  # onde fica, calculado no aparelho
        e.announce = None
        e.waiting["since"] -= GUIDE_LIMIT + 1
        why, tool = e.step(start)
        self.assertIn('name="wait"', tool)  # sem contagem: o agente não toca no lugar dela
        self.assertIsNone(e.announce)
        e.waiting["since"] -= GUIDE_REMIND
        why, tool = e.step(start)
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.announce, GUIDE_REMINDER)  # o lembrete de que o agente pode fazer, uma vez

    def test_a_control_cut_at_the_bottom_is_scrolled_into_view_first(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho da fonte"]}], "goal": {"shows": ["Fonte"]}}]
        e = Executor("como aumento a letra?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask = True
        cut = ('<device_state>\n1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
               '2. TextView: "Visor" - (0,100,1080,190)\n3. TextView: "Tamanho da fonte" - (79,2311,669,2340)\n</device_state>')
        why, tool = e.step(cut)
        self.assertIn('name="swipe"', tool)
        self.assertIn("subir um pouco a tela", e.announce)
        self.assertIn("[540, 1200]", tool)  # pouco: o controle não some da tela
        whole = cut.replace("(79,2311,669,2340)", "(79,1800,669,1900)")
        why, tool = e.step(whole)
        self.assertIn('name="wait"', tool)  # agora o destaque, para a pessoa tocar
        self.assertEqual(e.highlight, (79, 1800, 669, 1900))

    def test_the_person_pulls_the_quick_panel_with_the_gesture_shown(self):
        answers = [{"guide": True, "steps": [{"action": "quick_settings", "explain": "Puxe a tela de cima para baixo."},
                                              {"action": "tap", "target": ["Lanterna"]}], "goal": {"shows": ["x"]}}]
        e = Executor("como acendo a lanterna?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask = True
        home = screen(("TextView", "Telefone"), ("TextView", "Câmera"))
        why, tool = e.step(home)
        self.assertIn('name="wait"', tool)  # a vez da pessoa: o agente não abre o painel
        self.assertEqual(e.gesture, "puxar")
        self.assertIsNone(e.highlight)
        why, tool = e.step(home)
        self.assertEqual(e.gesture, "puxar")  # continua animado enquanto ela não faz
        why, tool = e.step(screen(("TextView", "Wi-Fi"), ("TextView", "Lanterna")))
        self.assertIsNone(e.gesture)
        self.assertEqual(e.owner_steps, 1)

    def test_a_slider_is_highlighted_on_its_right_part(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Toque"]}], "goal": {"shows": ["x"]}}]
        e = Executor("como aumento o volume do toque?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask = True
        bar = ('<device_state>\n1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
               '2. SeekBar: "Toque" - (100,600,900,680)\n</device_state>')
        why, tool = e.step(bar)
        self.assertEqual(e.highlight, (700, 600, 900, 680))
        self.assertIn("arraste a bolinha", e.announce)

    def test_a_screen_change_without_a_touch_is_not_the_persons_step(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "Toque em Wi-Fi."}],
                    "goal": {"shows": ["Redes"]}}]
        e = Executor("como abro o wifi?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask, e.reviewed = True, True
        e.touched_at = 0.0  # a faixa conta os toques, e a pessoa não tocou
        e.step(screen(("TextView", "Configurações"), ("TextView", "Wi-Fi")))
        moved = screen(("TextView", "Configurações"), ("TextView", "Bluetooth"), ("TextView", "Wi-Fi"))
        why, tool = e.step(moved)
        self.assertIn("touch to arrive", why)  # primeiro, espera o toque dela chegar
        e.waiting["changed"] -= 3  # não chegou em 2 s
        self.assertIn("touch to arrive", e.step(moved)[0])  # e espera mais uma leitura da faixa
        why, tool = e.step(moved)
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.owner_steps, 0)
        self.assertEqual(e.highlight, (0, 400, 1080, 490))  # o destaque no lugar novo do controle
        e.touched_at = time.monotonic() + 1  # agora ela tocou
        why, tool = e.step(screen(("TextView", "Redes"), ("TextView", "Adicionar rede")))
        self.assertIn('name="complete"', tool)
        self.assertEqual(e.owner_steps, 1)

    def test_another_screen_without_the_persons_tap_asks_the_way_back(self):
        asked = []
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "Toque em Wi-Fi."}],
                    "goal": {"shows": ["Redes"]}},
                   {"steps": [{"action": "open_app", "target": ["Configurações"], "explain": "Voltou para o início, sem problema."}]}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("como abro o wifi?", provider, lambda w, l: None)
        e.can_ask, e.touched_at = True, 0.0
        e.step(screen(("TextView", "Configurações"), ("TextView", "Wi-Fi"), ("TextView", "Bluetooth")))
        home = screen(("TextView", "Telefone"), ("TextView", "Mensagens"), ("TextView", "Câmera"))  # a tela inicial
        e.step(home)
        self.assertEqual(len(asked), 1)  # o toque dela pode estar a caminho
        e.waiting["changed"] -= 3
        self.assertIn("touch to arrive", e.step(home)[0])  # mais uma leitura da faixa
        why, tool = e.step(home)
        self.assertEqual(len(asked), 1)  # primeiro, o aviso: sem destaque, "espere", sem instrução
        self.assertIn("Espere um instantinho", e.announce)
        self.assertIsNone(e.highlight)
        self.assertTrue(e.rerouting)
        e.step(home)  # na leitura seguinte, a ajuda (rápida); com a instrução nova, o "recalculando" sai
        self.assertFalse(e.rerouting)
        self.assertEqual(len(asked), 2)
        self.assertIn("went back or touched something else by mistake", asked[1])
        self.assertFalse(e.quick)
        self.assertEqual(e.helps, 0)  # não gasta o limite de ajudas
        self.assertEqual(e.owner_steps, 0)

    def test_a_touch_that_changes_nothing_on_screen_still_counts_after_a_moment(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                    "goal": {"shows": ["Tamanho da fonte"]}}]
        e = Executor("como aumento a letra?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask, e.reviewed, e.touched_at = True, True, 0.0
        page = screen(("TextView", "Tamanho da fonte"), ("Button", "Aumentar tam. da fonte"))
        e.step(page)
        e.waiting["started"] -= 10  # o passo foi mostrado há 10 s
        e.touched_at = time.monotonic()  # ela tocou agora: ainda espera a tela assentar
        why, tool = e.step(page)
        self.assertIn('name="wait"', tool)
        self.assertEqual(e.owner_steps, 0)
        e.touched_at -= 3
        why, tool = e.step(page)
        self.assertEqual(e.owner_steps, 1)
        self.assertNotIn("Waiting for the owner", why)

    def test_the_guide_ends_the_moment_the_letters_get_bigger(self):
        state = {"font_scale": 1.0}
        asked = []
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                    "goal": {"fact": {"font_scale": "up"}}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("como aumento a letra?", provider, lambda w, l: None, facts=lambda: dict(state))
        e.can_ask, e.touched_at = True, 0.0
        page = screen(("TextView", "Tamanho da fonte"), ("Button", "Aumentar tam. da fonte"))
        e.step(page)
        self.assertEqual(e.start_state, {"font_scale": 1.0})
        e.waiting["started"] -= 10
        e.touched_at = time.monotonic() - 3  # ela tocou no «A» grande; a tela não mudou
        state["font_scale"] = 1.1
        why, tool = e.step(page)
        self.assertIn('name="complete"', tool)  # medido no aparelho: sem pedir de novo e sem perguntar ao provedor
        self.assertIn("letra maior", tool)
        self.assertEqual(len(asked), 1)

    def test_a_step_from_the_help_in_the_same_place_is_still_the_persons(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho"], "if_missing": "help"}],
                    "goal": {"shows": ["x"]}},
                   {"steps": [{"action": "tap", "index": 3, "explain": "Toque no A grande."}]}]
        e = Executor("como aumento a letra?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask = True
        page = screen(("TextView", "Tamanho e estilo"), ("Button", "Aumentar"))
        e.step(page)  # a tela assenta antes da ajuda
        e.guide_waited = 0  # a vez da pessoa já foi dada neste lugar do plano, a um passo que a ajuda trocou
        why, tool = e.step(page)
        self.assertIn('name="wait"', tool)  # destaca e espera: o agente não toca sozinho
        self.assertEqual(e.highlight, (0, 300, 1080, 390))

    def test_a_measured_end_of_a_guide_tells_the_way(self):
        state = {"font_scale": 1.0}
        answers = [{"guide": True, "steps": [{"action": "open_settings", "target": ["display"]},
                                              {"action": "tap", "target": ["Tamanho e estilo da fonte"]},
                                              {"action": "tap", "target": ["Aumentar"]}],
                    "goal": {"fact": {"font_scale": "up"}}}]
        e = Executor("como aumento a letra?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: dict(state), settings=lambda page: True)
        e.can_ask, e.touched_at = True, 0.0
        display = screen(("TextView", "Visor"), ("TextView", "Tamanho e estilo da fonte"))
        font = screen(("TextView", "Tamanho da fonte"), ("Button", "Aumentar"))
        for page, touch in ((display, False), (display, False), (display, False), (font, True), (font, False), (font, True)):
            if touch and e.waiting:
                e.waiting["started"] -= 10
                e.touched_at = time.monotonic() - 3
                if page is font and e.plan[e.i - 1:e.i] and e.i == 2:
                    state["font_scale"] = 1.1
            why, tool = e.step(page)
            if 'name="complete"' in tool:
                break
        self.assertIn("letra maior", tool)
        self.assertIn("Para fazer de novo sozinho: Configurações, depois Visor, depois Tamanho e estilo da fonte, "
                      "depois Aumentar", tool)

    def test_a_touch_that_arrives_after_the_new_screen_is_the_persons_step(self):
        # 2026-11-16, com o Pedro: o toque em «Tamanho e estilo da fonte» chegou depois da tela nova; o agente achou que
        # ela não tinha tocado, pediu ajuda e repetiu a instrução do «A».
        asked = []
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho e estilo da fonte"]},
                                              {"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                    "goal": {"shows": ["x"]}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("como aumento a letra?", provider, lambda w, l: None)
        e.can_ask, e.touched_at = True, 0.0
        e.step(screen(("TextView", "Visor"), ("TextView", "Tamanho e estilo da fonte"), ("TextView", "Modo escuro")))
        font = screen(("TextView", "Tamanho da fonte"), ("Button", "Aumentar tam. da fonte"))
        why, tool = e.step(font)
        self.assertIn("touch to arrive", why)
        self.assertIsNone(e.highlight)  # o destaque velho sai da tela nova
        e.touched_at = time.monotonic()  # o toque chegou na leitura seguinte da faixa
        why, tool = e.step(font)
        self.assertEqual(e.owner_steps, 1)
        self.assertEqual(len(asked), 1)  # sem ajuda
        self.assertEqual(e.highlight, (0, 300, 1080, 390))  # o «A» destacado, uma vez
        self.assertIn("Aumentar tam. da fonte", e.announce)

    def test_the_guide_says_how_to_reach_a_settings_page_opened_directly(self):
        answers = [{"guide": True, "steps": [{"action": "open_settings", "target": ["display"],
                                              "explain": "Primeiro, abra as Configurações, a engrenagem."},
                                             {"action": "tap", "target": ["Tamanho e estilo da fonte"]}],
                    "goal": {"shows": ["x"]}}]
        e = Executor("como aumento a letra?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None,
                     settings=lambda page: True)
        e.can_ask = True
        e.step(screen(("TextView", "Início")))
        self.assertIn("Abri as Configurações para você, em «Visor»", e.announce)
        self.assertIn("engrenagem das Configurações e depois em «Visor»", e.announce)

    def test_owner_tap_counts_as_the_step(self):
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Wi-Fi"], "explain": "O Wi-Fi fica aqui."}],
                    "goal": {"shows": ["Redes"]}}]
        e = Executor("como abro o wifi?", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        e.can_ask, e.reviewed = True, True
        e.step(screen(("TextView", "Configurações"), ("TextView", "Wi-Fi")))
        why, tool = e.step(screen(("TextView", "Redes"), ("TextView", "Adicionar rede")))
        self.assertIn('name="complete"', tool)
        self.assertEqual(e.owner_steps, 1)

    def test_setting_already_as_wanted_still_shows_the_way(self):
        state = {"dark_mode": True}
        answers = [{"guide": True, "steps": [{"action": "set", "target": ["dark_mode"], "value": True}],
                    "goal": {"fact": {"dark_mode": True}}}]
        e = Executor("como ativar o modo escuro", lambda p: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: dict(state), settings=lambda page: True)
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertNotIn('name="complete"', tool)  # abre a página em vez de dizer "já estava"
        self.assertTrue(e.was_met)
        page = DISPLAY.format(light="false", dark="true", shield="false")
        for _ in range(6):
            why, tool = e.step(page)
            if 'name="complete"' in tool:
                break
        self.assertIn("O caminho é esse que mostrei", tool)
        self.assertEqual(e.result, "já estava")


class SearchTest(unittest.TestCase):
    """O provedor que não sabe com certeza pede a pesquisa no Google do celular e responde vendo os resultados."""

    def test_search_on_the_phone_and_answer_from_the_results(self):
        asked, searched = [], []
        result = "HYROX é uma competição de fitness que combina corrida e exercícios funcionais, criada em 2017."
        answers = [{"search": "hyrox esporte"}, {"reply": "Hyrox é uma corrida de fitness."}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("o que é o esporte hirox", provider, lambda w, l: None)
        e.searcher = lambda query: searched.append(query) or True
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(searched, ["hyrox esporte"])
        self.assertIn('name="wait"', tool)
        for _ in range(4):
            why, tool = e.step(screen(("TextView", "Google"), ("TextView", result), ("TextView", "Todas")))
            if 'name="complete"' in tool:
                break
        self.assertEqual(e.result, "respondido")
        self.assertIn('{"search": "..."}', asked[0])
        self.assertIn(result, asked[-1])  # os resultados vão inteiros, não como "[hidden text]"
        self.assertIn("Do not search again", asked[-1])

    def test_search_that_does_not_open_ends_the_task(self):
        e = Executor("o que é hyrox", lambda p: json.dumps({"search": "hyrox"}), lambda w, l: None)
        e.searcher = lambda query: False
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(e.result, "falhou")


class KeepScrollingTest(unittest.TestCase):
    def test_scrolls_every_few_seconds_without_end(self):
        answers = [{"steps": [{"action": "keep_scrolling", "every": 3}]}]
        e = Executor("fica rolando a tela", lambda p: json.dumps(answers.pop(0)), lambda w, l: None)
        page = screen(("TextView", "Vídeo"))
        tools = [e.step(page)[1] for _ in range(4)]
        self.assertEqual([('name="swipe"' in t, 'name="wait"' in t) for t in tools],
                         [(True, False), (False, True), (True, False), (False, True)])
        self.assertIn('<parameter name="duration">3.0</parameter>', tools[1])
        self.assertIsNotNone(e.rolling)


class ProviderJsonTest(unittest.TestCase):
    """Uma resposta do provedor que não é JSON é pedida de novo uma vez; duas seguidas encerram com uma mensagem."""

    def test_answer_that_is_not_json_is_asked_again(self):
        answers = [" <invoke_result> </invoke_result>", json.dumps({"reply": "Oi!"})]
        e = Executor("oi", lambda p: answers.pop(0), lambda w, l: None)
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn("Oi!", tool)

    def test_two_bad_answers_end_the_task(self):
        e = Executor("oi", lambda p: "nada", lambda w, l: None)
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn('name="complete"', tool)
        self.assertEqual(e.result, "falhou")

    def test_help_answer_that_cannot_be_used_ends_the_task(self):
        answers = [json.dumps({"steps": [{"action": "tap", "target": ["Nada"], "if_missing": "help"}], "goal": {"shows": ["X"]}}),
                   "<x>", "<y>"]
        e = Executor("abre nada", lambda p: answers.pop(0), lambda w, l: None)
        page = screen(("TextView", "Início"))
        for _ in range(6):
            why, tool = e.step(page)
            if 'name="complete"' in tool:
                break
        self.assertEqual(e.result, "falhou")
        self.assertIn("não entendi", tool)


class ScreensSettingTest(unittest.TestCase):
    """No celular (o cérebro no app, sem o adb) o `set` vai pelas telas: a página das Configurações e a chave, sem
    pedir ajuda ao provedor; quem confere continua sendo o estado do sistema."""

    def test_set_goes_through_the_screens_when_the_phone_cannot_change_it(self):
        from lmphone.executor import SCREENS
        state, asked, opened = {"dark_mode": False}, [], []
        answers = [{"say": "Vou ligar o modo escuro.", "steps": [{"action": "set", "target": ["dark_mode"], "value": True}],
                    "goal": {"fact": {"dark_mode": True}}}]

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor("liga o modo escuro", provider, lambda w, l: None, facts=lambda: dict(state),
                     settings=lambda page: opened.append(page) or True)
        e.setter = lambda name, value: SCREENS
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(opened, ["dark_mode"])
        self.assertIn('name="wait"', tool)
        self.assertNotIn("explain", json.dumps(e.plan))
        why, tool = e.step(switch("Dark mode", False))
        self.assertIn('<parameter name="index">2</parameter>', tool)
        state["dark_mode"] = True
        why, tool = e.step(switch("Dark mode", True))
        self.assertIn('name="complete"', tool)
        self.assertEqual(e.result, "confirmado")
        self.assertEqual(len(asked), 1)


class OnlyGuideTest(unittest.TestCase):
    """O app da loja só ensina (docs/plano-play-store.md): o agente nunca toca, rola, digita, abre nem muda nada."""

    ACTIONS = ('name="click"', 'name="swipe"', 'name="type"', 'name="system_button"', 'name="open_app"',
               'name="open_settings"')

    def make(self, answers, task="liga o modo escuro", **kw):
        asked = []

        def provider(prompt):
            asked.append(prompt)
            return json.dumps(answers.pop(0))

        e = Executor(task, provider, lambda w, l: None, **kw)
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        return e, asked

    def assertNoAction(self, tool):
        for action in self.ACTIONS:
            self.assertNotIn(action, tool)

    def test_a_request_to_do_becomes_a_guide_and_settings_open_by_a_button(self):
        opened, changed = [], []
        e, asked = self.make([{"steps": [{"action": "set", "target": ["dark_mode"], "value": True}],
                               "goal": {"fact": {"dark_mode": True}}}],
                             facts=lambda: {"dark_mode": False}, settings=lambda page: opened.append(page) or True)
        e.setter = lambda name, value: changed.append(name) or True
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertIn("only guides", asked[0])
        self.assertNotIn('"search"', asked[0])
        self.assertTrue(e.guide)
        self.assertNoAction(tool)
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "dark_mode"})
        self.assertIn("Toque no botão «Abrir as Configurações»", e.announce)
        self.assertEqual((opened, changed), ([], []))  # nem a página nem o ajuste pelo sistema
        e.touched_at = e.pressed_at = time.monotonic() + 1  # ela tocou no botão da faixa, e as Configurações abriram
        settings = switch("Modo escuro", "false")
        for _ in range(5):  # a tela nova assenta
            why, tool = e.step(settings)
            self.assertNoAction(tool)
            if e.highlight:
                break
        self.assertEqual(e.owner_steps, 1)
        self.assertIsNotNone(e.highlight)  # a chave, para ela tocar
        self.assertIsNone(e.button)

    def test_scrolling_to_find_a_control_is_the_persons(self):
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Sobre o telefone"], "if_missing": "scroll"}],
                           "goal": {"shows": ["Modelo"]}}], task="onde vejo o modelo do celular?")
        page = screen(("TextView", "Conexões"), ("TextView", "Visor"))
        tools = [e.step(page)[1] for _ in range(4)]  # a tela assenta antes de rolar
        for tool in tools:
            self.assertNoAction(tool)
        self.assertEqual(e.gesture, "rolar")
        self.assertIn("arraste o dedo de baixo para cima", e.announce.lower())
        self.assertNotIn("Sobre o telefone", e.announce)  # o nome só depois de ele aparecer na tela
        e.touched_at = time.monotonic() + 1  # ela rolou: parte da tela continua, e o controle apareceu
        why, tool = e.step(screen(("TextView", "Visor"), ("TextView", "Sobre o telefone")))
        self.assertNoAction(tool)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))  # agora o controle, para ela tocar

    def test_keep_scrolling_is_explained_not_done(self):
        e, _ = self.make([{"steps": [{"action": "keep_scrolling"}], "goal": {"shows": ["x"]}}], task="fica rolando os vídeos")
        why, tool = e.step(screen(("TextView", "Shorts")))
        self.assertIn('name="complete"', tool)
        self.assertIn("arrastar o dedo", tool)

    def test_typing_is_the_persons_with_the_field_highlighted(self):
        e, _ = self.make([{"steps": [{"action": "type", "target": ["Pesquisar"], "text": "farmácia"}],
                           "goal": {"shows": ["farmácia"]}}], task="pesquisa farmácia no mapa")
        why, tool = e.step(screen(("TextView", "Mapa"), ("EditText", "Pesquisar")))
        self.assertNoAction(tool)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))
        self.assertIn("escreva", e.announce.lower())

    def test_leaving_the_screen_while_scrolling_brings_them_back(self):
        # 2026-11-17: depois de voltar à tela inicial, a pessoa ouviu "arraste para cima" 4 vezes.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Sobre o telefone"], "if_missing": "scroll"}],
                               "goal": {"shows": ["Modelo"]}},
                              {"steps": [{"action": "open_settings", "target": ["about_phone"]}]}],
                             task="onde vejo o modelo do celular?")
        page = screen(("TextView", "Conexões"), ("TextView", "Visor"), ("TextView", "Bateria"))
        for _ in range(4):
            e.step(page)
        self.assertEqual(e.gesture, "rolar")
        e.touched_at = time.monotonic() + 1  # ela tocou, mas foi parar na tela inicial
        home = screen(("TextView", "Telefone"), ("TextView", "Mensagens"), ("TextView", "Câmera"))
        e.step(home)
        self.assertEqual((len(asked), e.gesture), (1, None))  # a animação de rolar sai na hora, com o aviso
        self.assertIn("Espere um instantinho", e.announce)
        e.step(home)
        self.assertEqual(len(asked), 2)
        self.assertIn("went back or touched something else", asked[1])

    def test_the_way_starts_at_the_last_opening(self):
        e, _ = self.make([{"steps": [], "goal": {"shows": ["x"]}}])
        e.trail = [{"action": "open_settings", "target": ["display"]}, {"action": "tap", "target": ["Zoom da tela"]},
                   {"action": "open_settings", "target": ["display"]}, {"action": "tap", "target": ["Tamanho e estilo da fonte"]}]
        self.assertEqual(e.way(), " Para fazer de novo sozinho: Configurações, depois Visor, depois Tamanho e estilo da fonte.")

    def test_the_button_touch_that_arrives_after_a_slow_read_is_not_a_detour(self):
        # 2026-11-18: a leitura da tela nova levou 3,3 s, e o aviso do toque no botão chegou depois do "a tela mudou".
        e, asked = self.make([{"steps": [{"action": "open_settings", "target": ["do_not_disturb"]},
                                         {"action": "turn_off", "target": ["Não perturbar"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}],
                             facts=lambda: {"do_not_disturb": True}, settings=lambda page: True)
        e.step(screen(("TextView", "Telefone"), ("TextView", "YT Music")))
        e.touched_at = 0.5  # um toque de antes, no painel
        page = switch("Não perturbar", "true")
        self.assertIn("arrive", e.step(page)[0])
        e.waiting["changed"] -= 3  # a leitura seguinte veio 3 s depois, ainda sem o aviso
        self.assertIn("arrive", e.step(page)[0])
        self.assertFalse(e.rerouting)
        e.touched_at = e.pressed_at = time.monotonic() + 1  # o aviso chegou
        for _ in range(5):
            e.step(page)
            if e.highlight:
                break
        self.assertFalse(e.rerouting)
        self.assertEqual(e.owner_steps, 1)
        self.assertEqual(len(asked), 1)

    def test_status_bar_icons_are_not_targets(self):
        # 2026-11-18: o ícone «A função Não perturbar foi ativada», no alto do painel, foi destacado.
        shade = ('<device_state>\n• **App:** Interface do sistema (com.android.systemui)\n'
                 '1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
                 '2. ImageView: "A função Não perturbar foi ativada" - (498,108,537,147)\n'
                 '3. View: "Bateria em 25 por cento." - (934,94,1012,162)\n'
                 '4. TextView: "com.android.systemui:id/noti_setting", "Config. notificação" - (43,2174,469,2275)\n'
                 '</device_state>')
        e, asked = self.make([{"steps": [{"action": "tap", "target": ["A função Não perturbar foi ativada"]}],
                               "goal": {"shows": ["x"]}}])
        e.step(shade)
        self.assertEqual(e.labels, ["Config. notificação"])
        self.assertNotEqual(e.highlight, (498, 108, 537, 147))

    def test_a_touch_elsewhere_instead_of_the_button_is_a_detour(self):
        # 2026-11-17: o toque no YT Music, em vez do botão da faixa, contou como o passo.
        e, asked = self.make([{"steps": [{"action": "open_settings", "target": ["display"]},
                                         {"action": "tap", "target": ["Tamanho e estilo da fonte"]}],
                               "goal": {"shows": ["x"]}},
                              {"steps": [{"action": "back"}]}], settings=lambda page: True)
        e.step(screen(("TextView", "Telefone"), ("TextView", "YT Music")))
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text = "YT Music"
        music = screen(("TextView", "Início"), ("TextView", "Explorar"), ("TextView", "Biblioteca"))
        why, tool = e.step(music)
        self.assertIn("button to arrive", why)  # primeiro, espera o aviso do toque no botão
        e.waiting["pressed_late"] -= 3  # não veio: foi outro toque
        self.assertIn("button to arrive", e.step(music)[0])  # depois de mais uma leitura da faixa
        why, tool = e.step(music)
        self.assertIn("Espere um instantinho", e.announce)
        self.assertEqual(e.owner_steps, 0)
        e.step(music)
        self.assertIn("«YT Music»", asked[1])

    def test_a_touch_on_another_row_that_opens_another_page_is_a_detour(self):
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho e estilo da fonte"]}],
                               "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        visor = screen(("TextView", "Modo Fácil"), ("TextView", "Tamanho e estilo da fonte"), ("TextView", "Zoom da tela"))
        e.step(visor)
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text = "Modo Fácil"
        e.step(screen(("TextView", "Modo padrão"), ("TextView", "Modo Fácil ativado"), ("Switch", "Ícones grandes")))
        self.assertIn("Espere um instantinho", e.announce)
        self.assertTrue(e.rerouting)  # a faixa mostra "recalculando"
        self.assertIn("instead of «Tamanho e estilo da fonte» they touched «Modo Fácil»", e.lost)

    def test_the_right_row_still_counts(self):
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho e estilo da fonte"]}],
                           "goal": {"shows": ["Tamanho da fonte"]}}], task="como aumento a letra?")
        e.reviewed = True
        e.step(screen(("TextView", "Modo Fácil"), ("TextView", "Tamanho e estilo da fonte")))
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text = "Tamanho e estilo da fonte"
        why, tool = e.step(screen(("TextView", "Tamanho da fonte"), ("Button", "Aumentar tam. da fonte")))
        self.assertEqual(e.owner_steps, 1)
        self.assertIsNone(e.lost)

    def test_labels_seen_while_scrolling_go_to_the_help(self):
        # 2026-11-17: a ajuda mandou procurar "Tela"; no aparelho é "Visor", que tinha passado pela tela.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Tela"], "if_missing": "scroll"}],
                               "goal": {"shows": ["x"]}},
                              {"steps": [{"action": "back"}]}, {"steps": [{"action": "back"}]}],
                             task="como aumento a letra?")
        top = screen(("TextView", "Conexões"), ("TextView", "Aparelhos conectados"), ("TextView", "Modos e Rotinas"))
        for _ in range(4):
            e.step(top)
        down = top
        for rows in ((("TextView", "Modos e Rotinas"), ("TextView", "Sons e vibração"), ("TextView", "Notificações")),
                     (("TextView", "Notificações"), ("TextView", "Visor"), ("TextView", "Papel de parede e estilo")),
                     (("TextView", "Papel de parede e estilo"), ("TextView", "Temas"), ("TextView", "Tela inicial")),
                     (("TextView", "Tela inicial"), ("TextView", "Tela de bloqueio e AOD"), ("TextView", "Segurança"))):
            e.touched_at = time.monotonic() + 1  # ela rolou
            down = screen(*rows)
            for _ in range(3):
                e.step(down)
                if len(asked) > 1:
                    break
            if len(asked) > 1:
                break
        self.assertGreaterEqual(len(asked), 2)
        self.assertIn("use one of these exact names", asked[1])
        self.assertIn("Visor", asked[1])
        self.assertEqual(e.seen, [])

    def test_the_person_hears_the_name_on_the_screen(self):
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Tamanho da fonte", "Tamanho e estilo da fonte"],
                                                      "explain": "Toque em «Tamanho da fonte», a opção com a letra A."}],
                           "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        e.step(screen(("TextView", "Modo Fácil"), ("TextView", "Tamanho e estilo da fonte")))
        self.assertIn("«Tamanho e estilo da fonte»", e.announce)
        self.assertNotIn("«Tamanho da fonte»", e.announce)
        self.assertEqual(e.off_names, [])

    def test_a_quoted_name_that_is_not_on_the_screen_is_noted(self):
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Visor"],
                                                      "explain": "Toque em Visor, perto de «Tela» e «Brilho»."}],
                           "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        e.step(screen(("TextView", "Conexões"), ("TextView", "Visor"), ("TextView", "Brilho")))
        self.assertEqual(e.off_names, ["Tela"])

    def font_page(self, bold):
        return ('<device_state>\n1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
                '2. TextView: "Fonte em negrito" - (40,900,700,980)\n'
                f'3. Switch: "Ativado" ; isChecked={bold} - (900,900,1040,980)\n'
                '4. Button: "Reduzir tam. da fonte" - (60,2126,150,2216)\n'
                '5. Button: "Aumentar tam. da fonte" - (917,2126,1007,2216)\n</device_state>')

    def test_a_touch_outside_the_highlight_is_corrected_at_once(self):
        # 2026-11-17: o «Reduzir» tocado no lugar do «A» grande levou 10 a 15 s, pelo provedor.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                               "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        e.step(self.font_page(False))
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text, e.touched_box = "Reduzir tam. da fonte", [60, 2126, 150, 2216]
        page = self.font_page(False).replace("Reduzir tam. da fonte", "Reduzir tam. da fonte ")  # a tela mudou um pouco
        why, tool = e.step(page)
        self.assertEqual(len(asked), 1)  # sem o provedor
        self.assertIn("Esse foi o «Reduzir tam. da fonte»", e.announce)
        self.assertEqual(e.highlight, (917, 2126, 1007, 2216))
        self.assertEqual(e.owner_steps, 0)

    def test_a_switch_changed_by_mistake_is_undone_first(self):
        # 2026-11-17: a «Fonte em negrito» ficou ligada, e o guia seguiu sem pedir para desfazer.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                               "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        e.step(self.font_page(False))
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text, e.touched_box = "Ativado", [900, 900, 1040, 980]
        e.step(self.font_page(True))
        self.assertIn("Você ligou «Fonte em negrito» sem querer", e.announce)
        self.assertEqual(e.highlight, [900, 900, 1040, 980])
        e.touched_at = e.touched_text_at = time.monotonic() + 2  # ela desligou
        e.step(self.font_page(False))
        self.assertIn("Pronto, desfeito", e.announce)
        self.assertEqual(e.highlight, (917, 2126, 1007, 2216))
        self.assertEqual(len(asked), 1)

    def test_a_switch_changed_without_knowing_where_the_touch_was_is_undone(self):
        # 2026-11-18: a chave tocada por engano chegou com os limites [0,0,0,0] e o nome depois da tela nova.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Aumentar tam. da fonte"]}],
                               "goal": {"shows": ["x"]}}], task="como aumento a letra?")
        e.step(self.font_page(False))
        e.touched_at = time.monotonic() + 1  # só o aviso do toque; nem o nome nem os limites do controle
        e.touched_box = [0, 0, 0, 0]
        e.step(self.font_page(True))
        self.assertIn("Você ligou «Fonte em negrito» sem querer", e.announce)
        self.assertEqual((len(asked), e.owner_steps), (1, 0))

    def test_a_name_from_the_next_screen_known_by_the_map_is_not_off_screen(self):
        # 2026-11-18: «Mídia» está na tela seguinte (Volume); o mapa do aparelho a conhece.
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Volume"],
                                                      "explain": "Toque em Volume; lá a barra «Mídia» é a dos vídeos."}],
                           "goal": {"shows": ["x"]}}], task="o celular tá mudo")
        e.map = {"settings": {"children": {"Sons e vibração": {"children": {"Volume": {"children": {}, "controls": [],
                                                                                       "seen": ["Mídia", "Toque"]}},
                                                               "controls": []}}, "controls": []}}
        e.step(screen(("TextView", "Modo de som"), ("TextView", "Volume")))
        self.assertEqual(e.off_names, [])

    def dnd_page(self, on, shifted):
        top = 481 if shifted else 419
        extra = '4. TextView: "Até o próximo alarme" - (79,420,700,470)\n' if shifted else ""
        return ('<device_state>\n1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
                f'2. TextView: "Não perturbar" - (79,{top},700,{top + 56})\n'
                f'3. Switch: "Ativado" ; isChecked={on} - (900,{top},990,{top + 56})\n{extra}</device_state>')

    def test_the_steps_own_switch_that_moves_is_not_undone(self):
        # 2026-11-18: o «Não perturbar» desceu 60 px ao desligar, e o guia pediu para "desfazer" a chave certa.
        e, asked = self.make([{"guide": True, "steps": [{"action": "turn_off", "target": ["Não perturbar"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True})
        for _ in range(3):
            e.step(self.dnd_page(True, False))
            if e.waiting:
                break
        e.touched_at = time.monotonic() + 1
        e.step(self.dnd_page(False, True))
        self.assertNotIn("sem querer", e.announce or "")

    def test_a_reply_that_promises_the_steps_is_asked_again(self):
        # 2026-11-18: "Vou te mostrar como colocar o som de volta, passo a passo", sem passos, e a tarefa acabou.
        e, asked = self.make([{"reply": "Entendi. Vou te mostrar como colocar o som de volta, passo a passo."},
                              {"steps": [{"action": "open_settings", "target": ["do_not_disturb"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True})
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(len(asked), 2)
        self.assertIn("promised to show the way", asked[1])
        self.assertNotIn('name="complete"', tool)
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "do_not_disturb"})

    def test_a_plain_reply_is_not_asked_again(self):
        e, asked = self.make([{"reply": "O Wi-Fi é a internet sem fio da sua casa."}], task="o que é wifi?")
        why, tool = e.step(screen(("TextView", "Início")))
        self.assertEqual(len(asked), 1)
        self.assertIn('name="complete"', tool)

    def test_a_settings_page_by_its_menu_name_gets_the_button(self):
        # 2026-11-18: o plano deu «Sons e vibração», o app não sabia abrir, e o botão anunciado não apareceu.
        e, asked = self.make([{"guide": True, "steps": [{"action": "open_settings", "target": ["Sons e vibração", "Sons"]},
                                                        {"action": "tap", "target": ["Volume"]}],
                               "goal": {"shows": ["x"]}}], task="o celular tá mudo")
        e.step(screen(("TextView", "Não perturbar")))
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "sound"})

    def test_an_unknown_settings_page_asks_for_help_instead_of_a_dead_button(self):
        e, asked = self.make([{"guide": True, "steps": [{"action": "open_settings", "target": ["Toques e alertas"]}],
                               "goal": {"shows": ["x"]}},
                              {"steps": [{"action": "open_settings", "target": ["sound"]}]}], task="o celular tá mudo")
        e.step(screen(("TextView", "Início")))
        self.assertEqual(len(asked), 2)
        self.assertIn("not one of the settings pages", asked[1])
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "sound"})

    def test_what_the_person_writes_while_waiting_goes_to_the_provider(self):
        # 2026-11-18: "não apareceu nenhum botão" e "não tem botão amarelo", e o guia seguiu esperando.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Volume"]}], "goal": {"shows": ["x"]}},
                              {"steps": [{"action": "tap", "target": ["Modo de som"]}]}], task="o celular tá mudo")
        page = screen(("TextView", "Modo de som"), ("TextView", "Volume"))
        e.step(page)
        self.assertIsNotNone(e.waiting)
        e.instructions.append("não tem botão amarelo")
        e.step(page)
        self.assertEqual(len(asked), 2)
        self.assertIn("não tem botão amarelo", asked[1])
        self.assertEqual(e.highlight, (0, 200, 1080, 290))  # o passo novo, destacado

    def test_a_touch_the_screen_does_not_show_yet_is_not_called_outside(self):
        # 2026-11-18: 3 s depois do toque na chave certa, a tela lida ainda era a de antes, e o guia disse "esse toque
        # foi fora do destaque".
        state = {"do_not_disturb": True}
        e, asked = self.make([{"guide": True, "steps": [{"action": "turn_off", "target": ["Não perturbar"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: dict(state))
        for _ in range(3):
            e.step(self.dnd_page(True, False))
            if e.waiting:
                break
        e.waiting["started"] -= 10
        e.touched_at = e.touched_text_at = time.monotonic() - 3  # o toque, já com a chave no lugar novo
        e.touched_text, e.touched_box = "Ativado", [900, 481, 990, 537]
        state["do_not_disturb"] = False  # o aparelho já desligou
        why, tool = e.step(self.dnd_page(True, False))  # a leitura ainda é a de antes
        self.assertIn("show the owner's touch", why)
        self.assertNotIn("fora do destaque", e.announce or "")
        e.step(self.dnd_page(False, True))  # agora a tela mostra a chave desligada, no lugar novo
        self.assertNotIn("fora do destaque", e.announce or "")
        self.assertEqual(e.owner_steps, 1)

    def test_a_button_press_that_opens_nothing_is_not_the_step(self):
        # 2026-11-18: a página de Sons não abriu, o toque no botão contou como o passo, e o guia pediu o botão 4 vezes.
        e, asked = self.make([{"guide": True, "steps": [{"action": "open_settings", "target": ["sound"]},
                                                        {"action": "tap", "target": ["Volume"]}],
                               "goal": {"shows": ["x"]}}], task="o celular tá mudo")
        page = screen(("TextView", "Não perturbar"), ("TextView", "Agenda"))
        e.step(page)
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "sound"})
        e.waiting["started"] -= 10
        e.touched_at = e.pressed_at = time.monotonic() - 3  # tocou no botão, e a tela ficou igual
        why, tool = e.step(page)
        self.assertEqual(e.owner_steps, 0)
        self.assertEqual(len(asked), 1)
        self.assertEqual(e.button, {"text": "Abrir as Configurações", "open_settings": "sound"})  # o botão continua

    def test_a_settings_page_already_open_gets_no_button(self):
        # Com o botão só contando quando a tela muda, um botão para a página já aberta deixaria o passo parado.
        e, asked = self.make([{"guide": True, "steps": [{"action": "open_settings", "target": ["do_not_disturb"]},
                                                        {"action": "turn_off", "target": ["Não perturbar"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True})
        page = ('<device_state>\n• **App:** Config. (com.android.settings)\n'
                '1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
                '2. TextView: "Não perturbar" - (169,150,539,228)\n'
                '3. TextView: "Não perturbar" - (79,414,412,480)\n'
                '4. Switch: "Ativado" ; isChecked=True - (900,419,990,475)\n</device_state>')
        for _ in range(3):
            e.step(page)
            if e.waiting:
                break
        self.assertIsNone(e.button)
        self.assertEqual(e.highlight, (900, 419, 990, 475))  # direto na chave

    def test_a_set_through_the_screens_uses_the_phones_name_and_no_agent_sentence(self):
        e, asked = self.make([{"steps": [{"action": "set", "target": "do_not_disturb", "value": False,
                                          "explain": "Primeiro, eu desligo o modo Não perturbe."}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True}, settings=lambda page: True)
        e.step(screen(("TextView", "Início")))
        turn = e.plan[1]
        self.assertEqual(turn["target"][0], "Não perturbar")
        self.assertNotIn("explain", turn)

    def test_a_touch_with_a_late_screen_and_nothing_measured_is_not_the_step(self):
        # 2026-11-18, no simulador: a leitura 3,5 s atrás do toque em «Volume» contou o passo antes de a página abrir.
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Volume"]},
                                                        {"action": "tap", "target": ["Toque"]}],
                               "goal": {"fact": {"ring_volume": "up"}}}], task="não toca", facts=lambda: {"ring_volume": 7})
        page = screen(("TextView", "Toque"), ("TextView", "Volume"))
        e.step(page)
        e.waiting["started"] -= 10
        e.touched_at = time.monotonic() - 3  # ela tocou; a tela lida ainda é a de antes, e nada medido mudou
        e.step(page)
        self.assertEqual(e.owner_steps, 0)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))  # o «Volume» continua destacado, não o «Toque»

    def test_a_touch_elsewhere_on_the_same_screen_is_corrected_at_once(self):
        e, asked = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Som"]}],
                               "goal": {"fact": {"sound_mode": "som"}}}], task="não toca",
                             facts=lambda: {"sound_mode": "vibrar"})
        page = screen(("TextView", "Som"), ("TextView", "Vibrar"))
        e.step(page)
        e.touched_at = e.touched_text_at = time.monotonic() + 1  # agora mesmo, sem esperar a tela
        e.touched_text, e.touched_box = "Vibrar", [0, 300, 1080, 390]
        e.step(page)
        self.assertEqual(e.announce, "Esse foi o «Vibrar». O certo é o que está destacado em amarelo: «Som».")
        self.assertEqual(len(asked), 1)

    def test_a_switch_in_the_explanation_is_named_by_its_row(self):
        # 2026-11-18, no simulador: "Agora toque na chave do Ativado, para desligar."
        e, asked = self.make([{"guide": True, "steps": [{"action": "turn_off", "target": ["Não perturbar"],
                                                         "explain": "Toque na chave do Não perturbar, para desligar."}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True})
        for _ in range(3):
            e.step(self.dnd_page(True, False))
            if e.waiting:
                break
        self.assertIn("chave do Não perturbar", e.last_said)
        self.assertNotIn("Ativado", e.last_said)

    def test_a_button_that_opens_nothing_asks_for_the_way_through_the_menus(self):
        # 2026-11-18, no simulador: a página não abria, e a pessoa apertou o botão 18 vezes em 5 min.
        e, asked = self.make([{"guide": True, "steps": [{"action": "open_settings", "target": ["sound"]},
                                                        {"action": "tap", "target": ["Volume"]}],
                               "goal": {"shows": ["x"]}},
                              {"steps": [{"action": "tap", "target": ["Config."]}]}], task="o celular tá mudo")
        page = screen(("TextView", "Telefone"), ("TextView", "Config."))
        e.step(page)
        e.waiting["since"] -= 30  # o lembrete fala do botão: não há destaque amarelo
        e.step(page)
        self.assertEqual(e.announce, "Estou esperando você. Toque no botão «Abrir as Configurações», aqui embaixo; "
                                     "se não achar, me diga «não achei».")
        e.waiting["started"] -= 10
        e.touched_at = e.pressed_at = time.monotonic() - 7  # tocou no botão, e a página não abriu
        e.step(page)
        self.assertIn("não abriu a página", e.announce)
        self.assertIsNone(e.button)
        e.step(page)
        self.assertIn("did not open on this phone", asked[1])
        self.assertEqual(e.highlight, (0, 300, 1080, 390))  # o «Config.», pelos menus

    def test_a_touch_on_the_steps_switch_in_its_new_place_is_not_outside(self):
        # 2026-11-18: a chave desceu 62 px antes de a tela mostrá-la desligada, e o guia disse "fora do destaque".
        e, asked = self.make([{"guide": True, "steps": [{"action": "turn_off", "target": ["Não perturbar"]}],
                               "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                             facts=lambda: {"do_not_disturb": True})
        for _ in range(3):
            e.step(self.dnd_page(True, False))
            if e.waiting:
                break
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text, e.touched_box = "Ativado", [900, 481, 990, 537]
        e.step(self.dnd_page(True, True))  # o lugar novo, com o estado ainda não atualizado
        self.assertNotIn("fora do destaque", e.announce or "")

    def test_the_highlight_follows_a_control_that_moves(self):
        # 2026-11-18: depois do modo Som, a lista desceu e o destaque do «Volume» ficou no «Som do sistema».
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Volume"]}], "goal": {"shows": ["x"]}}],
                         task="o celular tá mudo")
        page = screen(("TextView", "Modo de som"), ("TextView", "Volume"))
        e.step(page)
        self.assertEqual(e.highlight, (0, 300, 1080, 390))
        moved = page.replace("(0,300,1080,390)", "(0,360,1080,450)")
        e.step(moved)
        self.assertEqual(e.highlight, (0, 360, 1080, 450))
        self.assertEqual(e.owner_steps, 0)

    def test_a_switch_step_on_its_title_highlights_the_switch(self):
        # 2026-11-18: o destaque caiu no título «Não perturbar», no alto da tela, e o toque ali não fazia nada.
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "index": 2,
                                                      "explain": "Toque no botão da direita da linha 'Não perturbar', que está ligado."}],
                           "goal": {"shows": ["x"]}}], task="não chega aviso")
        page = ('<device_state>\n1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)\n'
                '2. TextView: "Não perturbar" - (28,0,1052,115)\n'
                '3. TextView: "Não perturbar" - (79,419,700,475)\n'
                '4. Switch: "Ativado" ; isChecked=True - (900,419,990,475)\n</device_state>')
        e.step(page)
        self.assertEqual(e.highlight, (900, 419, 990, 475))

    def test_the_reminder_is_said_once_per_step(self):
        # 2026-11-18: "Estou esperando você..." dito 6 vezes no mesmo passo.
        e, _ = self.make([{"guide": True, "steps": [{"action": "tap", "target": ["Volume"]}], "goal": {"shows": ["x"]}}],
                         task="o celular tá mudo")
        page = screen(("TextView", "Modo de som"), ("TextView", "Volume"))
        e.step(page)
        said = 0
        for _ in range(3):
            e.waiting["since"] -= 30
            e.announce = None  # o serviço já disse o anterior
            e.step(page)
            said += "Estou esperando você" in (e.announce or "")
            e.waiting["reminded"] = False  # como num passo decidido de novo
        self.assertEqual(said, 1)

    def test_the_steps_switch_that_moves_after_a_touch_counts_as_done(self):
        # 2026-11-18: o toque na chave certa ficou fora do destaque antigo (ela desceu 60 px) e o guia mandou religar.
        e, _ = self.make([{"guide": True, "steps": [{"action": "turn_off", "target": ["Não perturbar"]}],
                           "goal": {"fact": {"do_not_disturb": False}}}], task="não chega aviso",
                         facts=lambda: {"do_not_disturb": True})
        for _ in range(3):
            e.step(self.dnd_page(True, False))
            if e.waiting:
                break
        e.touched_at = e.touched_text_at = time.monotonic() + 1
        e.touched_text, e.touched_box = "Ativado", [900, 481, 990, 537]  # onde a chave está agora
        e.step(self.dnd_page(False, True))
        self.assertNotIn("sem querer", e.announce or "")
        self.assertNotIn("Esse foi", e.announce or "")

    def test_a_done_that_the_measure_contradicts_is_not_confirmed(self):
        # 2026-11-18: "o volume dos toques subiu" com ele em 0 (o celular em Vibrar); o fim saiu "confirmado".
        state = {"do_not_disturb": False, "ring_volume": 0, "sound_mode": "vibrar"}
        e, asked = self.make([{"guide": True, "steps": [], "goal": {"fact": {"ring_volume": "up"}}},
                              {"steps": [{"action": "tap", "target": ["Volume"]}]},
                              {"steps": [{"action": "tap", "target": ["Volume"]}]}],
                             task="não chega aviso", facts=lambda: dict(state))
        e.step(screen(("TextView", "Volume"), ("SeekBar", "Toque")))  # o plano (o objetivo medido)
        e.unmet_asked = False
        why, tool = e.finish(True, "O volume dos toques subiu.", seen=True)
        self.assertIn("NOT met yet", asked[-1])
        self.assertNotIn("subiu", tool)
        self.assertNotEqual(e.result, "confirmado")


@unittest.skipUnless(os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "telas")), "sem as telas gravadas (tests/telas/)")
class RealScreensTest(unittest.TestCase):
    """Passos do guia nas telas de verdade do S23+ (a varredura de 2026-11-18, tests/telas/)."""

    @staticmethod
    def page(name, index=0):
        from lmphone import device
        from tests import celular_real
        tree = celular_real.carregar(name)["telas"][index]
        return "<device_state>\n" + device.render(tree, device.elements_of(tree)) + "\n</device_state>"

    def make(self, steps, goal):
        answers = [{"guide": True, "steps": steps, "goal": goal}]
        e = Executor("não chega aviso", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None,
                     facts=lambda: {"ring_volume": 0, "sound_mode": "som", "do_not_disturb": False})
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        return e

    def test_the_title_of_a_volume_bar_points_at_the_bar(self):
        # O «Toque» da página de Volume é um texto; a barra embaixo dele tem só o nível («7»). O guia destacava o
        # título, e a pessoa tocava nele sem nada acontecer até o fim do tempo.
        e = self.make([{"action": "tap", "target": ["Toque"], "explain": "Aumente o volume do toque."}],
                      {"fact": {"ring_volume": "up"}})
        e.step(self.page("estado-som-toque-7-sons-volume"))
        self.assertEqual(e.highlight, (807, 422, 1024, 506))  # a parte direita da barra (158,422,1024,506)
        self.assertIn(SLIDER, e.announce)

    def test_a_bar_to_turn_down_points_left_of_the_middle(self):
        # 2026-11-19, no simulador: "Como deixo a tela menos clara?" com o destaque e a fala de aumentar; quem seguia o
        # destaque subia o brilho (12 ajudas, o fim do tempo). Para diminuir: perto de um terço da barra.
        e = self.make([{"action": "tap", "target": ["Toque"], "explain": "Abaixe o volume do toque."}],
                      {"fact": {"ring_volume": "down"}})
        e.facts = lambda: {"ring_volume": 100, "sound_mode": "som", "do_not_disturb": False}
        e.step(self.page("estado-som-toque-7-sons-volume"))
        self.assertEqual(e.highlight, (374, 422, 590, 506))  # o meio a 37,5% (482) de (158,422,1024,506)
        self.assertIn(SLIDER_DOWN, e.announce)
        self.assertNotIn("aumentar", e.announce)

    def test_a_low_bar_to_turn_down_points_at_half_of_it(self):
        e = self.make([{"action": "tap", "target": ["Toque"]}], {"fact": {"ring_volume": "down"}})
        e.facts = lambda: {"ring_volume": 40, "sound_mode": "som", "do_not_disturb": False}
        e.step(self.page("estado-som-toque-7-sons-volume"))
        x1, _, x2, _ = e.highlight
        self.assertEqual((x1 + x2) // 2, 158 + 866 * 200 // 1000)  # metade de 40%

    def test_reading_a_bar_level_does_not_end_the_guide(self):
        # 2026-11-19, no simulador: o plano terminava em `read` da «Mídia»; o guia dizia "o volume está em 14" e acabava
        # antes de a pessoa mexer na barra. O objetivo dentro de um passo também vale.
        answer = {"guide": True, "steps": [
            {"action": "tap", "target": ["Toque"], "goal": {"fact": {"ring_volume": "down"}}},
            {"action": "read", "target": ["Toque"], "pattern": "\\d+", "answer": "O volume está em {value}."}]}
        self.assertEqual(Executor.plan_goal(answer), {"fact": {"ring_volume": "down"}})
        e = Executor("como abaixo o toque", lambda prompt: json.dumps(answer), lambda w, l: None,
                     facts=lambda: {"ring_volume": 100, "sound_mode": "som", "do_not_disturb": False})
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        page = self.page("estado-som-toque-7-sons-volume")
        e.step(page)
        self.assertEqual(e.goal, {"fact": {"ring_volume": "down"}})
        self.assertIsNotNone(e.highlight)  # a barra do «Toque», para a pessoa
        e.i = 1
        e.step(page)
        self.assertNotEqual(e.result, "lido")

    def test_a_row_under_the_floating_search_bar_asks_to_scroll_first(self):
        # A busca que flutua no pé da página inicial das Configurações cobre «Notificações»: o toque no destaque
        # cairia nela. A pessoa sobe a tela um pouco antes, como num controle cortado no pé da tela.
        e = self.make([{"action": "tap", "target": ["Notificações"], "explain": "Toque em «Notificações»."}],
                      {"shows": ["Não perturbar"]})
        e.step(self.page("inicio"))
        self.assertEqual(e.gesture, "rolar")
        self.assertIsNone(e.highlight)
        self.assertIn("pé da tela", e.announce)

    def test_a_name_with_another_ending_is_the_same_control(self):
        # O plano diz «Não perturbe»; a One UI 9 diz «Não perturbar». Antes, uma ajuda de 10 s a cada guia.
        e = self.make([{"action": "turn_off", "target": ["Não perturbe", "Do not disturb"]}], {"fact": {"do_not_disturb": False}})
        e.facts = lambda: {"do_not_disturb": True}
        for _ in range(3):
            e.step(self.page("estado-dnd-ligado-abre-do-not-disturb"))
            if e.waiting:
                break
        self.assertEqual(e.highlight, (900, 419, 990, 475))
        self.assertEqual(e.helps, 0)

    def test_a_sound_symptom_goal_also_asks_for_the_sound(self):
        # 1 de 5 planos do Haiku pôs só o Não perturbar no objetivo, e o guia acabou "confirmado" com o celular em Vibrar.
        e = self.make([{"action": "set", "target": ["do_not_disturb"], "value": False}], {"fact": {"do_not_disturb": False}})
        e.facts = lambda: {"do_not_disturb": True, "sound_mode": "vibrar", "ring_volume": 0}
        e.prepare()
        self.assertEqual(e.goal["fact"], {"do_not_disturb": False, "sound_mode": "som", "ring_volume": "up"})

    def test_a_volume_set_goes_through_the_screens_without_help(self):
        # 2026-11-18, no celular: "set ring_volume 70" não tinha caminho pelas telas, e a ajuda levou 14,6 s.
        e = self.make([{"action": "set", "target": ["ring_volume"], "value": 70}], {"fact": {"ring_volume": "up"}})
        e.step(self.page("launcher"))
        self.assertEqual([(s["action"], s.get("target")) for s in e.plan],
                         [("open_settings", ["sound"]), ("tap", ["Som"]), ("tap", ["Volume"]), ("tap", ["Toque"])])
        self.assertEqual(e.helps, 0)
        self.assertEqual(e.button["open_settings"], "sound")

    def test_a_bar_is_named_by_its_title_not_by_its_level(self):
        # 2026-11-18, no celular: "mexa a bolinha da barra '1'" (o «Toque» do plano trocado pelo nível da barra).
        e = self.make([{"action": "tap", "target": ["Toque"], "explain": "Mexa a bolinha da barra «Toque» para a direita."}],
                      {"fact": {"ring_volume": "up"}})
        e.step(self.page("estado-som-toque-7-sons-volume"))
        self.assertIn("barra «Toque»", e.announce)
        self.assertNotIn("«7»", e.announce)

    def test_an_unmet_volume_at_the_end_adds_the_bar_step_without_help(self):
        # 2026-11-18, no celular: o plano parou no «Volume» (a barra só na explicação); com o toque em 7%, a ajuda respondeu
        # duas vezes "pronto", e o guia acabou sem confirmação, com o celular baixo.
        e = self.make([{"action": "tap", "target": ["Volume"]}], {"fact": {"ring_volume": "up"}})
        state = {"ring_volume": 0, "sound_mode": "som"}
        e.facts = lambda: dict(state)
        e.prepare()
        state["ring_volume"] = 7  # o modo Som volta com o toque em 1 de 15: ainda não dá para ouvir
        e.i = len(e.plan)
        for _ in range(3):
            e.step(self.page("estado-som-toque-7-sons-volume"))
            if e.waiting:
                break
        self.assertEqual(e.highlight, (807, 422, 1024, 506))
        self.assertEqual(e.helps, 0)

    def test_the_verb_toque_is_not_taken_for_a_control_name(self):
        # 2026-11-18, no celular: "Toque em 'Volume' para ver as barras" virou "Volume em 'Volume' para ver as barras".
        e = self.make([{"action": "tap", "target": ["Volume", "Toque"], "explain": "Toque em 'Volume' para ver as barras."}],
                      {"fact": {"ring_volume": "up"}})
        for _ in range(3):
            e.step(self.page("estado-som-toque-7-abre-sound"))
            if e.waiting:
                break
        self.assertTrue(e.announce.startswith("Toque em 'Volume' para ver as barras."), e.announce)

    def test_the_sound_mode_in_the_goal_uses_the_phones_word(self):
        # 2026-11-18, no celular: o plano pôs "sound_mode": "sound", e o guia acabou sem confirmação com tudo certo.
        e = self.make([{"action": "tap", "target": ["Som"]}], {"fact": {"sound_mode": "sound", "do_not_disturb": False}})
        e.prepare()
        self.assertEqual(e.goal["fact"]["sound_mode"], "som")


    def test_a_gesture_step_is_reminded_with_the_gesture(self):
        # 2026-11-18, no simulador: "toque onde está o destaque amarelo" enquanto a faixa mostrava o gesto, sem destaque.
        from lmphone.executor import GUIDE_REMINDER_GESTURE
        e = self.make([{"action": "tap", "target": ["Notificações"], "explain": "Toque em «Notificações»."}],
                      {"shows": ["Não perturbar"]})
        page = self.page("inicio")
        e.step(page)
        self.assertEqual(e.gesture, "rolar")
        e.waiting["since"] -= 30
        e.step(page)
        self.assertEqual(e.announce, GUIDE_REMINDER_GESTURE["rolar"])


    def test_the_quick_panel_is_pulled_from_the_right_on_one_ui_9(self):
        # 2026-11-19, no S23+: com os painéis separados, puxar pelo meio abre só os avisos, e a pessoa ficava ali.
        from lmphone.executor import SHADE_ONLY_SAY
        answers = [{"guide": True, "steps": [{"action": "quick_settings", "explain": "Puxe a barra de cima para baixo."},
                                             {"action": "tap", "target": ["Rotação autom."]}], "goal": {"shows": ["x"]}}]
        e = Executor("como eu travo a tela", lambda prompt: json.dumps(answers.pop(0)), lambda w, l: None,
                     device="Samsung Galaxy S23+, Android 17, One UI 9.0. Interface language: Portuguese")
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        for _ in range(3):
            e.step(self.page("launcher"))
            if e.waiting:
                break
        self.assertEqual(e.gesture, "puxar_direita")
        self.assertIn("lado direito", e.announce)
        e.waiting = None
        e.i, e.announce = 1, None  # a pessoa puxou pelo meio: abriu só os avisos
        e.step(self.page("painel-notificacoes"))
        self.assertEqual(e.announce, SHADE_ONLY_SAY)
        self.assertEqual(e.gesture, "puxar_direita")


    def test_the_system_panel_is_not_scrolled_to_find_a_button(self):
        # 2026-11-19, no celular: a lanterna estava mais abaixo no painel de atalhos; rolar para cima fechou o painel.
        # No painel compacto, o «Expandir» vem antes, sem a ajuda.
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Lanterna"], "if_missing": "scroll"}],
                    "goal": {"shows": ["x"]}}]
        asked = []
        e = Executor("como eu acendo a lanterna", lambda prompt: asked.append(prompt) or json.dumps(answers.pop(0)),
                     lambda w, l: None)
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        for _ in range(3):
            e.step(self.page("painel-atalhos"))
            if e.waiting:
                break
        self.assertNotEqual(e.gesture, "rolar")
        self.assertEqual(len(asked), 1)  # só o plano
        self.assertEqual(e.waiting["step"]["target"], ["Expandir"])


    def test_a_highlight_that_does_not_react_asks_for_help(self):
        # 2026-11-19, no celular: o título de seção «Agenda» destacado; a pessoa tocou, e nada mudou. Só andou porque o
        # brilho automático mudou sozinho (no simulador, esperava até o fim do tempo).
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Agenda"]}], "goal": {"shows": ["x"]}},
                   {"steps": [{"action": "turn_on", "target": ["Dormir"]}]}]
        asked = []
        state = {"do_not_disturb": False, "brightness": 30, "auto_brightness": True}
        e = Executor("como eu deixo o celular sem barulho de noite", lambda prompt: asked.append(prompt) or json.dumps(answers.pop(0)),
                     lambda w, l: None, facts=lambda: dict(state))
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        page = self.page("abre-do-not-disturb")
        for _ in range(3):
            e.step(page)
            if e.waiting:
                break
        e.waiting["started"] -= 20
        e.touched_at = time.monotonic() - 9
        state["brightness"] = 35  # o brilho automático mudou sozinho: não é o efeito do toque
        e.step(page)
        self.assertIn("does not react to a tap", asked[-1])


    def test_the_open_quick_panel_is_scrolled_before_asking(self):
        # 2026-11-19, no celular: no painel aberto inteiro, a lanterna estava mais abaixo; sem rolar, a ajuda mandava
        # adicioná-la pelo «Editar».
        answers = [{"guide": True, "steps": [{"action": "tap", "target": ["Lanterna"], "if_missing": "help"}],
                    "goal": {"shows": ["x"]}}]
        asked = []
        e = Executor("como eu acendo a lanterna", lambda prompt: asked.append(prompt) or json.dumps(answers.pop(0)),
                     lambda w, l: None)
        e.acts, e.can_ask, e.touched_at = False, True, 0.0
        for _ in range(3):
            e.step(self.page("painel-atalhos-expandido"))
            if e.waiting:
                break
        self.assertEqual(e.gesture, "rolar")
        self.assertEqual(len(asked), 1)


class WayTest(unittest.TestCase):
    """O caminho do fim do guia ("Para fazer de novo sozinho") e as regras de fala de 2026-11-18, no celular."""

    def make(self, trail):
        e = Executor("x", None, None)
        e.trail = trail
        return e

    def test_every_part_of_the_way_goes_in_order(self):
        # O caminho de Sons ficou de fora; só o do Não perturbar entrou.
        e = self.make([{"action": "open_settings", "target": ["sound"]}, {"action": "tap", "target": ["Som"]},
                       {"action": "tap", "target": ["Volume"]}, {"action": "tap", "target": ["Toque"]},
                       {"action": "open_settings", "target": ["do_not_disturb"]},
                       {"action": "turn_off", "target": ["Não perturbar"]}])
        self.assertEqual(e.way(), " Para fazer de novo sozinho: Configurações, depois Sons e vibração, depois Som, depois "
                                  "Volume, depois Toque; e Configurações, depois Notificações, depois Não perturbar.")

    def test_a_part_done_again_counts_once(self):
        e = self.make([{"action": "open_settings", "target": ["display"]}, {"action": "tap", "target": ["Modo de tela"]},
                       {"action": "open_settings", "target": ["display"]}, {"action": "tap", "target": ["Tamanho e estilo da fonte"]}])
        self.assertEqual(e.way(), " Para fazer de novo sozinho: Configurações, depois Visor, depois Tamanho e estilo da fonte.")

    def test_a_reply_that_promises_to_look_is_asked_again(self):
        from lmphone.executor import PROMISE, plain
        self.assertIsNotNone(PROMISE.search(plain("Vou ver o que está ligado e arrumar isso pra você. Primeiro, deixa eu olhar a tela.")))

    def test_a_part_without_taps_is_left_out_of_the_way(self):
        # 2026-11-19, no celular: "Configurações, depois Visor; e o painel rápido, ..." (o Visor foi um desvio sem toque).
        e = self.make([{"action": "open_settings", "target": ["display"]}, {"action": "quick_settings"},
                       {"action": "tap", "target": ["Rotação autom."]}])
        self.assertEqual(e.way(), " Para fazer de novo sozinho: o painel rápido, depois Rotação autom.")

    def test_a_long_explanation_keeps_its_first_sentence_with_the_addition(self):
        from lmphone.executor import GUIDE_WORDS, SLIDER, fit
        explain = ("Agora arraste a bolinha da barrinha Toque para a direita, para o som ficar mais alto. Quando você "
                   "conseguir escutar bem, pode parar, e o celular já vai tocar nas ligações.")
        said = fit(explain, SLIDER)
        self.assertLessEqual(len(said.split()), GUIDE_WORDS)
        self.assertEqual(said, "Agora arraste a bolinha da barrinha Toque para a direita, para o som ficar mais alto. " + SLIDER)
        self.assertEqual(fit("Toque em «Volume».", "Fica no meio da tela."), "Toque em «Volume». Fica no meio da tela.")

    def test_a_long_first_sentence_is_cut_at_its_first_comma(self):
        # 2026-11-19, no simulador: a primeira frase sozinha, com a frase da barra, dava 38 palavras.
        from lmphone.executor import GUIDE_WORDS, SLIDER_DOWN, fit
        said = fit("Procure a opção Brilho, que é uma barrinha com um sol pequeno de um lado e um sol grande do outro.",
                   SLIDER_DOWN)
        self.assertEqual(said, "Procure a opção Brilho. " + SLIDER_DOWN)
        self.assertLessEqual(len(said.split()), GUIDE_WORDS)

    def test_a_long_explanation_alone_keeps_the_sentences_that_fit(self):
        from lmphone.executor import GUIDE_WORDS, short
        text = ("Olhe a barra embaixo da tela, na parte de baixo. Toque na letra A pequenininha, do lado esquerdo da barra, "
                "para a letra ficar menor. Toque quantas vezes precisar e veja se fica do jeito que você gosta.")
        self.assertEqual(short(text), "Olhe a barra embaixo da tela, na parte de baixo. Toque na letra A pequenininha, do "
                                      "lado esquerdo da barra, para a letra ficar menor.")
        self.assertLessEqual(len(short(text).split()), GUIDE_WORDS)
        self.assertEqual(short("Toque em «Visor»."), "Toque em «Visor».")

    def test_letters_in_quotes_are_not_a_name_between_them(self):
        # "um 'A' pequeno e um 'A' grande": « pequeno e um » não é um nome dito (o critério "nomes" da suíte).
        e = Executor("letra", lambda p: "{}", lambda w, l: None)
        e.labels = ["Tamanho e estilo da fonte"]
        self.assertEqual(e.names_off_screen("É a opção que mostra um 'A' pequeno e um 'A' grande."), [])
        self.assertEqual(e.names_off_screen("Toque em 'Tamanho da letra'."), ["Tamanho da letra"])

    def test_a_volume_set_after_the_bar_is_dropped_in_the_guide(self):
        # 2026-11-19, no simulador: o plano tocava em «Toque» e depois tinha o `set` do volume; no guia ele virava o
        # caminho todo de novo, e a pessoa voltava às Configurações.
        steps = [{"action": "open_settings", "target": ["sound"]}, {"action": "tap", "target": ["Volume"]},
                 {"action": "tap", "target": ["Toque", "Campainha"]}, {"action": "set", "target": "ring_volume", "value": 30}]
        self.assertEqual(Executor.guided(steps), steps[:3])
        self.assertEqual([s["action"] for s in Executor.guided(steps[:1] + steps[3:])],
                         ["open_settings", "open_settings", "tap", "tap", "tap"])
