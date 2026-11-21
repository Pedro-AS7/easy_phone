"""As gravações das rodadas do app da loja: tudo o que entrou no cérebro, na ordem, com o relógio dele.

O build de depuração da loja grava cada guia no celular (`android/cerebro/.../Gravacao.kt`, em
`files/cerebro/logs/gravacoes/<sessão>.jsonl`), e o simulador (`tests/simulador.py`) grava as rodadas dele no mesmo
formato. Com uma gravação dá para:

- repetir a rodada no executor do Python, com as mesmas entradas (as telas, os fatos, os toques da faixa, as respostas
  do provedor e do modelo de escolha, cada leitura do relógio), e conferir que ele decide o mesmo que o do celular;
- medir os tempos de verdade (quanto a tela lida leva para mostrar o toque, quanto o aviso do toque leva para chegar,
  quanto a pessoa leva para tocar, quanto o provedor demora), que o simulador usa nos atrasos dele;
- ver a linha do tempo (falas, destaques, botões, toques) e comparar a do celular com a do simulador.

Os valores vão reais, sem máscara (decisão do Pedro, 2026-11-18: os dados do celular não importam aqui).

    .venv/bin/python -m tests.gravacao puxar [nome]             # a última gravação do celular em tests/gravacoes/
    .venv/bin/python -m tests.gravacao repetir ARQUIVO          # o executor do Python decide igual ao do celular?
    .venv/bin/python -m tests.gravacao medir ARQUIVO            # os tempos da rodada
    .venv/bin/python -m tests.gravacao linha ARQUIVO [OUTRO]    # a linha do tempo; com dois arquivos, o que difere
"""

import argparse
import difflib
import json
import os
import statistics
import subprocess
import sys
import time as real_time
from unittest import mock

from lmphone import executor as ex
from lmphone.device import parse_call

APP = "dev.pedro.lmphone.guia"
NO_CELULAR = "files/cerebro/logs/gravacoes"
PASTA = os.path.join("tests", "gravacoes")
# O que o ciclo passa da faixa ao executor antes de cada leitura (Agent.kt, `loop`), com os nomes do Python.
VEZ = ("owner", "speaking", "touched_at", "pressed_at", "touched_text", "touched_text_at", "touched_box", "guide_agent")


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def gravar(caminho, eventos):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        for ev in eventos:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def normal(valor):
    """O valor como sai do JSON do Kotlin: tuplas viram listas."""
    return json.loads(json.dumps(valor, ensure_ascii=False))


def adb(*args, timeout=60):
    return subprocess.run(["adb", *args], capture_output=True, timeout=timeout, check=True).stdout


def puxar(nome=None, sessao=None):
    """Copia uma gravação do celular (a mais nova, ou a da sessão) para tests/gravacoes/; devolve o caminho."""
    arquivos = [n for n in adb("exec-out", "run-as", APP, "ls", "-t", NO_CELULAR).decode().split() if n.endswith(".jsonl")]
    if not arquivos:
        raise SystemExit("nenhuma gravação no celular (o build de depuração da loja grava cada guia)")
    escolhido = next((a for a in arquivos if sessao and sessao in a), arquivos[0])
    destino = os.path.join(PASTA, f"{nome or escolhido[:-len('.jsonl')]}.jsonl")
    os.makedirs(PASTA, exist_ok=True)
    with open(destino, "wb") as f:
        f.write(adb("exec-out", "run-as", APP, "cat", f"{NO_CELULAR}/{escolhido}"))
    return destino


# --- repetir no executor do Python ---

class Divergencia(Exception):
    """O executor do Python pediu de fora outra coisa que o do celular: dali em diante não dá para seguir a gravação."""


