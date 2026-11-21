"""O celular do simulador com as telas de verdade (2026-11-18): as páginas que a varredura gravou do S23+ (tests/telas/,
`tests/varredura.py`), na leitura do próprio app, e o que um toque faz nelas.

Cada página é uma lista de telas, do alto ao fim (uma por rolagem). As que mudam com o estado do aparelho (o Não
perturbar, o modo de som, o volume) foram gravadas em cada estado (`estado-*`), e a tela vem da gravação que bate com
o estado de agora. Um toque:

- numa linha de menu abre a página que a varredura achou atrás dela (`indice.json`, mais `LIGACOES`); uma linha que a
  varredura não abriu não faz nada (a linha do tempo marca);
- na seta «Navegar», volta;
- na chave do Não perturbar, numa opção do modo de som ou numa barra de volume muda o estado (e a tela é a gravada
  nesse estado); numa outra chave, só a vira na tela;
- no ícone das Configurações da tela inicial, abre as Configurações.

O texto que o executor lê sai de `device.elements_of` e `device.render`, como no app. A mesma interface do `Celular`
montado à mão (`tests/simulador.py`): `ler`, `fatos`, `tocar`, `voltar`, `abrir_pagina`, `rolar`, `itens`.
"""

import copy
import gzip
import json
import os
import re
import unicodedata

from lmphone import device as dv
from lmphone import executor as ex

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telas")
# O botão da faixa abre estas páginas (as gravadas pela varredura com o mesmo atalho, `proxy.SETTINGS`).
BOTAO = {"do_not_disturb": "abre-do-not-disturb", "sound": "abre-sound", "notifications": "notificacoes",
         "display": "abre-display", "wifi": "abre-wifi", "bluetooth": "abre-bluetooth", "accessibility": "abre-accessibility"}
# Ligações que a varredura não fez sozinha (a mesma página gravada por dois caminhos): (página, linha) -> página.
LIGACOES = {("painel-atalhos", "Configurações"): "inicio", ("painel-atalhos", "Expandir"): "painel-atalhos-expandido",
            ("painel-atalhos-expandido", "Configurações"): "inicio", ("painel-notificacoes", "Config. notificação"): "notificacoes",
            ("inicio", "Sons e vibração"): "abre-sound", ("abre-sound", "Volume"): "sons-volume",
            ("notificacoes", "Não perturbar"): "abre-do-not-disturb", ("inicio", "Visor"): "abre-display",
            ("inicio", "Acessibilidade"): "abre-accessibility"}
# As páginas gravadas em cada estado: o nome da gravação para o estado de agora (None: a gravação de sempre).
MODOS = {"som": "som-toque-7", "vibrar": "vibrar", "mudo": "silenciar"}
VARIANTES = {
    "abre-do-not-disturb": lambda e: "estado-dnd-ligado-abre-do-not-disturb" if e["dnd"] else None,
    "abre-sound": lambda e: f"estado-{MODOS[e['modo']]}-abre-sound",
    "sons-volume": lambda e: f"estado-{MODOS[e['modo']]}-sons-volume",
}
MODO_DA_OPCAO = {"som": "som", "vibrar": "vibrar", "silenciar": "mudo", "mudo": "mudo"}
BARRAS = {"toque": "toque", "toque e notificacoes": "toque", "midia": "midia", "notificacoes": "notificacao"}
VOLTAR = ("navegar", "navegar para cima", "voltar")
# As chaves que são um fato do aparelho: a tela mostra o estado (numa página sem a gravação nesse estado).
CHAVES = {"nao perturbar": "dnd", "nao perturbe": "dnd", "rotacao autom": "girar", "lanterna": "lanterna"}  # o começo do título
# Páginas em que a chave do alto (o "Ativado" sem título) é um fato: a localização.
CHAVE_DA_PAGINA = {"abre-location": "local", "local": "local"}
# Opções que são um fato: o modo escuro (Claro e Escuro no Visor).
OPCOES_ESTADO = {"claro": ("escuro", False), "escuro": ("escuro", True)}


