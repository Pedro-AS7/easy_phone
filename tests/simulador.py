"""O app da loja sem o celular: as rodadas que o Pedro faz no S23+, em código, num relógio de mentira.

Um celular de mentira (as páginas das Configurações da One UI 9 em português, montadas à mão a partir dos registros das
rodadas), a faixa com os atrasos dela (o aviso do toque chega depois do toque; a tela lida fica para trás da de verdade),
uma pessoa que faz o que o guia pede (lê, toca no destaque, aperta o botão da faixa, às vezes erra) e o executor de
verdade no meio, no ciclo do `Agent.kt` (passar os toques da faixa, ler a tela até ela parar, decidir, esperar). O
provedor responde por um roteiro: o plano, as ajudas e a conferência final que o cenário traz, com a demora de cada uma.

Um guia de dois minutos roda em menos de um segundo, sem custo e sem o aparelho. Cada cenário diz o que conferir no
fim (o estado do aparelho, nenhuma ação do agente, nenhuma bronca falsa, quantas vezes o botão apareceu, o tempo).

Os cenários `real-*` usam as telas de verdade do S23+ (a varredura, tests/telas/; tests/celular_real.py) no lugar das
montadas à mão. Com `--provedor real`, o Haiku de verdade faz o plano, as ajudas e a conferência (custa uns US$ 0,003 por
guia, e o plano muda de uma rodada para outra: rode várias vezes); com `--escolha`, o modelo de escolha de verdade (o
servidor dos modelos pequenos na porta 8788). Cada rodada é gravada no formato das gravações do celular (`gravacao`;
`--gravar PASTA`), que tests/gravacao.py repete e compara.

O que fica fora (continua nas rodadas no aparelho): o Android de verdade (a tarefa das Configurações, a acessibilidade,
os tempos da One UI), a faixa de verdade (`Overlay.kt`) e as telas que não foram gravadas.

    .venv/bin/python -m tests.simulador                  # todos os cenários, com o que deu errado em cada um
    .venv/bin/python -m tests.simulador sint-avisos -v   # um cenário, com a linha do tempo
    .venv/bin/python -m tests.simulador real-avisos --provedor real --vezes 5 --escolha
"""

import argparse
import copy
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from dataclasses import dataclass
from unittest import mock

from lmphone import executor as ex
from lmphone import trilha
from lmphone.device import parse_call

LARGURA, ALTURA = 1080, 2340
_PACOTE = re.compile(r"• \*\*App:\*\* .*?\(?([\w.]+)\)?$", re.M)  # o `APP` do Agent.kt (o pacote da tela)
# Os tempos do ciclo do app (service.py e Agent.kt): uma leitura da tela, a espera entre duas leituras para ver se ela
# parou, o limite dessa espera e a pausa depois de uma ação.
LEITURA, STILL_GAP, STILL_LIMIT, AFTER_ACTION = 0.1, 0.15, 1.5, 0.2
LIMITE = 300  # segundos de relógio de mentira por rodada
PICK_SPLIT = 0.8  # o do proxy e do Agent.kt
MAX_VOLTAS = 700  # como OWNER_WAIT_LIMIT + MAX_STEPS do serviço

# Falas que dizem à pessoa que ela errou: numa rodada sem erro dela, nenhuma pode aparecer.
# O guia pede para voltar sem destaque ("toque na setinha de voltar"): a pessoa aperta Voltar (como tests/pessoa_loja.py).
VOLTAR_FALA = re.compile(r"\b(voltar|volte)\b.*\b(setinha|seta|bot[aã]o de voltar)|\b(setinha|seta)\b.*\bvoltar\b", re.I)
BRONCAS = ("Esse foi o «", "Esse toque foi fora do destaque", "Opa, a tela mudou", "sem querer")


class Relogio:
    """O `time` do módulo do executor: só o `monotonic`, que anda quando o simulador manda."""

    def __init__(self):
        self.agora = 1000.0
        self.gravar = None  # a gravação da rodada (Simulacao.gravar), no formato do Gravacao.kt

    def monotonic(self):
        trilha._event({"cb": "clock", "ret": self.agora})  # com o gravador de trilhas ligado, o Kotlin lê o mesmo
        if self.gravar:
            self.gravar("cb", cb="clock", ret=self.agora)
        return self.agora


@dataclass
class Item:
    """Um elemento da tela. `toque` é o que um toque nele faz (None: o toque passa para o de baixo); `chave` acha o mesmo
    controle na tela de depois do toque (o aviso do toque traz os limites dele já no lugar novo, como no aparelho)."""
    cls: str
    texto: str
    limites: tuple
    marcado: object = None
    id: str = ""
    toque: object = None
    chave: str = ""
    nome: str = ""  # o texto do aviso do toque (uma linha de menu manda o título dela)


def renderizar(app, pacote, itens):
    """A tela no texto do Portal, que o executor lê."""
    linhas = [f"• **App:** {app} ({pacote})", '1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)']
    for n, item in enumerate(itens, 2):
        corpo = ", ".join(f'"{v}"' for v in (item.id, item.texto) if v) or f'"android.widget.{item.cls}"'
        marca = f" ; isChecked={item.marcado}" if item.marcado is not None else ""
        x1, y1, x2, y2 = item.limites
        linhas.append(f"{n}. {item.cls}: {corpo}{marca} - ({x1},{y1},{x2},{y2})")
    return "\n".join(linhas)


