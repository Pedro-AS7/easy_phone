"""Os modelos pequenos no app (etapa 2 de docs/plano-app-android.md), do lado do PC.

- `preparar`: grava `data/modelos/app/tokenizador.bin`, o `tokenizer.json` dos modelos num formato que o app lê
  rápido (o JSON tem 9,5 MB e 250 mil peças). Confere antes que o `tokenizer.json` é do tipo que o tokenizador em
  Kotlin (`android/modelos/.../Tokenizer.kt`) sabe ler: normalizador `Precompiled`, `WhitespaceSplit` e `Metaspace`,
  Unigram sem `byte_fallback`, os modelos de `<s> A </s>` e `<s> A </s></s> B </s>`. Qualquer outra coisa para aqui.
- `referencia`: as respostas do Python (biblioteca `tokenizers` e o `modelo_server`) para os textos da coleta, do
  conjunto congelado e de casos difíceis escritos aqui, em `data/modelos/app/referencia/`. A conferência em Kotlin
  (`android\\gradlew.bat :modelos:conferir`) as compara com as dela. Roda no `.venv-modelo`. Os textos da coleta são
  reais: ficam em `data/` (fora do git) e o terminal mostra só contagens.
- `enviar`: copia os dois modelos, o tokenizador e as configurações para o armazenamento do app no celular, pelo adb
  (`/data/local/tmp` e depois `run-as`), e apaga a cópia do meio.
- `ponte`: liga o modo de depuração dos modelos no app (`ModelService`) e atende em 127.0.0.1:8791 com a API do
  `modelo_server`, para `tests.eval_base --novo http://127.0.0.1:8791` rodar contra o celular.
- `medir`: o tempo de cada chamada medido no app (sem o adb), com os casos fictícios do conjunto congelado;
  `--threads 0 4 2` compara números de núcleos. Ligue antes a acessibilidade do app: sem ela, a One UI só dá ao
  processo os núcleos lentos (docs/plano-app-android.md, etapa 2).

Uso: .venv-modelo/Scripts/python.exe -m tools.app.modelos preparar | referencia | enviar | ponte | medir [--threads N ...]
"""

import argparse
import base64
import json
import os
import random
import struct
import subprocess
import sys

MODELS = "data/modelos"
OUT = "data/modelos/app"
TOKENIZER = OUT + "/tokenizador.bin"
REFERENCE = OUT + "/referencia"
COLLECTION = "data/treino/real/2026-10-17.jsonl"
APP = os.environ.get("LMPHONE_APP", "dev.pedro.lmphone")  # a variante loja: dev.pedro.lmphone.guia
MAGIC = b"LMTK"
VERSION = 1

PRE_TOKENIZER = {"type": "Sequence", "pretokenizers": [
    {"type": "WhitespaceSplit"},
    {"type": "Metaspace", "replacement": "▁", "prepend_scheme": "always", "split": True}]}


def template(*parts):
    out = []
    for part in parts:
        if part in "AB":
            out.append({"Sequence": {"id": part, "type_id": 0}})
        else:
            out.append({"SpecialToken": {"id": part, "type_id": 0}})
    return out


