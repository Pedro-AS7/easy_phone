"""A palavra de ativação no app ("Alexa", docs/plano-app-android.md), do lado do PC.

- `baixar`: os modelos do openWakeWord (https://github.com/dscripka/openWakeWord, versão 0.5.1 dos modelos) em
  data/modelos/escuta/: o espectrograma mel, o `speech_embedding` do Google e o detector da palavra. Confere o sha256.
- `referencia`: frases de teste faladas pelas vozes do Windows (System.Speech, pt-BR e en-US, em três velocidades),
  com e sem a palavra, em data/escuta/teste/ (16 kHz, com 2 s de chiado antes e 1 s depois), e a nota da biblioteca
  do openWakeWord (no `.venv-modelo`, instalada sem as dependências do treino) a cada 80 ms de cada uma, em
  data/escuta/referencia.json. A conferência em Kotlin (`android\\gradlew.bat :modelos:conferirEscuta`) refaz as notas
  com o `WakeWord` do app. As frases são escritas aqui, sem nada do celular.
- `enviar`: copia os três modelos para files/escuta/ do app no celular.
- `testar`: frases "Alexa, <comando>" (a palavra pela voz em inglês, o resto pela em português, emendados como quem
  fala de uma vez) tocadas no app no lugar do microfone (`WakeTest`), sem tarefa em curso: confere a palavra, o som
  passado ao reconhecedor do aparelho e o comando entendido, pelo logcat. Com nomes, só aquelas frases; `pedido` é
  um pedido de verdade ("abre a calculadora"), que vai ao cérebro escolhido no app.

Uso: .venv-modelo/Scripts/python.exe -m tools.app.escuta baixar | referencia | enviar | testar [frases...]
"""

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import types
import urllib.request
import wave

from tools.app.modelos import APP, adb

DIR = "data/modelos/escuta"
RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
MODELS = {
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    "alexa_v0.1.onnx": "6ff566a01d12670e8d9e3c59da32651db1575d17272a601b7f8a39283dfbae3e",
}
WAKE = "alexa_v0.1.onnx"  # o detector que o app usa (no aparelho, files/escuta/palavra.onnx)
ON_PHONE = {"melspectrogram.onnx": "melspectrogram.onnx", "embedding_model.onnx": "embedding_model.onnx", WAKE: "palavra.onnx"}

TESTS = "data/escuta/teste"
REFERENCE = "data/escuta/referencia.json"
RATE = 16000
CHUNK = 1280  # 80 ms: o passo da biblioteca e do app
BEFORE, AFTER = 2.0, 1.0  # segundos de chiado em volta da frase

VOICES = {"pt": "Microsoft Maria Desktop", "en": "Microsoft Zira Desktop"}
SPEEDS = (-2, 0, 2)
WITH = [
    ("pt", "Alexa"),
    ("pt", "Alexa, abre o Waze"),
    ("pt", "Alexa, que horas são?"),
    ("pt", "Ei Alexa, toca uma música no YouTube Music"),
    ("pt", "Alexa, liga a lanterna"),
    ("en", "Alexa"),
    ("en", "Alexa, what time is it?"),
]
WITHOUT = [
    ("pt", "Alessandra, vem cá"),
    ("pt", "A lista de compras está na mesa"),
    ("pt", "Alex, abre a porta"),
    ("pt", "Olá, tudo bem com você?"),
    ("pt", "Abre a calculadora"),
    ("pt", "O Alexandre chegou cedo"),
    ("pt", "Relaxa, vai dar tudo certo"),
    ("pt", "A lâmpada da sala queimou"),
    ("pt", "Eu quero uma pizza de calabresa"),
    ("pt", "Aleatoriamente"),
    ("en", "Alex, open the door"),
    ("en", "A next step"),
]


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def download():
    os.makedirs(DIR, exist_ok=True)
    for name, digest in MODELS.items():
        path = f"{DIR}/{name}"
        if not os.path.exists(path) or sha256(path) != digest:
            urllib.request.urlretrieve(RELEASE + name, path)
        if sha256(path) != digest:
            os.remove(path)
            sys.exit(f"{name}: o sha256 não confere com o da versão 0.5.1")
        print(f"{name}: {os.path.getsize(path) / 1e6:.1f} MB, sha256 conferido")


