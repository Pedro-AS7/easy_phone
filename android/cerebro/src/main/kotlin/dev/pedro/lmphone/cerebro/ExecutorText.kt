package dev.pedro.lmphone.cerebro

import java.util.regex.Pattern

/**
 * As funções de módulo de `lmphone/executor.py`: a tela em elementos, a tela reduzida dos pedidos de ajuda, as
 * comparações de rótulos, o mapa dos apps e o formato das chamadas de ferramenta. Os textos e as expressões regulares
 * vêm do Python (cerebro.json); os nomes seguem os do Python.
 */
object X {
    private const val M = "executor"
    val MAX_SCROLLS = Consts.i(M, "MAX_SCROLLS")
    val MAX_HELP = Consts.i(M, "MAX_HELP")
    val MAX_SAME_HELP = Consts.i(M, "MAX_SAME_HELP")
    val MAX_QUESTIONS = Consts.i(M, "MAX_QUESTIONS")
    val MAX_REVIEWS = Consts.i(M, "MAX_REVIEWS")
    val OWNER_LIMIT = Consts.d(M, "OWNER_LIMIT")
    val GUIDE_LIMIT = Consts.get(M, "GUIDE_LIMIT") as Number  // vai para o estado (`waiting`) como no Python: inteiro
    val GUIDE_REMIND = Consts.d(M, "GUIDE_REMIND")
    val GUIDE_REMINDER = Consts.s(M, "GUIDE_REMINDER")
    val GUIDE_REMINDER_ONLY = Consts.s(M, "GUIDE_REMINDER_ONLY")
    val POSITION = Consts.re(M, "_POSITION")
    val CUT_OFF = Consts.i(M, "CUT_OFF")
    val COVERED = Consts.d(M, "COVERED")
    val SLIDER = Consts.s(M, "SLIDER")
    val SLIDER_GAP = Consts.i(M, "SLIDER_GAP")
    val SLIDER_DOWN = Consts.s(M, "SLIDER_DOWN")
    val BAR_SAID = Consts.re(M, "_BAR_SAID")
    val SLIDER_DOWN_AT = Consts.i(M, "SLIDER_DOWN_AT")
    val SYSTEM_PANEL = Consts.s(M, "SYSTEM_PANEL")
    val GUIDE_WORDS = Consts.i(M, "GUIDE_WORDS")
    private val SENTENCE = Consts.re(M, "_SENTENCE")
    /** A explicação do provedor com o que o executor junta a ela; acima de GUIDE_WORDS palavras, só a primeira frase dela. */
    /** Uma explicação acima de GUIDE_WORDS palavras: as frases inteiras do começo que cabem, ao menos uma (como no Python). */
    fun short(text: String): String {
        if (Py.split(text).size <= GUIDE_WORDS) return text
        val out = mutableListOf<String>()
        for (sentence in SENTENCE.split(Py.strip(text))) {
            if (out.isNotEmpty() && Py.split((out + sentence).joinToString(" ")).size > GUIDE_WORDS) break
            out.add(sentence)
        }
        return out.joinToString(" ")
    }

