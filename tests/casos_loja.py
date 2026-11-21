"""Os 50 casos do app da loja que valem igual no celular e no simulador (2026-11-19, pedido do Pedro).

Cada caso tem o pedido (como quem tem dificuldade diria), o nível ("guia": como se faz; "sintoma": o problema), o
preparo (o estado do começo) e as conferências do fim, no formato de tests/phone_cases.py:

- no celular, `tests.loja_suite` usa o `prepare` e o `verify` da suíte (tests/phone_suite.py), com a pessoa simulada;
- no simulador, `tests.casos` põe o mesmo estado no celular de telas reais (tests/celular_real.py), roda com o Haiku e
  o modelo de escolha de verdade e aplica as mesmas conferências aos fatos do aparelho simulado e ao que o guia disse.

Só entram as áreas que a varredura gravou e que o aparelho mede (letra, brilho, modo escuro, rotação, tempo da tela,
Não perturbar, modo de som, volumes, lanterna, localização). Wi-Fi, Bluetooth e modo avião ficam de fora: no celular,
desligá-los corta o adb ou o fone do dono.
"""

LETRA_1 = [("ajuste", "font_scale", "1.0"), ("ajuste", "font_size", "2")]  # font_size: o nível da barra da One UI
SEM_REPETIR = ("guia", "explica", "pessoa_faz", "sem_pausa", "onde", "simples", "caminho", "nomes")  # para quem erra


def caso(id, nivel, pedido, preparo, confere, pessoa="toca", resposta=None):
    confere = list(confere)
    if resposta:
        confere.append(("resposta", resposta))
    if nivel == "guia":
        confere.append(SEM_REPETIR if pessoa == "erra" else ("guia",))
    return {"id": id, "nivel": nivel, "categoria": "ajuda", "pessoa": pessoa, "pedido": pedido, "preparo": preparo,
            "confere": confere, "fecha": "com.android.settings", "loja": True}