def prepare():
    """tokenizer.json -> tokenizador.bin (inteiros e reais em big-endian, textos em UTF-8 com o tamanho antes)."""
    paths = [f"{MODELS}/{part}/tokenizer.json" for part in ("marcacao", "escolha")]
    raw = open(paths[0], "rb").read()
    if open(paths[1], "rb").read() != raw:
        sys.exit("os dois modelos têm tokenizer.json diferentes; o app espera um só")
    t = json.loads(raw)
    check = [
        (t["truncation"] is None and t["padding"] is None, "truncation e padding vazios"),
        (t["normalizer"]["type"] == "Precompiled", "normalizador Precompiled"),
        (t["pre_tokenizer"] == PRE_TOKENIZER, "WhitespaceSplit e Metaspace"),
        (t["model"]["type"] == "Unigram" and not t["model"].get("byte_fallback"), "Unigram sem byte_fallback"),
        (t["post_processor"]["type"] == "TemplateProcessing"
         and t["post_processor"]["single"] == template("<s>", "A", "</s>")
         and t["post_processor"]["pair"] == template("<s>", "A", "</s>", "</s>", "B", "</s>"), "modelos <s> A </s>"),
        (all(a["special"] and not a["normalized"] and not a["lstrip"] and not a["rstrip"] and not a["single_word"]
             for a in t["added_tokens"]), "tokens especiais simples"),
    ]
    for ok, what in check:
        if not ok:
            sys.exit(f"tokenizer.json fora do que o tokenizador em Kotlin lê: {what}")
    ids = {a["content"]: a["id"] for a in t["added_tokens"]}
    vocab = t["model"]["vocab"]
    charsmap = base64.b64decode(t["normalizer"]["precompiled_charsmap"])
    out = bytearray(MAGIC + struct.pack(">i", VERSION))
    out += struct.pack(">i", t["model"]["unk_id"])
    out += struct.pack(">iii", ids["<s>"], ids["</s>"], ids["<pad>"])
    out += struct.pack(">i", len(t["added_tokens"]))
    for added in t["added_tokens"]:
        content = added["content"].encode("utf-8")
        out += struct.pack(">ih", added["id"], len(content)) + content
    out += struct.pack(">i", len(charsmap)) + charsmap
    out += struct.pack(">i", len(vocab))
    for piece, score in vocab:
        data = piece.encode("utf-8")
        out += struct.pack(">h", len(data)) + data + struct.pack(">d", score)
    os.makedirs(OUT, exist_ok=True)
    with open(TOKENIZER, "wb") as f:
        f.write(out)
    print(f"{TOKENIZER}: {len(vocab)} peças, {len(out) / 1e6:.1f} MB")


# --- referência ---

def utf16(text, index):
    """Posição em code points (Python) -> posição em unidades UTF-16 (Kotlin)."""
    return len(text[:index].encode("utf-16-le")) // 2


def offsets(encoding, texts):
    out = []
    for (start, end), sequence in zip(encoding.offsets, encoding.sequence_ids):
        text = texts[sequence or 0]
        out.append([utf16(text, start), utf16(text, end)] if sequence is not None else [0, 0])
    return out


def hard_cases():
    """Textos fictícios que exercitam as partes difíceis do tokenizador: normalização, espaços, emoji, outras
    escritas, tokens especiais escritos no texto, cortes."""
    base = [
        "", " ", "a", "  dois  espaços ", "\t tab\nnova linha\r\nwindows\r\n", "Ana Lima", "x y", "a b",
        "\x85nel", "\x1cfs\x1d", "José", "José", "é", "Ａ́", "Ａ", "ﬁm", "①②", "ｆｕｌｌｗｉｄｔｈ",
        "x²", "½ xícara", "Ⅻ", "℡", "㎏", "​zero", "a​b", "﻿bom", "a­b", "‎a‏",
        "👍🏽 ok", "❤️", "©️ marca", "1️⃣", "👨‍👩‍👧", "🇧🇷 Brasil", "日本語のテキスト", "한국어 텍스트", "각",
        "각", "العربية", "हिन्दी", "ไทย", "<s>abc</s>", "x<mask>y", "<unk>", "<pad><pad>", "< s >",
        "▁", "a▁b", "▁▁x", "x▁▁", "▁ ▁", "\x00nul", "a\x00b", "priv",
        "joao.vitor.silva", "@ana_lima92", "ana.lima@gmail.com", "+55 61 99123-4567", "(11) 3222-1100",
        "R$ 1.234,56", "12:30", "Configurações › Tela", "Wi-Fi", "Ãé ÕÇ ñ ü", "ÀÉÎÕÜ", "straße", "İstanbul", "ǅ",
        "́inicio", "́", "á́́", "\r", "\r\r\n", "\ń", "k⃣", "#️⃣",
        "ㅤ", "　ideográfico　", "…", "“aspas” ‘simples’", "—travessão–", "ｶﾞ", "ｶﾞ", "Ω Ω Å Å",
    ]
    # O que a normalização apaga (controles) ou troca por mais de um caractere, no começo, no meio e no fim.
    deleted = ["\x01", "\x08", "\x0b", "\x1f", "\x7f", "\x8f", "\x9f"]
    expanded = ["ﬁ", "½", "㎏", "℡", "ǅ", "Ⅻ", "…", "ｶﾞ", "㎒", "ﷺ", "ΐ", "ẛ̣"]
    for piece in deleted + expanded:
        base += [piece + "ab cd", "ab" + piece + "cd", "ab cd" + piece, piece + piece + " x " + piece, piece]
    base += ["\x01\x02\x03abc", "\x01 \x02 abc", "a\x01\x01b\x01 c"]
    return base