class Celular:
    """As Configurações que os sintomas de som usam. O estado muda na hora do toque; a tela lida mostra a mudança
    `atraso_tela` segundos depois (2026-11-18: 3 s depois do toque, a leitura ainda era a de antes)."""

    PAGINAS = {"do_not_disturb": "nao_perturbar", "sound": "sons", "notifications": "notificacoes"}
    APPS = {"inicio": ("One UI Home", "com.sec.android.app.launcher")}

    def __init__(self, sim, dnd=True, modo="vibrar", toque=0, atraso_tela=0.4, atraso_pagina=1.2, pagina_abre=True):
        self.sim = sim
        self.estado = {"dnd": dnd, "modo": modo, "toque": toque, "midia": 40, "vibrar_ao_tocar": False}
        self.pilha = ["inicio"]
        self.atraso_tela, self.atraso_pagina, self.pagina_abre = atraso_tela, atraso_pagina, pagina_abre
        self.vistas = [(float("-inf"), self.tela())]

    # O que está na tela de verdade (a pessoa vê); a leitura do agente vem de `vistas`, com o atraso.
    def itens(self):
        return getattr(self, "pagina_" + self.pilha[-1])()

    def tela(self):
        app, pacote = self.APPS.get(self.pilha[-1], ("Configurações", "com.android.settings"))
        return renderizar(app, pacote, self.itens())

    def mudou(self):
        self.vistas.append((self.sim.relogio.agora + self.atraso_tela, self.tela()))

    def ler(self):
        agora = self.sim.relogio.agora
        return [texto for quando, texto in self.vistas if quando <= agora][-1]

    def fatos(self):
        e = self.estado
        return {"wifi": "on, not connected", "airplane_mode": False, "bluetooth": False, "do_not_disturb": e["dnd"],
                "location": True, "dark_mode": False, "sound_mode": e["modo"], "media_playing": "nothing",
                "media_volume": e["midia"], "ring_volume": e["toque"], "brightness": 60, "auto_brightness": True,
                "font_scale": 1.0}

    # O que a pessoa faz.
    def tocar(self, x, y):
        """Um toque em (x, y): o controle tocável mais de cima nesse ponto. Devolve (o controle, os limites dele depois)."""
        alvo = next((i for i in reversed(self.itens()) if i.toque and i.limites[0] <= x <= i.limites[2]
                     and i.limites[1] <= y <= i.limites[3]), None)
        if alvo is None:
            return None, None
        alvo.toque(x, y)
        self.mudou()
        depois = next((i for i in self.itens() if alvo.chave and i.chave == alvo.chave), alvo)
        return alvo, depois.limites

    def abrir_pagina(self, chave):
        """O botão da faixa: a página abre numa tarefa limpa (FLAG_ACTIVITY_CLEAR_TASK), depois de `atraso_pagina`.
        Com `pagina_abre` False, como antes da correção, a tela de cima continua (a tarefa das Configurações reaproveitada)."""
        pagina = self.PAGINAS.get(chave)
        if pagina and self.pagina_abre:
            self.sim.depois(self.atraso_pagina, lambda: self.ir([pagina]), f"celular: abriu a página {pagina}")

    def ir(self, pilha):
        self.pilha = pilha
        self.mudou()

    def abrir(self, pagina):
        return lambda x, y: self.ir(self.pilha + [pagina])

    def voltar(self, x=0, y=0):
        self.ir(self.pilha[:-1] or ["inicio"])

    # As páginas.
    def topo(self, titulo):
        return [Item("ImageButton", "Navegar para cima", (0, 130, 150, 250), toque=self.voltar, chave="voltar"),
                Item("TextView", titulo, (169, 150, 760, 228))]

    def menu(self, y, titulo, resumo, toque):
        return [Item("LinearLayout", "", (28, y, 1052, y + 160), toque=toque, chave=titulo, nome=titulo),
                Item("TextView", titulo, (79, y + 30, 900, y + 92), id="android:id/title"),
                Item("TextView", resumo, (79, y + 95, 900, y + 140), id="android:id/summary")]

    def pagina_inicio(self):
        icones = ["Telefone", "Mensagens", "Câmera", "Config."]
        return [Item("TextView", nome, (40 + 260 * k, 1900, 260 + 260 * k, 2100), chave=nome, nome=nome,
                     toque=self.abrir("configuracoes") if nome == "Config." else (lambda x, y: None))
                for k, nome in enumerate(icones)]

    def pagina_configuracoes(self):
        itens = [Item("TextView", "Configurações", (69, 150, 760, 228))]
        linhas = [("Conexões", "Wi-Fi • Bluetooth • Modo avião", None), ("Dispositivos conectados", "Quick Share • Android Auto", None),
                  ("Modos e rotinas", "Modos • Rotinas", None), ("Sons e vibração", "Modo de som • Toque", "sons"),
                  ("Notificações", "Barra de status • Não perturbar", "notificacoes"), ("Visor", "Brilho • Conforto visual", None)]
        for k, (titulo, resumo, pagina) in enumerate(linhas):
            itens += self.menu(330 + 170 * k, titulo, resumo, self.abrir(pagina) if pagina else (lambda x, y: None))
        return itens

    def pagina_sons(self):
        itens = self.topo("Sons e vibração")
        for k, modo in enumerate(("Som", "Vibrar", "Mudo")):
            x = 28 + 341 * k
            escolher = (lambda m: lambda x, y: self.modo(m))(modo.lower())
            itens += [Item("LinearLayout", "", (x, 297, x + 341, 560), toque=escolher, chave="modo " + modo, nome=modo),
                      Item("TextView", modo, (x + 20, 440, x + 321, 500), id="com.android.settings:id/title"),
                      Item("RadioButton", "", (x + 130, 500, x + 210, 560), marcado=self.estado["modo"] == modo.lower(),
                           id="com.android.settings:id/radio")]
        y = 600
        if self.estado["modo"] == "som":
            # Com o modo Som, uma linha nova aparece em cima e a lista desce (2026-11-18: o destaque do «Volume» ficou
            # no lugar velho).
            trocar = lambda x, y: self.estado.update(vibrar_ao_tocar=not self.estado["vibrar_ao_tocar"])
            itens += [Item("LinearLayout", "", (28, y, 1052, y + 160), toque=trocar, chave="linha vibrar",
                           nome="Vibrar ao tocar"),
                      Item("TextView", "Vibrar ao tocar", (79, y + 40, 700, y + 100)),
                      Item("Switch", "", (900, y + 50, 990, y + 106), marcado=self.estado["vibrar_ao_tocar"],
                           chave="vibrar ao tocar", nome="Vibrar ao tocar", toque=trocar)]
            y += 160
        for titulo, resumo, toque in (("Toque", "Over the Horizon", None), ("Som de notificação", "Spaceline", None),
                                      ("Volume", "Toque, mídia, notificações e sistema", self.abrir("volume")),
                                      ("Vibração", "Padrão de chamada", None)):
            itens += self.menu(y, titulo, resumo, toque or (lambda x, y: None))
            y += 170
        return itens

    def modo(self, modo):
        self.estado["modo"] = modo
        if modo == "som" and self.estado["toque"] == 0:
            self.estado["toque"] = 7  # 1 de 15: o Android volta com o toque no mínimo
        elif modo != "som":
            self.estado["toque"] = 0

    def pagina_volume(self):
        itens = self.topo("Volume")
        for k, (nome, chave) in enumerate((("Toque", "toque"), ("Mídia", "midia"))):
            y = 330 + 230 * k
            nivel = self.estado[chave]
            ajustar = (lambda c: lambda x, y: self.nivel(c, x))(chave)
            itens += [Item("TextView", nome, (79, y, 500, y + 60)),
                      Item("SeekBar", nome, (169, y + 80, 1001, y + 170), id="com.android.settings:id/seekbar",
                           toque=ajustar, chave="barra " + nome, nome=f"{nome} {nivel}")]
        return itens

    def nivel(self, chave, x):
        self.estado[chave] = max(0, min(100, round((x - 169) * 100 / (1001 - 169))))
        if chave == "toque" and self.estado[chave] > 0 and self.estado["modo"] != "som":
            self.estado["modo"] = "som"

    def pagina_notificacoes(self):
        itens = self.topo("Notificações")
        y = 330
        for titulo, resumo, toque in (("Notificações de apps", "Escolha os apps", None),
                                      ("Notificações na tela de bloqueio", "Mostrar conteúdo", None),
                                      ("Barra de status", "Ícones de notificação", None),
                                      ("Não perturbar", "Ativado" if self.estado["dnd"] else "Desativado",
                                       self.abrir("nao_perturbar"))):
            itens += self.menu(y, titulo, resumo, toque or (lambda x, y: None))
            y += 170
        return itens

    def pagina_nao_perturbar(self):
        itens = self.topo("Não perturbar")
        top = 419 if self.estado["dnd"] else 481  # desligado, uma linha de texto entra em cima e a chave desce 62 px
        if not self.estado["dnd"]:
            itens.append(Item("TextView", "Silencie sons e avisos quando quiser", (79, 300, 1000, 360)))
        trocar = lambda x, y: self.estado.update(dnd=not self.estado["dnd"])
        itens += [Item("LinearLayout", "", (28, top - 30, 1052, top + 86), toque=trocar, chave="linha dnd",
                       nome="Não perturbar"),
                  Item("TextView", "Não perturbar", (79, top - 5, 412, top + 61), id="android:id/title"),
                  Item("Switch", "Ativado" if self.estado["dnd"] else "Desativado", (900, top, 990, top + 56),
                       marcado=self.estado["dnd"], id="android:id/switch_widget", toque=trocar, chave="chave dnd")]
        y = 700
        for titulo, resumo in (("Agenda", "Dormir • Trabalho"), ("Chamadas e mensagens", "Favoritos"),
                               ("Notificações de apps", "Nenhum app")):
            itens += self.menu(y, titulo, resumo, self.abrir("agenda") if titulo == "Agenda" else (lambda x, y: None))
            y += 170
        return itens

    def pagina_agenda(self):
        itens = self.topo("Agenda")
        for k, (titulo, resumo) in enumerate((("Dormir", "22:00 - 07:00"), ("Trabalho", "Seg a sex"))):
            itens += self.menu(330 + 170 * k, titulo, resumo, lambda x, y: None)
        return itens


