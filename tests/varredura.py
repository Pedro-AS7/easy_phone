"""A varredura das Configurações do celular: cada página como o cérebro do app a recebe, para o simulador.

Abre as Configurações e entra em cada linha de menu da página inicial, e um nível mais nas seções que os guias usam
(`FUNDO`). Abre também cada página que o botão da faixa abre direto (`proxy.SETTINGS`). Rola cada página até o fim e
grava cada tela em tests/telas/: a árvore de acessibilidade que o app lê (o build de depuração da loja, `DebugTela`;
dela sai o texto de `<device_state>`, por `device.elements_of` e `device.render`) e os fatos do aparelho como o app
os lê. `tests/telas/indice.json` liga cada linha de menu à página que ela abre. Quem toca é o PC, pelo adb; o app
continua sem agir.

Só toca em linhas de menu: nunca numa chave, numa opção, num controle deslizante, num campo ou num botão, nem numa
linha com nome de ação que não se desfaz (`PERIGO`: restaurar, apagar, desligar...). Para se os fatos do aparelho
mudarem e se alguém tocar no celular ou apertar uma tecla (o `getevent` do touchscreen e das teclas: os gestos do adb
não passam por ali). Os valores vão reais, sem máscara (decisão do Pedro, 2026-11-18).

    .venv/bin/python -m tests.varredura                # tudo (uns 30 a 60 min); --continuar pula o que já foi gravado
    .venv/bin/python -m tests.varredura --fundo 1      # só a página inicial e as que ela abre
    .venv/bin/python -m tests.varredura --direto       # só as páginas que o botão da faixa abre
    .venv/bin/python -m tests.varredura --estados      # o som e o Não perturbar em cada estado (muda e volta), o launcher
"""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata

from lmphone import device as dv
from lmphone import proxy

APP = "dev.pedro.lmphone.guia"
RECEPTOR = f"{APP}/dev.pedro.lmphone.DebugTela"
CONFIGURACOES = "com.android.settings"
PASTA = os.path.join("tests", "telas")
INDICE = os.path.join(PASTA, "indice.json")
# As seções da página inicial em que a varredura entra mais um nível (as que os guias e os sintomas usam).
FUNDO = ("Conexões", "Sons e vibração", "Notificações", "Visor", "Bateria", "Tela de bloqueio e AOD", "Acessibilidade",
         "Gerenciamento geral", "Modos e Rotinas", "Tela inicial", "Papel de parede e estilo", "Aparelhos conectados")
# Linhas que fazem algo que não se desfaz, ou que levam a isso: a varredura não toca nelas.
PERIGO = re.compile(r"restaur|redefin|exclu|apag|deslig|reinic|^sair|remov|format|atualiz|baixar|instal|forcar|limpar|"
                    r"reset|encerr|\bsos\b|emergenc|pagar|pagamento|compra|transfer|smart switch|backup|manutenc|depura|"
                    r"desenvolvedor|encontrar|find my|desemparelh|esquecer|parear|emparelh|adicionar|novo |nova ")
# Os controles que mudam algo com um toque: uma linha com um deles dentro não é tocada.
CONTROLES = ("Switch", "CheckBox", "RadioButton", "SeekBar", "EditText", "Button", "ImageButton", "CompoundButton",
             "ToggleButton", "Spinner")
LINHA = ("LinearLayout", "RelativeLayout", "FrameLayout", "ViewGroup", "ConstraintLayout")
ZONA = (330, 2000)  # onde a linha é tocada: abaixo do título que encolhe e acima da busca que flutua embaixo
# Fatos que mudam sozinhos: o brilho automático, o que toca, e o volume de mídia, que é o da saída de áudio ativa
# (2026-11-18: um fone Bluetooth se ligou no meio da varredura e o volume de mídia foi de 0 a 47).
VOLATEIS = ("brightness", "media_playing", "media_volume")
MAX_ROLAGENS = 14
# O touchscreen e as teclas (getevent -pl no S23+): um evento neles é de uma pessoa.
HUMANOS = ("sec_touchscreen", "pmic_pwrkey", "pmic_resin", "gpio-keys", "gpio_keys")


def adb(*args, timeout=30):
    return subprocess.run(["adb", *args], capture_output=True, timeout=timeout).stdout


def plain(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).casefold().strip()


def slug(caminho):
    texto = "-".join(plain(p) for p in caminho) or "inicio"
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:120]


class Parar(Exception):
    """Alguém mexeu no celular, ou um fato do aparelho mudou: a varredura para onde está."""