def collection():
    """Pedidos, trechos de tela, telas julgadas e escolhas da coleta (reais)."""
    requests, fragments, screens, picks = [], [], [], []
    if not os.path.exists(COLLECTION):
        return requests, fragments, screens, picks
    for line in open(COLLECTION, encoding="utf-8"):
        record = json.loads(line)
        kind = record["tipo"]
        if kind == "pedido":
            requests.append(record["texto"])
        elif kind == "trecho":
            fragments.append(record["texto"])
        elif kind == "julgamento":
            screens.append(record["trechos"])
        elif kind == "escolha" and record["rotulos"]:
            picks.append((record["passo"]["alvo"], record["rotulos"]))
    return requests, fragments, screens, picks


def frozen():
    from tests.base.controles import ESCOLHAS
    from tests.base.mascaramento import CASOS
    requests = [case["entrada"] for case in CASOS if case["tipo"] == "pedido"]
    screens = [case["trechos"] for case in CASOS if case["tipo"] == "tela"]
    picks = [([wanted], case["tela"]) for case in ESCOLHAS for wanted in case["pedidos"]]
    picks += [(case["pedidos"], case["tela"]) for case in ESCOLHAS]
    return requests, screens, picks


def fuzz(count, seed=17):
    """Textos aleatórios (fictícios) misturando letras, espaços, acentos soltos, emoji, apagados e especiais."""
    pool = (list("abcdefghij ABC 0123 .,;:-_@/") + ["  ", "\t", "\n", "\r\n", " ", "́", "̃", "̧",
            "​", "‍", "️", "﻿", "­", "👍", "🏽", "🇧", "🇷", "ﬁ", "①", "Ａ", "ｶ", "ﾞ", "가",
            "ᆨ", "日", "ä", "é", "▁", "<s>", "</s>", "<mask>", "<unk>", "\x00", "\x85", "²", "…"])
    rng = random.Random(seed)
    return ["".join(rng.choice(pool) for _ in range(rng.randint(1, 40))) for _ in range(count)]