    fun fit(explain: String, extra: String): String {
        val joined = "$explain $extra"
        if (Py.split(joined).size <= GUIDE_WORDS) return joined
        var first = SENTENCE.split(Py.strip(explain), 2)[0]
        if (Py.split("$first $extra").size > GUIDE_WORDS) {
            // A primeira frase sozinha já passa: até a primeira vírgula (como no Python).
            val head = first.split(", ", limit = 2)[0].trimEnd('.', '!', '?', ':', ';')
            if (Py.split(head).size >= 3) first = "$head."
        }
        return "$first $extra"
    }
    val FLIP_SLACK = Consts.i(M, "FLIP_SLACK")
    val EXPANDERS = Consts.strings(M, "EXPANDERS").toSet()
    val SPLIT_SHADE = Consts.re(M, "SPLIT_SHADE")
    val PULL_RIGHT = Consts.s(M, "PULL_RIGHT")
    val SHADE_ONLY_SAY = Consts.s(M, "SHADE_ONLY_SAY")
    /** A cortina das notificações aberta, sem os atalhos (os blocos do painel rápido). */
    fun shadeOnly(raw: String) = "com.android.systemui" in raw && "notification_stack_scroller" in raw && "TileIcon" !in raw
    val GUIDE_REMINDER_GESTURE: Map<String, String> = Consts.map(M, "GUIDE_REMINDER_GESTURE").mapValues { (_, v) -> v as String }
    val OWNER_QUIET = Consts.d(M, "OWNER_QUIET")
    val TOUCH_LATE = Consts.d(M, "TOUCH_LATE")
    val TOUCH_READS = Consts.i(M, "TOUCH_READS")
    val TOUCH_GAP = Consts.d(M, "TOUCH_GAP")
    val ONLY_GUIDE = Consts.s(M, "ONLY_GUIDE")
    val ONLY_GUIDE_HELP = Consts.s(M, "ONLY_GUIDE_HELP")
    val BUTTON_SETTINGS = Consts.s(M, "BUTTON_SETTINGS")
    val BUTTON_APP = Consts.s(M, "BUTTON_APP")
    val SCROLL_FOR = Consts.s(M, "SCROLL_FOR")
    val KEEP_SCROLLING_GUIDE = Consts.s(M, "KEEP_SCROLLING_GUIDE")
    val AGAIN_SCROLL = Consts.s(M, "AGAIN_SCROLL")
    val LOST_WAIT = Consts.s(M, "LOST_WAIT")
    val BUTTON_DEAD = Consts.d(M, "BUTTON_DEAD")
    val DEAD_TOUCH = Consts.d(M, "DEAD_TOUCH")
    val BUTTON_DEAD_SAY = Consts.s(M, "BUTTON_DEAD_SAY")
    val GUIDE_REMINDER_BUTTON = Consts.s(M, "GUIDE_REMINDER_BUTTON")
    val WRONG_SPOT = Consts.s(M, "WRONG_SPOT")
    val UNDO = Consts.s(M, "UNDO")
    val UNDONE = Consts.s(M, "UNDONE")
    val STATE_WORDS = Consts.strings(M, "STATE_WORDS").toSet()
    val BACK_NAMES = Consts.strings(M, "BACK_NAMES").toSet()
    val SWITCH_WORDS = Consts.re(M, "_SWITCH_WORDS")
    val WRONG_SPOT_BLIND = Consts.s(M, "WRONG_SPOT_BLIND")
    val SEEN_MAX = Consts.i(M, "SEEN_MAX")
    val SCREEN_NAMES = Consts.i(M, "SCREEN_NAMES")
    val QUOTED_NAME = Consts.re(M, "_QUOTED_NAME")
    val KEEP_SCROLLING = Consts.d(M, "KEEP_SCROLLING")
    val KEEP_SCROLLING_LIMIT = Consts.d(M, "KEEP_SCROLLING_LIMIT")
    val SEARCH_LABEL = Consts.i(M, "SEARCH_LABEL")
    val LOOKAHEAD = Consts.i(M, "LOOKAHEAD")
    val MAX_DEPTH = Consts.i(M, "MAX_DEPTH")
    val MAX_WAITS = Consts.i(M, "MAX_WAITS")
    val FEW_LABELS = Consts.i(M, "FEW_LABELS")
    val MAX_LABEL = Consts.i(M, "MAX_LABEL")
    val HIDDEN = Consts.s(M, "HIDDEN")
    val USER_BLOCK = Consts.s(M, "USER_BLOCK")
    val CONFIRM = Consts.strings(M, "CONFIRM").toSet()
    val CONFIRM_START = Consts.strings(M, "CONFIRM_START")
    val SENSITIVE = Consts.re(M, "SENSITIVE")
    val YES_WORDS = Consts.strings(M, "YES_WORDS").toSet()
    val NO_WORDS = Consts.strings(M, "NO_WORDS").toSet()
    val PLAIN_WORDS = Consts.strings(M, "PLAIN_WORDS").toSet()
    val NUMBER = Consts.re(M, "_NUMBER")
    val EDITABLE = Consts.strings(M, "EDITABLE")
    val ACTIONS = Consts.strings(M, "ACTIONS").toSet()
    val DIRECT = Consts.strings(M, "DIRECT").toSet()
    val SCREENS = Consts.s(M, "SCREENS")
    @Suppress("UNCHECKED_CAST")
    val SET_SCREENS: Map<String, Pair<String, List<String>>> = Consts.map(M, "SET_SCREENS").mapValues { (_, v) ->
        (v as List<Any?>).let { it[0] as String to (it[1] as List<Any?>).map { label -> label as String } }
    }
    val SET_SCREENS_OFF: Map<String, List<String>> = Consts.map(M, "SET_SCREENS_OFF").mapValues { (_, v) -> (v as List<*>).map { it as String } }
    @Suppress("UNCHECKED_CAST")
    val SET_ROUTES: Map<String, Pair<String, List<List<String>>>> = Consts.map(M, "SET_ROUTES").mapValues { (_, v) ->
        (v as List<Any?>).let { it[0] as String to (it[1] as List<Any?>).map { labels -> (labels as List<*>).map { label -> label as String } } }
    }
    val QUOTES: List<Pair<String, String>> = (Consts.get(M, "QUOTES") as List<*>).map { (it as List<*>).let { q -> q[0] as String to q[1] as String } }
    val SOUND_MODE_WORDS: Map<String, String> = Consts.map(M, "SOUND_MODE_WORDS").mapValues { (_, v) -> v as String }
    val SOUND_MODES: Map<String, List<String>> = Consts.map(M, "SOUND_MODES").mapValues { (_, v) -> (v as List<*>).map { it as String } }
    val HOW_TO = Consts.re(M, "HOW_TO")
    val SETTINGS_PAGES = Consts.strings(M, "SETTINGS_PAGES")
    val SETTINGS_WAY: Map<String, List<String>> = Consts.map(M, "SETTINGS_WAY").mapValues { (_, v) -> (v as List<*>).map { it as String } }
    val TOOL_ERROR = Consts.re(M, "_TOOL_ERROR")
    val STATE = Consts.re(M, "_STATE")
    val ELEMENT = Consts.re(M, "_ELEMENT")
    val SPLIT = Consts.s(M, "SPLIT")
    val PLAN_PROMPT = Consts.s(M, "PLAN_PROMPT")
    val ASK_OPTION = Consts.s(M, "ASK_OPTION")
    val NO_ASK_OPTION = Consts.s(M, "NO_ASK_OPTION")
    val NO_HISTORY = Consts.s(M, "NO_HISTORY")
    val SEARCH_OPTION = Consts.s(M, "SEARCH_OPTION")
    val SEARCHED = Consts.s(M, "SEARCHED")
    val GUIDE_HELP = Consts.s(M, "GUIDE_HELP")
    val NO_SCREEN = Consts.s(M, "NO_SCREEN")
    val PROMISE = Consts.re(M, "PROMISE")
    val SOUND_SYMPTOM = Consts.re(M, "SOUND_SYMPTOM")
    val NEAR_PREFIX = Consts.i(M, "NEAR_PREFIX")
    val NEAR_TAIL = Consts.i(M, "NEAR_TAIL")
    val PROMISED = Consts.s(M, "PROMISED")
    val HELP_PROMPT = Consts.s(M, "HELP_PROMPT")
    val ASK = Consts.s(M, "ASK")
    val ASK_NOW = Consts.s(M, "ASK_NOW")
    val REVIEW = Consts.s(M, "REVIEW")
    val KNOWN_HELP = Consts.s(M, "KNOWN_HELP")
    val MAX_KNOWN = Consts.i(M, "MAX_KNOWN")

