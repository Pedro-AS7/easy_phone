"""O conjunto congelado é coerente e o diagnóstico de tests/eval_base.py aponta a causa certa (Gemma e Laya falsos)."""

import json
import re
import unittest
from unittest import mock

from lmphone.executor import plain

from tests import eval_base
from tests.base.controles import ESCOLHAS
from tests.base.mascaramento import CASOS


class CaseSet(unittest.TestCase):
    def test_unique_ids(self):
        ids = [c["id"] for c in CASOS] + [c["id"] for c in ESCOLHAS]
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])

    def test_masking_targets_are_in_the_input(self):
        for case in CASOS:
            source = (case.get("entrada") or " • ".join(case["trechos"])).casefold()
            for key in ("pessoas", "usuarios", "outros", "liberar", "manter"):
                for value in case[key]:
                    self.assertIn(value.casefold(), source, f"{case['id']}: {key} {value!r}")

    def test_kept_text_does_not_contain_a_masked_name(self):
        for case in CASOS:
            words = {t.casefold() for name in case["pessoas"] for t in re.findall(r"[^\W\d_]{3,}", name)}
            for value in case["manter"] + case["liberar"]:
                clash = words & {t.casefold() for t in re.findall(r"[^\W\d_]+", value)}
                self.assertFalse(clash, f"{case['id']}: {value!r} precisa ficar e contém {clash}")

    def test_picks_need_the_model(self):
        for case in ESCOLHAS:
            self.assertTrue(all(right in case["tela"] for right in eval_base.rights(case)), case["id"])
            labels = {plain(l) for l in case["tela"]}
            for wanted in case["pedidos"]:
                self.assertNotIn(plain(wanted), labels, f"{case['id']}: {wanted!r} está escrito na tela; o código resolve sem o Laya")


def gemma(items):
    """find_private falso que devolve `items` (texto, tipo) para qualquer bloco."""
    found = {"itens": [{"texto": t, "tipo": k} for t, k in items]}
    return mock.patch.object(eval_base.local_ai, "find_private", return_value=(found, json.dumps(found), 0.1))


def laya_private(scores):
    """/private falso: p de cada trecho pelo texto (0,9 se não listado)."""
    return mock.patch.object(eval_base, "laya", side_effect=lambda path, body=None: {
        "p": [scores.get(f, 0.9) for f in body["fragments"]], "seconds": 0.01})


def screen(trechos, pessoas=(), usuarios=(), manter=()):
    return {"id": "t", "tipo": "tela", "app": "x", "onde": "x", "trechos": list(trechos), "intencao": [],
            "pessoas": list(pessoas), "usuarios": list(usuarios), "outros": [], "liberar": [], "manter": list(manter), "nota": ""}


def codes(result):
    return [k["codigo"] for c in result["conferencias"] if not c["ok"] for k in c["causas"]]