def reference():
    sys.path.insert(0, os.getcwd())
    from tokenizers import Tokenizer

    from lmphone import modelo_server
    from lmphone.modelo import SEPARATOR, query

    os.makedirs(REFERENCE, exist_ok=True)
    tokenizer = Tokenizer.from_file(f"{MODELS}/marcacao/tokenizer.json")
    edge = hard_cases()
    real_requests, fragments, real_screens, real_picks = collection()
    base_requests, base_screens, base_picks = frozen()
    random_texts = fuzz(3000)

    # Cortes da escolha (LongestFirst, 64 tokens no par): pares longos e curtos dos dois lados.
    words = "configurações de bateria e desempenho do aparelho com tela cheia".split()
    long_pairs = []
    for a in range(0, 90, 7):
        for b in range(0, 90, 11):
            long_pairs.append((" ".join((words * 12)[:a]), " ".join((words * 12)[3:3 + b])))
    long_single = [" ".join((words * 80)[:n]) for n in (200, 253, 254, 255, 256, 300, 600)]

    singles = {"casos": edge + long_single, "aleatorios": random_texts, "pedidos": real_requests + base_requests,
               "trechos": fragments,
               "telas": [SEPARATOR.join(s) for s in real_screens + base_screens]}
    counts = {}
    with open(f"{REFERENCE}/tokens.jsonl", "w", encoding="utf-8") as f:
        for name, texts in singles.items():
            for limit in (256, None):
                if limit:
                    tokenizer.enable_truncation(limit)
                else:
                    tokenizer.no_truncation()
                for text in texts:
                    encoding = tokenizer.encode(text)
                    f.write(json.dumps({"grupo": name, "t": text, "max": limit or 0, "ids": encoding.ids,
                                        "o": offsets(encoding, [text])}, ensure_ascii=False) + "\n")
                counts[f"{name} ({limit or 'sem corte'})"] = len(texts)
        pairs = {"pares longos": long_pairs, "escolhas": [(query(w), l) for w, labels in base_picks + real_picks
                                                          for l in labels + [modelo_server.NONE_LABEL]],
                 "pares aleatorios": list(zip(random_texts[::2], random_texts[1::2]))}
        for name, items in pairs.items():
            for limit in (64, 20, 5):
                tokenizer.enable_truncation(limit)
                for a, b in items:
                    encoding = tokenizer.encode(a, b)
                    f.write(json.dumps({"grupo": name, "a": a, "b": b, "max": limit, "ids": encoding.ids,
                                        "o": offsets(encoding, [a, b])}, ensure_ascii=False) + "\n")
                counts[f"{name} (par, {limit})"] = len(items)
    for name, n in counts.items():
        print(f"tokens: {name}: {n}")

    marker = modelo_server.load(f"{MODELS}/marcacao", "tabela")
    picker = modelo_server.load(f"{MODELS}/escolha", "tabela")
    texts = ([("pedido", t) for t in base_requests + real_requests]
             + [("tela", SEPARATOR.join(s)) for s in base_screens + real_screens]
             + [("caso", t) for t in edge + long_single])
    with open(f"{REFERENCE}/marcacao.jsonl", "w", encoding="utf-8") as f:
        for kind, text in texts:
            found, intent = marker.mark(text)
            f.write(json.dumps({"tipo": kind, "t": text, "itens": found, "intencao": intent}, ensure_ascii=False) + "\n")
    print(f"marcação: {len(texts)} textos")
    with open(f"{REFERENCE}/escolha.jsonl", "w", encoding="utf-8") as f:
        for wanted, labels in base_picks + real_picks:
            probs = picker.probabilities(wanted, labels)
            answer = picker.pick(wanted, labels)
            f.write(json.dumps({"wanted": wanted, "labels": labels, "p": [float(p) for p in probs],
                                "label": answer["label"], "ranking": answer["ranking"]}, ensure_ascii=False) + "\n")
    print(f"escolha: {len(base_picks) + len(real_picks)} pedidos")


# --- envio ao celular ---

FILES = {  # nome no aparelho -> arquivo no PC
    "marcacao.onnx": f"{MODELS}/marcacao/modelo-tabela.onnx",
    "marcacao.json": f"{MODELS}/marcacao/modelo.json",
    "escolha.onnx": f"{MODELS}/escolha/modelo-tabela.onnx",
    "escolha.json": f"{MODELS}/escolha/modelo.json",
    "tokenizador.bin": TOKENIZER,
}


def adb(*args):
    result = subprocess.run(["adb", *args], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"adb {args[0]} falhou: {(result.stderr or result.stdout).strip()[:200]}")
    return result.stdout


def send():
    """Copia os arquivos para files/modelos/ do app. Só reenvia o que mudou (tamanho diferente no aparelho)."""
    if not os.path.exists(TOKENIZER):
        prepare()
    adb("shell", "run-as", APP, "mkdir", "-p", "files/modelos")
    for name, path in FILES.items():
        size = os.path.getsize(path)
        there = adb("shell", "run-as", APP, "stat", "-c", "%s", f"files/modelos/{name}", "2>/dev/null", "||", "echo", "0")
        if there.strip() == str(size):
            print(f"{name}: já está no aparelho")
            continue
        temporary = f"/data/local/tmp/lmphone-{name}"
        adb("push", path, temporary)
        adb("shell", "run-as", APP, "cp", temporary, f"files/modelos/{name}")
        adb("shell", "rm", temporary)
        print(f"{name}: {size / 1e6:.0f} MB enviados")