class Faixa:
    """A faixa e o `LiveMode`: o que ela mostra à pessoa e os avisos dela ao agente, que chegam `atraso` segundos depois
    do que aconteceu (com a hora do acontecido, como o `poll` do LiveMode.kt)."""

    def __init__(self, sim, atraso=0.3):
        self.sim, self.atraso = sim, atraso
        self.destaque = self.botao = self.gesto = None
        self.fala, self.falas = None, 0
        self.fila = []
        self.touched_at, self.pressed_at = 0.0, None
        self.touched_text = self.touched_text_at = self.touched_box = None

    def aviso(self, tipo, **campos):
        agora = self.sim.relogio.agora
        self.fila.append((agora + self.atraso, tipo, agora, campos))

    def entregar(self):
        agora = self.sim.relogio.agora
        for item in [i for i in self.fila if i[0] <= agora]:
            self.fila.remove(item)
            _, tipo, quando, campos = item
            if tipo in ("toque_tela", "toque"):
                self.touched_at = max(self.touched_at, quando)
            if tipo == "toque" and campos.get("texto"):
                self.touched_text, self.touched_text_at, self.touched_box = campos["texto"], quando, campos["limites"]
            if tipo == "botao_tocado":
                self.pressed_at = quando

    def dizer(self, texto):
        self.fala, self.falas = texto, self.falas + 1