    private val HEAD = Py.re("\\*\\*(App|Keyboard|Focused Element):\\*\\* *(.*)")
    private val DIGIT = Py.re("\\d")
    private val WORDS = Py.re("\\w+")
    private val WORDS4 = Py.re("[^\\W\\d_]{4,}")
    private val SAID = Py.re("[\\w.-]+")
    private val IDENTIFIER = Py.re("[A-Z0-9]+(?:_[A-Z0-9]+)+")

    /** `plain` do executor: só aceita texto (no Python, outro tipo levanta TypeError). */
    fun plain(text: Any?): String = Py.plain(text as? String ?: throw TypeError("plain() argument must be str"))

    /** O texto de um controle cujo toque não se desfaz (SENSITIVE). */
    fun sensitive(text: String): Boolean {
        val squeezed = Py.squeeze(plain(text))
        return Py.split(squeezed).size in 1..4 && Py.match(SENSITIVE, squeezed) != null
    }

    /** A resposta a uma confirmação: true (sim), false (não) ou null (nem um nem outro: vale como instrução). */
    fun yesNo(text: String?): Boolean? {
        val words = Py.findallText(WORDS, plain(text ?: ""))
        if (words.isEmpty() || words.size > 4 || !(YES_WORDS + NO_WORDS + PLAIN_WORDS).containsAll(words)) return null
        if (words[0] in NO_WORDS || "nao" in words) return false
        return if (words[0] in YES_WORDS) true else null
    }