BRIDGE_PORT = 8791
SERVICE = f"{APP}/.ModelService"


def start_service(threads):
    """Liga o ModelService (com `threads` núcleos por modelo; 0, todos) e espera os modelos carregarem. Os pedidos
    vão pelo mesmo canal do `device.AppDevice` (`adb exec-out` e `nc`, sem túnel)."""
    import time

    sys.path.insert(0, os.getcwd())
    from lmphone.device import AppDevice

    class ModelDevice(AppDevice):
        PORT = 8082  # ModelService.PORT

    adb("shell", "am", "start-foreground-service", "-n", SERVICE, "--ei", "threads", str(threads))
    device = ModelDevice()
    for _ in range(60):
        try:
            info = device.request("/", timeout=120)
            break
        except Exception:
            time.sleep(1)
    else:
        sys.exit("o ModelService não respondeu; veja o logcat (tag lmphone)")
    memory = device.request("/memoria")
    print(f"modelos no celular ({info['threads'] or 'todos os'} núcleos): carregados em {info['carga_s']:.1f} s; "
          f"memória do app {memory['pss_mb']} MB (nativa {memory['nativo_mb']} MB)", flush=True)
    return device


def stop_service(device):
    memory = device.request("/memoria")
    print(f"memória do app no fim: {memory['pss_mb']} MB (nativa {memory['nativo_mb']} MB)")
    # O am stopservice sai com erro mesmo quando para o serviço ("Service stopped").
    subprocess.run(["adb", "shell", "am", "stopservice", "-n", SERVICE], capture_output=True)


def measure(threads_list):
    """Tempo das chamadas no celular (o "seconds" medido no app, sem o adb), com os casos fictícios do conjunto
    congelado: uma volta para aquecer e outra medida, para cada número de núcleos."""
    sys.path.insert(0, os.getcwd())
    from lmphone.modelo import SEPARATOR
    requests, screens, picks = frozen()
    calls = ([("/judge", {"text": t}) for t in requests] + [("/entities", {"text": SEPARATOR.join(s)}) for s in screens]
             + [("/pick", {"wanted": w, "labels": l}) for w, l in picks[:80]])
    for threads in threads_list:
        device = start_service(threads)
        for path, body in calls[::4]:
            device.request(path, body, timeout=60)
        times = {}
        for path, body in calls:
            times.setdefault(path, []).append(device.request(path, body, timeout=60)["seconds"])
        for path, values in times.items():
            values.sort()
            print(f"  {path}: mediana {values[len(values) // 2] * 1000:.0f} ms, p90 {values[int(len(values) * .9)] * 1000:.0f} ms, "
                  f"máximo {values[-1] * 1000:.0f} ms ({len(values)} chamadas)", flush=True)
        stop_service(device)


def bridge(threads):
    """Liga o ModelService no celular e atende em 127.0.0.1:8791 como o `modelo_server`. O "seconds" da resposta é o
    tempo medido no celular, sem o adb."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    device = start_service(threads)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(device.request(self.path, timeout=60))

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            self.reply(device.request(self.path, body, timeout=60))

    print(f"ponte no ar em http://127.0.0.1:{BRIDGE_PORT} (Ctrl+C encerra e solta os modelos)", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_service(device)


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parser = argparse.ArgumentParser(description="Os modelos pequenos no app: preparar, referência, envio, ponte e medir")
    parser.add_argument("acao", choices=["preparar", "referencia", "enviar", "ponte", "medir"])
    parser.add_argument("--threads", type=int, nargs="+", default=[0],
                        help="núcleos por modelo no celular (0: o padrão do onnxruntime, todos); medir aceita vários")
    options = parser.parse_args()
    if options.acao == "ponte":
        bridge(options.threads[0])
    elif options.acao == "medir":
        measure(options.threads)
    else:
        {"preparar": prepare, "referencia": reference, "enviar": send}[options.acao]()


if __name__ == "__main__":
    main()
