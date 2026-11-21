"""Casos das regras fixas de `lmphone/masking.py` que valem sem a IA local (2026-11-12). Todos os dados são fictícios.

`mascarar`: o que não pode aparecer no texto enviado; `manter`: o que precisa continuar lá; `senhas`: o que
`masking.passwords` tem de achar no pedido (lista vazia: nada). O cofre fictício é `CONTATOS`.
"""

CONTATOS = ["Lívia Bastos", "Caio Menezes", "Bruno Mercado Livre", "Rosa Lima"]


def caso(entrada, mascarar=(), manter=(), senhas=None):
    return {"entrada": entrada, "mascarar": list(mascarar), "manter": list(manter), "senhas": senhas}


CASOS = [
    # --- senha: o valor, não a palavra que vem depois de "senha" ---
    caso("troca a senha do wifi pra abc12345", ["abc12345"], ["pra", "wifi"], senhas=["abc12345"]),
    caso("esqueci a senha do instagram, me ajuda", manter=["instagram"], senhas=[]),
    caso("a senha do wifi da casa é limao2024", ["limao2024"], ["casa"], senhas=["limao2024"]),
    caso("senha do roteador, a atual é KYBA2686!", ["KYBA2686"], ["roteador"], senhas=["KYBA2686"]),
    caso("me lembra de trocar a senha amanhã", manter=["amanhã"], senhas=[]),
    caso("coloca a senha nova: Kz81!x", ["Kz81!x"], ["nova"], senhas=["Kz81!x"]),
    caso("a senha é muito fraca, troca por outra", manter=["muito", "fraca"], senhas=[]),
    caso("the password is hunter2", ["hunter2"], senhas=["hunter2"]),
    caso("entra com a senha fps141731 no site", ["fps141731"], ["site"], senhas=["fps141731"]),
    # --- documentos e códigos ---
    caso("o cnpj da loja é 11.222.333/0001-81", ["11.222.333/0001-81"], ["cnpj"]),
    caso("meu cpf é 52998224725", ["52998224725"]),
    caso("o pedido 12345678901 chegou", manter=["12345678901"]),
    caso("cartão 4111111111111111 no débito", ["4111111111111111"], ["débito"]),
    caso("o protocolo é 1234567812345678", manter=["1234567812345678"]),
    caso("manda pro cep 70297-400", ["70297-400"]),
    caso("minha placa é BRA2E19", ["BRA2E19"], ["placa"]),
    caso("a placa abc-1234 tá no nome dele", ["abc-1234"], ["placa"]),
    caso("norma ISO-9001 e RTX4090", manter=["ISO-9001", "RTX4090"]),
    caso("rg 2.345.678 ssp", ["2.345.678"], ["rg", "ssp"]),
    caso("deposita na conta 12345-6", ["12345-6"], ["conta"]),
    caso("a conta 2024 já foi paga", manter=["2024"]),
    # --- logradouro ---
    caso("moro na Rua das Acácias, 482, apto 301", ["Acácias"], ["Rua", "apto"]),
    caso("fica na avenida jacarandá 1500 perto do mercado", ["jacarandá"], ["avenida", "mercado"]),
    caso("a rua estava cheia hoje", manter=["estava", "cheia"]),
    # --- nomes sem a IA local ---
    caso("manda pro caio que a reunião mudou", ["caio"], ["reunião"]),
    caso("pergunta pra gisele se ela vai no churrasco", ["gisele"], ["churrasco"]),
    caso("Manda um oi pro Henrique Albuquerque", ["Henrique", "Albuquerque"], ["Manda"]),
    caso("fala pro lucas dias atrás eu avisei", ["lucas"], ["dias"]),
    caso("Livia mandou o arquivo", ["Livia"], ["arquivo"]),
    caso("segue o perfil livia_bastos", ["livia", "bastos"], ["perfil"]),
    caso("o mercado livre entrega amanhã", manter=["mercado", "livre"]),
    caso("deixa a tela mais clara e rosa", manter=["clara", "rosa"]),
    caso("Vitória ganhou o jogo em Salvador", manter=["Vitória", "Salvador"]),
    caso("Manda pra Clara Nunes a foto", ["Clara", "Nunes"], ["foto"]),
    # --- número curto não vira literal ---
    caso('3. TextView: "Sala 190" - (0,100,1080,190)', manter=["(0,100,1080,190)"]),
]