class Vigia(threading.Thread):
    """Lê o `getevent` do touchscreen e das teclas; qualquer evento ali é de uma pessoa."""

    def __init__(self):
        super().__init__(daemon=True)
        saida = adb("shell", "getevent", "-pl").decode(errors="replace")
        self.caminhos = [m.group(1) for m in re.finditer(r"add device \d+: (\S+)\s+name:\s+\"([^\"]+)\"", saida)
                         if m.group(2) in HUMANOS]
        self.mexeu = None
        self.processo = None

    def run(self):
        if not self.caminhos:
            return
        self.processo = subprocess.Popen(["adb", "shell", "getevent", "-l"], stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True)
        for linha in self.processo.stdout:
            if any(linha.startswith(c + ":") for c in self.caminhos):
                self.mexeu = linha.strip()
                break

    def parar(self):
        if self.processo:
            self.processo.kill()


class Tela:
    def __init__(self, dados):
        self.arvore, self.fatos = dados["tela"], dados.get("fatos") or {}
        self.elementos = dv.elements_of(self.arvore)
        self.texto = dv.render(self.arvore, self.elementos)
        self.pacote = (self.arvore.get("phone_state") or {}).get("packageName")


def _limites(no):
    b = no.get("boundsInScreen") or {}
    return [b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0)]


def _nos(no):
    yield no
    for filho in no.get("children") or []:
        yield from _nos(filho)


def linhas(arvore):
    """As linhas de menu da tela: [(título, resumo, limites)] dos contêineres tocáveis sem nenhum controle dentro."""
    saida = []

    def visitar(no):
        cls = (no.get("className") or "").split(".")[-1]
        if no.get("isClickable") and cls in LINHA and no.get("isVisibleToUser") is not False:
            if "search" in (no.get("resourceId") or ""):
                return  # a busca que flutua embaixo da página inicial
            dentro = list(_nos(no))
            if any(n.get("isCheckable") or (n.get("className") or "").split(".")[-1] in CONTROLES for n in dentro[1:]):
                return
            textos = [(n.get("resourceId") or "", n.get("text") or "") for n in dentro if n.get("text")]
            titulo = next((t for i, t in textos if i == "android:id/title"), textos[0][1] if textos else "")
            resumo = next((t for i, t in textos if i == "android:id/summary"), "")
            if titulo:
                saida.append((titulo, resumo, _limites(no)))
            return
        for filho in no.get("children") or []:
            visitar(filho)

    visitar(arvore["a11y_tree"])
    return saida


