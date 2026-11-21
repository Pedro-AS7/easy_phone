package dev.pedro.lmphone.cerebro

import java.io.File
import java.util.IdentityHashMap

/**
 * A conferência do executor pelas trilhas que o Python grava (lmphone/trilha.py): cada chamada parte do estado gravado
 * antes dela, os pedidos de fora (provedor, modelo de escolha, fatos, relógio...) são respondidos com o que foi gravado
 * e conferidos (o prompt inteiro, letra a letra), e no fim o valor devolvido e o estado inteiro têm de ser iguais.
 */
object Trilhas {
    /** Marca de uma função (callback) presente no estado. */
    object Fn

    class Mismatch(message: String) : RuntimeException(message)

    // --- o estado do executor, no mesmo JSON do Python ---

    @Suppress("UNCHECKED_CAST")
    private val ATTRS: List<Triple<String, (Executor) -> Any?, (Executor, Any?) -> Unit>> = listOf(
        a("task", { it.task }) { e, v -> e.task = v as String },
        a("provider", { it.provider }) { _, _ -> },
        a("pick", { it.pick }) { _, _ -> },
        a("device", { it.device }) { e, v -> e.device = v as String },
        a("settings", { it.settings }) { _, _ -> },
        a("setter", { it.setter }) { _, _ -> },
        a("history", { it.history }) { e, v -> e.history = v as String },
        a("assistant", { it.assistant }) { e, v -> e.assistant = v as Boolean },
        a("replied", { it.replied }) { e, v -> e.replied = v as String? },
        a("looking", { it.looking }) { e, v -> e.looking = v as Boolean },
        a("looked", { it.looked }) { e, v -> e.looked = v as Boolean },
        a("opening", { it.opening }) { e, v -> e.opening = v as MutableMap<String, Any?>? },
        a("announce", { it.announce }) { e, v -> e.announce = v as String? },
        a("guide", { it.guide }) { e, v -> e.guide = v as Boolean },
        a("guide_waited", { it.guideWaited }) { e, v -> e.guideWaited = v },
        a("was_met", { it.wasMet }) { e, v -> e.wasMet = v as Boolean? },
        a("speaking", { it.speaking }) { e, v -> e.speaking = v as Boolean },
        a("searching", { it.searching }) { e, v -> e.searching = v as String? },
        a("searched", { it.searched }) { e, v -> e.searched = v as Boolean },
        a("searcher", { it.searcher }) { _, _ -> },
        a("rolling", { it.rolling }) { e, v -> e.rolling = (v as Number?)?.toDouble() },
        a("rolled", { it.rolled }) { e, v -> e.rolled = v as Boolean },
        a("read_value", { it.readValue }) { e, v -> e.readValue = v as String? },
        a("final", { it.final }) { e, v -> e.final = v as String? },
        a("owner", { it.owner }) { e, v -> e.owner = v as Boolean },
        a("waiting", { it.waiting }) { e, v -> e.waiting = v as MutableMap<String, Any?>? },
        a("highlight", { it.highlight }) { e, v -> e.highlight = (v as List<*>?)?.map { (it as Number).toLong() } },
        a("owner_steps", { it.ownerSteps }) { e, v -> e.ownerSteps = (v as Number).toInt() },
        a("gesture", { it.gesture }) { e, v -> e.gesture = v as String? },
        a("guide_agent", { it.guideAgent }) { e, v -> e.guideAgent = v as Boolean },
        a("acts", { it.actsOnPhone }) { e, v -> e.actsOnPhone = v as Boolean },
        a("button", { it.button }) { e, v -> e.button = v as Map<String, Any?>? },
        a("last_said", { it.lastSaid }) { e, v -> e.lastSaid = v as String? },
        a("reminded_step", { it.remindedStep }) { e, v -> e.remindedStep = (v as Number?)?.toInt() },
        a("lost", { it.lost }) { e, v -> e.lost = v as String? },
        a("quick", { it.quick }) { e, v -> e.quick = v as Boolean },
        a("rerouting", { it.rerouting }) { e, v -> e.rerouting = v as Boolean },
        a("no_buttons", { it.noButtons }) { e, v -> e.noButtons = v as Boolean },
        a("unmet_asked", { it.unmetAsked }) { e, v -> e.unmetAsked = v as Boolean },
        a("seen", { it.seen }) { e, v -> e.seen = (v as List<*>).map { it as String }.toMutableList() },
        a("off_names", { it.offNames }) { e, v -> e.offNames = (v as List<*>).map { it as String } },
        a("pressed_at", { it.pressedAt }) { e, v -> e.pressedAt = (v as Number?)?.toDouble() },
        a("touched_text", { it.touchedText }) { e, v -> e.touchedText = v as String? },
        a("touched_text_at", { it.touchedTextAt }) { e, v -> e.touchedTextAt = (v as Number?)?.toDouble() },
        a("touched_box", { it.touchedBox }) { e, v -> e.touchedBox = (v as List<*>?)?.map { (it as Number).toLong() } },
        a("touched_at", { it.touchedAt }) { e, v -> e.touchedAt = (v as Number?)?.toDouble() },
        a("nudged", { it.nudged }) { e, v -> e.nudged = v as Boolean },
        a("start_state", { it.startState }) { e, v -> e.startState = v as Map<String, Any?>? },
        a("confirming", { it.confirming }) { e, v -> e.confirming = v as MutableMap<String, Any?>? },
        a("approved", { it.approved }) { e, v -> e.approved = v as List<Any?>? },
        a("declined", { it.declined }) { e, v -> e.declined = v },
        a("preapproved", { it.preapproved }) { e, v -> e.preapproved = v as Boolean },
        a("facts", { it.facts }) { _, _ -> },
        a("state", { it.state }) { e, v -> e.state = v as Map<String, Any?> },
        a("early", { it.early }) { e, v -> e.early = v as Map<String, Any?>? },
        a("acted", { it.acted }) { e, v -> e.acted = v as Boolean },
        a("repeats", { it.repeats }) { e, v -> e.repeats = (v as Set<*>).map { it as List<Any?> }.toMutableSet() },
        a("flagged", { it.flagged }) { e, v -> e.flagged = (v as Set<*>).map { it as List<Any?> }.toMutableSet() },
        a("last_key", { it.lastKey }) { e, v -> e.lastKey = v as List<Any?>? },
        a("message", { it.message }) { e, v -> e.message = v as String },
        a("raw", { it.raw }) { e, v -> e.raw = v as String },
        a("instructions", { it.instructions }) { e, v -> e.instructions = (v as List<*>).map { it as String }.toMutableList() },
        a("can_ask", { it.canAsk }) { e, v -> e.canAsk = v as Boolean },
        a("may_ask", { it.mayAsk }) { e, v -> e.mayAsk = v as Boolean },
        a("questions", { it.questions }) { e, v -> e.questions = (v as Number).toInt() },
        a("question", { it.question }) { e, v -> e.question = v as MutableMap<String, Any?>? },
        a("answers", { it.answers }) { e, v -> e.answers = (v as List<*>).map { pair -> (pair as List<*>).map { it as String } }.toMutableList() },
        a("opened", { it.opened }) { e, v -> e.opened = v as String? },
        a("tried", { it.tried }) { e, v -> e.tried = (v as List<Any?>).toMutableList() },
        a("stuck", { it.stuck }) { e, v -> e.stuck = v as MutableMap<String, Any?> },
        a("launch", { it.launch }) { _, _ -> },
        a("plan", { it.plan }) { e, v -> e.plan = (v as List<*>?)?.map { it as Step }?.toMutableList() },
        a("goal", { it.goal }) { e, v -> e.goal = v as MutableMap<String, Any?>? },
        a("i", { it.i }) { e, v -> e.i = (v as Number).toInt() },
        a("scrolls", { it.scrolls }) { e, v -> e.scrolls = (v as Number).toInt() },
        a("swiped", { it.swiped }) { e, v -> e.swiped = v as List<Any?>? },
        a("pending", { it.pending }) { e, v -> e.pending = v as Step? },
        a("helps", { it.helps }) { e, v -> e.helps = (v as Number).toInt() },
        a("waited", { it.waited }) { e, v -> e.waited = v as Boolean },
        a("waits", { it.waits }) { e, v -> e.waits = (v as Number).toInt() },
        a("asked", { it.asked }) { e, v -> e.asked = (v as Number?)?.toInt() },
        a("torn", { it.torn }) { e, v -> e.torn = v as List<Any?>? },
        a("elements", { it.elements }) { e, v -> e.elements = (v as List<*>).map { it as Element } },
        a("labels", { it.labels }) { e, v -> e.labels = (v as List<*>).map { it as String } },
        a("now", { it.now }) { e, v -> e.now = v as List<Any?>? },
        a("sign", { it.sign }) { e, v -> e.sign = v as List<Any?>? },
        a("before", { it.before }) { e, v -> e.before = (v as Set<*>).map { it as String }.toMutableSet() },
        a("start", { it.start }) { e, v -> e.start = (v as Set<*>?)?.map { it as String }?.toMutableSet() },
        a("guess", { it.guess }) { e, v -> e.guess = v as Boolean },
        a("focused", { it.focused }) { e, v -> e.focused = (v as Number?)?.toInt() },
        a("blind", { it.blind }) { e, v -> e.blind = v as Boolean },
        a("again", { it.again }) { e, v -> e.again = (v as Number?)?.toInt() },
        a("goal_asked", { it.goalAsked }) { e, v -> e.goalAsked = v as Boolean },
        a("switched", { it.switched }) { e, v -> e.switched = v as Boolean },
        a("confirmed", { it.confirmed }) { e, v -> e.confirmed = v as Boolean },
        a("map", { it.map }) { e, v -> e.map = v as Map<String, Any?> },
        a("tapped", { it.tapped }) { e, v -> e.tapped = v as MutableMap<String, Any?>? },
        a("trail_len", { it.trailLen }) { e, v -> e.trailLen = (v as Number).toInt() },
        a("trail", { it.trail }) { e, v -> e.trail = (v as List<*>).map { it as MutableMap<String, Any?> }.toMutableList() },
        a("cacheable", { it.cacheable }) { e, v -> e.cacheable = v as Boolean },
        a("tool_error", { it.toolError }) { e, v -> e.toolError = v as String? },
        a("result", { it.result }) { e, v -> e.result = v as String? },
        a("by", { it.by }) { e, v -> e.by = v as String },
        a("choices", { it.choices }) { e, v -> e.choices = (v as List<*>).map { it as MutableMap<String, Any?> }.toMutableList() },
        a("noted", { it.noted }) { e, v -> e.noted = v as MutableMap<String, Any?>? },
        a("choice", { it.choice }) { e, v -> e.choice = v as MutableMap<String, Any?>? },
        a("app", { it.app }) { e, v -> e.app = v as String? },
        a("cached", { it.cached }) { e, v -> e.cached = v as Boolean },
        a("reviewed", { it.reviewed }) { e, v -> e.reviewed = v as Boolean },
        a("reviews", { it.reviews }) { e, v -> e.reviews = (v as Number).toInt() },
    )

