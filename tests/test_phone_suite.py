import argparse
import unittest
from collections import Counter
from unittest import mock

from tests import phone_suite
from tests.phone_cases import CASES


def node(text, bounds, checkable=False, checked=False):
    return {"text": text, "boundsInScreen": dict(zip(("left", "top", "right", "bottom"), bounds)),
            "isCheckable": checkable, "isChecked": checked, "children": []}


class CasesTest(unittest.TestCase):
    def test_casos_por_nivel(self):
        self.assertEqual(Counter(c["nivel"] for c in CASES), {"crucial": 12, "simples": 12, "dia_a_dia": 11, "conversa": 5,
                                                              "guia": 8, "sintoma": 6})
        self.assertEqual(len({c["id"] for c in CASES}), 54)
        self.assertEqual({c["categoria"] for c in CASES}, {"sistema", "social", "navegador", "ferramentas", "ajuda"})
        for case in CASES:
            self.assertTrue(case["confere"] and case["testa"])
            if case["nivel"] == "guia":  # a pessoa simulada e os critérios do guia
                self.assertIn(case["pessoa"], ("toca", "erra", "olha"))
                self.assertTrue(any(check[0] == "guia" for check in case["confere"]))
            if case.get("conversa"):  # uma lista de conferências por turno
                self.assertEqual(len(case["confere"]), len(case["pedido"]))
                self.assertTrue(all(isinstance(turn, list) and turn for turn in case["confere"]))


class GuideTest(unittest.TestCase):
    LIVE = [
        {"tipo": "pedido", "texto": "Como eu aumento a letra?"},
        {"tipo": "acao", "ferramenta": "open_settings", "passo": 0, "disse": "Primeiro abro as Configurações."},
        {"tipo": "fala", "texto": "Primeiro abro as Configurações."},
        {"tipo": "destaque", "limites": [0, 100, 500, 200], "dono": True},
        {"tipo": "acao", "ferramenta": "wait", "passo": 1, "disse": "Toque em «Tela», no meio da lista."},
        {"tipo": "fala", "texto": "Toque em «Tela», no meio da lista."},
        {"tipo": "acao", "ferramenta": "swipe", "passo": 2},
        {"tipo": "fim", "mensagem": "Pronto! Configurações, depois Tela, depois Tamanho da fonte."},
    ]

    def checks(self, live, person, criteria=phone_suite.GUIDE_CRITERIA):
        return {name: ok for name, ok, _ in phone_suite.guide_checks(criteria, live, person)}

    def test_criterios(self):
        got = self.checks(self.LIVE, [{"tipo": "toque", "limites": [0, 100, 500, 200], "t": 3.0}])
        self.assertEqual(got, {"guia: cada ação do agente vem explicada": False,  # a rolagem não foi explicada
                               "guia: a pessoa tocou, o agente não": True,
                               "guia: o toque da pessoa não pausou a tarefa": True,
                               "guia: não pede de novo o passo que a pessoa já fez": True,
                               "guia: diz onde fica o controle (metade das falas ou mais)": True,
                               "guia: falas curtas e sem termos em inglês": True,
                               "guia: a resposta final resume o caminho": True,
                               "guia: os nomes ditos estão na tela": True})

    def test_pausa_toque_do_agente_e_ingles(self):
        live = self.LIVE[:-2] + [{"tipo": "usuario_pausa"}, {"tipo": "acao", "ferramenta": "click"},
                                 {"tipo": "fala", "texto": "Tap the switch to turn it on."}, {"tipo": "fim", "mensagem": "Pronto."}]
        got = self.checks(live, [], ("pessoa_faz", "sem_pausa", "simples", "caminho"))
        self.assertEqual(list(got.values()), [False, False, False, False])

    def test_sem_registro(self):
        self.assertEqual(self.checks([], None), {"guia: registro do live mode": False})

    def test_a_pessoa_fez_tudo(self):
        live = [{"tipo": "acao", "ferramenta": "wait", "passo": 1, "disse": "Toque em «Tela», no alto."},
                {"tipo": "fala", "texto": "Toque em «Tela», no alto."}, {"tipo": "fim", "mensagem": "Pronto."}]
        self.assertTrue(self.checks(live, [], ("explica",))["guia: cada ação do agente vem explicada"])