    /** O passo vai além dos ajustes do sistema: abre outro app que não as Configurações, ou lê um valor. */
    fun leavesSettings(step: Map<String, Any?>): Boolean {
        if (step["action"] == "read") return true
        val target = step["target"]
        val names = if (target is List<*>) Py.iter(Py.or(target, emptyList<Any?>())).map { plain(Py.str(it)) }.toSet()
        else setOf(plain(Py.str(target)))
        return step["action"] == "open_app" && names.none { it in setOf("settings", "configuracoes", "ajustes") }
    }

    /** `text` aparece em `label` como palavra ou frase inteira, e não como pedaço de outra palavra. */
    fun mentions(text: String, label: String): Boolean {
        val squeezed = Py.squeeze(plain(text))
        if (squeezed.isEmpty()) return false
        return Py.compile("(?<!\\w)" + Py.escape(squeezed) + "(?!\\w)").matcher(Py.squeeze(plain(label))).find()
    }

    /** Para o objetivo da tarefa: uma palavra só precisa ser o rótulo inteiro; uma frase pode ser parte dele. */
    fun matches(text: Any?, label: String): Boolean =
        plain(text) == plain(label) || Py.split(plain(text)).size > 1 && mentions(text as String, label)

    /** O que distingue uma tela de outra: app, teclado, foco, textos e estados marcados. */
    fun signature(elements: List<Element>, raw: String): List<Any?> {
        val head = Py.findall(HEAD, raw)
        val marks = elements.filter { it.text.isNotEmpty() || it.checked != null }
            .map { listOf(it.text, Py.str(it.checked)) }
            .sortedWith { a, b -> Py.ORDER.compare(a[0], b[0]).takeIf { it != 0 } ?: Py.ORDER.compare(a[1], b[1]) }
        return listOf(head, marks)
    }

    /** Elementos da última tela (`<device_state>`) de uma mensagem, e o texto dela. */
    fun parseScreen(text: String): Pair<List<Element>, String> {
        val states = Py.findallText(STATE, text)
        val elements = ArrayList<Element>()
        for (line in Py.splitlines(states.lastOrNull() ?: "")) {
            val m = Py.fullmatch(ELEMENT, line.trimEnd { Py.isSpace(it.code) }) ?: continue
            val cls = m.group(2)
            val parts = m.group(3).split("\", \"").map { Py.strip(it, "\"") }
            val texts = parts.filter { ":id/" !in it && !it.endsWith(".$cls") }
            elements.add(Element(m.group(1).toLong(), cls, texts, when (m.group(4)) { "True" -> true; "False" -> false; else -> null },
                (5..8).map { m.group(it).toLong() }, parts.filter { ":id/" in it }))
        }
        return elements to (states.lastOrNull()?.let { Py.strip(it) } ?: "")
    }

    /** A chave da página das Configurações de um passo, também pelo nome dela no menu (como no Python). */
    fun settingsPage(page: String): String {
        if (page in SETTINGS_PAGES) return page
        val name = plain(page)
        if (name.replace(" ", "_") in SETTINGS_PAGES) return name.replace(" ", "_")
        val named = SETTINGS_PAGES.filter { key -> !SETTINGS_WAY[key].isNullOrEmpty() && plain(SETTINGS_WAY.getValue(key).last()) == name }
        if ("connections" in named) return "connections"
        return named.firstOrNull() ?: page
    }