    private fun a(name: String, get: (Executor) -> Any?, set: (Executor, Any?) -> Unit) = Triple(name, get, set)

    /** Do JSON gravado para valores do Kotlin: os dicionários compartilhados voltam a ser o mesmo objeto. */
    @Suppress("UNCHECKED_CAST")
    fun decode(value: Any?, ids: MutableMap<Long, Any?> = HashMap()): Any? = when (value) {
        is Map<*, *> -> when {
            "\$ref" in value -> ids[value["\$ref"] as Long]
            "\$id" in value -> {
                val out = LinkedHashMap<String, Any?>()
                ids[value["\$id"] as Long] = out
                for ((k, v) in value["\$v"] as Map<String, Any?>) out[k] = decode(v, ids)
                out
            }
            "\$set" in value -> (value["\$set"] as List<Any?>).map { decode(it, ids) }.toCollection(LinkedHashSet())
            "\$el" in value -> (value["\$el"] as List<Any?>).let {
                Element((it[0] as Number).toLong(), it[1] as String, (it[2] as List<*>).map { t -> t as String }, it[3] as Boolean?,
                    (it[4] as List<*>).map { b -> (b as Number).toLong() }, (it[5] as List<*>).map { t -> t as String })
            }
            "\$fn" in value -> Fn
            else -> LinkedHashMap<String, Any?>().also { out -> for ((k, v) in value) out[k as String] = decode(v, ids) }
        }
        is List<*> -> value.map { decode(it, ids) }.toCollection(ArrayList())
        else -> value
    }

