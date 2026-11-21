"""O celular do simulador com as telas de verdade (tests/celular_real.py): o que um toque faz nas páginas gravadas."""

import unittest

from tests import celular_real as cr


class Relogio:
    agora = 0.0


class Sim:
    relogio = Relogio()

    def marcar(self, texto):
        pass

    def depois(self, segundos, funcao, nota=None):
        funcao()


def linha(celular, trecho):
    return next((l for l in celular.tela().splitlines() if trecho in l), None)


@unittest.skipUnless(cr.TEM_TELAS, "sem as telas gravadas (tests/telas/)")
class CelularRealTest(unittest.TestCase):
    def test_a_chave_do_nao_perturbar_desce_ao_desligar(self):
        c = cr.CelularReal(Sim(), dnd=True, comeco="abre-do-not-disturb")
        alvo, limites = c.tocar(945, 447)
        self.assertFalse(c.estado["dnd"])
        self.assertEqual(limites, (900, 481, 990, 537))  # o aviso do toque traz a chave no lugar novo
        self.assertIn("isChecked=False - (900,481,990,537)", linha(c, "switch_widget"))

    def test_som_muda_o_modo_e_a_barra_do_toque_mostra_o_nivel(self):
        c = cr.CelularReal(Sim(), dnd=False, modo="vibrar", comeco="abre-sound")
        c.tocar(194, 433)
        self.assertEqual((c.estado["modo"], c.fatos()["ring_volume"]), ("som", 7))  # o S23+ volta do mudo com 1 de 15
        c.tocar(540, 1423)  # «Volume», no lugar dele com a linha «Vibrar enquanto toca»
        self.assertEqual(c.pilha[-1][0], "sons-volume")
        c.tocar(900, 464)
        self.assertEqual(c.estado["toque"], 86)
        self.assertIn('"13"', linha(c, "android:id/seekbar"))

    def test_uma_opcao_da_luz_de_fundo_muda_o_tempo_sem_marca_na_tela(self):
        # A árvore da One UI 9 não traz qual opção está escolhida: a tela fica igual (o executor não vê a mudança).
        c = cr.CelularReal(Sim(), comeco="visor-duracao-da-luz-de-fundo")
        antes = c.tela()
        c.tocar(600, 943)  # «5 minutos»
        self.assertEqual(c.estado["tela_apaga"], 300)
        self.assertEqual(c.tela(), antes)

    def test_os_botoes_da_fonte_mudam_a_letra(self):
        c = cr.CelularReal(Sim(), comeco="visor-tamanho-e-estilo-da-fonte")
        c.tocar(962, 2171)  # «Aumentar tam. da fonte»
        self.assertEqual(c.fatos()["font_scale"], 1.08)  # medido no S23+
        self.assertIn('"3"', linha(c, "font_size_seek_bar\""))

    def test_puxar_pelo_meio_abre_os_avisos_e_pela_direita_os_atalhos(self):
        # One UI 9, painéis separados: puxar de novo pelo meio não abre os atalhos.
        c = cr.CelularReal(Sim(), comeco="launcher")
        c.puxar("meio")
        self.assertEqual(c.pilha[-1][0], "painel-notificacoes")
        c.puxar("meio")
        self.assertEqual(c.pilha[-1][0], "painel-notificacoes")
        c.puxar("direita")
        self.assertEqual(c.pilha[-1][0], "painel-atalhos")
        c.voltar()
        self.assertEqual(c.pilha[-1][0], "launcher")

    def test_expandir_abre_o_painel_inteiro(self):
        # O «Expandir» fica numa View sem nome dentro da tocável: com o título vazio, abria as Configurações.
        c = cr.CelularReal(Sim(), comeco="launcher")
        c.puxar("direita")
        c.tocar(540, 1908)
        self.assertEqual(c.pilha[-1][0], "painel-atalhos-expandido")

    def test_a_lanterna_fica_na_segunda_tela_do_painel_aberto(self):
        c = cr.CelularReal(Sim(), comeco="painel-atalhos-expandido")
        self.assertIsNone(linha(c, "Lanterna"))
        c.rolar()
        self.assertIn("isChecked=False", linha(c, "Lanterna"))
        c.tocar(197, 1690)
        self.assertTrue(c.estado["lanterna"])
        self.assertIn("isChecked=True", linha(c, "Lanterna"))

    def test_o_bloco_do_som_passa_ao_modo_seguinte(self):
        c = cr.CelularReal(Sim(), comeco="painel-atalhos-expandido", modo="vibrar")
        c.tocar(878, 2150)
        self.assertEqual(c.estado["modo"], "mudo")
        self.assertIsNotNone(linha(c, "Alternar para som"))

    def test_o_modo_escuro_e_a_localizacao_seguem_o_estado(self):
        c = cr.CelularReal(Sim(), comeco="visor", escuro=True)
        c.tocar(289, 949)  # «Claro»
        self.assertEqual((c.estado["escuro"], c.fatos()["dark_mode"]), (False, False))
        c = cr.CelularReal(Sim(), comeco="local", local=True)
        c.tocar(946, 347)
        self.assertFalse(c.fatos()["location"])
        self.assertIn('"Desativado" ; isChecked=False', linha(c, "sesl_switchbar_switch"))

    def test_as_barras_do_painel_mudam_a_midia_e_o_brilho(self):
        c = cr.CelularReal(Sim(), comeco="painel-atalhos-expandido", midia=0, brilho=0)
        c.tocar(782, 690)
        c.tocar(782, 920)
        self.assertEqual((c.estado["midia"], c.estado["brilho"]), (100, 100))


if __name__ == "__main__":
    unittest.main()