class Repeticao:
    """Repete uma gravação no executor do Python: o que ele pede de fora vem da gravação, na ordem em que o do celular
    pediu, e cada decisão é comparada com a gravada. `diferencas` diz onde ele decidiu diferente; `parou`, o que
    impediu de seguir (o Python pediu outra coisa)."""

    def __init__(self, eventos):
        self.eventos, self.k = eventos, 0
        self.e = None
        self.diferencas = []
        self.passos = 0
        self.parou = None

    # O `time` do módulo do executor, como o `_Clock` das trilhas.
    def __getattr__(self, nome):
        return getattr(real_time, nome)

    def monotonic(self):
        return self.cb("clock")["ret"]

    def cb(self, nome, args=None):
        if self.k >= len(self.eventos):
            raise Divergencia(f"o Python pediu «{nome}» depois do fim da gravação")
        ev = self.eventos[self.k]
        if ev["tipo"] != "cb" or ev["cb"] != nome:
            visto = f"pediu «{ev['cb']}»" if ev["tipo"] == "cb" else f"já tinha terminado a chamada («{ev['tipo']}» depois)"
            raise Divergencia(f"o Python pediu «{nome}», e o celular {visto}")
        self.k += 1
        if args is not None and "args" in ev and normal(list(args)) != ev["args"]:
            self.diferenca(f"«{nome}» com outros argumentos", ev["args"], normal(list(args)))
        return ev

    def provider(self, prompt):
        ev = self.cb("provider")
        if ev.get("pergunta") is not None and ev["pergunta"] != prompt:
            self.diferenca("o prompt ao provedor", ev["pergunta"], prompt)
        if ev.get("erro"):
            raise RuntimeError(ev.get("recusa") or ev["erro"])
        return ev["ret"]

    def pick(self, wanted, labels):
        ret = self.cb("pick", (wanted, labels))["ret"]
        return ("dividido", tuple(ret[1])) if isinstance(ret, list) else ret

    def simples(self, nome):
        return lambda *args: self.cb(nome, args)["ret"]

    def diferenca(self, oque, celular, python):
        self.diferencas.append({"passo": self.passos, "o que": oque, "celular": celular, "python": python})

    def rodar(self):
        with mock.patch.object(ex, "time", self):
            while self.k < len(self.eventos):
                ev = self.eventos[self.k]
                self.k += 1
                try:
                    getattr(self, "ev_" + ev["tipo"], lambda ev: None)(ev)
                except Divergencia as d:
                    self.parou = f"passo {self.passos}: {d}"
                    break
        return self

    def ev_cb(self, ev):
        raise Divergencia(f"o celular pediu «{ev['cb']}» fora de uma chamada do executor")

    def ev_executor(self, ev):
        e = ex.Executor(ev["pedido"], self.provider, self.pick, device=ev["aparelho"], launch=self.simples("launch"),
                        opened=ev.get("aberto"), facts=self.simples("facts"), history=ev.get("historia"),
                        settings=self.simples("settings"))
        e.assistant = True
        e.acts = ev.get("acts", False)
        e.setter, e.searcher = self.simples("setter"), self.simples("searcher")
        e.can_ask = e.may_ask = ev.get("ask", True)
        e.preapproved = ev.get("preaprovado", False)
        e.cached = ev.get("cache", False)
        e.map = ev.get("mapa") or {}
        self.e = e

    def ev_preparar(self, ev):
        self.e.prepare()

    def ev_vez(self, ev):
        for nome in VEZ:
            if nome in ev:
                setattr(self.e, nome, ev[nome])

    def ev_instrucao(self, ev):
        if ev.get("aplicada", True):
            self.e.instructions.append(ev["texto"])

    def ev_resposta(self, ev):
        if ev.get("aplicada", True):
            self.e.answers.append((ev["pergunta"], ev["resposta"]))

    def ev_confirmacao(self, ev):
        liberou = self.e.confirm_answer(ev["resposta"])
        if liberou != ev.get("liberou"):
            self.diferenca("a confirmação", ev.get("liberou"), liberou)

    def ev_parada(self, ev):
        self.e.result = "interrompida"

    def ev_passo(self, ev):
        self.passos += 1
        self.e.app = ev.get("app")
        erro = None
        try:
            why, tool = self.e.step(ev["mensagem"])
        except Divergencia:
            raise
        except Exception as falha:  # o Kotlin grava "erro" e devolve um complete de falha
            why = tool = None
            erro = repr(falha)
        seguinte = self.eventos[self.k] if self.k < len(self.eventos) else None
        if seguinte and seguinte["tipo"] == "cb":
            raise Divergencia(f"o celular ainda pediu «{seguinte['cb']}» neste passo, e o Python não")
        do_celular = None
        if seguinte and seguinte["tipo"] == "erro":
            do_celular = seguinte["erro"]
            self.k += 1
            seguinte = self.eventos[self.k] if self.k < len(self.eventos) else None
        if not seguinte or seguinte["tipo"] != "decisao":
            raise Divergencia("a gravação acabou no meio de um passo")
        self.k += 1
        if erro or do_celular:
            if not (erro and do_celular):
                self.diferenca("o executor falhou", do_celular, erro)
            return
        e = self.e
        decidido = {"acao": tool, "decisao": why, "destaque": e.highlight, "gesto": e.gesture, "botao": e.button,
                    "fala": e.announce, "esperando": e.waiting is not None, "passo": e.i, "por": e.by, "resultado": e.result}
        for campo, valor in decidido.items():
            if campo in seguinte and normal(valor) != seguinte[campo]:
                self.diferenca(campo, seguinte[campo], normal(valor))
        # O que o ciclo do Agent.kt faz depois do passo: a fala vai para a faixa, os nomes fora da tela para o registro.
        nome, _ = parse_call(tool)
        if nome not in ("ask_user", "confirm_user", "complete"):
            e.announce = None
        e.off_names = []

    def resumo(self):
        texto = f"{self.passos} passos repetidos, {len(self.diferencas)} diferenças"
        return texto + (f"; parou no {self.parou}" if self.parou else "")