class ScreenTest(unittest.TestCase):
    def test_chave_na_linha_do_rotulo(self):
        tree = {"a11y_tree": {"text": "", "children": [
            node("Private account", (40, 300, 600, 360)), node("", (900, 290, 1040, 370), True, True),
            node("Other", (40, 500, 600, 560)), node("", (900, 490, 1040, 570), True, False)]}}
        nodes = phone_suite.nodes_of({"status": "success", "result": __import__("json").dumps(tree)})
        self.assertIs(phone_suite.switch_state(nodes, r"^Private account$"), True)
        self.assertIs(phone_suite.switch_state(nodes, r"^Other$"), False)
        self.assertIsNone(phone_suite.switch_state(nodes, r"^Missing$"))


class LogTest(unittest.TestCase):
    ROWS = [
        {"session": "s", "local_ai": {"intencao": "x", "seconds": 9.0}},
        {"session": "s", "request": 1, "sent": [{"role": "user", "content": "plan"}], "masked": {"email": 1}},
        {"session": "s", "request": 1, "status": 200, "seconds": 2.5, "usage": {"prompt_tokens": 800, "completion_tokens": 200, "cost": 0.0012}},
        {"session": "s", "exec": {"por": "código", "ajudas": 1, "ia_seconds": 0.3, "decisao": "Tap", "acao": "click"}},
        {"session": "s", "request": 2, "sent": [{"role": "user", "content": "help <device_state>\nab\n</device_state>"}], "masked": {}},
        {"session": "s", "request": 2, "status": 429, "seconds": 0.4, "received": "rate limit"},
        {"session": "s", "local_ai_tela": {"trechos": 3, "seconds": 4.0, "erro": "TimeoutError()"}},
    ]

    def test_medidas(self):
        m = phone_suite.measure(self.ROWS)
        self.assertEqual((m["chamadas"], m["ajudas"], m["acoes"], m["trocas"], m["tela_caracteres"]), (2, 1, 1, 1, 4))
        self.assertEqual((m["provedor_s"], m["ia_local_s"], m["custo"]), (2.9, 13.3, 0.0012))
        self.assertEqual(m["erros"], ["provedor respondeu 429", "local_ai_tela: TimeoutError()"])

    def test_segredo_enviado_sem_mascara_reprova(self):
        case = {"segredos": ["ana.teste@example.com"], "liberado": ["Museu do Amanhã"]}
        rows = [{"sent": [{"content": "type ana.teste@example.com at the Museu do Amanhã"}]}]
        with mock.patch.object(phone_suite, "VAULT_PATH", None):
            checks = {name.split(":")[0] + ":" + name.split(":")[1][:9]: ok for name, ok, _ in phone_suite.privacy(case, rows, "", None)}
            masked = phone_suite.privacy(case, [{"sent": [{"content": "type contato1@exemplo.com"}]}], "", None)
        self.assertEqual(list(checks.values()), [True, False, True])
        self.assertEqual([ok for _, ok, _ in masked], [True, True, False])

    def test_valor_lido_nao_pode_estar_no_log(self):
        case = {"resposta_privada": True}
        with mock.patch.object(phone_suite, "VAULT_PATH", None):
            clean = phone_suite.privacy(case, [{"sent": ["screen ###"], "received": ["read it"]}], "482913", None)
            leaked = phone_suite.privacy(case, [{"sent": ["code 482913"]}], "482913", None)
        self.assertIs(clean[-1][1], True)
        self.assertIs(leaked[-1][1], False)


class ReportTest(unittest.TestCase):
    def test_relatorio_sem_medidas(self):
        record = {"id": "x", "rodada": 1, "nivel": "simples", "categoria": "sistema", "pedido": "p <b>",
                  "testa": "t", "erros": ["preparo: falhou"], "conferencias": [], "status": "erro"}
        page = phone_suite.render([record], "hoje", argparse.Namespace(modelo="m", sem_cache=False))
        self.assertIn("p &lt;b&gt;", page)
        self.assertIn("preparo: falhou", page)


if __name__ == "__main__":
    unittest.main()