# O bloco do modo de som no painel de atalhos: o nome diz o modo seguinte, e um toque passa a ele (Som, Vibrar, Silenciar,
# Som). Só o nome com o celular em Vibrar foi visto («Alternar para silenciar», 2026-11-19); os outros dois são supostos.
BLOCO_DO_SOM = {"som": "Alternar para vibrar", "vibrar": "Alternar para silenciar", "mudo": "Alternar para som"}
SEGUINTE = {"som": "vibrar", "vibrar": "mudo", "mudo": "som"}
# A varredura gravou só a primeira tela do painel de atalhos aberto; o bloco «Lanterna» fica abaixo da dobra no S23+
# (2026-11-19). A segunda tela é feita à mão: os blocos sobem ROLA_PAINEL px e entra uma linha com a lanterna.
ROLA_PAINEL = 700
TOPO_DO_PAINEL = 342  # o que sobe acima disto fica sob o cabeçalho (relógio, Editar, Configurações)


def _mover(no, dy):
    for n, _ in _nos(no):
        b = n.get("boundsInScreen")
        if b:
            b["top"] += dy
            b["bottom"] += dy


def painel_rolado(tela):
    """A segunda tela do painel de atalhos aberto, aproximada (ver ROLA_PAINEL)."""
    t = copy.deepcopy(tela)
    lista = next(n for n, _ in _nos(t["a11y_tree"]) if _cls(n) == "ScrollView")
    for filho in lista.get("children") or []:
        _mover(filho, -ROLA_PAINEL)

    def podar(no):  # o que subiu para baixo do cabeçalho sai da árvore
        no["children"] = [f for f in no.get("children") or [] if _limites(f)[1] >= TOPO_DO_PAINEL]
        for f in no["children"]:
            podar(f)
    for filho in lista.get("children") or []:
        podar(filho)
    lista["children"] = [f for f in lista.get("children") or [] if _limites(f)[3] > TOPO_DO_PAINEL]
    # A lanterna: uma cópia do último bloco da coluna da esquerda, uma linha abaixo dele.
    blocos = [(n, ps) for n, ps in _nos(lista) if _cls(n) == "Button" and n.get("isCheckable") and _texto(n)]
    modelo, pais = max(blocos, key=lambda b: (_limites(b[0])[1], -_limites(b[0])[0]))
    modelo, pais = min(((n, ps) for n, ps in blocos if _limites(n)[1] == _limites(modelo)[1]), key=lambda b: _limites(b[0])[0])
    caixa = pais[-1] if _limites(pais[-1]) == _limites(modelo) else modelo
    novo = copy.deepcopy(caixa)
    _mover(novo, _limites(modelo)[3] - _limites(modelo)[1] + 40)
    for n, _ in _nos(novo):
        if _texto(n) == _texto(modelo):
            n["contentDescription"], n["text"] = "Lanterna", ""
            n["isChecked"] = False
    dono = next(ps[-1] for n, ps in _nos(t["a11y_tree"]) if n is caixa)
    dono["children"].append(novo)
    return t


def chave_do_estado(titulo):
    return next((estado for comeco, estado in CHAVES.items() if plain(titulo).startswith(comeco)), None)


# A letra da One UI 9: a escala de cada nível da barra de «Tamanho e estilo da fonte» (o nível 2 é o padrão, 1.0),
# medida no S23+ tocando em «Reduzir» a partir do máximo (2026-11-19; o de cima não foi lido, 2.0 é suposto).
ESCALAS = [0.8, 0.9, 1.0, 1.08, 1.15, 1.3, 1.5, 1.7, 2.0]
FONTE_PADRAO = 1.0
# As opções de «Duração da luz de fundo», em segundos: a árvore não mostra qual está escolhida (nenhuma marca nela).
TEMPOS_DA_TELA = {"15 segundos": 15, "30 segundos": 30, "1 minuto": 60, "2 minutos": 120, "5 minutos": 300, "10 minutos": 600}
FONTE_BOTOES = {"aumentar tam. da fonte": 1, "reduzir tam. da fonte": -1}


