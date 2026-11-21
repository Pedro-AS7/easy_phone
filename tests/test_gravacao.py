"""A repetição das gravações (tests/gravacao.py): uma rodada do simulador, gravada no formato do celular
(Gravacao.kt), repete igual no executor do Python, e uma gravação adulterada aparece como diferença."""

import copy
import json
import os
import unittest

from tests import gravacao, simulador


class GravacaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = simulador.rodar("sint-avisos")

    def test_a_rodada_gravada_se_repete_igual(self):
        r = gravacao.repetir(self.sim.gravacao)
        self.assertIsNone(r.parou)
        self.assertEqual(r.diferencas, [])
        self.assertGreater(r.passos, 10)

    def test_uma_decisao_diferente_aparece(self):
        eventos = copy.deepcopy(self.sim.gravacao)
        falada = next(ev for ev in eventos if ev["tipo"] == "decisao" and ev.get("fala"))
        falada["fala"] = "outra fala"
        r = gravacao.repetir(eventos)
        self.assertEqual([d["o que"] for d in r.diferencas], ["fala"])

    def test_outro_plano_faz_o_python_seguir_outro_caminho(self):
        eventos = copy.deepcopy(self.sim.gravacao)
        plano = next(ev for ev in eventos if ev["tipo"] == "cb" and ev["cb"] == "provider")
        resposta = json.loads(plano["ret"])
        resposta["steps"] = resposta["steps"][1:]  # sem o Não perturbar
        plano["ret"] = json.dumps(resposta, ensure_ascii=False)
        r = gravacao.repetir(eventos)
        self.assertTrue(r.parou or r.diferencas)

    def test_a_linha_do_tempo_e_os_tempos(self):
        textos = [t for _, t in gravacao.linha(self.sim.gravacao)]
        self.assertTrue(any(t.startswith("diz: ") for t in textos))
        self.assertTrue(textos[-1].startswith("fim: confirmado"))
        self.assertEqual(gravacao.diferencas(gravacao.linha(self.sim.gravacao), gravacao.linha(self.sim.gravacao)), [])
        medidas = gravacao.medir(self.sim.gravacao)
        self.assertEqual(len(medidas["provedor (plano)"]), 1)
        self.assertTrue(all(0.3 <= s < 2.0 for s in medidas["aviso do toque"]))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gravacoes")), "sem as gravações do celular (tests/gravacoes/)")
class CelularTest(unittest.TestCase):
    """O simulador contra as rodadas no celular (tests/gravacoes/celular-avisos-9 a 11, a versão final de 2026-11-18): a
    mesma rodada (o pedido, o estado do começo, as respostas do provedor, as telas de verdade) repetida no simulador
    termina igual, com o aparelho no mesmo estado, quase tudo o que o guia faz na mesma ordem e um tempo parecido."""

    def test_o_simulador_repete_as_rodadas_do_celular(self):
        for n in (9, 10, 11):
            with self.subTest(n):
                c = gravacao.comparar(gravacao.ler(f"tests/gravacoes/celular-avisos-{n}.jsonl"))
                self.assertEqual(c["resultado"][0], c["resultado"][1])
                self.assertEqual(c["estado"][0], c["estado"][1])
                self.assertGreaterEqual(c["iguais"], 0.9 * c["celular_n"], "\n".join(c["diferencas"]))
                celular, simulado = c["tempo"]
                self.assertLess(abs(simulado - celular), 0.3 * celular, f"{celular:.0f} s no celular, {simulado:.0f} s no simulador")