    /**
     * A tela sem os ícones da barra de status (Não perturbar, vibração, bateria), que aparecem com o painel aberto e
     * não reagem a um toque: ImageView ou View sem id, pequenos, no alto da tela, no app da interface do sistema.
     */
    fun statusIcons(elements: List<Element>, raw: String): List<Element> {
        val app = Py.splitlines(raw).firstOrNull { "**App:**" in it } ?: ""
        if ("com.android.systemui" !in app) return elements
        val bottom = elements.maxOfOrNull { it.bounds[3] } ?: 0L
        fun icon(e: Element) = e.ids.isEmpty() && e.cls in setOf("ImageView", "View") && e.bounds[3] * 100 <= bottom * 8 &&
            (e.bounds[3] - e.bounds[1]) * 100 <= bottom * 4
        return elements.filterNot { icon(it) }
    }

    /**
     * A tela como vai num pedido de ajuda: só rótulos curtos. Textos longos somem e números de 3 ou mais dígitos viram
     * "#"; na página de resultados de uma pesquisa (`limit` maior, `numbers` falso) o texto vai inteiro.
     */
    fun redact(raw: String, limit: Int = MAX_LABEL, numbers: Boolean = true): String {
        val number = { m: java.util.regex.Matcher ->
            val hide = numbers && Py.findall(DIGIT, m.group()).size >= 3
            if (hide) Py.sub(DIGIT, m.group(), "#") else m.group()
        }
        val lines = ArrayList<String>()
        for (original in Py.splitlines(raw)) {
            var line = original
            val m = Py.fullmatch(ELEMENT, line.trimEnd { Py.isSpace(it.code) })
            if (m != null) {
                val cls = m.group(2)
                val parts = m.group(3).split("\", \"").toMutableList()
                for ((i, part) in parts.withIndex()) {
                    var text = Py.strip(part, "\"")
                    if (":id/" in text || text.endsWith(".$cls")) continue
                    text = if (Py.len(text) > limit) HIDDEN else Py.sub(NUMBER, text, number)
                    parts[i] = (if (part.startsWith("\"")) "\"" else "") + text + (if (part.endsWith("\"")) "\"" else "")
                }
                line = line.substring(0, m.start(3)) + parts.joinToString("\", \"") + line.substring(m.end(3))
            } else if (Py.len(line) > limit || Py.search(NUMBER, line) != null) {
                line = if (Py.len(Py.strip(line)) > limit) HIDDEN else Py.sub(NUMBER, line, number)
            }
            lines.add(line)
        }
        return lines.joinToString("\n")
    }

    /** Onde a execução está no app: (app, rótulos tocados desde a abertura), ou null. */
    fun position(trail: List<Map<String, Any?>>): Pair<String, List<Any?>>? {
        var app: String? = null
        var path: List<Any?> = emptyList()
        for (step in trail) {
            val action = step["action"]
            when {
                action == "open_app" -> {
                    app = plain((step["target"] as List<*>)[0])
                    path = emptyList()
                }
                action == "open_settings" -> {
                    // A página aberta direto fica no mapa onde ela está no menu (como no Python).
                    app = "settings"
                    path = SETTINGS_WAY[Py.str(Py.iter(Py.or(step["target"], listOf<Any?>(""))).firstOrNull() ?: "")] ?: emptyList()
                }
                action == "back" -> path = path.dropLast(1)
                action == "tap" && "at" in step -> app = null
                action == "tap" && !Py.truthy(step["noop"]) && step["if_missing"] != "skip" ->
                    path = path + listOf((step["target"] as List<*>)[0])
            }
        }
        return if (Py.truthy(app)) app!! to path else null
    }