CASOS = [
    # --- letra ---
    caso("caso-letra-aumentar", "guia", "Como eu deixo a letra do celular maior?", LETRA_1,
         [("ajuste_maior", "font_scale", "1.0")]),
    caso("caso-letra-miudinha", "sintoma", "Não tô conseguindo ler as mensagens, a letra é muito miudinha",
         [("ajuste", "font_scale", "0.8"), ("ajuste", "font_size", "0")], [("ajuste_maior", "font_scale", "0.8")],
         resposta=r"letra|fonte|tamanho"),
    caso("caso-letra-diminuir", "guia", "Como diminuo o tamanho da letra? Ficou grande demais",
         [("ajuste", "font_scale", "1.3"), ("ajuste", "font_size", "5")], [("ajuste_menor", "font_scale", "1.3")]),
    caso("caso-letra-enorme", "sintoma", "As letras ficaram enormes, não cabe nada na tela",
         [("ajuste", "font_scale", "1.7"), ("ajuste", "font_size", "7")], [("ajuste_menor", "font_scale", "1.7")],
         resposta=r"letra|fonte|tamanho"),
    caso("caso-letra-oculos", "sintoma", "Mesmo de óculos eu não enxergo o que tá escrito no celular",
         [("ajuste", "font_scale", "0.9"), ("ajuste", "font_size", "1")], [("ajuste_maior", "font_scale", "0.9")],
         resposta=r"letra|fonte|tamanho"),
    caso("caso-letra-neta", "guia", "Minha neta mexeu e a letra ficou pequena, como eu volto ao normal?",
         [("ajuste", "font_scale", "0.8"), ("ajuste", "font_size", "0")], [("ajuste_maior", "font_scale", "0.8")]),
    caso("caso-letra-erra", "guia", "Me mostra como aumentar a letra", LETRA_1, [("ajuste_maior", "font_scale", "1.0")],
         pessoa="erra"),
    # --- brilho (sem o automático, que muda sozinho) ---
    caso("caso-brilho-aumentar", "guia", "Como eu aumento o brilho da tela?",
         [("ajuste", "screen_brightness_mode", "0"), ("ajuste", "screen_brightness", "30")],
         [("ajuste_maior", "screen_brightness", "30")]),
    caso("caso-brilho-sol", "sintoma", "No sol eu não vejo nada na tela do celular",
         [("ajuste", "screen_brightness_mode", "0"), ("ajuste", "screen_brightness", "15")],
         [("ajuste_maior", "screen_brightness", "15")], resposta=r"brilho|clar"),
    caso("caso-brilho-forte", "sintoma", "A tela tá muito clara, tá doendo a vista de noite",
         [("ajuste", "screen_brightness_mode", "0"), ("ajuste", "screen_brightness", "230")],
         [("ajuste_menor", "screen_brightness", "230")], resposta=r"brilho|escur|clar"),
    caso("caso-brilho-diminuir", "guia", "Como deixo a tela menos clara?",
         [("ajuste", "screen_brightness_mode", "0"), ("ajuste", "screen_brightness", "200")],
         [("ajuste_menor", "screen_brightness", "200")]),
    caso("caso-brilho-apagada", "sintoma", "A tela tá quase apagada, mal dá pra ver alguma coisa",
         [("ajuste", "screen_brightness_mode", "0"), ("ajuste", "screen_brightness", "3")],
         [("ajuste_maior", "screen_brightness", "40")], resposta=r"brilho|clar"),
    # --- modo escuro ---
    caso("caso-escuro-ligar", "guia", "Como eu coloco o celular no modo escuro?", [("noturno", "no")],
         [("ajuste", "ui_night_mode", "2")]),
    caso("caso-escuro-desligar", "guia", "Como eu tiro o modo escuro? Quero o fundo branco de novo", [("noturno", "yes")],
         [("ajuste", "ui_night_mode", "1")]),
    caso("caso-escuro-preto", "sintoma", "O celular ficou com as telas todas de fundo preto, como volta ao normal?",
         [("noturno", "yes")], [("ajuste", "ui_night_mode", "1")], resposta=r"escur|clar"),
    caso("caso-escuro-vista", "sintoma", "O fundo branco do celular cansa minha vista de noite", [("noturno", "no")],
         [("ajuste", "ui_night_mode", "2")], resposta=r"escur"),
    # --- rotação ---
    caso("caso-girar-travar", "guia", "Como eu travo a tela pra ela não ficar virando?",
         [("ajuste", "accelerometer_rotation", "1")], [("ajuste", "accelerometer_rotation", "0")]),
    caso("caso-girar-deitado", "sintoma", "Quando eu deito pra ver vídeo a tela fica virando de lado",
         [("ajuste", "accelerometer_rotation", "1")], [("ajuste", "accelerometer_rotation", "0")], resposta=r"gir|vir"),
    caso("caso-girar-ligar", "guia", "Como eu faço a tela virar quando eu viro o celular pra ver vídeo?",
         [("ajuste", "accelerometer_rotation", "0")], [("ajuste", "accelerometer_rotation", "1")]),
    caso("caso-girar-nao-vira", "sintoma", "Eu viro o celular e a tela não vira pra ver o vídeo grande",
         [("ajuste", "accelerometer_rotation", "0")], [("ajuste", "accelerometer_rotation", "1")], resposta=r"gir|vir"),
    # --- tempo da tela ---
    caso("caso-tela-demorar", "guia", "Como eu faço a tela demorar mais pra apagar?",
         [("ajuste", "screen_off_timeout", "15000")], [("ajuste_maior", "screen_off_timeout", "15000")]),
    caso("caso-tela-receita", "sintoma", "A tela apaga enquanto eu tô lendo a receita no celular",
         [("ajuste", "screen_off_timeout", "30000")], [("ajuste_maior", "screen_off_timeout", "30000")],
         resposta=r"tempo|apag|minuto|segundo"),
    caso("caso-tela-rapida", "guia", "Como eu faço a tela apagar mais rápido quando eu largo o celular?",
         [("ajuste", "screen_off_timeout", "600000")], [("ajuste_menor", "screen_off_timeout", "600000")]),
    caso("caso-tela-acesa", "sintoma", "A tela fica acesa muito tempo depois que eu largo o celular",
         [("ajuste", "screen_off_timeout", "600000")], [("ajuste_menor", "screen_off_timeout", "600000")],
         resposta=r"tempo|apag|minuto|segundo"),
    # --- Não perturbar ---
    caso("caso-dnd-ligar", "guia", "Como eu ligo o não perturbe?", [("nao_perturbe", "off")], [("nao_perturbe", True)]),
    caso("caso-dnd-desligar", "guia", "Como eu desligo o não perturbe?", [("nao_perturbe", "on")], [("nao_perturbe", False)]),
    caso("caso-dnd-reuniao", "guia", "Vou entrar numa reunião, como eu deixo o celular sem tocar?",
         [("nao_perturbe", "off"), ("modo_som", "som")], [("silencio",)]),
    caso("caso-dnd-ligacao", "sintoma", "Ninguém consegue me ligar, o celular não toca quando ligam",
         [("nao_perturbe", "on"), ("modo_som", "som")], [("nao_perturbe", False)], resposta=r"perturb"),
    caso("caso-dnd-whatsapp", "sintoma", "O WhatsApp não apita mais quando chega mensagem",
         [("nao_perturbe", "on"), ("modo_som", "som")], [("nao_perturbe", False)], resposta=r"perturb|som"),
    # --- modo de som ---
    caso("caso-som-vibrar", "guia", "Como eu coloco o celular só pra vibrar?", [("modo_som", "som")],
         [("modo_som", "vibrar")]),
    caso("caso-som-silencioso", "sintoma", "O celular tá no silencioso e eu não sei tirar", [("modo_som", "mudo")],
         [("modo_som", "som")], resposta=r"som|silenci|mudo"),
    caso("caso-som-mudo", "guia", "Como eu deixo o celular no mudo?", [("modo_som", "som")], [("modo_som", "mudo")]),
    caso("caso-som-so-vibra", "sintoma", "Quando me ligam o celular só vibra, não toca", [("modo_som", "vibrar")],
         [("modo_som", "som")], resposta=r"som|vibr"),
    caso("caso-som-missa", "guia", "Vou pra missa, como eu deixo o celular sem barulho mas vibrando?",
         [("modo_som", "som")], [("modo_som", "vibrar")]),
    # --- volume do toque (no modo Som: em Vibrar a barra fica travada) ---
    caso("caso-toque-aumentar", "guia", "Como eu aumento o volume do celular quando me ligam?",
         [("modo_som", "som"), ("volume", 2, 2)], [("volume_min", 2, 6)]),
    caso("caso-toque-baixo", "sintoma", "Quase não escuto o celular tocar", [("modo_som", "som"), ("volume", 2, 1)],
         [("volume_min", 2, 5)], resposta=r"volume|toque|som"),
    caso("caso-toque-abaixar", "guia", "Como eu abaixo o volume do toque? Tá muito alto",
         [("modo_som", "som"), ("volume", 2, 15)], [("volume_max", 2, 12)]),
    caso("caso-toque-susto", "sintoma", "O celular toca alto demais e me dá susto", [("modo_som", "som"), ("volume", 2, 15)],
         [("volume_max", 2, 12)], resposta=r"volume|toque|som"),
    # --- volume da mídia ---
    caso("caso-midia-videos", "sintoma", "Os vídeos do WhatsApp não têm som nenhum", [("volume", 3, 0)],
         [("volume_min", 3, 3)], resposta=r"volume|som|m[ií]dia"),
    caso("caso-midia-aumentar", "guia", "Como eu aumento o som dos vídeos?", [("volume", 3, 3)], [("volume_min", 3, 6)]),
    caso("caso-midia-alto", "sintoma", "O som dos vídeos tá alto demais", [("volume", 3, 15)], [("volume_max", 3, 12)],
         resposta=r"volume|som|m[ií]dia"),
    caso("caso-midia-abaixar", "guia", "Como eu abaixo o volume das músicas?", [("volume", 3, 14)],
         [("volume_max", 3, 11)]),
    caso("caso-midia-youtube", "sintoma", "O YouTube tá sem som", [("volume", 3, 0)], [("volume_min", 3, 3)],
         resposta=r"volume|som|m[ií]dia"),
    # --- lanterna ---
    caso("caso-lanterna-acender", "guia", "Como eu acendo a luz do celular? Tá escuro aqui", [("lanterna",)],
         [("lanterna", True)]),
    caso("caso-lanterna-chave", "sintoma", "Preciso de luz pra achar a chave no escuro, o celular tem lanterna?",
         [("lanterna",)], [("lanterna", True)], resposta=r"lanterna|luz"),
    caso("caso-lanterna-erra", "guia", "Me ensina a ligar a lanterna", [("lanterna",)], [("lanterna", True)], pessoa="erra"),
    # --- localização ---
    caso("caso-local-desligar", "guia", "Como eu desligo a localização do celular?", [("localizacao", "on")],
         [("localizacao", False)]),
    caso("caso-local-mapa", "sintoma", "O mapa não acha onde eu estou", [("localizacao", "off")],
         [("localizacao", True)], resposta=r"locali|gps"),
    caso("caso-local-gps", "guia", "Como eu ligo o GPS?", [("localizacao", "off")], [("localizacao", True)]),
    # --- avisos: o Não perturbar desligado, mas o celular em Vibrar com o toque no zero ---
    caso("caso-avisos-vibrar", "sintoma", "Não escuto quando chega mensagem",
         [("nao_perturbe", "off"), ("modo_som", "vibrar"), ("volume", 2, 0)], [("modo_som", "som"), ("volume_min", 2, 3)],
         resposta=r"som|toque|vibr|volume"),
]

assert len(CASOS) == 50 and len({c["id"] for c in CASOS}) == 50