class Varredura:
    def __init__(self, fundo=2, continuar=False):
        self.fundo, self.continuar = fundo, continuar
        self.indice = {}
        if os.path.exists(INDICE):
            with open(INDICE, encoding="utf-8") as f:
                self.indice = json.load(f)
        self.vigia = Vigia()
        self.fatos = None
        self.paginas = 0

    # --- o aparelho ---
    def ler(self):
        for _ in range(4):
            adb("shell", "am", "broadcast", "-n", RECEPTOR, "--es", "nome", "varredura")
            dados = adb("exec-out", "run-as", APP, "cat", "files/cerebro/varredura/varredura.json")
            try:
                dados = json.loads(dados)
            except ValueError:
                time.sleep(0.5)
                continue
            if "erro" in dados:
                raise SystemExit(f"a captura falhou: {dados['erro']}")
            return Tela(dados)
        raise SystemExit("a captura não respondeu (o build de depuração da loja está instalado?)")

    def tela(self):
        """A tela parada: duas leituras seguidas iguais, como o Agent.kt."""
        tela = self.ler()
        for _ in range(6):
            time.sleep(0.4)
            outra = self.ler()
            if outra.texto == tela.texto:
                break
            tela = outra
        self.conferir()
        return tela

    def conferir(self):
        if self.vigia.mexeu:
            raise Parar(f"alguém mexeu no celular ({self.vigia.mexeu})")

    def tocar(self, x, y):
        self.conferir()
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(1.6)

    def rolar(self, de=1700, ate=900, devagar=False):
        self.conferir()
        adb("shell", "input", "swipe", "540", str(de), "540", str(ate), "1500" if devagar else "450")
        time.sleep(0.9)

    def abrir(self, acao):
        self.conferir()
        adb("shell", "am", "start", "-a", acao, "-f", "0x10008000")  # NEW_TASK | CLEAR_TASK: a página do começo
        time.sleep(1.8)

    # --- a navegação ---
    def tocar_linha(self, titulo):
        """Acha a linha na página aberta (rolando para baixo) e toca nela; False se não achou. Com a linha à vista e
        fora da zona, rola devagar (sem o impulso do gesto rápido) só o que falta para ela chegar ao meio da zona."""
        anterior, meio = None, (ZONA[0] + ZONA[1]) // 2
        for _ in range(MAX_ROLAGENS):
            tela = self.tela()
            achadas = [l for l in linhas(tela.arvore) if l[0] == titulo]
            for _, _, (x1, y1, x2, y2) in achadas:
                y = (y1 + y2) // 2
                if ZONA[0] <= y <= ZONA[1]:
                    self.tocar((x1 + x2) // 2, y)
                    return True
            if tela.texto == anterior:
                return False
            if achadas:
                falta = max(-700, min(700, (achadas[0][2][1] + achadas[0][2][3]) // 2 - meio))
                self.rolar(1500, 1500 - falta, devagar=True) if falta > 0 else self.rolar(800, 800 - falta, devagar=True)
            else:
                self.rolar()
            anterior = tela.texto
        return False

    def ir(self, caminho):
        self.abrir("android.settings.SETTINGS")
        for titulo in caminho:
            if not self.tocar_linha(titulo):
                return False
        return True

    def pagina(self):
        """As telas da página aberta, do alto ao fim."""
        telas = []
        for _ in range(MAX_ROLAGENS):
            tela = self.tela()
            if telas and tela.texto == telas[-1].texto:
                break
            telas.append(tela)
            self.rolar(1700, 900, devagar=True)  # sem o impulso: cada tela anda o mesmo tanto
        return telas

    # --- gravar ---
    def gravar(self, nome, caminho, abre, telas):
        os.makedirs(PASTA, exist_ok=True)
        pagina = {"caminho": caminho, "abre": abre, "pacote": telas[0].pacote, "fatos": telas[0].fatos,
                  "telas": [t.arvore for t in telas]}
        with gzip.open(os.path.join(PASTA, nome + ".json.gz"), "wt", encoding="utf-8") as f:
            json.dump(pagina, f, ensure_ascii=False)
        vistas = []
        for t in telas:
            for titulo, resumo, _ in linhas(t.arvore):
                if titulo not in [v[0] for v in vistas]:
                    vistas.append((titulo, resumo))
        self.indice[nome] = {"caminho": caminho, "abre": abre, "pacote": telas[0].pacote, "telas": len(telas),
                             "linhas": [{"titulo": t, "resumo": r, "pagina": None} for t, r in vistas]}
        if caminho:  # a linha da página de cima aponta para esta
            pai = self.indice.get(slug(caminho[:-1]))
            for linha in (pai or {}).get("linhas", []):
                if linha["titulo"] == caminho[-1]:
                    linha["pagina"] = nome
        with open(INDICE, "w", encoding="utf-8") as f:
            json.dump(self.indice, f, ensure_ascii=False, indent=1)
        self.paginas += 1
        return [t for t, _ in vistas]

    def guardar_fatos(self, tela):
        estado = {k: v for k, v in tela.fatos.items() if k not in VOLATEIS}
        if self.fatos is None:
            self.fatos = estado
        mudou = {k: (self.fatos.get(k), v) for k, v in estado.items() if self.fatos.get(k) != v}
        if mudou:
            raise Parar(f"um fato do aparelho mudou: {mudou}")

    # --- a varredura ---
    def menus(self):
        fila = [[]]
        while fila:
            caminho = fila.pop(0)
            nome = slug(caminho)
            if self.continuar and nome in self.indice:
                titulos = [l["titulo"] for l in self.indice[nome]["linhas"]]
                pacote = self.indice[nome]["pacote"]
            else:
                if not self.ir(caminho):
                    print(f"  não achei o caminho: {' > '.join(caminho)}", flush=True)
                    continue
                telas = self.pagina()
                self.guardar_fatos(telas[-1])
                titulos = self.gravar(nome, caminho, None, telas)
                pacote = telas[0].pacote
                print(f"  {' > '.join(caminho) or 'Configurações'}: {len(telas)} telas, {len(titulos)} linhas"
                      + ("" if pacote == CONFIGURACOES else f" ({pacote})"), flush=True)
            fundo = len(caminho) == 0 or len(caminho) == 1 and caminho[0] in FUNDO
            if len(caminho) < self.fundo and pacote == CONFIGURACOES and fundo:
                fila += [caminho + [t] for t in titulos if not PERIGO.search(plain(t))]

    def diretas(self):
        for chave, acao in proxy.SETTINGS.items():
            nome = "abre-" + slug([chave])
            if self.continuar and nome in self.indice:
                continue
            self.abrir(acao)
            telas = self.pagina()
            self.guardar_fatos(telas[-1])
            self.gravar(nome, [], chave, telas)
            print(f"  botão {chave}: {len(telas)} telas ({telas[0].pacote})", flush=True)

    def estados(self):
        """As páginas que mudam com o estado do aparelho, em cada estado que os cenários usam: o Não perturbar ligado,
        o modo Som, Vibrar e Silenciar com o volume do toque em 0 e no meio. Muda o estado pelo adb (`cmd notification
        set_dnd`, `cmd audio`) e, no fim, volta ao que estava (lido antes)."""
        def volume(stream):
            return int(adb("shell", "cmd", "audio", "get-stream-volume", str(stream)).decode().split()[-1])
        antes = {"zen": adb("shell", "settings", "get", "global", "zen_mode").decode().strip(),
                 "modo": adb("shell", "settings", "get", "global", "mode_ringer").decode().strip(),
                 "volumes": {s: volume(s) for s in (2, 3, 5)}}
        print(f"  estado de antes: {antes}", flush=True)
        # O Não perturbar em "prioridade" (o "on" é o silêncio total, que força o modo Silenciar e deixava as variantes
        # de som todas em "mudo"); desligado de novo antes das de som.
        variantes = [("dnd-ligado", ["set_dnd priority"], []),
                     ("som-toque-7", ["set_dnd off", "set-ringer-mode NORMAL", "set-volume 2 7", "set-volume 5 7"], []),
                     ("silenciar", ["set-ringer-mode SILENT"], []),
                     ("vibrar", ["set-ringer-mode VIBRATE"], [])]
        try:
            for nome, comandos, _ in variantes:
                for comando in comandos:
                    partes = comando.split()
                    adb("shell", "cmd", "notification" if partes[0] == "set_dnd" else "audio", *partes)
                time.sleep(1.0)
                paginas = [("abre-do-not-disturb", "android.settings.ZEN_MODE_SETTINGS", None)] if nome == "dnd-ligado" else \
                    [("abre-sound", "android.settings.SOUND_SETTINGS", None), ("sons-volume", "android.settings.SOUND_SETTINGS", "Volume")]
                for pagina, acao, linha in paginas:
                    self.abrir(acao)
                    if linha and not self.tocar_linha(linha):
                        print(f"  {nome}: não achei «{linha}»", flush=True)
                        continue
                    telas = self.pagina()
                    self.gravar(f"estado-{nome}-{pagina}", [linha] if linha else [], pagina, telas)
                    print(f"  estado {nome}, {pagina}: {len(telas)} telas, {telas[0].fatos}", flush=True)
        finally:
            for stream, valor in antes["volumes"].items():
                adb("shell", "cmd", "audio", "set-volume", str(stream), str(valor))
            adb("shell", "cmd", "audio", "set-ringer-mode", {"0": "SILENT", "1": "VIBRATE"}.get(antes["modo"], "NORMAL"))
            adb("shell", "cmd", "notification", "set_dnd", "off" if antes["zen"] == "0" else "on")
            time.sleep(1.0)
            depois = {"zen": adb("shell", "settings", "get", "global", "zen_mode").decode().strip(),
                      "modo": adb("shell", "settings", "get", "global", "mode_ringer").decode().strip(),
                      "volumes": {s: volume(s) for s in (2, 3, 5)}}
            print(f"  estado restaurado: {depois}" + ("" if depois == antes else "  (DIFERENTE do de antes!)"), flush=True)

    def inicio(self):
        """A tela inicial do celular (o launcher), de onde a pessoa abre as Configurações pelo ícone."""
        self.conferir()
        adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(1.5)
        self.gravar("launcher", [], "launcher", [self.tela()])
        print("  tela inicial gravada", flush=True)

    def rodar(self, menus=True, diretas=True, estados=False):
        self.vigia.start()
        comeco = time.monotonic()
        try:
            if estados:
                self.estados()
                self.inicio()
            if diretas:
                self.diretas()
            if menus:
                self.menus()
        except Parar as parada:
            print(f"PAROU: {parada}", flush=True)
            return False
        finally:
            self.vigia.parar()
            if not self.vigia.mexeu:
                adb("shell", "input", "keyevent", "KEYCODE_HOME")
            print(f"{self.paginas} páginas gravadas em {(time.monotonic() - comeco) / 60:.1f} min", flush=True)
        return True


def carregar(nome):
    """Uma página gravada: {"caminho", "abre", "pacote", "fatos", "telas": [árvores]}."""
    with gzip.open(os.path.join(PASTA, nome + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fundo", type=int, default=2, help="quantos níveis abaixo da página inicial (padrão 2)")
    parser.add_argument("--continuar", action="store_true", help="pula as páginas que já estão em tests/telas/")
    parser.add_argument("--direto", action="store_true", help="só as páginas que o botão da faixa abre")
    parser.add_argument("--estados", action="store_true",
                        help="só as páginas do som e do Não perturbar em cada estado (muda o estado e volta) e a tela inicial")
    args = parser.parse_args()
    if args.estados:
        ok = Varredura(args.fundo, True).rodar(menus=False, diretas=False, estados=True)
    else:
        ok = Varredura(args.fundo, args.continuar).rodar(menus=not args.direto)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
