"""O estado do aparelho que não depende da tela: Wi-Fi e rede, modo avião, Bluetooth, não perturbe, localização,
modo escuro e o que está tocando. Uma chamada ao adb (uns 0,5 s).

O plano é pedido sabendo esse estado, para o provedor ver quando a tarefa já está feita (o celular já na rede pedida),
e um objetivo `{"fact": {...}}` é conferido por aqui antes do primeiro passo e depois de cada um.
"""

import re
import subprocess
import unicodedata

COMMAND = ('cmd wifi status | grep -iE "^wifi is|connected to"; echo "#"; settings get global airplane_mode_on; '
           'settings get global bluetooth_on; settings get global zen_mode; settings get secure location_mode; '
           'settings get secure ui_night_mode; settings get global mode_ringer; echo "#"; dumpsys media_session | grep -E "package=|state=PlaybackState"; '
           # Volumes, brilho e letra (docs/plano-tutor.md): o que explica "tá mudo", "não escuto", "tela escura", "letra pequena".
           'echo "#"; cmd media_session volume --stream 3 --get; cmd media_session volume --stream 2 --get; '
           'settings get system screen_brightness; settings get system screen_brightness_mode; settings get system font_scale; '
           # A rotação automática e o tempo para a tela apagar (2026-11-19: a tela não mostra o estado deles, e os guias
           # de "girar" e de "a tela apaga" acabavam "conferido" sem nada mudar).
           'settings get system accelerometer_rotation; settings get system screen_off_timeout')
# Os fatos que são um número de 0 a 100 (por cento) e o que o `set` muda com um valor.
LEVELS = ("media_volume", "ring_volume", "brightness")
BRIGHTNESS_MAX = 255
LEVEL_SLACK = 10  # um objetivo de nível vale com até tantos pontos de diferença (a tela arredonda)

# O que pode ser objetivo. A mídia fica de fora: "tocando no YouTube Music" já vale antes de a música pedida tocar.
GOAL_KEYS = {"wifi", "airplane_mode", "bluetooth", "do_not_disturb", "location", "dark_mode", "font_scale", "sound_mode",
             "auto_rotate", "screen_timeout", *LEVELS}
# O modo de som do Android: em "vibrar" ou "mudo", as barras do toque e das notificações ficam travadas no zero
# (2026-11-18: a pessoa não conseguia mexer a bolinha, e o celular estava em Vibrar).
SOUND_MODES = {"0": "mudo", "1": "vibrar", "2": "som"}
SPOKEN_SOUND = {"mudo": "Mudo", "vibrar": "Vibrar", "som": "Som"}
# Um objetivo de nível ou de letra pode ser uma mudança em relação ao começo da tarefa ("up": maior, "down": menor): o
# aparelho compara com o estado que leu antes do primeiro passo (docs/plano-tutor.md: medir a mudança, não supor).
CHANGES = {"up": 1, "down": -1}
SCALES = ("font_scale", "screen_timeout", *LEVELS)
# Um volume "up" que sai do zero só vale audível (2026-11-18: o toque foi de 0 a 1 de 15, e o guia deu o sintoma do
# "não faz barulho" por resolvido): em %, como os níveis.
AUDIBLE = 20
VOLUMES = ("media_volume", "ring_volume")
SPOKEN_CHANGE = {"font_scale": ("letra maior", "letra menor"), "media_volume": ("volume da mídia mais alto", "volume da mídia mais baixo"),
                 "ring_volume": ("volume do toque mais alto", "volume do toque mais baixo"),
                 "brightness": ("tela mais clara", "tela mais escura"),
                 "screen_timeout": ("a tela demorando mais para apagar", "a tela apagando mais rápido")}