def nivel_da_fonte(escala):
    # Entre dois níveis, o de baixo (de 0.85, um «Aumentar» a leva a 0.9: tests/gravacoes/sint-letra-1.jsonl).
    return min(range(len(ESCALAS)), key=lambda n: (round(abs(ESCALAS[n] - escala), 6), n))


def plain(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)).casefold().strip()


class Item:
    """O que a pessoa toca (a mesma forma do `Item` do simulador, para a faixa e para os erros dos cenários)."""

    def __init__(self, cls, texto, limites, nome=""):
        self.cls, self.texto, self.limites, self.nome = cls, texto, tuple(limites), nome


def _limites(no):
    b = no.get("boundsInScreen") or {}
    return (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))


def _nos(no, pais=()):
    yield no, pais
    for filho in no.get("children") or []:
        yield from _nos(filho, pais + (no,))


def _cls(no):
    return (no.get("className") or "").split(".")[-1]


def _texto(no):
    return no.get("text") or no.get("contentDescription") or ""


def _titulo(no):
    """O título de uma linha: o `android:id/title` dela, ou o primeiro texto de dentro."""
    textos = [(n.get("resourceId") or "", n.get("text") or "") for n, _ in _nos(no) if n.get("text")]
    return next((t for i, t in textos if i.endswith("id/title") or i.endswith("_text")), textos[0][1] if textos else "")


LISTAS = ("RecyclerView", "ScrollView", "ListView", "NestedScrollView")


def _tem_titulo(no):
    return any((n.get("resourceId") or "").endswith(("id/title", "_text")) and n.get("text") for n, _ in _nos(no))


def _linha(no, pais):
    """A linha de um controle: ele mesmo ou o ancestral mais próximo com um título dentro (sem subir além da lista);
    sem nenhum, o tocável mais próximo."""
    for p in (no,) + tuple(reversed(pais)):
        if _cls(p) in LISTAS:
            break
        if _tem_titulo(p):
            return p
    return next((p for p in (no,) + tuple(reversed(pais)) if p.get("isClickable")), no)


def slug(caminho):
    """O nome de uma página na varredura (`tests.varredura.slug`)."""
    texto = "-".join(plain(p) for p in caminho) or "inicio"
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:120]


POR_BOTAO = {slug([chave]): chave for chave in ex.SETTINGS_PAGES}  # "do-not-disturb" -> "do_not_disturb"