class Pessoa:
    """Lê o que a faixa diz e faz: toca no meio do destaque, aperta o botão, arrasta a tela. `erros` troca o n-ésimo
    gesto dela (contando do 1) por outro: {"toca": texto} toca nesse texto, {"volta": True} volta uma tela."""

    def __init__(self, sim, leitura=1.0, por_letra=0.03, insiste=15.0, erros=None, botao=0.0, erra=False):
        self.sim, self.leitura, self.por_letra, self.insiste, self.botao = sim, leitura, por_letra, insiste, botao
        self.erra, self.errou = erra, False  # "erra": no primeiro destaque, ela volta em vez de tocar (tests/pessoa_loja.py)
        self.erros = dict(erros or {})
        self.visto, self.agendado, self.ultimo, self.feitos = None, None, 0.0, 0

    def olhar(self):
        faixa, agora = self.sim.faixa, self.sim.relogio.agora
        alvo = faixa.destaque or faixa.botao or faixa.gesto
        mostra = (faixa.falas, faixa.destaque, (faixa.botao or {}).get("text"), faixa.gesto)
        if mostra != self.visto:
            self.visto = mostra
            self.agendado = None
            if alvo or VOLTAR_FALA.search(faixa.fala or ""):
                self.agendado = agora + self.leitura + self.por_letra * len(faixa.fala or "") + (
                    self.botao if faixa.botao and not faixa.destaque else 0.0)
                self.sim.depois(self.agendado - agora, self.agir)
        elif alvo and self.agendado is None and agora - self.ultimo > self.insiste:
            self.agendado = agora + 1.0  # nada aconteceu: ela tenta de novo
            self.sim.depois(1.0, self.agir)

    def agir(self):
        agora = self.sim.relogio.agora
        if self.agendado is None or agora + 1e-9 < self.agendado:
            return  # o que a faixa mostrava mudou antes de ela fazer
        self.agendado, self.ultimo = None, agora
        self.feitos += 1
        faixa, celular = self.sim.faixa, self.sim.celular
        erro = self.erros.pop(self.feitos, None)
        if self.erra and not self.errou and faixa.destaque:
            self.errou = True
            celular.voltar()  # a tecla Voltar: a faixa não vê toque na tela
            self.sim.marcar("pessoa: aperta Voltar no primeiro destaque (o erro de propósito)")
        elif not (faixa.destaque or faixa.botao or faixa.gesto) and VOLTAR_FALA.search(faixa.fala or ""):
            celular.voltar()  # o guia pediu para voltar, sem destaque: ela aperta Voltar
            self.sim.marcar("pessoa: aperta Voltar")
        elif erro and erro.get("volta"):
            faixa.aviso("toque_tela")
            celular.voltar()
            self.sim.marcar("pessoa: volta uma tela (erro do cenário)")
        elif erro and erro.get("toca"):
            item = next(i for i in celular.itens() if i.texto == erro["toca"])
            self.tocar((item.limites[0] + item.limites[2]) // 2, (item.limites[1] + item.limites[3]) // 2,
                       f"«{erro['toca']}» (erro do cenário)")
        elif faixa.destaque:
            x1, y1, x2, y2 = faixa.destaque
            self.tocar((x1 + x2) // 2, (y1 + y2) // 2, f"o destaque {list(faixa.destaque)}")
        elif faixa.botao:
            faixa.aviso("toque_tela")
            self.sim.registro("usuario_toque_tela")
            faixa.aviso("botao_tocado", texto=faixa.botao.get("text"))
            self.sim.marcar(f"pessoa: aperta o botão «{faixa.botao.get('text')}»")
            celular.abrir_pagina(faixa.botao.get("open_settings"))
        elif faixa.gesto == "rolar":
            faixa.aviso("toque_tela")
            self.sim.registro("usuario_toque_tela")
            self.sim.marcar("pessoa: arrasta a tela para cima")
            if hasattr(celular, "rolar"):
                celular.rolar()
        elif faixa.gesto in ("puxar", "puxar_direita"):
            # Ela segue a instrução: pelo lado direito só se o gesto ou a fala disserem.
            lado = "direita" if faixa.gesto == "puxar_direita" or "direit" in ex.plain(faixa.fala or "") else "meio"
            faixa.aviso("toque_tela")
            self.sim.registro("usuario_toque_tela")
            self.sim.marcar(f"pessoa: puxa a barra do alto da tela para baixo, pelo {'lado direito' if lado == 'direita' else 'meio'}")
            if hasattr(celular, "puxar"):
                celular.puxar(lado)

    def tocar(self, x, y, onde):
        celular, faixa = self.sim.celular, self.sim.faixa
        faixa.aviso("toque_tela")
        self.sim.registro("usuario_toque_tela")
        alvo, limites = celular.tocar(x, y)
        if alvo is not None:
            faixa.aviso("toque", texto=alvo.nome or alvo.texto, limites=list(limites), classe=alvo.cls)
        self.sim.marcar(f"pessoa: toca em {onde}" + ("" if alvo else " (nada acontece)"))


class ProvedorGravado:
    """As respostas do provedor de uma rodada no celular (tests/gravacao.py), na ordem e com a demora de cada uma: o
    simulador repete a rodada para comparar com o aparelho. Uma pergunta a mais que a gravação encerra a rodada."""

    def __init__(self, sim, respostas):
        self.sim, self.respostas, self.pedidos = sim, list(respostas), []

    def __call__(self, prompt, raciocinio=True):
        tipo = "plano" if "You live on their phone" in prompt else "conferência" if ex.REVIEW[:50] in prompt else "ajuda"
        self.pedidos.append(tipo)
        self.sim.marcar(f"provedor: {tipo} (gravado)")
        if not self.respostas:
            return json.dumps({"finish": {"success": False, "message": "A GRAVAÇÃO ACABOU"}})
        resposta, segundos = self.respostas.pop(0)
        self.sim.esperar(segundos)
        return resposta


class Provedor:
    """O provedor por roteiro: o plano, as ajudas na ordem e a conferência final, cada um com a demora de verdade (o
    relógio anda enquanto ele pensa, e a pessoa pode fazer coisas nesse tempo). Uma ajuda fora do roteiro encerra."""

    def __init__(self, sim, plano, ajudas=(), conferencia=None, demora_plano=2.5, demora_ajuda=10.0):
        self.sim, self.plano, self.ajudas, self.conferencia = sim, plano, list(ajudas), conferencia
        self.demora_plano, self.demora_ajuda = demora_plano, demora_ajuda
        self.pedidos = []

    def __call__(self, prompt, raciocinio=True):
        tipo = "plano" if "You live on their phone" in prompt else "conferência" if ex.REVIEW[:50] in prompt else "ajuda"
        self.pedidos.append(tipo)
        self.sim.marcar(f"provedor: {tipo}")
        self.sim.esperar(self.demora_plano if tipo == "plano" else self.demora_ajuda)
        if tipo == "plano":
            resposta = self.plano
        elif tipo == "conferência":
            resposta = self.conferencia or {"finish": {"success": True, "message": "Pronto."}}
        elif self.ajudas:
            resposta = self.ajudas.pop(0)
            resposta = resposta(prompt) if callable(resposta) else resposta
        else:
            resposta = {"finish": {"success": False, "message": "AJUDA FORA DO ROTEIRO"}}
        return json.dumps(resposta, ensure_ascii=False)


class ProvedorReal:
    """O provedor de verdade (o Haiku pelo OpenRouter, com a chave do `.env`), montado como o app monta o pedido
    (`Agent.askProvider`): as instruções fixas como mensagem de sistema com marca de cache, a máscara só com as regras
    (o cofre da loja não tem contatos) e o raciocínio desligado no plano. O relógio de mentira anda a demora de verdade.
    `custo` soma o que o OpenRouter cobrou."""

    def __init__(self, sim, modelo=None):
        from lmphone.masking import Masker, Vault
        self.sim, self.modelo = sim, modelo or os.environ.get("MODEL") or "anthropic/claude-haiku-5.5"
        self.masker = Masker(Vault())
        self.pedidos, self.custo, self.segundos = [], 0.0, []
        self.chave = _chave()

    def __call__(self, prompt, raciocinio=True):
        tipo = "plano" if "You live on their phone" in prompt else "conferência" if ex.REVIEW[:50] in prompt else "ajuda"
        self.pedidos.append(tipo)
        self.sim.marcar(f"provedor: {tipo} (de verdade)")
        fixo, split, situacao = prompt.partition(ex.SPLIT)
        partes = [fixo, situacao] if split else [prompt]
        partes = [self.masker.mask(p, learn=not (split and i == 0)) for i, p in enumerate(partes)]
        mensagens = ([{"role": "system", "content": [{"type": "text", "text": partes[0],
                                                       "cache_control": {"type": "ephemeral"}}]},
                      {"role": "user", "content": partes[1]}] if split else [{"role": "user", "content": partes[0]}])
        corpo = {"model": self.modelo, "messages": mensagens, "usage": {"include": True}}
        if not raciocinio:
            corpo["reasoning"] = {"enabled": False}
        pedido = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                        data=json.dumps(corpo).encode(), method="POST",
                                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.chave}"})
        comeco = time.monotonic()
        with urllib.request.urlopen(pedido, timeout=300) as resposta:
            dados = json.loads(resposta.read())
        segundos = time.monotonic() - comeco
        self.segundos.append(round(segundos, 1))
        self.custo += float((dados.get("usage") or {}).get("cost") or 0)
        self.sim.esperar(segundos)
        return self.masker.unmask(dados["choices"][0]["message"]["content"])


