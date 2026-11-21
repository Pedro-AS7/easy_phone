"""Os cenários do simulador (tests/simulador.py) como testes: cada um roda um guia inteiro do app da loja, com o celular,
a faixa e a pessoa de mentira, e não pode ter nenhum dos problemas que ele confere (o agente agir, uma bronca falsa,
uma ajuda a mais, o botão a mais ou a menos, o aparelho fora do estado pedido, a demora)."""

import unittest

from tests import celular_real, simulador


class SimuladoTest(unittest.TestCase):
    def test_os_cenarios(self):
        for nome in simulador.CENARIOS:
            if nome.startswith("real-") and not celular_real.TEM_TELAS:
                continue
            with self.subTest(nome):
                sim = simulador.rodar(nome)
                linha = "\n".join(f"{s:6.1f}  {t}" for s, t in sim.linha)
                self.assertEqual(sim.problemas(), [], f"{nome}: {sim.resumo()}\n{linha}")

    @unittest.skipUnless(celular_real.TEM_TELAS, "sem as telas gravadas (tests/telas/)")
    def test_o_caminho_do_fim_nao_tem_o_voltar_nem_o_botao_que_nao_abriu(self):
        # 2026-11-18: "Para fazer de novo sozinho: Configurações, depois Sons e vibração, depois Navegar, depois Sons e
        # vibração, ..." (o botão que não abriu a página e a seta de voltar no caminho).
        sim = simulador.rodar("real-avisos-pagina-nao-abre")
        self.assertIn("Para fazer de novo sozinho: Config., depois Sons e vibração, depois Som, depois Volume, depois Toque.",
                      sim.fim[1])


if __name__ == "__main__":
    unittest.main()