    private fun count(value: Any?, counts: IdentityHashMap<Any, Int>) {
        when (value) {
            is Map<*, *> -> {
                counts[value] = (counts[value] ?: 0) + 1
                if (counts[value] == 1) value.values.forEach { count(it, counts) }
            }
            is Pair<*, *> -> count(value.toList(), counts)
            is Collection<*> -> value.forEach { count(it, counts) }
        }
    }

    /** Dos valores do Kotlin para o JSON do Python (o mesmo algoritmo de lmphone/trilha.encode). */
    fun encode(value: Any?, memo: IdentityHashMap<Any, Int> = IdentityHashMap(), counts: IdentityHashMap<Any, Int>? = null): Any? = when (value) {
        is Element -> linkedMapOf("\$el" to listOf(value.index, value.cls, value.texts, value.checked, value.bounds, value.ids))
        is Map<*, *> -> {
            val known = memo[value]
            if (known != null) {
                linkedMapOf("\$ref" to known.toLong())
            } else {
                val shared = counts != null && (counts[value] ?: 0) > 1
                if (shared) memo[value] = memo.size
                val body = LinkedHashMap<String, Any?>()
                for ((k, v) in value) body[k.toString()] = encode(v, memo, counts)
                if (shared) linkedMapOf("\$id" to memo[value]!!.toLong(), "\$v" to body) else body
            }
        }
        is Set<*> -> linkedMapOf("\$set" to value.map { encode(it, memo, counts) }.sortedWith { x, y -> Py.ORDER.compare(canonical(x), canonical(y)) })
        is Pair<*, *> -> listOf(encode(value.first, memo, counts), encode(value.second, memo, counts))
        is List<*> -> value.map { encode(it, memo, counts) }
        is Function<*> -> linkedMapOf("\$fn" to true)
        is Int -> value.toLong()
        else -> value
    }