def escolha_real(wanted, labels):
    """O modelo de escolha de verdade (o servidor ONNX dos modelos pequenos na porta 8788, o mesmo do app), com a regra
    do "dividido" do proxy e do Agent.kt."""
    pedido = urllib.request.Request(f"http://127.0.0.1:{os.environ.get('LMPHONE_LAYA_PORT', '8788')}/pick",
                                    data=json.dumps({"wanted": wanted, "labels": labels}).encode(), method="POST",
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        answer = json.loads(resposta.read())
    ranked = [(l, p) for l, p in answer.get("ranking") or [] if l is not None]
    if answer["label"] is None and len(ranked) >= 2 and ranked[0][1] + ranked[1][1] >= PICK_SPLIT:
        return ("dividido", (ranked[0][0], ranked[1][0]))
    return answer["label"]


def _chave():
    """A chave do OpenRouter, do ambiente ou do `.env` (nunca impressa)."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), encoding="utf-8") as f:
        for linha in f:
            nome, _, valor = linha.strip().partition("=")
            if nome == "OPENROUTER_API_KEY":
                return valor.strip().strip('"').strip("'")
    raise SystemExit("sem OPENROUTER_API_KEY no .env")


class Simulacao:
    def __init__(self, cenario):
        self.cenario = cenario
        self.relogio = Relogio()
        self.inicio = self.relogio.agora
        self.agenda = []  # (quando, ordem, função, nota)
        self.linha = []  # (segundos desde o começo, texto)
        if cenario.get("telas") == "reais":
            from tests.celular_real import CelularReal
            self.celular = CelularReal(self, **cenario.get("celular", {}))
        else:
            self.celular = Celular(self, **cenario.get("celular", {}))
        self.faixa = Faixa(self, **cenario.get("faixa", {}))
        self.pessoa = Pessoa(self, **cenario.get("pessoa", {}))
        if cenario.get("provedor_real"):
            self.provedor = ProvedorReal(self, cenario.get("modelo"))
        elif cenario.get("respostas") is not None:
            self.provedor = ProvedorGravado(self, cenario["respostas"])
        else:
            self.provedor = Provedor(self, copy.deepcopy(cenario["plano"]), copy.deepcopy(cenario.get("ajudas", [])),
                                     cenario.get("conferencia"), **cenario.get("provedor", {}))
        self.acoes, self.botoes, self.falas = [], [], []
        self.fim = None
        # A rodada no formato das gravações do celular (Gravacao.kt; tests/gravacao.py repete e compara as duas).
        self.gravacao, self.vez, self.ultima_tela = [], None, None
        self.live = []  # o registro no formato do live mode (as conferências do guia de tests/phone_suite.py)
        self.relogio.gravar = self.gravar

    def registro(self, tipo, **campos):
        self.live.append({"tipo": tipo, "ts": self.relogio.agora, **campos})

    def gravar(self, tipo, **campos):
        self.gravacao.append({"tipo": tipo, "t": self.relogio.agora, **json.loads(json.dumps(campos, ensure_ascii=False))})

    def gravado(self, nome, funcao):
        """Um callback do executor que vai para a gravação, como os do Agent.kt (`record`)."""
        def chamada(*args):
            ret = funcao(*args)
            self.gravar("cb", cb=nome, ret=ret, **({"args": list(args)} if args else {}))
            return ret
        return chamada

    def perguntar(self, prompt):
        e, comeco = self.executor, self.relogio.agora
        raciocinio = e.plan is not None and not e.quick  # como o Agent.kt (`makeExecutor`)
        resposta = self.provedor(prompt, raciocinio)
        self.gravar("cb", cb="provider", ret=resposta, pergunta=prompt, raciocinio=raciocinio,
                    segundos=round(self.relogio.agora - comeco, 1))
        return resposta

    def marcar(self, texto):
        self.linha.append((round(self.relogio.agora - self.inicio, 1), texto))

    def depois(self, segundos, funcao, nota=None):
        self.agenda.append((self.relogio.agora + segundos, len(self.agenda), funcao, nota))

    def esperar(self, segundos):
        """O relógio anda; o que estava marcado para esse tempo acontece na hora dele."""
        ate = self.relogio.agora + segundos
        while True:
            prontos = sorted(a for a in self.agenda if a[0] <= ate + 1e-9)
            if not prontos:
                break
            quando, ordem, funcao, nota = prontos[0]
            self.agenda.remove(prontos[0])
            self.relogio.agora = max(self.relogio.agora, quando)
            funcao()
            if nota:
                self.marcar(nota)
        self.relogio.agora = ate

    def ler(self):
        """Uma leitura da tela, gravada como no Gravacao.kt (o texto inteiro só quando muda)."""
        tela = self.celular.ler()
        self.esperar(self.cenario.get("leitura", LEITURA))
        if tela == self.ultima_tela:
            self.gravar("tela", igual=True)
        else:
            self.ultima_tela = tela
            self.gravar("tela", texto=tela, pacote=_PACOTE.search(tela).group(1))
        return tela

    def ler_tela(self):
        """A leitura do Agent.kt: lê até duas leituras seguidas saírem iguais."""
        tela = self.ler()
        limite = self.relogio.agora + STILL_LIMIT
        while self.relogio.agora < limite:
            self.esperar(STILL_GAP)
            outra = self.ler()
            if outra == tela:
                break
            tela = outra
        return tela

    def rodar(self):
        with mock.patch.object(ex, "time", self.relogio):
            pedido = self.cenario["pedido"]
            self.gravar("inicio", pedido=pedido, sessao="simulador", modelo="roteiro", acts=False, ask=True, owner=False,
                        continuo=False)
            escolha = escolha_real if self.cenario.get("escolha_real") else lambda wanted, labels: None
            e = ex.Executor(pedido, self.perguntar, self.gravado("pick", escolha),
                            device="Samsung Galaxy S23+ (One UI 9.0)", facts=self.gravado("facts", self.celular.fatos),
                            settings=self.gravado("settings", lambda page: True))
            e.assistant, e.acts, e.can_ask, e.may_ask, e.map = True, False, True, True, {}
            e.setter = self.gravado("setter", lambda name, value: ex.SCREENS)
            self.executor = e
            self.gravar("executor", pedido=pedido, aparelho=e.device, aberto=None, historia=e.history, acts=False, ask=True,
                        preaprovado=False, cache=False, mapa={})
            marcado = oferecido = gesto = None
            self.marcar(f"pedido: {pedido}")
            # O plano é pedido antes da primeira leitura, como no Agent.kt (`planAhead`).
            self.gravar("preparar")
            e.prepare()
            for _ in range(MAX_VOLTAS):
                if self.relogio.agora - self.inicio > LIMITE:
                    self.fim = ("tempo esgotado", None)
                    break
                self.faixa.entregar()
                e.touched_at, e.pressed_at = self.faixa.touched_at, self.faixa.pressed_at
                e.touched_text, e.touched_text_at, e.touched_box = (self.faixa.touched_text, self.faixa.touched_text_at,
                                                                    self.faixa.touched_box)
                vez = {"owner": e.owner, "speaking": e.speaking, "touched_at": e.touched_at, "pressed_at": e.pressed_at,
                       "touched_text": e.touched_text, "touched_text_at": e.touched_text_at,
                       "touched_box": e.touched_box, "guide_agent": e.guide_agent}
                if vez != self.vez:
                    self.vez = vez
                    self.gravar("vez", **vez)
                tela = self.ler_tela()
                mensagem = f"\n<device_state>\n{tela}\n</device_state>\n"
                e.app = _PACOTE.search(tela).group(1)
                self.gravar("passo", mensagem=mensagem, app=e.app)
                why, tool = e.step(mensagem)
                self.gravar("decisao", decisao=why, acao=tool, destaque=e.highlight, gesto=e.gesture, botao=e.button,
                            fala=e.announce, esperando=e.waiting is not None, passo=e.i, por=e.by, resultado=e.result)
                nome, params = parse_call(tool)
                if e.highlight != marcado:
                    self.registro("destaque", limites=list(e.highlight) if e.highlight else None,
                                  dono=True if e.highlight else None)
                    marcado = e.highlight
                    self.faixa.destaque = list(marcado) if marcado else None
                    self.marcar(f"faixa: destaque {self.faixa.destaque}" if marcado else "faixa: sem destaque")
                if e.gesture != gesto:
                    self.registro("gesto", gesto=e.gesture)
                    gesto = self.faixa.gesto = e.gesture
                    self.marcar(f"faixa: gesto {gesto}")
                if e.button != oferecido:
                    self.registro("botao", texto=(e.button or {}).get("text"))
                    oferecido = e.button
                    self.faixa.botao = dict(oferecido) if oferecido else None
                    if oferecido:
                        self.botoes.append(oferecido.get("open_settings") or oferecido.get("open_app"))
                    self.marcar(f"faixa: botão «{oferecido['text']}» ({self.botoes[-1]})" if oferecido else "faixa: sem botão")
                if e.off_names:
                    self.registro("nome_fora_da_tela", nomes=list(e.off_names))
                if nome == "complete":
                    self.registro("fim", resultado=e.result, mensagem=params.get("message", ""))
                    self.fim = (e.result, params.get("message", ""))
                    self.marcar(f"fim: {e.result}: {params.get('message', '')}")
                    break
                self.registro("acao", ferramenta=nome, parametros=params, por=e.by, passo=e.i,
                              **({"disse": e.announce} if e.announce else {}))
                if nome == "ask_user":
                    # A pergunta na faixa: o Agent.kt espera a resposta (`live.ask`). A pessoa lê e escolhe a primeira
                    # opção (a que o provedor põe primeiro é a mais provável).
                    opcoes = json.loads(params.get("options") or "[]")
                    resposta = opcoes[0] if opcoes else "sim"
                    self.registro("pergunta", texto=params.get("question"), opcoes=opcoes)
                    self.marcar(f"faixa pergunta: {params.get('question')} {opcoes}")
                    self.esperar(self.pessoa.leitura + self.pessoa.por_letra * len(params.get("question") or "") + 1.5)
                    e.answers.append((params.get("question") or "", resposta))
                    self.gravar("resposta", pergunta=params.get("question") or "", resposta=resposta, aplicada=True)
                    self.registro("resposta", texto=resposta)
                    self.marcar(f"pessoa responde: {resposta}")
                    continue
                if e.announce:
                    self.registro("fala", texto=e.announce)
                    self.falas.append(e.announce)
                    self.faixa.dizer(e.announce)
                    self.marcar(f"faixa diz: {e.announce}")
                    e.announce = None
                e.off_names = []  # vão para o registro do live mode (Agent.kt)
                if nome not in ("wait", "ask_user", None):  # perguntar à pessoa não é mexer no celular
                    self.acoes.append((nome, params))  # o app da loja não age: qualquer uma é defeito
                    self.marcar(f"AGENTE AGIU: {nome} {params}")
                self.pessoa.olhar()
                self.esperar(float(params.get("duration") or 1.0) if nome == "wait" else AFTER_ACTION)
            else:
                self.fim = ("voltas esgotadas", None)
            self.gravar("fim", ok=bool(self.fim and self.fim[0] in ("confirmado", "já estava")),
                        mensagem=self.fim[1] if self.fim else None, resultado=e.result)
        return self

    # O que conferir.
    def problemas(self):
        c, saida = self.cenario, []
        fim, mensagem = self.fim or (None, None)
        if fim not in c.get("resultados", ("confirmado", "já estava")):
            saida.append(f"terminou como «{fim}»" + (f": {mensagem}" if mensagem else ""))
        fatos = self.celular.fatos()
        for chave, valor in c.get("fatos", {}).items():
            if callable(valor) and not valor(fatos[chave]) or not callable(valor) and fatos[chave] != valor:
                saida.append(f"{chave} ficou {fatos[chave]!r}")
        if self.acoes:
            saida.append(f"o agente agiu {len(self.acoes)} vezes: {self.acoes[0]}")
        broncas = [f for f in self.falas if any(b in f for b in BRONCAS)]
        if len(broncas) > c.get("broncas", 0):
            saida.append(f"{len(broncas)} falas de erro da pessoa (o cenário espera {c.get('broncas', 0)}): {broncas[0]}")
        if c.get("botoes") is not None and len(self.botoes) != c["botoes"]:
            saida.append(f"o botão apareceu {len(self.botoes)} vezes (o cenário espera {c['botoes']}): {self.botoes}")
        ajudas = self.provedor.pedidos.count("ajuda")
        if ajudas > c.get("ajudas_max", 0):
            saida.append(f"{ajudas} ajudas do provedor (o cenário aceita {c.get('ajudas_max', 0)})")
        # A mesma frase duas vezes seguidas, sem nada no meio (2026-11-16: "Arraste o dedo..." 4 vezes).
        repetidas = [a for a, b in zip(self.falas, self.falas[1:]) if a == b and a != ex.AGAIN_SCROLL]
        if repetidas:
            saida.append(f"fala repetida: {repetidas[0]}")
        segundos = self.relogio.agora - self.inicio
        if segundos > c.get("segundos_max", LIMITE):
            saida.append(f"levou {segundos:.0f} s (o cenário aceita {c['segundos_max']})")
        return saida

    def resumo(self):
        fim = self.fim[0] if self.fim else None
        return (f"{fim}, {self.relogio.agora - self.inicio:.0f} s, {self.pessoa.feitos} gestos da pessoa, "
                f"provedor: {', '.join(self.provedor.pedidos) or 'nada'}, botões: {self.botoes}")


def rodar(cenario, **mudancas):
    """Roda um cenário (o nome em CENARIOS ou o dicionário), com partes trocadas: rodar("sint-avisos",
    celular={"atraso_tela": 3.5})."""
    cenario = copy.deepcopy(CENARIOS[cenario] if isinstance(cenario, str) else cenario)
    for parte, valor in mudancas.items():
        if isinstance(valor, dict) and isinstance(cenario.get(parte), dict):
            cenario[parte].update(valor)
        else:
            cenario[parte] = valor
    return Simulacao(cenario).rodar()


# O plano que o provedor deu nas rodadas de 2026-11-18 (sint-avisos): o `set` do Não perturbar com a frase do agente,
# a página de Sons, o modo Som e o volume do toque.
PLANO_AVISOS = {
    "guide": True, "say": "Vou te mostrar como fazer o celular voltar a avisar quando chega mensagem.",
    "steps": [
        {"action": "set", "target": ["do_not_disturb"], "value": False,
         "explain": "Primeiro, eu desligo o modo Não perturbe."},
        {"action": "open_settings", "target": ["sound"], "explain": "Agora vamos ver o som do celular."},
        {"action": "tap", "target": ["Som"], "if_missing": "help",
         "explain": "Toque em «Som», para o celular tocar quando chegar mensagem."},
        {"action": "tap", "target": ["Volume"], "if_missing": "scroll", "explain": "Agora toque em «Volume»."},
        {"action": "tap", "target": ["Toque"], "if_missing": "help", "explain": "Aumente o volume do toque."}],
    "goal": {"fact": {"do_not_disturb": False, "sound_mode": "som", "ring_volume": "up"}}}

AVISOS = {
    "pedido": "Não tá chegando aviso de nada, o celular não faz barulho quando chega mensagem",
    "celular": {"dnd": True, "modo": "vibrar", "toque": 0},
    "plano": PLANO_AVISOS,
    "fatos": {"do_not_disturb": False, "sound_mode": "som", "ring_volume": lambda v: v >= 20},
    "botoes": 2, "segundos_max": 90,
}

CENARIOS = {
    "sint-avisos": AVISOS,
    # 2026-11-18: a leitura ficou 3 s para trás do toque, e o guia disse "esse toque foi fora do destaque".
    "sint-avisos-tela-lenta": dict(AVISOS, celular=dict(AVISOS["celular"], atraso_tela=3.5)),
    # 2026-11-18: o aviso do toque chegou 2 s depois da tela nova, e o guia disse "recalculando".
    "sint-avisos-aviso-lento": dict(AVISOS, faixa={"atraso": 2.5}),
    # Uma pessoa lenta: lê devagar e demora para tocar.
    "sint-avisos-pessoa-lenta": dict(AVISOS, pessoa={"leitura": 4.0, "por_letra": 0.08}, segundos_max=150),
    # Ela toca em «Vibrar» no lugar de «Som» (a mesma tela, nada muda): o guia diz onde era, na hora, sem o provedor.
    "sint-avisos-erra-o-toque": dict(AVISOS, pessoa={"erros": {4: {"toca": "Vibrar"}}}, broncas=1),
    # Ela liga «Vibrar ao tocar» no lugar de tocar em «Volume»: o guia pede para desfazer e depois mostra o «Volume».
    "sint-avisos-liga-outra-chave": dict(AVISOS, pessoa={"erros": {5: {"toca": "Vibrar ao tocar"}}}, broncas=1),
    # Ela toca na «Agenda» no lugar da chave do Não perturbar, e a Agenda abre: o guia pede para esperar e o provedor
    # dá o caminho de volta (o botão para a página do Não perturbar de novo).
    "sint-avisos-abre-outra-tela": dict(AVISOS, pessoa={"erros": {2: {"toca": "Agenda"}}}, broncas=1, ajudas_max=1,
                                        botoes=3, ajudas=[{"steps": [
                                            {"action": "open_settings", "target": ["do_not_disturb"],
                                             "explain": "Vamos voltar para o Não perturbar."},
                                            {"action": "turn_off", "target": ["Não perturbar"], "if_missing": "help",
                                             "explain": "Agora toque na chave do Não perturbar, para desligar."}]
                                            + PLANO_AVISOS["steps"][1:]}]),
    # 2026-11-18: o botão de Sons não abria a página (a tarefa das Configurações reaproveitada). Aqui nenhuma página
    # abre pelo botão: depois do toque nele, o guia avisa e o provedor dá o caminho pelos menus.
    # Depois do primeiro botão morto, nenhum outro botão: o resto vai pelos menus.
    "sint-avisos-pagina-nao-abre": dict(AVISOS, celular=dict(AVISOS["celular"], pagina_abre=False), ajudas_max=2,
                                        botoes=1, segundos_max=150, ajudas=[
        {"steps": [{"action": "tap", "target": ["Config."], "explain": "Toque em «Config.», a engrenagem."},
                   {"action": "tap", "target": ["Notificações"], "if_missing": "scroll", "explain": "Toque em «Notificações»."},
                   {"action": "tap", "target": ["Não perturbar"], "if_missing": "scroll", "explain": "Toque em «Não perturbar»."},
                   {"action": "turn_off", "target": ["Não perturbar"], "explain": "Toque na chave, para desligar."}]
         + PLANO_AVISOS["steps"][1:]},
        {"steps": [{"action": "tap", "target": ["Navegar para cima"], "explain": "Toque na seta, no alto, para voltar."},
                   {"action": "tap", "target": ["Navegar para cima"], "explain": "Toque na seta de novo."},
                   {"action": "tap", "target": ["Sons e vibração"], "if_missing": "scroll",
                    "explain": "Toque em «Sons e vibração»."}] + PLANO_AVISOS["steps"][2:]}]),
}

# Os mesmos guias nas telas de verdade do S23+ (a varredura de 2026-11-18, tests/telas/; tests/celular_real.py): a
# página de Volume com o título separado da barra, o «Silenciar», a linha «Vibrar enquanto toca» do modo Som, a busca
# que flutua sobre a página inicial.
# Os tempos medidos nas rodadas finais no celular (tests/gravacoes/celular-avisos-9 a 11, `tests.gravacao medir` e
# `comparar`): uma leitura da tela leva 0,5 s, a tela lida mostra o toque em 0,7 a 1,8 s, o aviso do toque chega ao
# executor em 1,2 a 1,9 s, e a pessoa simulada do celular (tests/pessoa_loja.py) toca uns 2,5 s depois do destaque, sem
# ler a fala, e 1 s mais tarde no botão da faixa (a posição dele vai ao registro depois).
REAIS = dict(AVISOS, telas="reais", celular={"dnd": True, "modo": "vibrar", "toque": 0, "atraso_tela": 0.6},
             faixa={"atraso": 0.6}, leitura=0.5, segundos_max=150,
             pessoa={"leitura": 2.5, "por_letra": 0.0, "botao": 1.0, "insiste": 1e9})  # a do celular não insiste
CENARIOS.update({
    # 2026-11-18: o guia destacava o título «Toque» da página de Volume, não a barra, e esperava até o fim do tempo.
    "real-avisos": REAIS,
    "real-avisos-erra-o-toque": dict(REAIS, pessoa=dict(REAIS["pessoa"], erros={4: {"toca": "Vibrar"}}), broncas=1),
    # 2026-11-18, no celular (tests/gravacoes/celular-avisos-3.jsonl): o plano parou no «Volume», com a barra só na
    # explicação; o executor põe o passo da barra no fim, sem a ajuda.
    "real-avisos-plano-sem-barra": dict(REAIS, plano=dict(PLANO_AVISOS, steps=PLANO_AVISOS["steps"][:4])),
    "real-avisos-pagina-nao-abre": dict(REAIS, celular=dict(REAIS["celular"], pagina_abre=False), ajudas_max=2,
                                        botoes=1, segundos_max=150, ajudas=[
        {"steps": [{"action": "tap", "target": ["Config."], "explain": "Toque em «Config.», a engrenagem."},
                   {"action": "tap", "target": ["Notificações"], "if_missing": "scroll", "explain": "Toque em «Notificações»."},
                   {"action": "tap", "target": ["Não perturbar"], "if_missing": "scroll", "explain": "Toque em «Não perturbar»."},
                   {"action": "turn_off", "target": ["Não perturbar"], "explain": "Toque na chave, para desligar."}]
         + PLANO_AVISOS["steps"][1:]},
        {"steps": [{"action": "tap", "target": ["Navegar"], "explain": "Toque na seta, no alto, para voltar."},
                   {"action": "tap", "target": ["Navegar"], "explain": "Toque na seta de novo."},
                   {"action": "tap", "target": ["Sons e vibração"], "if_missing": "scroll",
                    "explain": "Toque em «Sons e vibração»."}] + PLANO_AVISOS["steps"][2:]}]),
})


# 2026-11-19, nos 50 casos (tests/casos.py, caso-letra-oculos): depois da letra, "Toque na setinha de voltar"; a pessoa
# apertou a tecla de voltar, que não chega à faixa como toque, e o guia disse que ela se perdeu e acabou sem o brilho.
CENARIOS["real-letra-e-volta"] = dict(
    REAIS, pedido="Mesmo de óculos eu não enxergo o que tá escrito no celular",
    celular=dict(REAIS["celular"], brilho_auto=False, brilho=20), segundos_max=150, resultados=("confirmado",), botoes=1,
    fatos={"font_scale": lambda v: v > 1.0, "brightness": lambda v: v > 20},
    plano={"guide": True, "say": "Vou te mostrar como deixar as letras maiores e a tela mais clara.",
           "goal": {"fact": {"font_scale": "up", "brightness": "up"}},
           "steps": [{"action": "open_settings", "target": ["display"], "explain": "Vamos abrir a página do Visor."},
                     {"action": "tap", "target": ["Tamanho e estilo da fonte"], "explain": "Toque em «Tamanho e estilo da fonte»."},
                     {"action": "tap", "target": ["Aumentar tam. da fonte"], "explain": "Toque no A grande, para a letra crescer."},
                     {"action": "back", "explain": "Toque na setinha de voltar, no alto à esquerda, para voltar ao Visor."},
                     {"action": "tap", "target": ["Brilho"], "explain": "Agora a barra do Brilho, para a tela ficar mais clara."}]})


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cenarios", nargs="*", help="nomes de CENARIOS (sem nenhum, todos)")
    parser.add_argument("-v", action="store_true", help="mostra a linha do tempo de cada rodada")
    parser.add_argument("--provedor", choices=("roteiro", "real"), default="roteiro",
                        help="real: o Haiku de verdade no lugar do roteiro (custa; a rodada leva minutos)")
    parser.add_argument("--vezes", type=int, default=1, help="quantas rodadas por cenário (com o provedor real, 5 a 10)")
    parser.add_argument("--modelo", help="o modelo do provedor real (padrão: MODEL ou anthropic/claude-haiku-5.5)")
    parser.add_argument("--escolha", action="store_true",
                        help="o modelo de escolha de verdade (o servidor dos modelos pequenos na porta 8788: "
                             ".venv-modelo/bin/python -m lmphone.modelo_server)")
    parser.add_argument("--gravar", metavar="PASTA", help="grava cada rodada nessa pasta (tests/gravacao.py as lê)")
    args = parser.parse_args()
    mudancas = {"provedor_real": True, "modelo": args.modelo} if args.provedor == "real" else {}
    if args.escolha:
        mudancas["escolha_real"] = True
    falhas, custo = 0, 0.0
    from tests.celular_real import TEM_TELAS  # sem as telas gravadas (fora do repositório público), os real-* ficam de fora
    for nome in args.cenarios or [n for n in CENARIOS if TEM_TELAS or not n.startswith("real-")]:
        boas, tempos = 0, []
        for vez in range(args.vezes):
            sim = rodar(nome, **mudancas)
            problemas = sim.problemas()
            boas += not problemas
            tempos.append(sim.relogio.agora - sim.inicio)
            custo += getattr(sim.provedor, "custo", 0.0)
            rotulo = nome if args.vezes == 1 else f"{nome} #{vez + 1}"
            print(f"{'ok   ' if not problemas else 'FALHA'} {rotulo}: {sim.resumo()}", flush=True)
            for problema in problemas:
                print(f"      - {problema}")
            if args.v:
                for segundos, texto in sim.linha:
                    print(f"      {segundos:6.1f}  {texto}")
            if args.gravar:
                from tests import gravacao
                gravacao.gravar(os.path.join(args.gravar, f"{rotulo.replace(' #', '-')}.jsonl"), sim.gravacao)
        falhas += args.vezes - boas
        if args.vezes > 1:
            print(f"      {nome}: {boas} de {args.vezes} sem problemas, mediana {statistics.median(tempos):.0f} s")
    if args.provedor == "real":
        print(f"custo do provedor: US$ {custo:.4f}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