def repetir(eventos):
    return Repeticao(eventos).rodar()


# --- os tempos ---

def _mediana(valores):
    return f"mediana {statistics.median(valores):.2f} s, de {min(valores):.2f} a {max(valores):.2f} s ({len(valores)})" \
        if valores else "nenhum"


def medir(eventos):
    """Os tempos da rodada, em segundos: cada lista é uma medida, na ordem em que aconteceu."""
    medidas = {"provedor (plano)": [], "provedor (ajuda)": [], "leitura da tela": [], "aviso do toque": [],
               "toque até a tela lida mudar": [], "pessoa: destaque até o toque": [], "pessoa: botão até o toque": []}
    ultima_tela = None  # o t da leitura anterior, na mesma rajada de leituras
    tocou = None  # um toque cuja tela nova ainda não foi lida
    visto = apertou = 0.0
    destaque_em = botao_em = None
    for ev in eventos:
        tipo, t = ev["tipo"], ev.get("t")
        if tipo == "cb" and ev["cb"] == "provider" and ev.get("segundos") is not None:
            medidas["provedor (ajuda)" if ev.get("raciocinio") else "provedor (plano)"].append(ev["segundos"])
        elif tipo == "tela":
            if ultima_tela is not None:
                medidas["leitura da tela"].append(max(0.0, t - ultima_tela - 0.15))  # menos o STILL_GAP entre as duas
            ultima_tela = t
            if "texto" in ev and tocou is not None and t > tocou:
                medidas["toque até a tela lida mudar"].append(t - tocou)
                tocou = None
        elif tipo == "passo":
            ultima_tela = None
        elif tipo == "vez":
            novo = ev.get("touched_at")
            if novo and novo > visto:
                visto = tocou = novo
                medidas["aviso do toque"].append(t - novo)
                if destaque_em is not None and novo > destaque_em:
                    medidas["pessoa: destaque até o toque"].append(novo - destaque_em)
                    destaque_em = None
            if ev.get("pressed_at") and ev["pressed_at"] > apertou:
                apertou = ev["pressed_at"]
                if botao_em is not None and apertou > botao_em:
                    medidas["pessoa: botão até o toque"].append(apertou - botao_em)
                    botao_em = None
        elif tipo == "decisao":
            if ev.get("destaque") and ev.get("esperando") and destaque_em is None:
                destaque_em = t
            if not ev.get("destaque"):
                destaque_em = None
            if ev.get("botao") and botao_em is None:
                botao_em = t
            if not ev.get("botao"):
                botao_em = None
    return medidas


# --- a linha do tempo ---

def _rotulo(tela, limites):
    """O texto do elemento da tela com esses limites (o que está destacado)."""
    for elemento in ex.parse_screen(tela or "")[0]:
        if list(elemento.bounds) == list(limites):
            return elemento.text or elemento.cls
    return str(list(limites))