    /** `json.dumps(sort_keys=True)`. */
    fun canonical(value: Any?): String = Json.dumps(sortKeys(value))

    private fun sortKeys(value: Any?): Any? = when (value) {
        is Map<*, *> -> value.entries.sortedWith { x, y -> Py.ORDER.compare(x.key.toString(), y.key.toString()) }
            .associateTo(LinkedHashMap()) { (k, v) -> k.toString() to sortKeys(v) }
        is List<*> -> value.map { sortKeys(it) }
        else -> value
    }

    fun dump(executor: Executor): Map<String, Any?> {
        val values = ATTRS.map { it.second(executor) }
        val counts = IdentityHashMap<Any, Int>()
        values.forEach { count(it, counts) }
        val memo = IdentityHashMap<Any, Int>()
        return ATTRS.indices.associateTo(LinkedHashMap()) { ATTRS[it].first to encode(values[it], memo, counts) }
    }

    /** Igualdade estrita (ordem das chaves inclusive), com 1 == 1.0 como no Python. */
    fun same(a: Any?, b: Any?): Boolean = when {
        a is Map<*, *> && b is Map<*, *> -> a.keys.toList() == b.keys.toList() && a.keys.all { same(a[it], b[it]) }
        a is List<*> && b is List<*> -> a.size == b.size && a.indices.all { same(a[it], b[it]) }
        a is Number && b is Number -> Py.eq(a, b)
        else -> a == b
    }

