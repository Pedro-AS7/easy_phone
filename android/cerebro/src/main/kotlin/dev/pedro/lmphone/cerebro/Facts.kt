package dev.pedro.lmphone.cerebro

/**
 * A tradução de `lmphone/facts.py`, menos a leitura pelo adb (no app, o estado vem das APIs do Android): o estado em
 * uma linha para o provedor, o objetivo dito ao dono, a comparação de nomes de rede e a conferência de um objetivo por
 * fato. Os valores do estado são `Boolean` ou texto, como no Python.
 */
object Facts {
    val GOAL_KEYS = Consts.strings("facts", "GOAL_KEYS").toSet()
    @Suppress("UNCHECKED_CAST")
    private val SPOKEN_SOUND = Consts.map("facts", "SPOKEN_SOUND").mapValues { (_, v) -> v as String }
    private val SPOKEN = Consts.map("facts", "SPOKEN").mapValues { (_, v) -> (v as List<Any?>).let { it[0] as String to it[1] as Boolean } }
    private val BAND = Consts.re("facts", "_BAND")
    val LEVELS = Consts.strings("facts", "LEVELS").toSet()  // os fatos de 0 a 100 (volume, brilho): docs/plano-tutor.md
    private val LEVEL_SLACK = Consts.d("facts", "LEVEL_SLACK")
    private val SPOKEN_LEVELS = Consts.map("facts", "SPOKEN_LEVELS").mapValues { (_, v) -> v as String }
    val CHANGES = Consts.map("facts", "CHANGES").mapValues { (_, v) -> (v as Number).toInt() }  // "up": 1, "down": -1
    private val SCALES = Consts.strings("facts", "SCALES").toSet()
    val AUDIBLE = Consts.i("facts", "AUDIBLE")  // um volume "up" que sai do zero só vale audível (em %)
    private val VOLUMES = Consts.strings("facts", "VOLUMES").toSet()
    @Suppress("UNCHECKED_CAST")
    private val SPOKEN_CHANGE = Consts.map("facts", "SPOKEN_CHANGE").mapValues { (_, v) -> (v as List<Any?>).map { it as String } }

    /** O que mudou desde o começo da tarefa, em uma linha ("font_scale: 1.0 → 1.3"); "" se nada. */
    fun changes(start: Map<String, Any?>?, now: Map<String, Any?>?): String =
        (now ?: emptyMap()).entries.filter { (key, value) -> start != null && key in start && !Py.eq(start[key], value) }
            .joinToString("; ") { (key, value) -> "$key: ${Py.str(start!![key])} → ${Py.str(value)}" }

    /** O que mudou num nível desde o começo, como se diz ("letra maior e tela mais clara"); "" se nada (como no Python). */
    fun told(start: Map<String, Any?>?, now: Map<String, Any?>?): String {
        val parts = mutableListOf<String>()
        for ((key, words) in SPOKEN_CHANGE) {
            val before = start?.get(key)
            val after = now?.get(key)
            if (before is Number && after is Number && before !is Boolean && after !is Boolean && before.toDouble() != after.toDouble()) {
                parts.add(if (after.toDouble() > before.toDouble()) words[0] else words[1])
            }
        }
        return parts.joinToString(" e ")
    }

    /** Um número do Python (int ou float, não bool), como Double; null se não é. */
    private fun number(value: Any?): Double? = if (value is Number) value.toDouble() else null
    private val NOT_WORD = Py.re("\\W|_")

    /** O estado em uma linha, para o pedido ao provedor. */
    fun describe(facts: Map<String, Any?>?): String {
        if (facts.isNullOrEmpty()) return "unknown"
        return facts.entries.joinToString("; ") { (key, value) ->
            if (key in LEVELS) "$key: ${Py.str(value)}%" else if (key == "font_scale") "$key: ${Py.str(value)} (normal 1.0)"
            else if (key == "screen_timeout") "$key: ${Py.str(value)} s"
            else "$key: ${when (value) { true -> "on"; false -> "off"; else -> Py.str(value) }}"
        }
    }

    private fun on(wanted: Any?) = Py.plain(Py.str(wanted)) in setOf("on", "true")