    /** Todos os nomes do mapa dos apps (tocados, chaves e vistos nas telas), como `executor.map_names`. */
    @Suppress("UNCHECKED_CAST")
    fun mapNames(tree: Map<String, Any?>?): Set<String> {
        val out = HashSet<String>()
        fun walk(node: Map<String, Any?>) {
            ((node["controls"] as List<*>? ?: emptyList<Any?>()) + (node["seen"] as List<*>? ?: emptyList<Any?>())).forEach { out.add(plain(it)) }
            (node["children"] as Map<String, Any?>? ?: emptyMap()).forEach { (label, child) ->
                out.add(plain(label))
                walk(child as Map<String, Any?>)
            }
        }
        (tree ?: emptyMap()).values.forEach { walk(it as Map<String, Any?>) }
        return out
    }

    @Suppress("UNCHECKED_CAST")
    fun nodeAt(tree: Map<String, Any?>, place: Pair<String, List<Any?>>?): Map<String, Any?>? {
        var node = if (place != null) tree[place.first] as Map<String, Any?>? else null
        if (node != null) {
            for (label in place!!.second) {
                node = (node!!["children"] as Map<String, Any?>)[label as String] as Map<String, Any?>? ?: return null
            }
        }
        return node
    }

    /** Caminho mais curto, a partir de `node`, até um toque (ou a tela de uma chave) com rótulo em `wanted`. */
    @Suppress("UNCHECKED_CAST")
    fun search(node: Map<String, Any?>, wanted: Set<String>, control: Boolean): List<String>? {
        val queue = ArrayDeque<Pair<Map<String, Any?>, List<String>>>()
        queue.add(node to emptyList())
        while (queue.isNotEmpty()) {
            val (here, path) = queue.removeFirst()
            if (control && path.isNotEmpty() && (here["controls"] as List<*>? ?: emptyList<Any?>()).any { plain(it) in wanted }) return path
            for ((label, child) in here["children"] as Map<String, Any?>) {
                if (!control && plain(label) in wanted) return path + label
                if (path.size + 1 < MAX_DEPTH) queue.add(child as Map<String, Any?> to path + label)
            }
        }
        return null
    }

    /** Os apps do mapa de que o pedido fala: pelo nome do app ou por uma palavra de algum rótulo dele. */
    @Suppress("UNCHECKED_CAST")
    fun related(tree: Map<String, Any?>, task: String): Map<String, Any?> {
        fun words(text: String) = Py.findallText(WORDS4, plain(text)).toSet()
        fun labels(node: Map<String, Any?>): List<String> =
            (node["controls"] as List<*>? ?: emptyList<Any?>()).map { it as String } +
                (node["seen"] as List<*>? ?: emptyList<Any?>()).map { it as String } +
                (node["children"] as Map<String, Any?>).flatMap { (label, child) -> listOf(label) + labels(child as Map<String, Any?>) }
        val asked = words(task)
        return tree.filter { (app, node) ->
            (words(app) intersect asked).isNotEmpty() ||
                (asked intersect labels(node as Map<String, Any?>).flatMap { words(it) }.toSet()).isNotEmpty()
        }
    }

    /** O mapa dos apps como texto para o provedor: um rótulo por linha, recuado pela profundidade. */
    @Suppress("UNCHECKED_CAST")
    fun render(tree: Map<String, Any?>, only: String? = null): String {
        fun lines(node: Map<String, Any?>, depth: Int): List<String> {
            val out = ArrayList<String>()
            (node["controls"] as List<*>? ?: emptyList<Any?>()).forEach { out.add("${"  ".repeat(depth)}[switch] ${Py.str(it)}") }
            val seen = node["seen"] as List<*>?
            if (!seen.isNullOrEmpty()) out.add("${"  ".repeat(depth)}(also on this screen: ${seen.joinToString("; ") { Py.str(it) }})")
            for ((label, child) in node["children"] as Map<String, Any?>) {
                out.add("${"  ".repeat(depth)}$label")
                out.addAll(lines(child as Map<String, Any?>, depth + 1))
            }
            return out
        }
        fun text(apps: Collection<String>) = apps.flatMap { app -> listOf("App $app:") + lines(tree[app] as Map<String, Any?>, 1) }
            .joinToString("\n")
        if (tree.isEmpty()) return "none yet."
        var known = text(tree.keys)
        if (Py.len(known) > MAX_KNOWN && Py.truthy(only) && plain(only) in tree) known = text(listOf(plain(only)))
        return "\n" + Py.head(known, MAX_KNOWN) + KNOWN_HELP
    }