    // --- a reprodução ---

    class Outcome(val ok: Boolean, val problem: String? = null)

    @Suppress("UNCHECKED_CAST")
    fun replay(entry: Map<String, Any?>): Outcome {
        val executor = Executor("", null, null)
        val ids = HashMap<Long, Any?>()
        val before = entry["before"] as Map<String, Any?>
        for ((name, _, set) in ATTRS) set(executor, decode(before[name], ids).takeIf { it !== Fn })
        val events = ArrayDeque((entry["events"] as List<Any?>).map { it as Map<String, Any?> })

        fun answer(name: String, args: List<Any?>): Any? {
            val event = events.removeFirstOrNull() ?: throw Mismatch("pediu $name a mais (o Python não pediu)")
            if (event["cb"] != name) throw Mismatch("pediu $name, o Python pediu ${event["cb"]}")
            if (name != "clock" && !same(encode(args), event["args"])) {
                throw Mismatch("pediu $name com outros argumentos:\n  kotlin: ${Json.dumps(encode(args))}\n  python: ${Json.dumps(event["args"])}")
            }
            if ("raise" in event) throw RuntimeException("${event["raise"]} (gravado)")
            return decode(event["ret"])
        }
        if (before["provider"] != null) executor.provider = { answer("provider", listOf(it)) as String }
        if (before["pick"] != null) executor.pick = { wanted, labels -> answer("pick", listOf(wanted, labels)) }
        if (before["launch"] != null) executor.launch = { answer("launch", listOf(it)) as Boolean }
        if (before["facts"] != null) executor.facts = { answer("facts", emptyList()) as Map<String, Any?>? }
        if (before["settings"] != null) executor.settings = { answer("settings", listOf(it)) as Boolean }
        if (before["setter"] != null) executor.setter = { name, value -> answer("setter", listOf(name, value)) }
        if (before["searcher"] != null) executor.searcher = { answer("searcher", listOf(it)) as Boolean }
        executor.clock = { (answer("clock", emptyList()) as Number).toDouble() }

        val args = decode(entry["args"]) as List<Any?>
        val kwargs = decode(entry["kwargs"]) as Map<String, Any?>
        val result: Any?
        try {
            result = when (entry["call"]) {
                "step" -> executor.step(args[0] as String)
                "prepare" -> executor.prepare()
                "use" -> executor.use(Py.iter(args[0]), args.getOrNull(1) ?: kwargs["goal"])
                "confirm_answer" -> executor.confirmAnswer(args[0] as String?)
                else -> return Outcome(false, "chamada desconhecida ${entry["call"]}")
            }
        } catch (e: Mismatch) {
            return Outcome(false, e.message)
        } catch (e: Exception) {
            if ("raise" !in entry) return Outcome(false, "o Kotlin levantou ${e.javaClass.simpleName}: ${e.message}\n${e.stackTrace.take(6).joinToString("\n") { "    $it" }}")
            return compareState(executor, entry, events)
        }
        if ("raise" in entry) return Outcome(false, "o Python levantou ${entry["raise"]}, o Kotlin não")
        val returned = if (result is Unit) null else result
        if (!same(encode(returned), entry["ret"])) {
            return Outcome(false, "devolveu outra coisa:\n  kotlin: ${Json.dumps(encode(returned))}\n  python: ${Json.dumps(entry["ret"])}")
        }
        return compareState(executor, entry, events)
    }

    @Suppress("UNCHECKED_CAST")
    private fun compareState(executor: Executor, entry: Map<String, Any?>, events: ArrayDeque<Map<String, Any?>>): Outcome {
        if (events.isNotEmpty()) return Outcome(false, "o Python pediu ${events.first()["cb"]} e o Kotlin não")
        val after = entry["after"] as Map<String, Any?>
        val mine = dump(executor)
        val differs = mine.keys.filter { !same(mine[it], after[it]) }
        if (differs.isEmpty()) return Outcome(true)
        return Outcome(false, "estado diferente em ${differs.joinToString(", ")}:\n" + differs.take(3).joinToString("\n") {
            "  $it\n    kotlin: ${Py.head(Json.dumps(mine[it]), 600)}\n    python: ${Py.head(Json.dumps(after[it]), 600)}"
        })
    }