class MaskingDiagnosis(unittest.TestCase):
    def test_ok(self):
        with laya_private({}), gemma([("Dagoberto Prates", "pessoa")]):
            r = eval_base.run_masking(screen(["Dagoberto Prates", "Settings"], pessoas=["Dagoberto Prates"], manter=["Settings"]))
        self.assertEqual(r["status"], "ok")

    def test_filter_dropped_the_fragment(self):
        with laya_private({"Dagoberto Prates": 0.05}), gemma([]):
            r = eval_base.run_masking(screen(["Dagoberto Prates", "Settings"], pessoas=["Dagoberto Prates"]))
        self.assertEqual(r["status"], "vazamento")
        self.assertEqual(set(codes(r)), {"filtro_laya"})

    def test_gemma_missed_it(self):
        with laya_private({}), gemma([]):
            r = eval_base.run_masking(screen(["Dagoberto Prates"], pessoas=["Dagoberto Prates"]))
        self.assertEqual(set(codes(r)), {"ia_omitiu"})

    def test_gemma_copied_half_a_username(self):
        with laya_private({}), gemma([("lari.pr", "usuario")]):
            r = eval_base.run_masking(screen(["lari.prado"], usuarios=["lari.prado"]))
        self.assertEqual(codes(r), ["ia_parcial"])

    def test_gemma_marked_an_interface_label(self):
        with laya_private({}), gemma([("Switch to private account?", "pessoa")]):
            r = eval_base.run_masking(screen(["Switch to private account?"], manter=["Switch to private account?"]))
        self.assertEqual(r["status"], "excesso")
        self.assertIn("ia_marcou", codes(r))

    def test_vault_word_masks_a_common_word(self):
        # "Bom" está no cofre fictício (Pet Shop Bicho Bom).
        with laya_private({}), gemma([]):
            r = eval_base.run_masking(screen(["Bom dia!"], manter=["Bom dia"]))
        self.assertEqual(codes(r), ["cofre"])

    def test_gemma_error(self):
        with laya_private({}), mock.patch.object(eval_base.local_ai, "find_private", side_effect=TimeoutError("lento")):
            r = eval_base.run_masking(screen(["Dagoberto Prates"], pessoas=["Dagoberto Prates"]))
        self.assertEqual(set(codes(r)), {"ia_erro"})

    def test_request_type_and_release(self):
        judgment = {"intencao": "acao", "entidades": [{"texto": "Dagoberto", "tipo": "negocio", "precisa_pesquisa": False}]}
        case = {"id": "p", "tipo": "pedido", "app": "x", "onde": "x", "entrada": "manda pro Dagoberto", "intencao": ["acao"],
                "pessoas": ["Dagoberto"], "usuarios": [], "outros": [], "liberar": [], "manter": [], "nota": ""}
        with mock.patch.object(eval_base.local_ai, "judge_request", return_value=(judgment, json.dumps(judgment), 0.1)):
            r = eval_base.run_masking(case)
        self.assertEqual(codes(r), ["ia_tipo"])


class PickDiagnosis(unittest.TestCase):
    CASE = {"id": "c", "app": "x", "onde": "x", "pedidos": ["Dark mode"], "tela": ["Display", "Battery"], "certo": "Display", "nota": ""}

    def pick(self, label, ranking, certo="Display"):
        answer = {"label": label, "p": ranking[0][1], "ranking": ranking, "seconds": 0.1}
        with mock.patch.object(eval_base, "laya", return_value=answer):
            return eval_base.run_pick({**self.CASE, "certo": certo})

    def test_statuses(self):
        self.assertEqual(self.pick("Display", [["Display", 0.8]])["status"], "ok")
        below = self.pick(None, [["Display", 0.4], ["(none)", 0.3]])
        self.assertEqual((below["status"], below["causas"][0]["codigo"]), ("nao_achou", "limiar"))
        wrong = self.pick("Battery", [["Battery", 0.7], ["Display", 0.2]])
        self.assertEqual((wrong["status"], wrong["causas"][0]["codigo"]), ("toque_errado", "toque_errado"))
        self.assertIn("2º", wrong["causas"][0]["detalhe"])
        none = self.pick(None, [["(none)", 0.6], ["Display", 0.3]])
        self.assertEqual(none["causas"][0]["codigo"], "nao_achou")
        tapped = self.pick("Battery", [["Battery", 0.7]], certo=None)
        self.assertEqual(tapped["status"], "falso_positivo")

    def test_same_control_with_two_labels(self):
        # A etiqueta da linha e o texto dela são o mesmo controle: tocar em qualquer um está certo.
        both = ("Display", "Battery")
        self.assertEqual(self.pick("Battery", [["Battery", 0.7]], certo=both)["status"], "ok")
        below = self.pick(None, [["(none)", 0.6], ["Battery", 0.3]], certo=both)
        self.assertIn("«Battery» ficou em 2º", below["causas"][0]["detalhe"])


if __name__ == "__main__":
    unittest.main()