    /** Nomes do pedido que estão na tela com outra grafia, comparados com os valores reais. */
    fun closeNames(task: String, labels: List<String>): String {
        val words = Py.findallText(SAID, task)
        val found = LinkedHashMap<String, List<String>>()
        for (size in listOf(3, 2, 1)) {
            for (i in 0..words.size - size) {
                val said = words.subList(i, i + size).joinToString(" ")
                if (Py.len(Facts.networkKey(said)) < 5 || found.keys.any { said in it }) continue
                val hits = labels.distinct().filter { Py.len(it) <= 40 && plain(said) != plain(it) && Facts.sameNetwork(said, it) }
                if (hits.isNotEmpty()) found[said] = hits.take(3)
            }
        }
        if (found.isEmpty()) return ""
        return "\nNames the owner used that are on this screen with another spelling: " +
            found.entries.take(3).joinToString("; ") { (said, hits) -> "«$said» is " + hits.joinToString(" or ") { "«$it»" } }
    }

    /** Uma chamada de ferramenta, no formato de texto que o aparelho lê. */
    fun call(name: String, vararg params: Pair<String, Any?>): String {
        val body = params.joinToString("\n") { (key, value) -> "<parameter name=\"$key\">${Py.str(value)}</parameter>" }
        return "<function_calls>\n<invoke name=\"$name\">\n$body\n</invoke>\n</function_calls>"
    }

    fun parseJson(text: String): Any? {
        val start = text.indexOf('{')
        val end = text.lastIndexOf('}')
        if (start < 0 || end < 0) throw IllegalArgumentException("substring not found")
        return Json.parse(if (end + 1 > start) text.substring(start, end + 1) else "")
    }

    fun isIdentifier(text: String) = Py.fullmatch(IDENTIFIER, text) != null

    /** A chave de um texto para o cache: as palavras, sem caixa nem acento. */
    fun words(text: String): List<String> = Py.findallText(WORDS, text)
}

/** Um elemento da tela (`Element` do Python). */
data class Element(val index: Long, val cls: String, val texts: List<String>, val checked: Boolean?, val bounds: List<Long>,
                   val ids: List<String> = emptyList()) {
    val text: String get() = texts.lastOrNull() ?: ""
}

class TypeError(message: String) : RuntimeException(message)

/** `str.format` do Python com campos por nome (`{device}`), e `{{` `}}` para as chaves. */
fun pyFormat(template: String, values: Map<String, Any?>): String {
    val out = StringBuilder()
    var i = 0
    while (i < template.length) {
        val c = template[i]
        when {
            c == '{' && i + 1 < template.length && template[i + 1] == '{' -> {
                out.append('{')
                i += 2
            }
            c == '}' && i + 1 < template.length && template[i + 1] == '}' -> {
                out.append('}')
                i += 2
            }
            c == '{' -> {
                val end = template.indexOf('}', i)
                val name = template.substring(i + 1, end)
                if (name !in values) throw IllegalArgumentException("KeyError: '$name'")
                out.append(Py.str(values[name]))
                i = end + 1
            }
            else -> {
                out.append(c)
                i++
            }
        }
    }
    return out.toString()
}

/** Compilar sem guardar (padrões montados a cada chamada). */
fun Py.compile(pattern: String, flags: String = ""): Pattern {
    var options = 0
    if ('i' in flags) options = options or Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE
    if ('s' in flags) options = options or Pattern.DOTALL
    if ('m' in flags) options = options or Pattern.MULTILINE
    return Pattern.compile(translate(pattern), options)
}

/** O que `for x in value` percorre no Python: a lista, as chaves do dicionário ou os caracteres do texto. */
fun Py.iter(value: Any?): List<Any?> = when (value) {
    is List<*> -> value
    is Map<*, *> -> value.keys.toList()
    is String -> value.codePoints().toArray().map { String(Character.toChars(it)) }
    is Set<*> -> value.toList()
    else -> throw TypeError("'${value?.javaClass?.simpleName}' object is not iterable")
}