    // --- as funções do módulo ---

    @Suppress("UNCHECKED_CAST")
    fun function(entry: Map<String, Any?>): Outcome {
        val args = decode(entry["args"]) as List<Any?>
        val kwargs = decode(entry["kwargs"]) as Map<String, Any?>
        fun arg(n: Int, name: String): Any? = if (n < args.size) args[n] else kwargs[name]
        fun has(n: Int, name: String) = n < args.size || name in kwargs
        val value: Any? = try {
            when (entry["fn"]) {
                "executor.plain" -> X.plain(arg(0, "text"))
                "executor.sensitive" -> X.sensitive(arg(0, "text") as String)
                "executor.yes_no" -> X.yesNo(arg(0, "text") as String?)
                "executor.leaves_settings" -> X.leavesSettings(arg(0, "step") as Map<String, Any?>)
                "executor.mentions" -> X.mentions(arg(0, "text") as String, arg(1, "label") as String)
                "executor.matches" -> X.matches(arg(0, "text"), arg(1, "label") as String)
                "executor.signature" -> X.signature(arg(0, "elements") as List<Element>, arg(1, "raw") as String)
                "executor.parse_screen" -> X.parseScreen(arg(0, "text") as String)
                "executor.redact" -> X.redact(arg(0, "raw") as String, if (has(1, "limit")) (arg(1, "limit") as Number).toInt() else X.MAX_LABEL,
                    if (has(2, "numbers")) arg(2, "numbers") as Boolean else true)
                "executor.position" -> X.position(arg(0, "trail") as List<Map<String, Any?>>)?.toList()
                "executor.node_at" -> X.nodeAt(arg(0, "tree") as Map<String, Any?>, (arg(1, "place") as List<Any?>?)?.let { it[0] as String to it[1] as List<Any?> })
                "executor.search" -> X.search(arg(0, "node") as Map<String, Any?>, (arg(1, "wanted") as Collection<*>).map { it as String }.toSet(), arg(2, "control") as Boolean)
                "executor.related" -> X.related(arg(0, "tree") as Map<String, Any?>, arg(1, "task") as String)
                "executor.render" -> X.render(arg(0, "tree") as Map<String, Any?>, arg(1, "only") as String?)
                "executor.close_names" -> X.closeNames(arg(0, "task") as String, (arg(1, "labels") as List<*>).map { it as String })
                "executor.call" -> X.call(arg(0, "name") as String, *kwargs.filterKeys { it != "name" }.map { it.key to it.value }.toTypedArray())
                "executor.parse_json" -> X.parseJson(arg(0, "text") as String)
                "facts.describe" -> Facts.describe(arg(0, "facts") as Map<String, Any?>?)
                "facts.speak" -> Facts.speak(arg(0, "goal") as Map<String, Any?>?)
                "facts.network_key" -> Facts.networkKey(arg(0, "name"))
                "facts.distance" -> Facts.distance(arg(0, "a") as String, arg(1, "b") as String).toLong()
                "facts.same_network" -> Facts.sameNetwork(arg(0, "wanted"), arg(1, "actual"))
                "facts.met" -> Facts.met(arg(0, "goal") as Map<String, Any?>?, arg(1, "facts") as Map<String, Any?>?,
                    arg(2, "start") as Map<String, Any?>?)
                "device.elements_of" -> DeviceText.elementsOf(arg(0, "state") as Map<String, Any?>)
                "device.one_line" -> DeviceText.oneLine(arg(0, "text") as String)
                "device.render" -> DeviceText.render(arg(0, "state") as Map<String, Any?>, arg(1, "elements") as List<Map<String, Any?>>)
                "device.uncovered" -> DeviceText.uncovered((arg(0, "bounds") as List<*>).map { (it as Number).toLong() },
                    (arg(1, "blockers") as List<*>).map { b -> (b as List<*>).map { (it as Number).toLong() } })
                "device.point" -> DeviceText.point(arg(0, "element") as Map<String, Any?>, (arg(1, "width") as Number?)?.toLong(),
                    (arg(2, "height") as Number?)?.toLong())
                "device.parse_call" -> DeviceText.parseCall(arg(0, "text") as String).let { (name, params) -> listOf(name, params) }
                "difflib.get_close_matches" -> Difflib.closeMatches(arg(0, "word") as String, (arg(1, "possibilities") as List<*>).map { it as String },
                    if (has(2, "n")) (arg(2, "n") as Number).toInt() else 3, if (has(3, "cutoff")) (arg(3, "cutoff") as Number).toDouble() else 0.6)
                "Executor.read" -> Executor("", null, null).read(arg(0, "step") as Map<String, Any?>, (arg(1, "labels") as List<*>).map { it as String })
                "Executor.guided" -> Executor.guided(arg(0, "steps"))
                "Executor.find" -> Executor.find(arg(0, "step") as Map<String, Any?>, arg(1, "elements") as List<Element>)
                "Executor.control" -> Executor.control(arg(0, "target") as Element, arg(1, "elements") as List<Element>)
                "Executor.flips" -> Executor.flips(arg(0, "target") as Element, arg(1, "elements") as List<Element>)
                "Executor.checked" -> Executor.checked(arg(0, "target") as Element, arg(1, "elements") as List<Element>)
                "Executor.locate" -> Executor("", null, null).locate(arg(0, "at") as Map<String, Any?>, arg(1, "elements") as List<Element>)
                "Executor.locator" -> Executor("", null, null).locator(arg(0, "element") as Element?, arg(1, "elements") as List<Element>)
                "Executor.visible" -> Executor("", null, null).visible(arg(0, "texts") as List<Any?>, (arg(1, "labels") as List<*>).map { it as String })
                else -> return Outcome(false, "função desconhecida ${entry["fn"]}")
            }
        } catch (e: Exception) {
            if ("raise" in entry) return Outcome(true)
            return Outcome(false, "o Kotlin levantou ${e.javaClass.simpleName}: ${e.message}")
        }
        if ("raise" in entry) return Outcome(false, "o Python levantou ${entry["raise"]}, o Kotlin não")
        if (!same(encode(value), entry["ret"])) {
            return Outcome(false, "devolveu outra coisa:\n  kotlin: ${Py.head(Json.dumps(encode(value)), 800)}\n  python: ${Py.head(Json.dumps(entry["ret"]), 800)}")
        }
        return Outcome(true)
    }