def linha(eventos):
    """O que a pessoa viu e fez, na ordem: [(segundos desde o começo, texto)]."""
    inicio = next((ev["t"] for ev in eventos if "t" in ev), 0.0)
    saida, tela = [], None
    destaque = botao = gesto = None
    tocou = apertou = 0.0
    for ev in eventos:
        tipo, s = ev["tipo"], round(ev.get("t", inicio) - inicio, 1)
        if tipo == "inicio":
            saida.append((s, f"pedido: {ev.get('pedido')}"))
        elif tipo == "passo":
            tela = ev["mensagem"]
        elif tipo == "decisao":
            if ev.get("fala"):
                saida.append((s, f"diz: {ev['fala']}"))
            if ev.get("destaque") != destaque:
                destaque = ev.get("destaque")
                saida.append((s, f"destaque: «{_rotulo(tela, destaque)}»" if destaque else "sem destaque"))
            if ev.get("botao") != botao:
                botao = ev.get("botao")
                saida.append((s, f"botão: «{botao.get('text')}»" if botao else "sem botão"))
            if ev.get("gesto") != gesto:
                gesto = ev.get("gesto")
                saida.append((s, f"gesto: {gesto}" if gesto else "sem gesto"))
            nome, params = parse_call(ev.get("acao") or "")
            if nome == "complete":
                saida.append((s, f"fim: {ev.get('resultado')}: {params.get('message', '')}"))
            elif nome not in ("wait", None):
                saida.append((s, f"o agente agiu: {nome}"))
        elif tipo == "vez":
            if ev.get("touched_at") and ev["touched_at"] > tocou:
                tocou = ev["touched_at"]
                texto = ev.get("touched_text") if ev.get("touched_text_at") == tocou else None
                saida.append((round(tocou - inicio, 1), f"toque" + (f" em «{texto}»" if texto else "")))
            if ev.get("pressed_at") and ev["pressed_at"] > apertou:
                apertou = ev["pressed_at"]
                saida.append((round(apertou - inicio, 1), "aperta o botão da faixa"))
        elif tipo == "cb" and ev["cb"] == "provider":
            saida.append((s, f"provedor ({ev.get('segundos', 0):.1f} s)"))
        elif tipo in ("instrucao", "resposta"):
            saida.append((s, f"a pessoa diz: {ev.get('texto') or ev.get('resposta')}"))
        elif tipo == "fim" and ev.get("erro"):
            saida.append((s, f"o cérebro falhou: {ev['erro']}"))
    return sorted(saida, key=lambda item: item[0])


def diferencas(a, b):
    """O que difere entre duas linhas do tempo (sem os tempos): as linhas de `difflib`, com - para a primeira."""
    textos_a, textos_b = [t for _, t in a], [t for _, t in b]
    return [d for d in difflib.unified_diff(textos_a, textos_b, lineterm="", n=1) if not d.startswith(("---", "+++"))]


# --- comparar o celular com o simulador ---

AGENTE = ("diz:", "destaque:", "botão:", "gesto:", "fim:", "o agente agiu")  # o que o guia faz (não a pessoa)


def acao(texto):
    """O que o guia fez, sem a redação: que falou (não o quê: a fala muda com o executor), o controle destacado, o
    botão, o gesto (sem o lado) e o resultado (sem a mensagem)."""
    if texto.startswith("diz:"):
        return "diz"
    if texto.startswith("gesto:"):
        return texto.replace("_direita", "")
    if texto.startswith("fim:"):
        return texto.split(":")[1].strip()
    return texto


def cenario(eventos):
    """A rodada do celular como cenário do simulador: o pedido, o estado do começo, as telas de verdade e as respostas
    do provedor na ordem, com a demora de cada uma."""
    from tests import simulador
    fatos = next((e["ret"] for e in eventos if e["tipo"] == "cb" and e["cb"] == "facts"), {}) or {}
    pedido = next(e["pedido"] for e in eventos if e["tipo"] == "inicio")
    respostas = [(e["ret"], e.get("segundos") or 0.0) for e in eventos if e["tipo"] == "cb" and e["cb"] == "provider"
                 and e.get("ret") is not None]
    estado = {"dnd": bool(fatos.get("do_not_disturb")), "modo": fatos.get("sound_mode") or "vibrar",
              "toque": fatos.get("ring_volume") or 0, "midia": fatos.get("media_volume") or 0,
              "fonte": fatos.get("font_scale") or 1.0, "brilho": fatos.get("brightness") or 35,
              "girar": fatos.get("auto_rotate", True), "tela_apaga": fatos.get("screen_timeout") or 15,
              "brilho_auto": fatos.get("auto_brightness", True)}
    return dict(simulador.REAIS, pedido=pedido, celular=dict(simulador.REAIS["celular"], **estado), respostas=respostas,
                fatos={}, botoes=None, ajudas_max=99, segundos_max=simulador.LIMITE)