def carregar(nome):
    with gzip.open(os.path.join(PASTA, nome + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


# As telas gravadas no S23+ têm dados reais e não vão ao repositório público: sem elas, os testes que as usam são pulados.
TEM_TELAS = os.path.isdir(PASTA)


def existe(nome):
    return os.path.exists(os.path.join(PASTA, nome + ".json.gz"))


class CelularReal:
    def __init__(self, sim, dnd=True, modo="vibrar", toque=0, midia=0, atraso_tela=0.4, atraso_pagina=1.2,
                 pagina_abre=True, comeco="launcher", fonte=1.0, brilho=35, girar=True, tela_apaga=15, brilho_auto=True,
                 escuro=True, local=True, lanterna=False):
        self.sim = sim
        with open(os.path.join(PASTA, "indice.json"), encoding="utf-8") as f:
            self.indice = json.load(f)
        self.estado = {"dnd": dnd, "modo": modo, "toque": toque, "midia": midia, "notificacao": toque}
        self.chaves = {}  # (página, título) -> marcado: as chaves que o simulador não conhece, viradas na tela
        self.opcoes = {}  # página -> o título da opção escolhida num grupo de opções (fora o modo de som)
        self.estado.update(fonte=fonte, brilho=brilho, tela_apaga=tela_apaga, girar=girar, brilho_auto=brilho_auto,
                           escuro=escuro, local=local, lanterna=lanterna)
        self.pilha = [[comeco, 0]]  # [página, rolagem]
        self.atraso_tela, self.atraso_pagina, self.pagina_abre = atraso_tela, atraso_pagina, pagina_abre
        self.cache = {}
        self.fora = []  # linhas tocadas que a varredura não abriu
        self.vistas = [(float("-inf"), self.tela())]

    # --- as gravações ---
    def gravacao(self, nome):
        variante = VARIANTES.get(nome, lambda e: None)(self.estado)
        nome = variante if variante and existe(variante) else nome
        if nome not in self.cache:
            self.cache[nome] = carregar(nome) if existe(nome) else None
            if nome == "painel-atalhos-expandido" and self.cache[nome] and len(self.cache[nome]["telas"]) == 1:
                self.cache[nome]["telas"].append(painel_rolado(self.cache[nome]["telas"][0]))
        return self.cache[nome]

    def arvore(self):
        nome, rolagem = self.pilha[-1]
        pagina = self.gravacao(nome)
        if pagina is None:
            return {"a11y_tree": {"children": []}, "phone_state": {"currentApp": "?", "packageName": "?"},
                    "device_context": {"screen_bounds": {"width": 1080, "height": 2340}}}
        arvore = copy.deepcopy(pagina["telas"][min(rolagem, len(pagina["telas"]) - 1)])
        for no, pais in _nos(arvore["a11y_tree"]):
            if no.get("isCheckable") and _cls(no) != "RadioButton":
                titulo = _titulo(_linha(no, pais)) or _texto(no)
                if nome in CHAVE_DA_PAGINA and plain(_texto(no)) in ("ativado", "desativado"):
                    ligado = self.estado[CHAVE_DA_PAGINA[nome]]
                    no["isChecked"], no["text"] = ligado, "Ativado" if ligado else "Desativado"
                    continue
                marcado = self.estado[chave_do_estado(titulo)] if chave_do_estado(titulo) else self.chaves.get((nome, titulo))
                if marcado is not None:
                    no["isChecked"] = marcado
            elif _cls(no) == "RadioButton" and plain(_titulo(_linha(no, pais))) in OPCOES_ESTADO:
                chave, valor = OPCOES_ESTADO[plain(_titulo(_linha(no, pais)))]
                no["isChecked"] = self.estado[chave] == valor
            elif _cls(no) == "RadioButton" and nome in self.opcoes:
                no["isChecked"] = plain(_titulo(_linha(no, pais))) == plain(self.opcoes[nome])
            elif (no.get("resourceId") or "").endswith("id/font_size_seek_bar"):
                no["contentDescription"] = str(nivel_da_fonte(self.estado["fonte"]))
            if plain(_texto(no)).startswith("alternar para"):
                no["contentDescription"], no["text"] = BLOCO_DO_SOM[self.estado["modo"]], ""
                no["isChecked"] = self.estado["modo"] != "som"
            elif _cls(no) == "SeekBar" and (no.get("contentDescription") or "").isdigit():
                # A barra de volume traz o nível (de 0 a 15) na descrição; o simulador guarda o volume em %.
                chave = BARRAS.get(plain(_titulo(_linha(no, pais))))
                if chave in ("toque", "notificacao", "midia"):
                    no["contentDescription"] = str(round(self.estado[chave] * 15 / 100))
        return arvore

    # --- o que o executor lê ---
    def tela(self):
        arvore = self.arvore()
        return dv.render(arvore, dv.elements_of(arvore))

    def mudou(self):
        self.vistas.append((self.sim.relogio.agora + self.atraso_tela, self.tela()))

    def ler(self):
        agora = self.sim.relogio.agora
        return [texto for quando, texto in self.vistas if quando <= agora][-1]

    def fatos(self):
        base = dict((self.gravacao("abre-sound") or {}).get("fatos") or {})
        e = self.estado
        base.update(do_not_disturb=e["dnd"], sound_mode=e["modo"], ring_volume=e["toque"], media_volume=e["midia"],
                    media_playing="nothing", font_scale=e["fonte"], brightness=e["brilho"], auto_brightness=e["brilho_auto"],
                    dark_mode=e["escuro"], location=e["local"],
                    auto_rotate=e["girar"],
                    screen_timeout=e["tela_apaga"])
        return base

    def itens(self):
        """Os elementos com texto da tela de agora (para os erros dos cenários: "toca" num texto)."""
        return [Item(_cls(no), _texto(no), _limites(no), nome=_texto(no))
                for no, _ in _nos(self.arvore()["a11y_tree"]) if _texto(no)]

    # --- o que a pessoa faz ---
    def tocar(self, x, y):
        """Um toque em (x, y): o tocável mais fundo nesse ponto (uma barra também conta). Devolve (o que foi tocado,
        os limites dele depois): o aviso do toque traz o controle já no lugar novo, como no aparelho."""
        nome = self.pilha[-1][0]
        alvo, pais = None, ()
        for no, ps in _nos(self.arvore()["a11y_tree"]):
            x1, y1, x2, y2 = _limites(no)
            if (no.get("isClickable") or no.get("isCheckable") or _cls(no) == "SeekBar") and x1 <= x <= x2 and y1 <= y <= y2:
                alvo, pais = no, ps
        if alvo is None:
            return None, None
        linha = _linha(alvo, pais)
        titulo, cls = _titulo(linha), _cls(alvo)
        dentro = [n for n, _ in _nos(linha)]
        # Sem título, o nome que a pessoa vê: a descrição do controle ou de algo dentro dele (o «Expandir» do painel de
        # atalhos fica numa View sem nome dentro da tocável; com o título vazio, a página seguinte era a inicial).
        titulo = titulo or _texto(alvo) or next((_texto(n) for n in dentro if _texto(n)), "")
        aviso = Item(cls, titulo or _texto(alvo), _limites(alvo), nome=titulo or _texto(alvo))
        marca = (alvo.get("resourceId"), cls, titulo)  # o mesmo controle na tela de depois
        if plain(_texto(alvo)) in VOLTAR:
            self.voltar()
        elif plain(_texto(alvo)) in FONTE_BOTOES:
            passo = FONTE_BOTOES[plain(_texto(alvo))]
            self.estado["fonte"] = ESCALAS[max(0, min(len(ESCALAS) - 1, nivel_da_fonte(self.estado["fonte"]) + passo))]
        elif any(_cls(n) == "RadioButton" for n in dentro) and plain(titulo) in OPCOES_ESTADO:
            chave, valor = OPCOES_ESTADO[plain(titulo)]
            self.estado[chave] = valor
        elif any(_cls(n) == "RadioButton" for n in dentro):
            if plain(titulo) in MODO_DA_OPCAO:
                self.modo(MODO_DA_OPCAO[plain(titulo)])
            else:
                self.opcoes[nome] = titulo  # um grupo de opções (a duração da luz de fundo): a tocada fica marcada
        elif cls == "SeekBar" and (alvo.get("resourceId") or "").endswith("id/font_size_seek_bar"):
            x1, _, x2, _ = _limites(alvo)
            self.estado["fonte"] = ESCALAS[max(0, min(len(ESCALAS) - 1, round((x - x1) * (len(ESCALAS) - 1) / max(1, x2 - x1))))]
        elif cls == "SeekBar" and ("brightness" in (alvo.get("resourceId") or "") or plain(_texto(alvo)).startswith("brilho")):
            x1, _, x2, _ = _limites(alvo)
            self.estado["brilho"] = max(0, min(100, round((x - x1) * 100 / max(1, x2 - x1))))
        elif cls == "SeekBar" and plain(_texto(alvo)).startswith("volume da midia"):  # a barra do painel de atalhos
            self.nivel("midia", x, _limites(alvo))
        elif plain(_texto(alvo)).startswith("alternar para"):
            self.modo(SEGUINTE[self.estado["modo"]])
        elif cls == "SeekBar":
            self.nivel(BARRAS.get(plain(titulo), "toque"), x, _limites(alvo))
        elif any(_cls(n) == "SeekBar" for n in dentro):
            return aviso, aviso.limites  # o título da barra: nada acontece
        elif any(n.get("isCheckable") for n in dentro):
            chave = next(n for n in dentro if n.get("isCheckable"))
            rotulo = titulo or _texto(chave)  # os blocos do painel de atalhos têm o nome só na descrição
            if nome in CHAVE_DA_PAGINA and plain(_texto(chave)) in ("ativado", "desativado"):
                self.estado[CHAVE_DA_PAGINA[nome]] = not self.estado[CHAVE_DA_PAGINA[nome]]
            elif chave_do_estado(rotulo):
                self.estado[chave_do_estado(rotulo)] = not self.estado[chave_do_estado(rotulo)]
            else:
                self.chaves[(nome, titulo)] = not self.chaves.get((nome, titulo), chave.get("isChecked"))
        elif titulo in TEMPOS_DA_TELA:
            self.estado["tela_apaga"] = TEMPOS_DA_TELA[titulo]
        elif plain(titulo) in ("config.", "configuracoes") and nome == "launcher":
            self.abrir("inicio")
        else:
            filho = LIGACOES.get((nome, titulo))
            caminho = (self.indice.get(nome) or {}).get("caminho")
            if nome.startswith("abre-") and nome[len("abre-"):] in POR_BOTAO:
                caminho = ex.SETTINGS_WAY.get(POR_BOTAO[nome[len("abre-"):]], caminho)  # a mesma página, pelos menus
            if filho is None and titulo and caminho is not None and existe(slug(caminho + [titulo])):
                filho = slug(caminho + [titulo])  # o nome que a varredura dá à página atrás da linha
            if filho:
                self.abrir(filho)
            else:
                self.fora.append((nome, titulo))
                self.sim.marcar(f"celular: «{titulo}» abre uma página que a varredura não gravou")
                return aviso, aviso.limites
        self.mudou()
        if self.pilha[-1][0] != nome:
            return aviso, aviso.limites
        for no, ps in _nos(self.arvore()["a11y_tree"]):
            if (no.get("resourceId"), _cls(no), _titulo(_linha(no, ps))) == marca:
                return aviso, _limites(no)
        return aviso, aviso.limites

    def modo(self, modo):
        self.estado["modo"] = modo
        if modo == "som" and self.estado["toque"] == 0:
            # 1 de 15 (7%), como o S23+ volta do mudo (tests/gravacoes/celular-avisos-3.jsonl): ainda não dá para ouvir.
            self.estado["toque"] = self.estado["notificacao"] = 7
        elif modo != "som":
            self.estado["toque"] = self.estado["notificacao"] = 0

    def nivel(self, chave, x, limites):
        x1, _, x2, _ = limites
        self.estado[chave] = max(0, min(100, round((x - x1) * 100 / max(1, x2 - x1))))
        if chave == "toque" and self.estado[chave] > 0 and self.estado["modo"] != "som":
            self.estado["modo"] = "som"

    def abrir(self, pagina):
        self.pilha = self.pilha + [[pagina, 0]]
        self.mudou()

    def voltar(self, x=0, y=0):
        self.pilha = self.pilha[:-1] or [["launcher", 0]]
        self.mudou()

    def puxar(self, lado="meio"):
        """A pessoa puxa a barra do alto da tela para baixo. Na One UI 9 os painéis são separados (2026-11-19, no S23+):
        pelo lado direito abrem os atalhos; pelo meio, as notificações, e puxar de novo pelo meio não muda nada. Voltar
        fecha."""
        nome = self.pilha[-1][0]
        if nome.startswith("painel-atalhos"):
            return
        if lado == "direita":
            if nome == "painel-notificacoes":
                self.pilha[-1] = ["painel-atalhos", 0]
            else:
                self.pilha = self.pilha + [["painel-atalhos", 0]]
        elif nome != "painel-notificacoes":
            self.pilha = self.pilha + [["painel-notificacoes", 0]]
        else:
            return
        self.mudou()

    def rolar(self):
        """A pessoa arrasta a tela para cima: a próxima tela gravada da página (a última fica)."""
        pagina = self.gravacao(self.pilha[-1][0])
        if pagina and self.pilha[-1][1] < len(pagina["telas"]) - 1:
            self.pilha[-1][1] += 1
            self.mudou()

    def abrir_pagina(self, chave):
        """O botão da faixa: a página abre numa tarefa limpa depois de `atraso_pagina` (com `pagina_abre` False, não abre)."""
        pagina = BOTAO.get(chave)
        if pagina and self.pagina_abre:
            def ir():
                self.pilha = [[pagina, 0]]
                self.mudou()
            self.sim.depois(self.atraso_pagina, ir, f"celular: abriu a página {pagina}")