    /** Um objetivo de fato em português, para a mensagem ao dono: "Wi-Fi na rede X", "modo avião desligado". */
    fun speak(goal: Map<String, Any?>?): String {
        val parts = ArrayList<String>()
        for ((key, wanted) in goal ?: emptyMap()) {
            val isOn = if (wanted is Boolean) wanted else on(wanted)
            if (key == "wifi") {
                parts.add(when {
                    wanted == false || Py.plain(Py.str(wanted)) == "off" -> "Wi-Fi desligado"
                    wanted == true || on(wanted) -> "Wi-Fi ligado"
                    else -> "Wi-Fi na rede ${Py.str(wanted)}"
                })
            } else if (key in SPOKEN_CHANGE && Py.plain(Py.str(wanted)) in CHANGES) {
                parts.add(SPOKEN_CHANGE.getValue(key)[if (CHANGES.getValue(Py.plain(Py.str(wanted))) > 0) 0 else 1])
            } else if (key in SPOKEN_LEVELS && number(wanted) != null) {
                parts.add("${SPOKEN_LEVELS[key]} em ${Math.rint(number(wanted)!!).toLong()}%")
            } else if (key == "sound_mode" && Py.plain(Py.str(wanted)) in SPOKEN_SOUND) {
                parts.add("modo de som em ${SPOKEN_SOUND.getValue(Py.plain(Py.str(wanted)))}")
            } else {
                val (name, feminine) = SPOKEN[key] ?: continue
                parts.add("$name ${if (isOn) "ligad" else "desligad"}${if (feminine) "a" else "o"}")
            }
        }
        return parts.joinToString(", ")
    }

    /** O nome da rede sem caixa, acento, pontuação nem sufixo de faixa. */
    fun networkKey(name: Any?): String {
        val key = Py.sub(NOT_WORD, Py.plain(Py.str(name)), "")
        val stripped = Py.sub(BAND, key, "")
        return if (Py.len(stripped) >= 3) stripped else key
    }

    /** Distância de edição (inserir, apagar, trocar uma letra), em code points. */
    fun distance(a: String, b: String): Int {
        val x = a.codePoints().toArray()
        val y = b.codePoints().toArray()
        val row = IntArray(y.size + 1) { it }
        for (i in 1..x.size) {
            var previous = row[0]
            row[0] = i
            for (j in 1..y.size) {
                val here = row[j]
                row[j] = minOf(row[j] + 1, row[j - 1] + 1, previous + if (x[i - 1] != y[j - 1]) 1 else 0)
                previous = here
            }
        }
        return row[y.size]
    }

    /** O mesmo nome sem o sufixo de faixa, com até uma letra errada (duas em nome de 10 ou mais). */
    fun sameNetwork(wanted: Any?, actual: Any?): Boolean {
        val a = networkKey(wanted)
        val b = networkKey(actual)
        if (a == b) return true
        if ("off" == a || "off" == b || minOf(Py.len(a), Py.len(b)) < 5) return false
        return distance(a, b) <= if (minOf(Py.len(a), Py.len(b)) >= 10) 2 else 1
    }

    /** True se cada fato do objetivo bate com o estado; null se o estado não foi lido ou o objetivo cita outra coisa. */
    fun met(goal: Map<String, Any?>?, facts: Map<String, Any?>?, start: Map<String, Any?>? = null): Boolean? {
        val wantedFacts = (goal ?: emptyMap()).filterKeys { it in GOAL_KEYS }
        if (wantedFacts.isEmpty() || facts.isNullOrEmpty() || wantedFacts.keys.any { it !in facts }) return null
        for ((key, wanted) in wantedFacts) {
            val value = facts[key]
            if (key in SCALES && wanted !is Boolean && Py.plain(Py.str(wanted)) in CHANGES) {
                val before = start?.get(key)
                if (start == null || key !in start || number(value) == null || number(before) == null) return null
                if ((number(value)!! - number(before)!!) * CHANGES.getValue(Py.plain(Py.str(wanted))) <= 0) return false
                if (key in VOLUMES && CHANGES.getValue(Py.plain(Py.str(wanted))) > 0 && number(value)!! < AUDIBLE) return false
                continue
            }
            if (key == "font_scale") {
                val want = number(wanted) ?: return null
                if (Math.abs((number(value) ?: return null) - want) > 0.05) return false
                continue
            }
            if (key in LEVELS) {
                val want = number(wanted) ?: return null
                if (Math.abs((number(value) ?: return null) - want) > LEVEL_SLACK) return false
                continue
            }
            if (value is Boolean) {
                if (wanted !is Boolean && Py.plain(Py.str(wanted)) !in setOf("on", "off", "true", "false")) return null
                if (value != (if (wanted is Boolean) wanted else on(wanted))) return false
            } else if (key == "wifi" && (wanted == true || on(wanted))) {
                if (Py.plain(Py.str(value)) == "off") return false
            } else if (key == "wifi" && wanted == false) {
                if (Py.plain(Py.str(value)) != "off") return false
            } else if (key == "sound_mode") {
                if (Py.plain(Py.str(value)) != Py.plain(Py.str(wanted))) return false
            } else if (!sameNetwork(wanted, value)) {
                return false
            }
        }
        return true
    }
}