def plain(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold().strip()


def read(app_name=lambda package: package):
    """O estado atual, ou {} se o adb falhar. `app_name` traduz o pacote do que está tocando no nome do app."""
    try:
        out = subprocess.run(["adb", "shell", COMMAND], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse(out, app_name)


def parse(out, app_name=lambda package: package):
    parts = out.split("#\n") if "#\n" in out else out.split("#")
    if len(parts) < 3:
        return {}
    wifi, settings, media = parts[0], parts[1].split(), parts[2]
    found = {}
    network = re.search(r'connected to "([^"]*)"', wifi)
    if network:
        found["wifi"] = network.group(1)
    elif re.search(r"wifi is enabled", wifi, re.I):
        found["wifi"] = "on, not connected"
    elif re.search(r"wifi is disabled", wifi, re.I):
        found["wifi"] = "off"
    names = ("airplane_mode", "bluetooth", "do_not_disturb", "location", "dark_mode")
    for name, value in zip(names, settings):
        if value.lstrip("-").isdigit():
            number = int(value)
            found[name] = number == 2 if name == "dark_mode" else number != 0
    if len(settings) > len(names) and settings[len(names)] in SOUND_MODES:
        found["sound_mode"] = SOUND_MODES[settings[len(names)]]
    playing = None
    for block in re.split(r"\n\s*(?=package=)", media):
        package = re.search(r"package=(\S+)", block)
        if package and re.search(r"state=PlaybackState \{state=(?:PLAYING\(3\)|3\b)", block):
            playing = app_name(package.group(1))
    found["media_playing"] = playing or "nothing"
    if len(parts) > 3:
        found.update(levels(parts[3]))
    return found


def levels(out):
    """Volumes da mídia e do toque, brilho (em %), brilho automático e tamanho da letra, da saída do COMMAND."""
    found = {}
    for name, (value, low, high) in zip(("media_volume", "ring_volume"),
                                        re.findall(r"volume is (\d+) in range \[(\d+)\.\.(\d+)\]", out)):
        value, low, high = int(value), int(low), int(high)
        found[name] = round((value - low) * 100 / (high - low)) if high > low else 0
    rest = [line.strip() for line in out.splitlines() if line.strip() and not line.lstrip().startswith("[")]
    if len(rest) >= 5:
        rotation, timeout = rest[-2:]
        rest = rest[:-2]
        if rotation.isdigit():
            found["auto_rotate"] = rotation == "1"
        if timeout.isdigit():
            found["screen_timeout"] = int(timeout) // 1000
    if len(rest) >= 3:
        brightness, mode, scale = rest[-3:]
        if brightness.isdigit():
            found["brightness"] = min(100, round(int(brightness) * 100 / BRIGHTNESS_MAX))
        if mode.isdigit():
            found["auto_brightness"] = mode == "1"
        try:
            found["font_scale"] = float(scale)
        except ValueError:
            pass
    return found


def describe(facts):
    """O estado em uma linha, para o pedido ao provedor."""
    if not facts:
        return "unknown"
    words = {True: "on", False: "off"}
    return "; ".join(f"{key}: {value}%" if key in LEVELS else f"{key}: {value} (normal 1.0)" if key == "font_scale"
                     else f"{key}: {value} s" if key == "screen_timeout"
                     else f"{key}: {words.get(value, value)}" for key, value in facts.items())


# Como cada fato é dito ao dono: nome e se a palavra é feminina ("localização ligada").
SPOKEN = {"airplane_mode": ("modo avião", False), "bluetooth": ("Bluetooth", False), "do_not_disturb": ("Não perturbe", False),
          "location": ("localização", True), "dark_mode": ("modo escuro", False), "auto_rotate": ("giro automático da tela", False)}
SPOKEN_LEVELS = {"media_volume": "volume da mídia", "ring_volume": "volume do toque", "brightness": "brilho da tela"}


def speak(goal):
    """Um objetivo de fato em português, para a mensagem ao dono: "Wi-Fi na rede X", "modo avião desligado"."""
    parts = []
    for key, wanted in (goal or {}).items():
        on = wanted if isinstance(wanted, bool) else plain(str(wanted)) in ("on", "true")
        if key == "wifi":
            parts.append("Wi-Fi desligado" if wanted is False or plain(str(wanted)) == "off" else
                         "Wi-Fi ligado" if wanted is True or plain(str(wanted)) in ("on", "true") else f"Wi-Fi na rede {wanted}")
        elif key in SPOKEN_CHANGE and plain(str(wanted)) in CHANGES:
            parts.append(SPOKEN_CHANGE[key][0 if CHANGES[plain(str(wanted))] > 0 else 1])
        elif key in SPOKEN_LEVELS and isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
            parts.append(f"{SPOKEN_LEVELS[key]} em {round(wanted)}%")
        elif key == "sound_mode" and plain(str(wanted)) in SPOKEN_SOUND:
            parts.append(f"modo de som em {SPOKEN_SOUND[plain(str(wanted))]}")
        elif key in SPOKEN:
            name, feminine = SPOKEN[key]
            parts.append(f"{name} {'ligad' if on else 'desligad'}{'a' if feminine else 'o'}")
    return ", ".join(parts)


# Sufixo de faixa no fim do nome de uma rede ("Alamada 2g", "ALAMEDA-5G", "Casa_2.4GHz"), já sem espaço nem pontuação.
_BAND = re.compile(r"(2g|5g|24g|24ghz|5ghz|24|5)$")


def network_key(name):
    """O nome da rede sem caixa, acento, pontuação nem sufixo de faixa."""
    key = re.sub(r"\W|_", "", plain(str(name)))
    stripped = _BAND.sub("", key)
    return stripped if len(stripped) >= 3 else key


def distance(a, b):
    """Distância de edição (inserir, apagar, trocar uma letra)."""
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (x != y))
    return row[-1]


def same_network(wanted, actual):
    """O dono fala o nome da rede de memória: "Alamada 2g" é a ALAMEDA-5G em que o aparelho está. Vale o mesmo nome
    sem o sufixo de faixa, com até uma letra errada (duas em nome de 10 ou mais). "off" só vale com "off"."""
    a, b = network_key(wanted), network_key(actual)
    if a == b:
        return True
    if "off" in (a, b) or min(len(a), len(b)) < 5:
        return False
    return distance(a, b) <= (2 if min(len(a), len(b)) >= 10 else 1)


def changes(start, now):
    """O que mudou desde o começo da tarefa, em uma linha ("font_scale: 1.0 → 1.3"); "" se nada."""
    return "; ".join(f"{key}: {start[key]} → {value}" for key, value in (now or {}).items()
                     if key in (start or {}) and start[key] != value)


def told(start, now):
    """O que mudou num nível desde o começo, como se diz ("letra maior e tela mais clara"); "" se nada."""
    parts = []
    for key, (up, down) in SPOKEN_CHANGE.items():
        before, after = (start or {}).get(key), (now or {}).get(key)
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (before, after)) and before != after:
            parts.append(up if after > before else down)
    return " e ".join(parts)