def comparar(eventos):
    """Roda a rodada do celular no simulador e compara: o que o guia fez (falas, destaques, botões, gestos, o fim), na
    ordem, o estado do aparelho no fim e o tempo. Devolve um dicionário com as duas linhas e as medidas."""
    from tests import simulador
    sim = simulador.rodar(cenario(eventos))
    celular = [(s, t) for s, t in linha(eventos) if t.startswith(AGENTE)]
    simulado = [(s, t) for s, t in linha(sim.gravacao) if t.startswith(AGENTE)]
    bate = difflib.SequenceMatcher(a=[acao(t) for _, t in celular], b=[acao(t) for _, t in simulado], autojunk=False)
    iguais = sum(bloco.size for bloco in bate.get_matching_blocks())
    fatos = [e["ret"] for e in eventos if e["tipo"] == "cb" and e["cb"] == "facts"]
    chaves = ["do_not_disturb", "sound_mode", "ring_volume", "media_volume", "font_scale", "brightness", "auto_rotate",
              "screen_timeout"]
    # O que muda sozinho no celular não se compara: o brilho com o brilho automático, o volume de mídia com um fone
    # Bluetooth (é o da saída de áudio ativa; 2026-11-18, o fone se ligou e desligou no meio das rodadas).
    comeco = fatos[0] if fatos else {}
    if comeco.get("auto_brightness"):
        chaves.remove("brightness")
    if comeco.get("bluetooth"):
        chaves.remove("media_volume")
    chaves = [k for k in chaves if k in comeco]  # uma gravação de antes de um fato existir não o tem
    fim_celular = {k: (fatos[-1] if fatos else {}).get(k) for k in chaves}
    fim_simulado = {k: sim.celular.fatos().get(k) for k in chaves}
    from lmphone import facts as device_facts
    for k in chaves:  # um nível vale com a folga dos objetivos (a barra do brilho não é linear)
        a, b = fim_celular.get(k), fim_simulado.get(k)
        if k in device_facts.LEVELS and isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= device_facts.LEVEL_SLACK:
            fim_simulado[k] = a
    resultado = lambda ev: next((e.get("resultado") for e in reversed(ev) if e["tipo"] == "fim"), None)
    return {"iguais": iguais, "celular_n": len(celular), "simulado_n": len(simulado),
            "resultado": (resultado(eventos), resultado(sim.gravacao)), "estado": (fim_celular, fim_simulado),
            "tempo": (eventos[-1]["t"] - eventos[0]["t"], sim.gravacao[-1]["t"] - sim.gravacao[0]["t"]),
            "diferencas": diferencas(celular, simulado), "sim": sim}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("puxar", help="a gravação mais nova do celular para tests/gravacoes/")
    p.add_argument("nome", nargs="?")
    p.add_argument("--sessao")
    p = sub.add_parser("repetir", help="o executor do Python com as entradas gravadas")
    p.add_argument("arquivo")
    p.add_argument("-v", action="store_true", help="cada diferença inteira")
    p = sub.add_parser("medir", help="os tempos da rodada")
    p.add_argument("arquivo")
    p = sub.add_parser("comparar", help="a rodada do celular repetida no simulador, lado a lado")
    p.add_argument("arquivos", nargs="+")
    p = sub.add_parser("linha", help="a linha do tempo")
    p.add_argument("arquivo")
    p.add_argument("outro", nargs="?")
    args = parser.parse_args()
    if args.comando == "puxar":
        print(puxar(args.nome, args.sessao))
    elif args.comando == "repetir":
        r = repetir(ler(args.arquivo))
        print(r.resumo())
        for d in r.diferencas:
            celular, python = json.dumps(d["celular"], ensure_ascii=False), json.dumps(d["python"], ensure_ascii=False)
            if not args.v:
                celular, python = celular[:300], python[:300]
            print(f"  passo {d['passo']}, {d['o que']}:\n    celular: {celular}\n    python:  {python}")
        sys.exit(1 if r.diferencas or r.parou else 0)
    elif args.comando == "comparar":
        for arquivo in args.arquivos:
            c = comparar(ler(arquivo))
            print(f"{os.path.basename(arquivo)}: {c['iguais']} de {c['celular_n']} iguais na ordem (simulador: "
                  f"{c['simulado_n']}); resultado {c['resultado'][0]} / {c['resultado'][1]}; tempo {c['tempo'][0]:.0f} s / "
                  f"{c['tempo'][1]:.0f} s; estado {'igual' if c['estado'][0] == c['estado'][1] else c['estado']}")
            for d in c["diferencas"]:
                print("    " + d)
    elif args.comando == "medir":
        for nome, valores in medir(ler(args.arquivo)).items():
            print(f"{nome}: {_mediana(valores)}")
    else:
        a = linha(ler(args.arquivo))
        if args.outro:
            for d in diferencas(a, linha(ler(args.outro))):
                print(d)
        else:
            for s, texto in a:
                print(f"{s:6.1f}  {texto}")


if __name__ == "__main__":
    main()