    /** Confere um arquivo de trilhas. `real`: telas de verdade, e o terminal mostra só o tipo da diferença. */
    @Suppress("UNCHECKED_CAST")
    fun check(file: File, real: Boolean, show: Int = 10): Boolean {
        var calls = 0
        var callsOk = 0
        var functions = 0
        var functionsOk = 0
        var shown = 0
        file.bufferedReader(Charsets.UTF_8).useLines { lines ->
            for (line in lines) {
                if (line.isBlank()) continue
                val entry = Json.parse(line) as Map<String, Any?>
                val outcome = if ("call" in entry) replay(entry) else function(entry)
                if ("call" in entry) {
                    calls++
                    if (outcome.ok) callsOk++
                } else {
                    functions++
                    if (outcome.ok) functionsOk++
                }
                if (!outcome.ok && shown < show) {
                    shown++
                    val what = entry["call"]?.let { "executor ${entry["exec"]}, $it" } ?: entry["fn"]
                    println("  diferente: $what")
                    if (!real) println(outcome.problem!!.prependIndent("    ")) else println("    " + outcome.problem!!.lineSequence().first().substringBefore(":"))
                }
            }
        }
        println("${file.path}: chamadas ao executor iguais em $callsOk de $calls; funções em $functionsOk de $functions")
        return callsOk == calls && functionsOk == functions
    }
}