def library():
    """O `Model` do openWakeWord. A biblioteca foi instalada sem as dependências (`pip install --no-deps
    openwakeword==0.6.0`): as do treino e do download (scipy, sklearn, tqdm, requests) o `Model` não usa, e entram como
    módulos vazios."""
    for name in ("requests", "tqdm", "scipy", "sklearn", "sklearn.linear_model", "sklearn.pipeline", "sklearn.preprocessing"):
        try:
            importlib.import_module(name)
        except ImportError:
            module = types.ModuleType(name)
            module.__getattr__ = lambda attribute: None
            sys.modules[name] = module
    from openwakeword.model import Model
    return Model


def speak(voice, speed, text, path):
    """A frase falada por uma voz do Windows, em WAV de 16 kHz, 16 bits, mono."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{voice}'); $s.Rate = {speed};"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
        "$s.SetOutputToWaveFile($env:LMPHONE_WAV, $f); $s.Speak($env:LMPHONE_TEXTO); $s.Dispose()"
    )
    env = dict(os.environ, LMPHONE_WAV=os.path.abspath(path), LMPHONE_TEXTO=text)
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True, capture_output=True)


def padded(path, rng):
    """A frase com chiado baixo antes e depois (um microfone nunca dá zero), cortada em pedaços de 80 ms."""
    import numpy as np
    with wave.open(path, "rb") as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (RATE, 1, 2), path
        speech = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    noise = lambda seconds: rng.integers(-30, 31, int(seconds * RATE)).astype(np.int16)
    audio = np.concatenate((noise(BEFORE), speech, noise(AFTER)))
    audio = audio[:len(audio) // CHUNK * CHUNK]
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(audio.tobytes())
    return audio


def reference():
    if sys.platform != "win32":
        sys.exit("referencia usa as vozes do Windows (System.Speech); rode na máquina da RTX")
    import numpy as np
    download()
    Model = library()
    os.makedirs(TESTS, exist_ok=True)
    rng = np.random.default_rng(17)
    clips = []
    for has, phrases in ((True, WITH), (False, WITHOUT)):
        for language, text in phrases:
            for speed in (SPEEDS if language == "pt" else (0,)):
                name = f"{'com' if has else 'sem'}-{len(clips):02d}"
                path = f"{TESTS}/{name}.wav"
                speak(VOICES[language], speed, text, path)
                audio = padded(path, rng)
                # Um Model novo por frase, como o app ao voltar a ouvir.
                model = Model(wakeword_models=[f"{DIR}/{WAKE}"], inference_framework="onnx",
                              melspec_model_path=f"{DIR}/melspectrogram.onnx",
                              embedding_model_path=f"{DIR}/embedding_model.onnx")
                key = next(iter(model.models))
                scores = [float(model.predict(audio[i:i + CHUNK])[key]) for i in range(0, len(audio), CHUNK)]
                clips.append({"nome": name, "texto": text, "voz": language, "velocidade": speed, "tem_palavra": has,
                              "notas": scores})
                print(f"{name} {'com' if has else 'sem'} {language} {speed:+d} max {max(scores):.3f}  {text}")
    with open(REFERENCE, "w", encoding="utf-8") as f:
        json.dump({"modelos": {name: MODELS[name] for name in MODELS}, "pedaco": CHUNK, "clipes": clips}, f,
                  ensure_ascii=False)
    hits = sum(max(c["notas"]) >= 0.5 for c in clips if c["tem_palavra"])
    false = sum(max(c["notas"]) >= 0.5 for c in clips if not c["tem_palavra"])
    total = sum(c["tem_palavra"] for c in clips)
    print(f"{REFERENCE}: {len(clips)} frases; com a palavra, {hits} de {total} acima de 0,5; sem, {false} de "
          f"{len(clips) - total} acima de 0,5")


def send():
    download()
    adb("shell", "run-as", APP, "mkdir", "-p", "files/escuta")
    for name, there in ON_PHONE.items():
        temporary = f"/data/local/tmp/lmphone-{there}"
        adb("push", f"{DIR}/{name}", temporary)
        adb("shell", "run-as", APP, "cp", temporary, f"files/escuta/{there}")
        adb("shell", "rm", temporary)
        print(f"{name}: enviado como files/escuta/{there}")


COMMANDS = "data/escuta/comandos"
# (nome, o que vem depois de "Alexa", o comando esperado no logcat). Sem tarefa, o painel é quem ouve.
SPOKEN = [
    ("silencio", "silêncio", "MUTE"),
    ("voz", "liga a voz", "UNMUTE"),
    ("repete", "repete", "REPEAT"),
    ("fecha", "fecha", "CLOSE"),
    ("pausa", "pausa", "pedido"),  # sem tarefa, "pausa" é um pedido (pausar a música), e o teste o fecha antes de ir
]
REQUEST = ("pedido", "abre a calculadora", "pedido")


def joined(after, path, rng):
    """ "Alexa" (voz em inglês) e a frase (em português) com 150 ms entre elas, chiado antes e 2,5 s depois."""
    import numpy as np
    parts = []
    for voice, text in (("en", "Alexa"), ("pt", after)):
        speak(VOICES[voice], 0, text, path)
        with wave.open(path, "rb") as f:
            audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
        nonzero = np.flatnonzero(np.abs(audio) > 300)  # sem o silêncio que a voz põe antes e depois
        parts.append(audio[nonzero[0]:nonzero[-1] + 1])
    noise = lambda seconds: rng.integers(-30, 31, int(seconds * RATE)).astype(np.int16)
    audio = np.concatenate((noise(1.0), parts[0], noise(0.15), parts[1], noise(2.5)))
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(audio.tobytes())


def logcat_lines():
    out = subprocess.run(["adb", "logcat", "-d", "-s", "lmphone:*"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    return [line for line in out.splitlines()
            if "lmphone" in line and any(k in line for k in ("escuta", "voz", "faixa", "painel"))]


def close_panel():
    adb("shell", "am", "broadcast", "-n", f"{APP}/.WakeTest", "--ez", "fechar", "true")


def test(names):
    import time
    import numpy as np
    if sys.platform != "win32":
        sys.exit("testar usa as vozes do Windows (System.Speech); rode na máquina da RTX")
    os.makedirs(COMMANDS, exist_ok=True)
    rng = np.random.default_rng(23)
    cases = [case for case in SPOKEN + [REQUEST] if case[0] in names] if names else SPOKEN
    adb("shell", "run-as", APP, "mkdir", "-p", "files/escuta/teste")
    for name, after, _ in cases:
        path = f"{COMMANDS}/{name}.wav"
        joined(after, path, rng)
        temporary = f"/data/local/tmp/lmphone-{name}.wav"
        adb("push", path, temporary)
        adb("shell", "run-as", APP, "cp", temporary, f"files/escuta/teste/{name}.wav")
        adb("shell", "rm", temporary)
    passed = 0
    for name, after, expected in cases:
        subprocess.run(["adb", "logcat", "-c"])
        adb("shell", "am", "broadcast", "-n", f"{APP}/.WakeTest", "--es", "arquivo", f"teste/{name}.wav")
        heard, started = None, time.monotonic()
        while time.monotonic() - started < 15 and heard is None:
            time.sleep(0.3)
            heard = next((line for line in logcat_lines() if "voz (" in line), None)
        if heard and expected == "pedido" and name != REQUEST[0]:
            close_panel()  # antes de o pedido ir sozinho
        time.sleep(1.0)
        lines = logcat_lines()
        ok = heard is not None and f": {expected}," in heard
        passed += ok
        print(f"{'ok ' if ok else 'ERRO'} Alexa, {after}  (esperado {expected})")
        for line in lines:
            print("     " + line.split(": ", 1)[-1])
        if name != REQUEST[0]:
            close_panel()
        time.sleep(2.5)
    print(f"{passed} de {len(cases)} frases com o comando esperado")


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parser = argparse.ArgumentParser(description="A palavra de ativação no app: baixar, referência, envio e teste")
    parser.add_argument("acao", choices=["baixar", "referencia", "enviar", "testar"])
    parser.add_argument("nomes", nargs="*", help="com testar: só estas frases (pedido: um pedido de verdade)")
    options = parser.parse_args()
    if options.acao == "testar":
        test(options.nomes)
    else:
        {"baixar": download, "referencia": reference, "enviar": send}[options.acao]()


if __name__ == "__main__":
    main()