def met(goal, facts, start=None):
    """True se cada fato do objetivo bate com o estado; None se o estado não foi lido ou o objetivo cita outra coisa.
    Um objetivo "up" ou "down" (letra, volume, brilho) compara com `start`, o estado do começo da tarefa."""
    goal = {k: v for k, v in (goal or {}).items() if k in GOAL_KEYS}
    if not goal or not facts or any(key not in facts for key in goal):
        return None
    for key, wanted in goal.items():
        value = facts[key]
        if key in SCALES and not isinstance(wanted, bool) and plain(str(wanted)) in CHANGES:
            if not start or key not in start or not isinstance(value, (int, float)) or not isinstance(start[key], (int, float)):
                return None
            if (value - start[key]) * CHANGES[plain(str(wanted))] <= 0:
                return False
            if key in VOLUMES and CHANGES[plain(str(wanted))] > 0 and value < AUDIBLE:
                return False
            continue
        if key == "font_scale":
            if isinstance(wanted, bool) or not isinstance(wanted, (int, float)) or not isinstance(value, (int, float)):
                return None
            if abs(value - wanted) > 0.05:
                return False
            continue
        if key in LEVELS:
            if isinstance(wanted, bool) or not isinstance(wanted, (int, float)):
                return None
            if abs(value - wanted) > LEVEL_SLACK:
                return False
            continue
        if isinstance(value, bool):
            if not isinstance(wanted, bool) and plain(str(wanted)) not in ("on", "off", "true", "false"):
                return None
            if value != (wanted if isinstance(wanted, bool) else plain(str(wanted)) in ("on", "true")):
                return False
        elif key == "wifi" and (wanted is True or plain(str(wanted)) in ("on", "true")):
            # "Wi-Fi ligado", sem rede: vale qualquer estado menos desligado (a ação `set` liga sem escolher rede).
            if plain(str(value)) == "off":
                return False
        elif key == "wifi" and wanted is False:
            if plain(str(value)) != "off":
                return False
        elif key == "sound_mode":
            if plain(str(value)) != plain(str(wanted)):
                return False
        else:
            # Nome de rede aproximado (2026-10-21): o provedor escrevia no objetivo o nome como o dono falou ("Alamada
            # 2g"), mesmo com o aparelho já na ALAMEDA-5G e o prompt mandando usar o nome da tela, e seguia procurando
            # uma rede "2G" até desistir. Quem decide agora é o código (`same_network`).
            if not same_network(wanted, value):
                return False
    return True
