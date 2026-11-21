package dev.pedro.lmphone.cerebro

import dev.pedro.lmphone.cerebro.X.ACTIONS
import dev.pedro.lmphone.cerebro.X.ASK
import dev.pedro.lmphone.cerebro.X.ASK_NOW
import dev.pedro.lmphone.cerebro.X.ASK_OPTION
import dev.pedro.lmphone.cerebro.X.CONFIRM
import dev.pedro.lmphone.cerebro.X.CONFIRM_START
import dev.pedro.lmphone.cerebro.X.DIRECT
import dev.pedro.lmphone.cerebro.X.EDITABLE
import dev.pedro.lmphone.cerebro.X.FEW_LABELS
import dev.pedro.lmphone.cerebro.X.GUIDE_HELP
import dev.pedro.lmphone.cerebro.X.GUIDE_LIMIT
import dev.pedro.lmphone.cerebro.X.GUIDE_REMIND
import dev.pedro.lmphone.cerebro.X.GUIDE_REMINDER
import dev.pedro.lmphone.cerebro.X.POSITION
import dev.pedro.lmphone.cerebro.X.HELP_PROMPT
import dev.pedro.lmphone.cerebro.X.HOW_TO
import dev.pedro.lmphone.cerebro.X.KEEP_SCROLLING
import dev.pedro.lmphone.cerebro.X.KEEP_SCROLLING_LIMIT
import dev.pedro.lmphone.cerebro.X.LOOKAHEAD
import dev.pedro.lmphone.cerebro.X.MAX_HELP
import dev.pedro.lmphone.cerebro.X.MAX_LABEL
import dev.pedro.lmphone.cerebro.X.MAX_QUESTIONS
import dev.pedro.lmphone.cerebro.X.MAX_REVIEWS
import dev.pedro.lmphone.cerebro.X.MAX_SAME_HELP
import dev.pedro.lmphone.cerebro.X.MAX_SCROLLS
import dev.pedro.lmphone.cerebro.X.MAX_WAITS
import dev.pedro.lmphone.cerebro.X.NO_ASK_OPTION
import dev.pedro.lmphone.cerebro.X.NO_HISTORY
import dev.pedro.lmphone.cerebro.X.NO_SCREEN
import dev.pedro.lmphone.cerebro.X.OWNER_LIMIT
import dev.pedro.lmphone.cerebro.X.PLAN_PROMPT
import dev.pedro.lmphone.cerebro.X.REVIEW
import dev.pedro.lmphone.cerebro.X.SEARCHED
import dev.pedro.lmphone.cerebro.X.SEARCH_LABEL
import dev.pedro.lmphone.cerebro.X.SEARCH_OPTION
import dev.pedro.lmphone.cerebro.X.SET_SCREENS
import dev.pedro.lmphone.cerebro.X.TOOL_ERROR
import dev.pedro.lmphone.cerebro.X.USER_BLOCK
import dev.pedro.lmphone.cerebro.X.call
import dev.pedro.lmphone.cerebro.X.plain

typealias Step = MutableMap<String, Any?>
typealias Tool = Pair<String, String>  // (explicação, chamada de ferramenta)

/**
 * A tradução de `lmphone/executor.py` (a referência; os comentários de cada decisão estão lá): o estado de uma tarefa.
 * O provedor escreve o plano; regras em código e o modelo de escolha o executam; o provedor ajuda quando a execução
 * sai do plano. Recebe cada tela em texto e devolve a próxima ação no formato de chamada de ferramenta.
 *
 * Os passos, o objetivo e o caminho ficam em mapas como os dicionários do Python (as chaves na mesma ordem), para os
 * prompts saírem iguais. `clock` é o `time.monotonic` (a conferência o troca pelo que o Python leu).
 */
@Suppress("UNCHECKED_CAST")
class Executor(
    var task: String,
    var provider: ((String) -> String)?,
    var pick: ((List<String>, List<String>) -> Any?)?,
    var device: String = "Android phone",
    var launch: ((String) -> Boolean)? = null,
    var opened: String? = null,
    var facts: (() -> Map<String, Any?>?)? = null,
    history: String? = null,
    var settings: ((String) -> Boolean)? = null,
) {
    var clock: () -> Double = { System.nanoTime() / 1e9 }
    var setter: ((String, Any?) -> Any?)? = null  // false, true ou a mensagem ao dono (texto); o valor é Boolean ou um nível (Long)
    var history: String = if (Py.truthy(history)) history!! else NO_HISTORY
    var assistant = false
    var replied: String? = null
    var looking = false
    var looked = false
    var opening: MutableMap<String, Any?>? = null
    var announce: String? = null
    var guide = false
    var guideWaited: Any? = null
    var wasMet: Boolean? = false
    var speaking = false
    var searching: String? = null
    var searched = false
    var searcher: ((String) -> Boolean)? = null
    var rolling: Double? = null
    var rolled = false
    var readValue: String? = null
    var final: String? = null
    var owner = false
    var waiting: MutableMap<String, Any?>? = null
    var highlight: List<Long>? = null
    var gesture: String? = null  // o gesto que a faixa mostra animado na vez do dono: "puxar" ou "rolar"
    var ownerSteps = 0
    var guideAgent = false  // opção do app: no guia, o agente toca depois de GUIDE_LIMIT (o padrão é a pessoa tocar)
    var actsOnPhone = true  // `acts` do Python: false é o app da loja, que só guia (o agente nunca age)
    var button: Map<String, Any?>? = null  // o botão da faixa para a pessoa abrir um app ou uma página (só guia)
    var lastSaid: String? = null  // a última instrução dita na vez da pessoa (não se repete igual)
    var remindedStep: Int? = null  // o passo do plano em que o lembrete do guia já foi dito
    var lost: String? = null  // a pessoa saiu do caminho: o motivo da ajuda que vem na leitura seguinte
    var quick = false  // a ajuda em curso vai sem raciocínio
    var rerouting = false  // a faixa mostra "recalculando": da saída do caminho até a instrução nova
    var noButtons = false  // o botão da faixa já não abriu uma página neste celular: o resto vai pelos menus
    var unmetAsked = false  // no fim, a medida contradisse o "pronto" e a ajuda já procurou o que trava
    var seen: MutableList<String> = ArrayList()  // rótulos vistos enquanto se rolava atrás do passo atual
    var offNames: List<String> = emptyList()  // nomes ditos entre aspas que não estão na tela
    var pressedAt: Double? = null  // quando a pessoa tocou no botão da faixa (só guia)
    var touchedText: String? = null  // o texto do controle em que ela tocou no app de baixo
    var touchedTextAt: Double? = null
    var touchedBox: List<Long>? = null  // os limites do controle em que ela tocou
    var touchedAt: Double? = null  // quando a pessoa tocou na tela pela última vez (o relógio do executor); null sem faixa
    var nudged = false  // no guia, a tela já subiu para mostrar inteiro o controle deste passo
    var confirming: MutableMap<String, Any?>? = null
    var approved: List<Any?>? = null
    var declined: Any? = null
    var preapproved = false
    var state: Map<String, Any?> = LinkedHashMap()
    var startState: Map<String, Any?>? = null  // o estado antes do primeiro passo: base dos objetivos "up"/"down"
    var early: Map<String, Any?>? = null
    var acted = false
    var repeats: MutableSet<List<Any?>> = LinkedHashSet()
    var flagged: MutableSet<List<Any?>> = LinkedHashSet()
    var lastKey: List<Any?>? = null
    var message = ""
    var raw = ""
    var instructions: MutableList<String> = ArrayList()
    var canAsk = false
    var mayAsk = true
    var questions = 0
    var question: MutableMap<String, Any?>? = null
    var answers: MutableList<List<String>> = ArrayList()
    var tried: MutableList<Any?> = ArrayList()
    var stuck: MutableMap<String, Any?> = LinkedHashMap()
    var plan: MutableList<Step>? = null
    var goal: MutableMap<String, Any?>? = null
    var i = 0
    var scrolls = 0
    var swiped: List<Any?>? = null
    var pending: Step? = null
    var helps = 0
    var waited = false
    var waits = 0
    var asked: Int? = null
    var torn: List<Any?>? = null
    var elements: List<Element> = emptyList()
    var labels: List<String> = emptyList()
    var now: List<Any?>? = null
    var sign: List<Any?>? = null
    var before: MutableSet<String> = LinkedHashSet()
    var start: MutableSet<String>? = null
    var guess = false
    var focused: Int? = null
    var blind = false
    var again: Int? = null
    var goalAsked = false
    var switched = false
    var confirmed = false
    var map: Map<String, Any?> = LinkedHashMap()
    var tapped: MutableMap<String, Any?>? = null
    var trailLen = 0
    var trail: MutableList<MutableMap<String, Any?>> = ArrayList()
    var cacheable = true
    var toolError: String? = null
    var result: String? = null
    var by = "código"
    var choices: MutableList<MutableMap<String, Any?>> = ArrayList()
    var noted: MutableMap<String, Any?>? = null
    var choice: MutableMap<String, Any?>? = null
    var app: String? = null
    var cached = false
    var reviewed = false
    var reviews = 0

    private val plan_ get() = plan!!

    fun use(steps: List<Any?>, goal: Any? = null) {
        plan = adopt(steps, goal, complete = true)
        cached = true
    }

    fun prepare() {
        if (plan == null) {
            by = "provedor"
            var answer = turn(NO_SCREEN)
            // Só guia: uma resposta sem passos que promete mostrar o caminho é pedida de novo uma vez (como no Python).
            if (!actsOnPhone && answer != null && Py.truthy(answer["reply"]) && !Py.truthy(answer["steps"]) &&
                Py.search(X.PROMISE, plain(Py.str(answer["reply"]))) != null) {
                answer = turn(NO_SCREEN + X.PROMISED) ?: answer
            }
            take(answer)
        }
    }

    fun turn(screen: String): Map<String, Any?>? {
        val known = X.render(X.related(map, task), opened)
        return askJson(pyFormat(PLAN_PROMPT, linkedMapOf(
            "device" to device, "task" to requestText(), "known" to known, "screen" to screen,
            "ask_option" to if (mayAsk) ASK_OPTION else NO_ASK_OPTION,
            "search_option" to if (!actsOnPhone) "" else if (searched) SEARCHED else SEARCH_OPTION,
            "state" to stateLine(), "history" to history)))
    }

    /** O pedido como vai ao provedor: no app que só guia, com o aviso de que todo pedido é guia. */
    fun requestText(help: Boolean = false): String = if (actsOnPhone) task else task + if (help) X.ONLY_GUIDE_HELP else X.ONLY_GUIDE

    fun askJson(prompt: String): Map<String, Any?>? {
        repeat(2) {
            val answer = try {
                X.parseJson(provider!!(prompt))
            } catch (e: IllegalArgumentException) {
                return@repeat
            }
            if (answer is Map<*, *>) return answer as Map<String, Any?>
        }
        return null
    }

    fun take(answer: Map<String, Any?>?) {
        plan = ArrayList()
        if (answer == null) {
            early = linkedMapOf("success" to false, "message" to "O provedor respondeu algo que não entendi. Pode pedir de novo?")
            return
        }
        val acts = Py.truthy(answer["steps"])
        if (Py.truthy(answer["reply"]) && !acts) {
            replied = Py.str(answer["reply"])
            return
        }
        if (Py.truthy(answer["look"]) && !looked && !acts) {
            looking = true
            return
        }
        val ask = answer["ask"]
        if (ask is Map<*, *> && Py.truthy(ask["question"]) && !acts) {
            guide = !actsOnPhone || Py.search(HOW_TO, plain(task)) != null  // o plano vem pela ajuda (como no Python)
            opening = linkedMapOf("question" to Py.str(ask["question"]), "secret" to Py.truthy(ask["secret"]),
                "options" to Py.iter(Py.or(ask["options"], emptyList<Any?>())).map { Py.str(it) }.take(4))
            return
        }
        val search = answer["search"]
        if (search is String && Py.strip(search).isNotEmpty() && !acts && !searched) {
            searching = Py.strip(search)
            return
        }
        if ("finish" in answer && !acts) {
            early = answer["finish"] as? Map<String, Any?> ?: linkedMapOf("success" to true)
        }
        announce = if (Py.truthy(answer["say"]) && acts) Py.str(answer["say"]) else null
        guide = Py.truthy(answer["guide"]) || (acts && (!actsOnPhone || Py.search(HOW_TO, plain(task)) != null))
        val steps = Py.or(answer["steps"], emptyList<Any?>())
        plan = adopt(if (guide) guided(steps) else steps, planGoal(answer), complete = true)
        if (guide && Py.truthy(factGoal()) && Py.truthy(readState())) wasMet = Facts.met(factGoal(), state, startState)
    }

    fun askOwner(question: MutableMap<String, Any?>): Tool {
        questions += 1
        this.question = question
        return "Ask the owner." to call("ask_user", "question" to question["question"],
            "options" to Json.dumps(question["options"]), "secret" to if (question["secret"] == true) "true" else "false")
    }

    fun readState(): Map<String, Any?> {
        val read = facts
        if (read != null) {
            state = try {
                read() ?: LinkedHashMap()
            } catch (e: Exception) {
                LinkedHashMap()
            }
            if (startState == null && state.isNotEmpty()) startState = LinkedHashMap(state)
        }
        return state
    }

    /** O estado para o provedor: o de agora e o que mudou desde o começo da tarefa (medido, não suposto). */
    fun stateLine(): String {
        val now = readState()
        val changed = Facts.changes(startState, now)
        return Facts.describe(now) + (if (changed.isNotEmpty()) ". Changed since the start of this task: $changed" else "")
    }

    fun factNow(): Map<String, Any?>? {
        val out = LinkedHashMap<String, Any?>()
        for ((key, wanted) in factGoal() ?: emptyMap()) {
            out[key] = if (key == "wifi" && plain(Py.str(wanted)) in setOf("on", "off", "true", "false") ||
                plain(Py.str(wanted)) in Facts.CHANGES) wanted
            else if (key in state) state[key] else wanted
        }
        return out.ifEmpty { null }
    }

    fun factGoal(): Map<String, Any?>? = (goal ?: emptyMap<String, Any?>())["fact"] as? Map<String, Any?>

    fun step(message: String): Tool {
        val (parsed, raw) = X.parseScreen(message)
        val elements = X.statusIcons(parsed, raw)
        val labels = elements.filter { it.text.isNotEmpty() }.map { it.text }
        if (waited && waits < MAX_WAITS && (labels.size <= FEW_LABELS || labels != this.labels)) waited = false
        this.elements = elements
        this.labels = labels
        now = X.signature(elements, raw)
        if (scrolls != 0) remember(labels)
        by = "código"
        noted = null
        val errors = Py.findallText(TOOL_ERROR, message.split("<device_state>")[0])
        toolError = errors.lastOrNull()?.let { Py.strip(it) }
        this.message = message
        this.raw = raw
        highlight = null
        gesture = null
        button = null
        rerouting = false
        prepare()

        if (waiting != null && instructions.isNotEmpty()) {
            // Ela escreveu na faixa durante a espera: a instrução vale mais que o passo mostrado (como no Python).
            waiting = null
            guideWaited = null
        }
        if (waiting != null) {
            ownerProgress()?.let { return it }
        }

        lost?.let { reason ->
            // A pessoa saiu do caminho e já ouviu "espere": agora a ajuda, rápida, mostra a volta (como no Python).
            lost = null
            quick = true
            val stop = try {
                help(raw, reason, owner = true)
            } finally {
                quick = false
            }
            if (stop != null) return stop
        }

        pending?.let { done ->
            pending = null
            verify(done, elements, labels, raw)?.let { return it }
        }

        if (Py.truthy(declined)) {
            val label = declined
            declined = null
            markNoop()
            result = "cancelada"
            val said = if (label is String && label.isNotEmpty()) "Tudo bem, parei antes de tocar em «$label»." else "Tudo bem, parei aqui."
            return "The owner did not confirm." to complete(true, said)
        }

        if (answers.isNotEmpty()) {
            val (asked, said) = answers.removeAt(0)
            cacheable = false
            help(raw, "you asked the owner «$asked» and they answered «$said». Go on from this screen with that answer " +
                "(give the steps, or finish if they said to stop)", owner = true)?.let { return it }
        }

        if (instructions.isNotEmpty()) {
            val said = instructions.joinToString(" / ")
            instructions = ArrayList()
            cacheable = false
            quick = guide  // no guia, a pessoa espera parada: sem raciocínio (como no Python)
            val stop = try {
                help(raw, "the owner, watching the phone, just told you: «$said». This has priority over the plan: it " +
                    "may change what to do, say that the agent is stuck or doing something wrong, or ask it to stop. " +
                    "Give the steps that do what they asked from this screen on, or finish if they asked to stop or " +
                    "the task is done", owner = true)
            } finally {
                quick = false
            }
            if (stop != null) return stop
        }

        searching?.let { query ->
            searching = null
            searched = true
            if (!(searcher?.invoke(query) ?: false)) {
                return fail("The web search could not be opened.", "Não consegui abrir a pesquisa no Google do celular.")
            }
            looking = true
            looked = false
            waited = false
            waits = 0
            acted = true
            cacheable = false
            return "Search Google on the phone: $query" to call("wait", "duration" to "2.0")
        }
        if (looking) {
            if (!waited) return settle()
            looking = false
            looked = true
            by = "provedor"
            val shown = if (searched) X.redact(raw, SEARCH_LABEL, numbers = false) else X.redact(raw)
            take(turn("<device_state>\n$shown\n</device_state>"))
        }
        replied?.let { reply ->
            replied = null
            markNoop()
            result = "respondido"
            return "Answer the owner: nothing to do on the phone." to complete(true, reply)
        }
        opening?.let { question ->
            opening = null
            if (canAsk && questions < MAX_QUESTIONS) return askOwner(question)
            markNoop()
            result = "pergunta"
            val options = question["options"] as List<String>
            val suffix = if (options.isNotEmpty()) " (${options.joinToString(" / ")})" else ""
            return "Ask the owner before doing anything." to complete(true, Py.str(question["question"]) + suffix)
        }
        if (Py.truthy(factGoal()) && !guide && (plan ?: emptyList<Step>()).drop(i).none { X.leavesSettings(it) } &&
            Py.truthy(readState()) && Facts.met(factGoal(), state, startState) == true) {
            return finish(true, Py.str((early ?: emptyMap<String, Any?>())["message"] ?: ""))
        }
        early?.let { found ->
            early = null
            if (!Py.truthy(if ("success" in found) found["success"] else true)) {
                return fail("The provider ended the task before any step.", Py.str(found["message"] ?: ""))
            }
            return finish(goalState(elements, labels) == true, Py.str(found["message"] ?: ""))
        }

        repeat(40) {
            if (i >= plan_.size) {
                conclude(elements, labels, raw)?.let { return it }
                return@repeat
            }
            val jump = goalStep(elements)
            if (jump != null && jump > i) {
                i = jump
                scrolls = 0
            }
            val step = plan_[i]
            val action = step["action"]
            val targets = Py.iter(Py.or(step["target"], emptyList<Any?>()))
            if (!actsOnPhone && action != "quick_settings" && splitShade() && X.shadeOnly(raw) && trail.isNotEmpty() &&
                trail.last()["action"] == "quick_settings" && !(i > 0 && Py.truthy(plan_[i - 1]["again"]))) {
                // A pessoa puxou pelo meio e abriu só os avisos: ela puxa de novo, pelo lado direito (como no Python).
                plan_.add(i, linkedMapOf("action" to "quick_settings", "explain" to X.SHADE_ONLY_SAY, "again" to true))
                return@repeat
            }
            when (action) {
                "check" -> {
                    i += 1
                    return@repeat
                }
                "open_app" -> {
                    trail.add(linkedMapOf("action" to "open_app", "target" to targets.take(1)))
                    if (i == 0 && Py.truthy(opened) && plain(opened) == plain(targets[0])) {
                        i += 1
                        return@repeat
                    }
                    if (launch != null && !owner && actsOnPhone && launch!!(Py.str(targets[0]))) {
                        return advance(step, "Open the app ${Py.str(targets[0])} (launched directly).", call("wait", "duration" to "1.0"))
                    }
                    return advance(step, "Open the app ${Py.str(targets[0])}.", call("open_app", "text" to targets[0]))
                }
                "set" -> {
                    val rawName = if (targets.isNotEmpty()) targets[0] else ""
                    val name = Py.str(rawName)
                    val given = if ("value" in step) step["value"] else true
                    // Um nível (volume, brilho): de 0 a 100, como o round do Python (metade para o par); sem número, null.
                    val value: Any? = if (rawName is String && rawName in Facts.LEVELS) {
                        when (given) {
                            is Boolean -> if (given) 1.0 else 0.0
                            is Number -> given.toDouble()
                            is String -> Py.strip(given).toDoubleOrNull()
                            else -> null
                        }?.takeIf { it.isFinite() }?.let { maxOf(0L, minOf(100L, Math.rint(it).toLong())) }
                    } else if (name == "sound_mode") (X.SOUND_MODE_WORDS[plain(Py.str(given))] ?: plain(Py.str(given))) else Py.truthy(given)
                    trail.add(linkedMapOf("action" to "set", "target" to listOf(rawName), "value" to value))
                    val screens = name in SET_SCREENS || name in X.SET_ROUTES
                    var done: Any? = if (!actsOnPhone) {
                        if (screens) X.SCREENS else false  // só guia: pelas telas, nunca pelo sistema
                    } else if (name in DIRECT && setter != null && value != null) setter!!(name, value) else false
                    if (done == X.SCREENS && !screens) done = false  // sem caminho pelas telas: a ajuda dá os passos
                    if (done == X.SCREENS && screens) {
                        trail.removeAt(trail.size - 1)
                        val route = guided(listOf(step)).map { it as Map<String, Any?> }
                        val steps = route.map { s -> LinkedHashMap(if (guide) s else s.filterKeys { it != "explain" }) as Step }
                        plan_.removeAt(i)
                        plan_.addAll(i, steps)
                        if (!Py.truthy(factGoal())) {
                            // Um nível com número exato só valeria com ele: vale subir ou descer a partir de agora (como no Python).
                            val level = name in Facts.LEVELS && value is Number
                            val now = state[name]
                            val wanted: Any? = if (level) {
                                if (now !is Number || (value as Number).toDouble() >= now.toDouble()) "up" else "down"
                            } else value
                            goal = linkedMapOf("fact" to linkedMapOf<String, Any?>(name to wanted))
                        }
                        return@repeat
                    }
                    if (done is String) return fail("The setting $name cannot be changed now.", done)
                    if (Py.truthy(done)) {
                        if (!Py.truthy(factGoal())) goal = linkedMapOf("fact" to linkedMapOf<String, Any?>(name to value))
                        acted = true
                        markNoop()
                        i += 1
                        return "Set $name to ${Py.str(value)} directly." to call("wait", "duration" to "0.5")
                    }
                    help(raw, "the setting «$name» cannot be changed directly: do it through the screens")?.let { return it }
                    return@repeat
                }
                "open_settings" -> {
                    val page = X.settingsPage(Py.str(if (targets.isNotEmpty()) targets[0] else ""))
                    if (!actsOnPhone && page !in X.SETTINGS_PAGES) {
                        // O botão da faixa só abre as páginas conhecidas (como no Python).
                        help(raw, "«$page» is not one of the settings pages that open directly " +
                            "(${X.SETTINGS_PAGES.joinToString(", ")}): use one of these, or tap through the screens")?.let { return it }
                        return@repeat
                    }
                    if (!actsOnPhone && noButtons && !pageOpen(page)) {
                        // O botão da faixa já não abriu uma página neste celular: o caminho pelos menus (como no Python).
                        help(raw, "the strip's button did not open settings pages on this phone: guide them to " +
                            "«$page» through the menus, one tap per step, with no \"open_settings\" or \"open_app\" step")?.let { return it }
                        return@repeat
                    }
                    trail.add(linkedMapOf("action" to "open_settings", "target" to listOf(page)))
                    if (!actsOnPhone && pageOpen(page)) {
                        // A página já está aberta: um botão para abri-la não mudaria a tela (como no Python).
                        i += 1
                        return@repeat
                    }
                    val wayIn = X.SETTINGS_WAY[page]
                    var shown = step
                    if (!actsOnPhone && guide && !wayIn.isNullOrEmpty()) {
                        // Só guia: a pessoa abre a página pelo botão da faixa; o caminho pelo menu vai junto.
                        shown = LinkedHashMap(step)
                        shown["explain"] = "Toque no botão «${X.BUTTON_SETTINGS}», aqui embaixo. Sozinho, é tocar na " +
                            "engrenagem das Configurações e depois em «${wayIn.joinToString("», depois em «")}»."
                    } else if (!actsOnPhone && guide) {
                        shown = LinkedHashMap(step)
                        shown["explain"] = "Toque no botão «${X.BUTTON_SETTINGS}», aqui embaixo."  // sem caminho conhecido
                    }
                    if (owner || !actsOnPhone) return advance(shown, "Open the settings page $page.", call("open_settings", "page" to page))
                    if (settings != null && settings!!(page)) {
                        val way = X.SETTINGS_WAY[page]
                        if (guide && !way.isNullOrEmpty()) {
                            // O agente abriu a página direto: diz o que fez e como se chega lá (como no Python).
                            val copy: Step = LinkedHashMap(step)
                            copy["explain"] = "Abri as Configurações para você, em «${way.last()}». " +
                                "Sozinho, é tocar na engrenagem das Configurações e depois em «${way.joinToString("», depois em «")}»."
                            return advance(copy, "Open the settings page $page directly.", call("wait", "duration" to "1.0"))
                        }
                        return advance(step, "Open the settings page $page directly.", call("wait", "duration" to "1.0"))
                    }
                    help(raw, "the settings page «$page» cannot be opened directly: reach it through the Settings menus")?.let { return it }
                    return@repeat
                }
                "keep_scrolling" -> return keepScrolling(step)
                "type" -> {
                    cacheable = false
                    var typed: Step = step  // só guia: uma cópia com o campo a destacar, como no Python
                    if (focused != i) {
                        var index: Any? = step.remove("index")
                        val field = if (index != null) null else field(step, elements)
                        if (index == null && targets.isNotEmpty() && !waited && field(step, elements, named = true) == null) return settle()
                        if (field != null && targets.isNotEmpty() && written(field) && plain(field.text) !in targets.map { plain(it) }) {
                            if (!waited) return settle()
                            help(raw, "the field this step names is not on screen: the only text field holds the text typed by " +
                                "an earlier step, and typing there would replace or extend it. Give first the step that " +
                                "moves to the right field (\"enter\" or a tap), then the \"type\" step")?.let { return it }
                            return@repeat
                        }
                        index = field?.index ?: index
                        if (index != null && !actsOnPhone) {
                            typed = LinkedHashMap(step).apply { put("field", index) }  // só guia: a pessoa toca no campo e escreve
                        } else if (index != null) {
                            focused = i
                            if (start == null) start = LinkedHashSet(labels)
                            return "Tap element ${Py.str(index)} to put the focus on the field." to call("click", "index" to index)
                        }
                    }
                    trail.add(linkedMapOf("action" to "type", "text" to Py.or(step["text"], "")))
                    val params = mutableListOf<Pair<String, Any?>>("text" to Py.or(step["text"], ""))
                    if (Py.truthy(step["clear"])) params.add("clear" to "true")
                    if (typed["field"] != null) params.add("index" to Py.str(typed["field"]))
                    return advance(typed, "Type the text of the step into the focused field.", call("type", *params.toTypedArray()))
                }
                "enter" -> {
                    trail.add(linkedMapOf("action" to "enter"))
                    return advance(step, "Press Enter on the keyboard.", call("system_button", "button" to "enter"))
                }
                "back" -> {
                    trail.add(linkedMapOf("action" to "back"))
                    return advance(step, "Go back one screen.", call("system_button", "button" to "back"))
                }
                "quick_settings" -> {
                    trail.add(linkedMapOf("action" to "quick_settings"))
                    return advance(step, "Open the quick settings panel.", call("system_button", "button" to "quick_settings"))
                }
            }
            val wanted: Boolean? = when (action) {
                "turn_on" -> true
                "turn_off" -> false
                else -> null
            }
            var stop: Tool? = null
            if (action == "read" && guide && !actsOnPhone && readsBar(step, elements)) {
                i += 1  // o nível de uma barra no guia: quem muda é a pessoa (como no Python)
                return@repeat
            }
            if (action == "read") {
                val value = read(step, labels)
                if (Py.truthy(value)) {
                    result = "lido"
                    readValue = value
                    val answer = Py.str(Py.or(step["answer"], ""))
                    val said = if ("{value}" in answer) answer.replace("{value}", value!!) else Py.strip("$answer $value")
                    return "Read the value on screen; it stays on the device." to complete(true, said)
                }
                if (!waited) return settle()
                if (step["if_missing"] == "scroll" && scrolls < MAX_SCROLLS && now != swiped) return scroll("The value is not on screen: scroll down.")
                stop = help(raw, "no text on screen has both the target words and a match for the pattern")
            } else if ("index" in step) {
                val index = step.remove("index")
                val element = elements.firstOrNull { Py.eq(it.index, index) }
                note(step, element?.text, "provedor")
                val control = if (wanted != null && element != null) control(element, elements) else null
                if (control != null && (element!!.text.isNotEmpty() || control.text.isNotEmpty())) {
                    step["target"] = listOf(element.text.ifEmpty { control.text })
                    trail.add(linkedMapOf("action" to action, "target" to step["target"]))
                    if (control.checked == wanted) {
                        noted!!["efeito"] = "já estava"
                        i += 1
                        return@repeat
                    }
                    return advance(step, "Tap element ${control.index}, the switch pointed out by the provider.", call("click", "index" to control.index))
                }
                trail.add((linkedMapOf<String, Any?>("action" to "tap") + locator(element, elements)).toMutableMap())
                return advance(step, "Tap element ${Py.str(index)}, pointed out by the provider.", call("click", "index" to index))
            } else if ("at" in step) {
                val target = locate(step["at"] as Map<String, Any?>, elements)
                if (target != null) {
                    note(step, target.text, "cache")
                    trail.add(linkedMapOf("action" to "tap", "at" to step["at"]))
                    return advance(step, "Tap element ${target.index}, as in the saved path.", call("click", "index" to target.index))
                }
                if (!waited) return settle()
                stop = help(raw, "the control this step taps (it has no text) is not on screen")
            } else {
                var target = find(step, elements)
                var guessed = false
                if (target == null && route(elements)) return@repeat
                if (target == null && !waited) return settle()
                if (target == null && labels.size <= FEW_LABELS) {
                    stop = help(raw, "the screen shows almost no text, so the target cannot be found by its label")
                } else if (target == null && asked != i && ask(targets, elements, labels).also { target = it } != null) {
                    guessed = true
                } else if (target == null && Py.truthy(torn)) {
                    val (first, second) = torn!!
                    torn = null
                    stop = help(raw, "none of the target labels is on screen, but the on-device model thinks the control " +
                        "is on this very screen under another label: it hesitated between «${Py.str(first)}» and " +
                        "«${Py.str(second)}». Pick the right control from this screen; do not scroll away from it")
                } else if (target == null && X.SYSTEM_PANEL in raw && expander(elements) != null &&
                    !(i > 0 && Py.truthy(plan_[i - 1]["expand"]))) {
                    // O painel de atalhos compacto: rolar o fecha; o botão que o abre inteiro vem antes (como no Python).
                    val name = expander(elements)!!.text
                    plan_.add(i, linkedMapOf("action" to "tap", "target" to mutableListOf(name), "expand" to true,
                        "explain" to "Toque em «$name», para ver todos os botões."))
                    return@repeat
                } else if (target == null && (step["if_missing"] == "scroll" || X.SYSTEM_PANEL in raw && !X.shadeOnly(raw)) &&
                    scrolls < MAX_SCROLLS && now != swiped) {
                    // No painel de atalhos aberto inteiro, a lista continua para baixo: rolar antes da ajuda (como no Python).
                    return scroll("“${Py.str(targets[0])}” is not on screen: scroll down.")
                } else if (target == null && step["if_missing"] == "skip") {
                    i += 1
                    return@repeat
                } else if (target == null) {
                    target = ask(targets, elements, labels)
                    if (target == null) stop = help(raw, "none of the target labels is on screen") else guessed = true
                }
                if (target != null && action == "tap" && checked(target!!, elements) != null && plan_.drop(i + 1).any { s ->
                        s["action"] in setOf("turn_on", "turn_off") &&
                            Py.iter(Py.or(s["target"], emptyList<Any?>())).map { plain(it) }.toSet()
                                .intersect(targets.map { plain(it) }.toSet()).isNotEmpty()
                    }) {
                    i += 1
                    return@repeat
                }
                if (target != null && action == "tap" && chosen(target!!, elements)) {
                    // Uma opção que já está escolhida: tocar nela não muda nada; ela continua no caminho do fim (como no Python).
                    if (target!!.text.isNotEmpty()) trail.add(linkedMapOf("action" to "tap", "target" to listOf(target!!.text)))
                    i += 1
                    return@repeat
                }
                val flips = if (target != null && action == "tap") flips(target!!, elements) else null
                if (flips != null) {
                    target = null
                    stop = help(raw, "this step taps “${flips.text.ifEmpty { Py.str(targets[0]) }}”, which is a switch that is now " +
                        "${if (flips.checked == true) "ON" else "OFF"}: a tap would flip it without looking. Say what it must become " +
                        "with a \"turn_on\" or \"turn_off\" step for it (and an on/off \"goal\" if that is the task)")
                }
                val chosen = target
                if (chosen != null) {
                    val control = if (wanted != null) control(chosen, elements) else null
                    if (wanted != null && control == null && !waited) return settle()
                    if (wanted != null && control == null && again == i) {
                        i += 1
                        return@repeat
                    }
                    if (!guessed) note(step, chosen.text, if (step["via"] == "map") "mapa" else "rótulo exato")
                    trail.add(linkedMapOf<String, Any?>("action" to action, "target" to listOf(chosen.text)).apply {
                        if (scrolls != 0 || step["if_missing"] == "scroll") put("if_missing", "scroll")
                    })
                    if (control != null && control.checked == wanted) {
                        noted!!["efeito"] = "já estava"
                        i += 1
                        return@repeat
                    }
                    if (guessed) by = "IA local"
                    if (wanted != null) step["target"] = listOf(chosen.text) + targets.filter { plain(it) != plain(chosen.text) }
                    val spot = control ?: chosen
                    val via = if (step["via"] == "map") " The app map knows this way." else ""
                    return advance(step, "Tap “${chosen.text}” (element ${spot.index}).$via", call("click", "index" to spot.index), guessed,
                        blind = wanted != null && control == null)
                }
            }
            if (stop != null) return stop
        }
        return fail("The execution is going in circles.", "Não consegui terminar: a execução estava andando em círculos.")
    }

    fun adopt(steps: Any?, goal: Any? = null, complete: Boolean = false): MutableList<Step> {
        if (goal is Map<*, *>) {
            val g = goal as Map<String, Any?>
            val out = LinkedHashMap<String, Any?>()
            for (key in listOf("on", "off", "shows", "gone")) {
                if (Py.truthy(g[key])) out[key] = if (g[key] is String) mutableListOf(g[key]) else Py.iter(g[key]).toMutableList()
            }
            val fact = g["fact"]
            if (fact is Map<*, *> && fact.isNotEmpty()) out["fact"] = LinkedHashMap(fact as Map<String, Any?>)
            if (out.isNotEmpty()) this.goal = out
            val factNow = (this.goal ?: emptyMap<String, Any?>())["fact"]
            if (factNow is MutableMap<*, *> && factNow["sound_mode"] is String) {
                // O modo de som no objetivo com o nome do aparelho (como no Python).
                val mode = factNow["sound_mode"] as String
                (factNow as MutableMap<String, Any?>)["sound_mode"] = X.SOUND_MODE_WORDS[plain(mode)] ?: mode
            }
        }
        var adopted: MutableList<Step> = Py.iter(steps).filter { it is Map<*, *> && it["action"] in ACTIONS }
            .map { LinkedHashMap(it as Map<String, Any?>) as Step }.toMutableList()
        for (step in adopted) if (step["target"] is String) step["target"] = mutableListOf(step["target"])

        val fact = (this.goal ?: emptyMap<String, Any?>())["fact"]
        if (complete && guide && !actsOnPhone && fact is Map<*, *> && fact.keys.any { it in Facts.LEVELS }) {
            adopted = adopted.filter { it["action"] != "read" }.toMutableList()  // no guia, o nível a pessoa muda (como no Python)
        }
        if (complete && fact is Map<*, *> && adopted.any { X.leavesSettings(it) }) {
            val changed = adopted.filter { it["action"] == "set" }
                .map { plain(Py.str(Py.iter(Py.or(it["target"], listOf<Any?>(""))).firstOrNull() ?: "")) }.toSet()
            if (!changed.containsAll((fact as Map<String, Any?>).keys.map { plain(it) })) {
                this.goal = this.goal!!.filterKeys { it != "fact" }.toMutableMap().ifEmpty { null }
            }
        }

        val factNow = (this.goal ?: emptyMap<String, Any?>())["fact"]
        if (complete && factNow is Map<*, *> && factNow["do_not_disturb"] == false && Py.search(X.SOUND_SYMPTOM, plain(task)) != null) {
            // "Não chega aviso": o objetivo pede também o modo Som e o toque audível (como no Python).
            val wanted = LinkedHashMap(factNow as Map<String, Any?>)
            if (state["sound_mode"] in setOf("vibrar", "mudo") && "sound_mode" !in wanted) wanted["sound_mode"] = "som"
            val ring = state["ring_volume"]
            if (ring is Number && ring.toDouble() < Facts.AUDIBLE && "ring_volume" !in wanted) wanted["ring_volume"] = "up"
            if (wanted.size != factNow.size) (this.goal as MutableMap<String, Any?>)["fact"] = wanted
        }

        fun names(step: Map<String, Any?>) = Py.iter(Py.or(step["target"], emptyList<Any?>())).map { plain(it) }.toSet()

        adopted = adopted.filterIndexed { n, step ->
            !(step["action"] == "tap" && "index" !in step && n + 1 < adopted.size && adopted[n + 1]["action"] == "type" &&
                names(step).intersect(names(adopted[n + 1])).isNotEmpty())
        }.toMutableList()
        val (action, labels) = goalTurn()
        if (action != null) {
            val wanted = this.goal!![if (action == "turn_on") "on" else "off"] as MutableList<Any?>
            for (step in adopted) {
                if ((step["action"] == "tap" || step["action"] == action) && "index" !in step && labels.intersect(names(step)).isNotEmpty()) {
                    step["action"] = action
                    val known = wanted.map { plain(it) }.toSet()
                    wanted.addAll(Py.iter(step["target"]).filter { plain(it) !in known })
                }
            }
            adopted = adopted.filterIndexed { n, step ->
                !(n > 0 && step["action"] == action && adopted[n - 1]["action"] == action && names(step).intersect(names(adopted[n - 1])).isNotEmpty())
            }.toMutableList()
            val reads = adopted.isNotEmpty() && adopted.last()["action"] == "read"
            if (complete && !reads && adopted.none { it["action"] == action && labels.intersect(names(it)).isNotEmpty() }) {
                adopted.add(linkedMapOf("action" to action, "target" to wanted.toMutableList(), "if_missing" to "scroll"))
            }
        }
        return adopted
    }

    fun goalTurn(): Pair<String?, Set<String>> {
        for ((key, action) in listOf("on" to "turn_on", "off" to "turn_off")) {
            if (Py.truthy((goal ?: emptyMap<String, Any?>())[key])) return action to Py.iter(goal!![key]).map { plain(it) }.toSet()
        }
        return null to emptySet()
    }

    fun goalStep(elements: List<Element>): Int? {
        val (action, labels) = goalTurn()
        if (action == null) return null
        val target = find(linkedMapOf("action" to action, "target" to goal!![if (action == "turn_on") "on" else "off"]), elements)
        if (target == null || checked(target, elements) == null) return null
        return (i until plan_.size).firstOrNull { j ->
            plan_[j]["action"] == action && labels.intersect(Py.iter(Py.or(plan_[j]["target"], emptyList<Any?>())).map { plain(it) }.toSet()).isNotEmpty()
        }
    }

    fun goalState(elements: List<Element>, labels: List<String>): Boolean? {
        val goal = this.goal ?: emptyMap<String, Any?>()
        if (Py.truthy(factGoal())) return Facts.met(factGoal(), state, startState)
        if (Py.iter(Py.or(goal["gone"], emptyList<Any?>())).any { text -> labels.any { X.matches(text, it) } }) return false
        for ((key, wanted) in listOf("on" to true, "off" to false)) {
            if (Py.truthy(goal[key])) {
                val target = find(linkedMapOf("action" to "turn_on", "target" to goal[key]), elements)
                val state = if (target != null) checked(target, elements) else null
                return if (state == null) null else state == wanted
            }
        }
        if (Py.truthy(goal["shows"])) {
            val hits = labels.filter { label -> Py.iter(goal["shows"]).any { X.matches(it, label) } }
            if (hits.isEmpty()) return false
            return if (hits.any { it !in (start ?: emptySet<String>()) }) true else null
        }
        return null
    }

    fun verify(done: Step, elements: List<Element>, labels: List<String>, raw: String): Tool? {
        val error = toolError
        if (error != null && USER_BLOCK in error) {
            settled(null)
            i -= 1
            cacheable = false
            repeats.remove(lastKey)
            return null
        }
        if (Py.truthy(error)) {
            settled("erro")
            i -= 1
            return help(raw, "the tool reported an error: ${Py.head(error!!, 200)}")
        }
        val following = if (i < plan_.size) plan_[i] else null
        val expected = Py.iter(Py.or(done["expected"], emptyList<Any?>()))
        val wanted: Boolean? = when (done["action"]) {
            "turn_on" -> true
            "turn_off" -> false
            else -> null
        }
        val shown = visible(expected, labels)
        val changed = now != sign
        var state: Boolean? = null
        var ok: Boolean
        val reason: String
        if (wanted != null) {
            val switch = find(done, elements)
            state = if (switch != null) checked(switch, elements) else null
            ok = state == wanted
            reason = "the switch was tapped, but it is not in the wanted state"
        } else {
            val typed = done["action"] == "type" && visible(listOf(Py.or(done["text"], "")), labels)
            ok = shown || typed || arrived(elements) || changed && !(guess && expected.isNotEmpty())
            if (done["action"] == "type" && !typed && !waited) ok = false
            reason = if (changed) "the local model guessed which control to tap, and none of the expected texts showed up afterwards"
            else "the step was executed, but nothing changed on screen"
        }
        if (ok) {
            settled("conferido")
            return null
        }
        if (!waited) {
            pending = done
            return settle()
        }
        if (wanted == null) {
            if (following != null && find(following, elements) != null) {
                settled("incerto")
                return null
            }
        } else if (blind && changed && again != i - 1) {
            i -= 1
            again = i
            if (trail.isNotEmpty() && trail.last()["action"] == done["action"]) trail.last()["action"] = "tap"
            settled("incerto")
            return null
        } else {
            val button = if (confirmed) null else confirmButton(elements)
            if (button != null) {
                confirmed = true
                waited = false
                pending = done
                trail.add(linkedMapOf("action" to "tap", "target" to listOf(button.text), "if_missing" to "skip"))
                val why = "Confirm the change: tap “${button.text}” (element ${button.index})."
                if (!actsOnPhone) {
                    // Só guia: quem confirma é a pessoa; depois do toque dela, o passo é conferido de novo.
                    return ownerTurn(linkedMapOf("target" to listOf(button.text)), why, call("click", "index" to button.index),
                        false, false, guide = true, redo = true)
                }
                return why to call("click", "index" to button.index)
            }
            if (state == null && (shown || expected.isEmpty())) {
                settled("incerto")
                return null
            }
        }
        settled("desfeito")
        i -= 1
        return help(raw, reason)
    }

    fun conclude(elements: List<Element>, labels: List<String>, raw: String): Tool? {
        if (Py.truthy(factGoal())) readState()
        if (!reviewed && !Py.truthy(factGoal()) && (assistant || (!cached && goalTurn().first == null))) {
            if (!waited) return settle()
            reviews += 1
            reviewed = reviews >= (if (assistant) MAX_REVIEWS else 1)
            val owner = if (ownerSteps != 0) ". The owner did $ownerSteps of the steps themselves, following your instructions (you only " +
                "showed them where to touch): in \"message\", say what THEY did, praising it (\"Você aumentou a letra\"), " +
                "never \"I did\" or \"aumentei\" for those steps" else ""
            return help(raw, REVIEW + typedNote(labels) + owner, review = true)
        }
        val state = goalState(elements, labels)
        if (Py.truthy(goal) && state != true && !waited) return settle()
        if (state == false) {
            val more = levelSteps(elements)
            if (more.isNotEmpty()) {
                plan_.addAll(more)
                return null
            }
            return help(raw, "every step was carried out, but the goal is not met on this screen. The goal was your guess of how " +
                "the result would look: if this screen shows that the task itself is done, answer with \"finish\" " +
                "(success true) and the corrected \"goal\"; give steps only if the task is really not done")
        }
        if (state == null && goalTurn().first != null && !goalAsked) {
            goalAsked = true
            return help(raw, "every step was carried out, but no switch or option with the goal's label is on this screen, so " +
                "its state cannot be read. If the screen shows the control under another label, answer with " +
                "\"finish\" (success true) and the corrected \"goal\"; give steps only if the task is really not done")
        }
        return finish(state == true)
    }

    fun finish(confirmed: Boolean, said: String = "", seen: Boolean = false): Tool {
        var confirmed = confirmed
        var seen = seen
        var said = said
        val fact = factGoal()
        if ((confirmed || seen) && Py.truthy(fact) && Py.truthy(readState()) && Facts.met(fact, state, startState) == false) {
            // O aparelho mede que o pedido não aconteceu: o "pronto" do provedor não vale (como no Python).
            if (guide && !unmetAsked) {
                unmetAsked = true
                val stop = help(raw, "the state measured on the phone shows the goal is NOT met yet " +
                    "(${stateLine()}). Something may be blocking it (the sound mode in vibrar or " +
                    "mudo locks the ringtone and notification bars at zero; a switch is off): find what " +
                    "it is and give the steps; finish only when the state shows it done")
                return stop ?: step(message)
            }
            confirmed = false
            seen = false
            said = ""
        }
        markNoop()
        result = if (confirmed) "confirmado" else if (seen) "conferido" else "sem confirmação"
        val (action, _) = goalTurn()
        if (confirmed && guide && wasMet == true) {
            result = "já estava"
            return "The goal was already met; the way was shown." to complete(true,
                said.ifEmpty { "Já estava assim (${Facts.speak(factNow())}). O caminho é esse que mostrei." })
        }
        if (confirmed && Py.truthy(factGoal()) && !acted) {
            result = "já estava"
            return "The goal was already met: nothing was changed." to complete(true,
                said.ifEmpty { "Já estava assim (${Facts.speak(factNow())}); não mudei nada." })
        }
        if (confirmed && action != null && !switched) {
            result = "já estava"
            val label = Py.str((goal!![if (action == "turn_on") "on" else "off"] as List<*>)[0])
            val state = if (action == "turn_on") "ligado" else "desligado"
            return "The goal was already met: nothing was changed." to complete(true,
                "${if (said.isNotEmpty()) "$said " else ""}“$label” já estava $state; não mudei nada.")
        }
        if (confirmed) {
            val fact = factNow()
            val way = if (guide && said.isEmpty()) way() else ""
            return "The screen confirms the goal." to complete(true,
                said.ifEmpty { if (Py.truthy(fact)) "Pronto: ${Facts.speak(fact)}.$way" else "Pronto, conferido na tela.$way" })
        }
        if (seen) return "The provider checked the final screen: the task is done." to complete(true, said.ifEmpty { "Pronto." })
        val changed = if (guide && said.isEmpty()) Facts.told(startState, state) else ""  // como no Python
        if (changed.isNotEmpty()) {
            return "Every step was carried out, but the screen does not confirm the whole goal." to complete(true, "Pronto: $changed.${way()}")
        }
        return "Every step was carried out, but the screen does not confirm the goal." to complete(true,
            "${said.ifEmpty { if (guide) "Todos os passos foram feitos." else "Fiz todos os passos." }} (Não consegui conferir o resultado na tela.)")
    }

    fun fail(why: String, message: String): Tool {
        result = "falhou"
        return why to complete(false, message)
    }

    fun complete(success: Boolean, message: String): String {
        final = message
        return call("complete", "success" to if (success) "true" else "false", "message" to message)
    }

    fun keepScrolling(step: Step): Tool {
        if (!actsOnPhone) {
            result = "conferido"
            return "Only guiding: tell them how to keep scrolling." to complete(true, X.KEEP_SCROLLING_GUIDE)
        }
        if (rolling == null) {
            rolling = clock()
            acted = true
            cacheable = false
        }
        if (clock() - rolling!! > KEEP_SCROLLING_LIMIT) {
            result = "conferido"
            return "Scrolled long enough." to complete(true, "Parei de rolar a tela.")
        }
        rolled = !rolled
        if (rolled) return "Keep scrolling." to call("swipe", "coordinate" to "[540, 1700]", "coordinate2" to "[540, 700]", "duration" to "0.4")
        val every = try {
            minOf(maxOf(toFloat(Py.or(step["every"], KEEP_SCROLLING)), 1.0), 30.0)
        } catch (e: NumberFormatException) {
            KEEP_SCROLLING
        }
        val text = java.math.BigDecimal(every).setScale(1, java.math.RoundingMode.HALF_EVEN).toPlainString()
        return "Wait before the next scroll." to call("wait", "duration" to text)
    }

    private fun toFloat(value: Any?): Double = when (value) {
        is Number -> value.toDouble()
        is String -> Py.strip(value).toDouble()
        is Boolean -> if (value) 1.0 else 0.0
        else -> throw NumberFormatException()
    }

    /** Os rótulos curtos da tela atual, sem repetir (os nomes de menu que o mapa guarda). */
    fun screenNames(): List<String> {
        val out = ArrayList<String>()
        for (label in labels) {
            if (Py.len(label) in 2..40 && label !in out && out.size < X.SCREEN_NAMES) out.add(label)
        }
        return out
    }

    fun remember(labels: List<String>) {
        for (label in labels) {
            if (label.isNotEmpty() && Py.len(label) <= 40 && label !in seen && seen.size < X.SEEN_MAX) seen.add(label)
        }
    }

    /** Os nomes entre aspas de uma fala que não estão em nenhum rótulo da tela (como no Python). */
    fun namesOffScreen(text: String?): List<String> {
        if (text.isNullOrEmpty()) return emptyList()
        val screen = labels.map { plain(it) }
        val strip = mutableSetOf(plain(X.BUTTON_SETTINGS))
        X.SETTINGS_WAY.values.forEach { way -> way.forEach { strip.add(plain(it)) } }  // o caminho no menu, dito pelo código
        strip.addAll(X.mapNames(map))  // um nome que o mapa do aparelho conhece também vale
        button?.let { strip.add(plain(pyFormat(X.BUTTON_APP, linkedMapOf("app" to Py.str(it["open_app"] ?: ""))))) }
        val out = ArrayList<String>()
        val found = X.QUOTED_NAME.matcher(text)
        while (found.find()) {
            val name = (1..found.groupCount()).mapNotNull { found.group(it) }.first { it.isNotEmpty() }
            val wanted = plain(name)
            if (wanted in strip || screen.any { it.isNotEmpty() && (wanted in it || it in wanted) }) continue
            out.add(name)
        }
        return out
    }

    fun scroll(why: String): Tool {
        remember(labels)
        scrolls += 1
        swiped = now
        val tool = call("swipe", "coordinate" to "[540, 1800]", "coordinate2" to "[540, 800]", "duration" to "1.0")
        if (!actsOnPhone) {
            // Só guia: a pessoa rola (a faixa mostra o gesto); depois, o passo é decidido de novo na tela nova.
            val step = plan?.let { if (i < it.size) it[i] else null }
            val target = Py.iter(Py.or(step?.get("target"), emptyList<Any?>())).take(1)
            return ownerTurn(linkedMapOf("target" to target), why, tool, false, false, guide = true, redo = true)
        }
        return why to tool
    }

    fun field(step: Step, elements: List<Element>, named: Boolean = false): Element? {
        val editable = elements.filter { e -> EDITABLE.any { e.cls.endsWith(it) } }
        val asTap = LinkedHashMap(step).apply {
            put("action", "tap")
            put("target", Py.or(step["target"], emptyList<Any?>()))
        }
        val found = find(asTap, editable) ?: find(asTap, elements)
        return found ?: if (named) null else if (editable.size == 1) editable[0] else null
    }

    fun written(field: Element): Boolean = trail.any { it["action"] == "type" && X.mentions(Py.str(Py.or(it["text"], "")), field.text) }

    fun locator(element: Element?, elements: List<Element>): Map<String, Any?> {
        if (element == null) return linkedMapOf("at" to LinkedHashMap<String, Any?>())
        if (element.text.isNotEmpty() && elements.count { it.text == element.text } == 1) return linkedMapOf("target" to listOf(element.text))
        return linkedMapOf("at" to linkedMapOf("id" to element.ids.firstOrNull(), "cls" to element.cls, "bounds" to element.bounds.toList()))
    }

    fun locate(at: Map<String, Any?>, elements: List<Element>): Element? {
        val byId = elements.filter { Py.truthy(at["id"]) && at["id"] in it.ids }
        if (byId.size == 1) return byId[0]
        val hits = byId.ifEmpty { elements }.filter { it.cls == at["cls"] && listEq(it.bounds, at["bounds"]) }
        return if (hits.size == 1) hits[0] else null
    }

    private fun listEq(a: List<Long>, b: Any?): Boolean = b is List<*> && a.size == b.size && a.indices.all { Py.eq(a[it], b[it]) }

    fun ask(targets: List<Any?>, elements: List<Element>, labels: List<String>): Element? {
        asked = i
        torn = null
        if (i + 1 < plan_.size && plan_[i + 1]["action"] == "type") return null
        var chosen = pick!!(targets.map { it as String }, labels.filter { Py.len(it) <= MAX_LABEL }.distinct())
        if (chosen is List<*>) {
            torn = chosen[1] as List<Any?>
            chosen = null
        }
        note(linkedMapOf("action" to plan_[i]["action"], "target" to targets), chosen as String?, "IA local")
        if (chosen == null) {
            noted!!["efeito"] = "nenhum"
            noted = null
        }
        return elements.firstOrNull { chosen != null && it.text == chosen }
    }

    fun note(step: Map<String, Any?>, chosen: String?, by: String) {
        noted = linkedMapOf("app" to app, "passo" to linkedMapOf("acao" to step["action"], "alvo" to Py.iter(Py.or(step["target"], emptyList<Any?>())).toList()),
            "rotulos" to labels.distinct(), "escolhido" to chosen, "por" to by, "efeito" to null)
        choices.add(noted!!)
    }

    fun settled(effect: String?) {
        choice?.let {
            it["efeito"] = effect
            choice = null
        }
    }

    fun settle(): Tool {
        waited = true
        waits += 1
        return "The screen may still be changing: wait and read it again." to call("wait", "duration" to if (waits == 1) "0.7" else "1.0")
    }

    fun confirmButton(elements: List<Element>): Element? = elements.filter {
        it.text.isNotEmpty() && it.text !in before && (plain(it.text) in CONFIRM || CONFIRM_START.any { s -> plain(it.text).startsWith(s) })
    }.lastOrNull()

    fun route(elements: List<Element>): Boolean {
        val node = X.nodeAt(map, X.position(trail)) ?: return false
        val onScreen = elements.map { it.text }.toSet()
        for (j in i until minOf(i + LOOKAHEAD, plan_.size)) {
            val step = plan_[j]
            if (step["action"] !in setOf("tap", "turn_on", "turn_off") || "index" in step || "at" in step) continue
            val control = step["action"] != "tap"
            val path = X.search(node, Py.iter(Py.or(step["target"], emptyList<Any?>())).map { plain(it) }.toSet(), control)
            if (!path.isNullOrEmpty() && path[0] in onScreen) {
                val taps = path.map { linkedMapOf<String, Any?>("action" to "tap", "target" to mutableListOf(it), "via" to "map") as Step }
                val end = if (control) j else j + 1
                repeat(end - i) { plan_.removeAt(i) }
                plan_.addAll(i, taps)
                return true
            }
        }
        return false
    }

    fun arrived(elements: List<Element>): Boolean {
        val node = X.nodeAt(map, X.position(trail))
        val known = if (node != null) (node["children"] as Map<String, Any?>).keys + (node["controls"] as List<*>? ?: emptyList<Any?>()).map { it as String }
        else emptySet()
        return elements.any { it.text in known }
    }

    fun markNoop() {
        if (tapped != null && now == sign) tapped!!["noop"] = true
    }

    fun advance(step: Step, why: String, tool: String, guess: Boolean = false, blind: Boolean = false, byOwner: Boolean = false): Tool {
        if ((owner || !actsOnPhone) && !byOwner &&
            Py.search(Py.re("invoke name=\"(click|type|swipe|system_button|open_app|open_settings)\""), tool) != null) {
            return ownerTurn(step, why, tool, guess, blind, guide = !actsOnPhone && guide)
        }
        if (!byOwner) confirmation(step, tool)?.let { return it }
        if (guide && canAsk && !byOwner && ("name=\"click\"" in tool || ">quick_settings<" in tool) && !Py.eq(guideWaited, i)) {
            guideWaited = i
            return ownerTurn(step, why, tool, guess, blind, limit = if (guideAgent) GUIDE_LIMIT else null, guide = true)
        }
        if (guide && !byOwner) highlight = targetBounds(tool)
        val key = listOf(now, tool)
        if (!byOwner && ("click" in tool || "name=\"type\"" in tool)) {
            if (key in repeats && key !in flagged) {
                flagged.add(key)
                if (trail.isNotEmpty()) trail.removeAt(trail.size - 1)
                noted?.let {
                    it["efeito"] = "repetida"
                    noted = null
                }
                val stop = help(raw, "this exact action was already done on this same screen and the task did " +
                    "not move forward ($why). Do not repeat it: check whether the screen or the current state " +
                    "already shows the task done, and finish if so; otherwise take another way")
                return stop ?: step(message)
            }
            repeats.add(key)
        }
        lastKey = key
        acted = true
        var explain: Any? = if (byOwner) null else step["explain"]  // o passo da pessoa já foi explicado quando foi mostrado
        if (!Py.truthy(explain) && guide && !byOwner) explain = narrate(tool)
        if (Py.truthy(explain)) announce = if (Py.truthy(announce)) "$announce ${Py.str(explain)}" else Py.str(explain)
        markNoop()
        if (trail.size > trailLen && trail.last()["action"] in setOf("tap", "turn_on", "turn_off") && "seen" !in trail.last()) {
            // Os nomes da tela em que o passo foi feito, para o mapa (como no Python).
            (trail.last() as MutableMap<String, Any?>)["seen"] = screenNames()
        }
        val fresh = trail.size > trailLen && trail.last()["action"] == "tap" && "target" in trail.last()
        tapped = if (fresh) trail.last() else null
        trailLen = trail.size
        if (start == null && step["action"] != "open_app") start = LinkedHashSet(labels)
        i += 1
        scrolls = 0
        seen = ArrayList()
        swiped = null
        focused = null
        waited = false
        waits = 0
        confirmed = false
        before = LinkedHashSet(labels)
        sign = now
        this.guess = guess
        this.blind = blind
        switched = switched || step["action"] in setOf("turn_on", "turn_off")
        pending = step
        choice = noted
        noted = null
        return why to tool
    }

    fun typedNote(labels: List<String>): String {
        val typed = trail.filter { it["action"] == "type" && Py.len(Py.str(Py.or(it["text"], ""))) > MAX_LABEL }.map { Py.str(it["text"]) }
        if (typed.isEmpty()) return ""
        val screen = labels.map { Py.squeeze(plain(it)) }
        val shown = typed.count { text -> screen.any { Py.head(Py.squeeze(plain(text)), 40) in it } }
        return ". Checked on the device against the real screen: $shown of the ${typed.size} long texts this task typed " +
            "are on this final screen (they reach you as [hidden text])"
    }

    fun confirmation(step: Step, tool: String): Tool? {
        val name = Py.search(INVOKE, tool)!!.group(1)
        if (step["action"] in setOf("turn_on", "turn_off")) return null
        val marked = if (name == "click" || name == "system_button" && ">enter<" in tool) step["confirm"] else null
        val element = if (name == "click") toolElement(tool) else null
        if (!Py.truthy(marked) && !(element != null && element.texts.any { X.sensitive(it) })) return null
        val label = element?.text ?: Py.str(Py.iter(Py.or(step["target"], listOf<Any?>(""))).first())
        if (preapproved || approved != null && approved!!.size == 2 && Py.eq(approved!![0], i) && approved!![1] == label) {
            approved = null
            return null
        }
        if (trail.size > trailLen) trail.removeAt(trail.size - 1)
        noted?.let { mine ->
            choices = choices.filter { it !== mine }.toMutableList()
            noted = null
        }
        if (element != null && !Py.truthy(step["target"]) && "at" !in step) step["index"] = element.index
        val question = if (marked is String && Py.strip(marked).isNotEmpty()) Py.strip(marked)
        else if (label.isNotEmpty()) "Posso tocar em «$label»? Isso não dá para desfazer." else "Posso seguir? Isso não dá para desfazer."
        confirming = linkedMapOf("i" to i, "label" to label, "question" to question)
        val why = "Ask the owner to confirm an action that cannot be undone."
        if (canAsk) {
            highlight = element?.bounds
            return why to call("confirm_user", "question" to question)
        }
        markNoop()
        result = "a confirmar"
        return why to complete(true, "$question (sim / não)")
    }

    fun confirmAnswer(answer: String?): Boolean? {
        val pending = confirming ?: emptyMap()
        confirming = null
        val verdict = X.yesNo(answer)
        if (verdict == true) approved = listOf(pending["i"], pending["label"])
        else if (verdict == false) declined = if (Py.truthy(pending["label"])) pending["label"] else true
        return verdict
    }

    fun toolElement(tool: String): Element? {
        val index = Py.search(INDEX, tool) ?: return null
        return elements.firstOrNull { it.index == index.group(1).toLong() }
    }

    fun narrate(tool: String): String? {
        val name = Py.search(INVOKE, tool)!!.group(1)
        val element = toolElement(tool)
        if (name == "click") return if (element != null && element.text.isNotEmpty()) "Agora toco em «${element.text}»." else "Agora toco aqui."
        return mapOf("swipe" to "Agora rolo a tela.", "type" to "Agora escrevo no campo.", "open_app" to "Agora abro o app.")[name]
    }

    /** Onde fica o controle na tela, em palavras ("no alto da tela, à direita"); null sem a tela. Como no Python. */
    /** O caminho feito no guia, para a pessoa refazer sozinha (montado no aparelho, com os nomes da tela). */
    fun way(): String {
        // Cada parte começa ao abrir as Configurações, um app ou o painel; de uma parte que se repete vale a última, e as
        // partes diferentes vão todas, na ordem (como no Python).
        val starts = trail.indices.filter { trail[it]["action"] in setOf("open_settings", "open_app", "quick_settings") }
        val parts = LinkedHashMap<Pair<Any?, String>, List<Map<String, Any?>>>()
        for ((n, begin) in starts.withIndex()) {
            val end = if (n + 1 < starts.size) starts[n + 1] else trail.size
            val key = trail[begin]["action"] to Py.str(trail[begin]["target"])
            parts.remove(key)
            parts[key] = trail.subList(begin, end).toList()
        }
        // Uma parte sem nenhum toque foi um desvio, se outra teve (como no Python).
        val chosen = if (starts.isNotEmpty()) parts.values.toList() else listOf(trail.toList())
        val touched = chosen.filter { p -> p.drop(1).any { it["action"] in setOf("tap", "turn_on", "turn_off") } }
        val ways = touched.ifEmpty { chosen }.map { partWay(it) }.filter { it.size >= 2 }
        val text = ways.joinToString("; e ") { it.joinToString(", depois ") }
        return if (ways.isNotEmpty()) " Para fazer de novo sozinho: $text${if (text.endsWith(".")) "" else "."}" else ""
    }

    /** Os nomes de uma parte do caminho, na ordem. */
    fun partWay(entries: List<Map<String, Any?>>): List<String> {
        val names = ArrayList<String>()
        for (entry in entries) {
            val target = entry["target"]
            if (entry["action"] == "open_settings") {
                val page = Py.str(Py.iter(Py.or(target, listOf<Any?>(""))).first())
                for (name in listOf("Configurações") + (X.SETTINGS_WAY[page] ?: emptyList())) {
                    if (names.isEmpty() || names.last() != name) names.add(name)
                }
                continue
            }
            if (entry["action"] == "back" || entry["action"] == "tap" && Py.truthy(target) &&
                plain(Py.str(Py.iter(target).first())) in X.BACK_NAMES) {
                if (names.isNotEmpty()) names.removeAt(names.size - 1)  // voltar desfaz o passo de antes (como no Python)
                continue
            }
            val name = when {
                entry["action"] == "quick_settings" -> "o painel rápido"
                entry["action"] in setOf("tap", "turn_on", "turn_off") && Py.truthy(target) -> Py.str(Py.iter(target).first())
                else -> continue
            }
            if (names.isEmpty() || names.last() != name) names.add(name)
        }
        return names
    }

    fun where(bounds: List<Long>?): String? {
        val boxes = elements.mapNotNull { it.bounds }.filter { it.isNotEmpty() }
        if (bounds == null || bounds.isEmpty() || boxes.isEmpty()) return null
        val width = (boxes.maxOf { it[2] }.takeIf { it != 0L } ?: 1L).toDouble()
        val height = (boxes.maxOf { it[3] }.takeIf { it != 0L } ?: 1L).toDouble()
        val x = (bounds[0] + bounds[2]) / 2.0 / width
        val y = (bounds[1] + bounds[3]) / 2.0 / height
        val row = if (y < 1.0 / 3) "no alto" else if (y > 2.0 / 3) "embaixo" else "no meio"
        val column = if (x < 1.0 / 3) "à esquerda" else if (x > 2.0 / 3) "à direita" else ""
        if (row == "no meio" && column.isEmpty()) return "no meio da tela"
        return if (column.isNotEmpty()) "$row da tela, $column" else "$row da tela"
    }

    fun targetBounds(tool: String): List<Long>? = toolElement(tool)?.bounds

    fun ownerTurn(step: Step, why: String, tool: String, guess: Boolean, blind: Boolean, limit: Number? = null, guide: Boolean = false,
                  redo: Boolean = false): Tool {
        val name = Py.search(INVOKE, tool)!!.group(1)
        val params = LinkedHashMap<String, String>()
        Py.findall(PARAMETER, tool).forEach { (it as List<*>).let { (k, v) -> params[k as String] = v as String } }
        val index = params["index"]
        var element = elements.firstOrNull { index != null && it.index.toString() == index }
        val label = if (element != null && element.text.isNotEmpty()) element.text else Py.str(Py.iter(Py.or(step["target"], listOf<Any?>(""))).first())
        val bottom = elements.mapNotNull { it.bounds.takeIf { b -> b.isNotEmpty() }?.get(3) }.maxOrNull() ?: 0L
        if (guide && name == "click" && element != null && element.bounds.isNotEmpty() && !blind && !nudged && (
            element.bounds[3] >= bottom - 10 && element.bounds[3] - element.bounds[1] < X.CUT_OFF || covered(element, bottom))) {
            if (guess && element.text.isNotEmpty()) {
                // Um palpite: o nome real do controle vai à frente no passo, para achá-lo pelo nome depois de a tela subir.
                val others = Py.iter(Py.or(step["target"], emptyList<Any?>())).filter { !Py.eq(it, element.text) }
                step["target"] = (listOf<Any?>(element.text) + others).toMutableList()
            }
            // O controle está cortado no pé da tela: a tela sobe um pouco antes, e o passo é mostrado de novo.
            nudged = true
            guideWaited = null
            if (!actsOnPhone) {
                // Só guia: a pessoa sobe a tela um pouco, com o gesto mostrado na faixa.
                announce = "O botão está no pé da tela. Arraste a tela um pouquinho para cima, devagar."
                waiting = linkedMapOf("step" to step, "why" to why, "tool" to tool, "guess" to guess, "blind" to blind, "now" to now,
                    "labels" to labels.toMutableList(), "bounds" to null, "since" to clock(), "limit" to null,
                    "started" to clock(), "guide" to true, "gesture" to "rolar", "redo" to true, "button" to null)
                gesture = "rolar"
                return "Waiting for the owner to scroll a little." to call("wait", "duration" to "1.0")
            }
            announce = "Vou subir um pouco a tela para você ver melhor."
            return "Scroll a little so the control is fully visible." to call("swipe", "coordinate" to "[540, 1500]",
                "coordinate2" to "[540, 1200]", "duration" to "0.6")
        }
        nudged = false
        if (name == "click" && element != null && element.checked == null &&
            (step["action"] in setOf("turn_on", "turn_off") || Py.search(X.SWITCH_WORDS, Py.str(step["explain"] ?: "")) != null)) {
            element = switchFor(element) ?: element  // o destaque vai na chave, não no título (como no Python)
        }
        if (name == "click" && element != null && "seekbar" !in element.cls.lowercase()) {
            element = sliderFor(element) ?: element  // o título de uma barra: o destaque vai na barra (como no Python)
        }
        val slider = element != null && "seekbar" in element.cls.lowercase()
        var barText = X.SLIDER
        var down = false
        if (name == "click" && slider) {
            // Para diminuir, o destaque perto de um terço da barra, ou na metade do nível de agora (como no Python).
            val b = element!!.bounds
            val way = sliderWay()
            down = way.first
            val now = way.second
            if (down) {
                val at = if (now != null) minOf(X.SLIDER_DOWN_AT.toLong(), (now * 5).toLong()) else X.SLIDER_DOWN_AT.toLong()
                val middle = b[0] + Math.floorDiv((b[2] - b[0]) * at, 1000L)
                val half = Math.floorDiv(b[2] - b[0], 8L)
                element = element.copy(bounds = listOf(maxOf(b[0], middle - half), b[1], minOf(b[2], middle + half), b[3]))
                barText = X.SLIDER_DOWN
            } else {
                element = element.copy(bounds = listOf(b[0] + Math.floorDiv((b[2] - b[0]) * 3, 4L), b[1], b[2], b[3]))
            }
        }
        var say = when (name) {
            "click" -> if (slider) barText.substring(0, 1).lowercase() + barText.substring(1, barText.length - 1)
                else if (label.isNotEmpty()) "toque em «$label»" else "toque no ponto destacado"
            "type" -> if (label.isNotEmpty()) "escreva no campo «$label»" else "escreva o texto no campo"
            "swipe" -> if (label.isNotEmpty()) pyFormat(X.SCROLL_FOR, linkedMapOf("label" to label)) else "role a tela para ver mais"
            "open_app" -> if (!actsOnPhone) "toque no botão «${pyFormat(X.BUTTON_APP, linkedMapOf("app" to (params["text"] ?: "")))}», aqui embaixo"
                else Py.strip("abra o app ${params["text"] ?: ""}")
            "open_settings" -> if (!actsOnPhone) "toque no botão «${X.BUTTON_SETTINGS}», aqui embaixo"
                else Py.strip("abra as Configurações na página ${params["page"] ?: ""}")
            else -> mapOf("back" to "volte uma tela", "home" to "vá para a tela inicial", "enter" to "toque em Enter no teclado",
                "quick_settings" to "puxe a tela de cima para baixo, começando bem no alto, para abrir o painel rápido")[params["button"] ?: ""] ?: "faça o passo"
        }
        val pull = params["button"] == "quick_settings"
        gesture = if (pull) (if (splitShade()) "puxar_direita" else "puxar") else if (name == "swipe") "rolar" else null
        // Só guia: um app ou uma página das Configurações abre por um botão da faixa, que a pessoa toca.
        button = when {
            !actsOnPhone && name == "open_app" -> linkedMapOf("text" to pyFormat(X.BUTTON_APP, linkedMapOf("app" to (params["text"] ?: ""))),
                "open_app" to (params["text"] ?: ""))
            !actsOnPhone && name == "open_settings" -> linkedMapOf("text" to X.BUTTON_SETTINGS, "open_settings" to (params["page"] ?: ""))
            else -> null
        }
        var explain: String? = if (redo) null else if (Py.truthy(step["explain"])) Py.str(step["explain"]) else if (limit != null) narrate(tool) else null
        if (pull && splitShade()) {
            // Os painéis separados da One UI 7 em diante: os atalhos pelo lado direito do alto (como no Python).
            if (X.shadeOnly(raw)) explain = X.SHADE_ONLY_SAY
            else if (!explain.isNullOrEmpty() && "direit" !in plain(explain!!)) explain = X.fit(explain!!, X.PULL_RIGHT)
            else if (explain.isNullOrEmpty()) say = "puxe a tela de cima para baixo pelo lado direito, começando bem no alto, para abrir o painel rápido"
        }
        // O nome de uma chave é o da linha dela, não o estado escrito nela (como no Python).
        var shown = if (element != null && element.checked != null && element.bounds.isNotEmpty()) switchName(element)
            else element?.text ?: ""
        // Uma barra mostra só o nível ("1"): o nome dela é o título da linha (como no Python).
        if (slider && Py.search(LETTER, shown) == null) shown = sliderTitle(element!!)
        if (!explain.isNullOrEmpty() && shown.isNotEmpty()) {
            // A pessoa ouve o nome que está na tela, não o que o provedor imaginou (como no Python).
            // Só um nome entre aspas ou de mais de uma palavra: uma palavra solta pode ser outra coisa (como no Python).
            for (name in Py.iter(Py.or(step["target"], emptyList<Any?>())).map { Py.str(it) }.distinct()) {
                if (name.isEmpty() || plain(name) in plain(shown)) continue  // o nome da tela já diz o do plano
                val quoted = X.QUOTES.map { (left, right) -> left + name + right }.filter { it in explain!! }
                for (form in quoted) explain = explain!!.replace(form, form.first() + shown + form.last())
                if (quoted.isEmpty() && Py.split(name).size > 1 && name in explain!!) explain = explain!!.replace(name, shown)
            }
        }
        val where = if (element != null) where(element.bounds) else null
        if (guide && limit == null && slider) {
            val said = explain
            val own = said != null && said.isNotEmpty() && Py.search(X.BAR_SAID, said) != null &&
                (if (down) "direit" else "esquerd") !in plain(said) && Py.split(said).size <= X.GUIDE_WORDS
            announce = if (said == null || said.isEmpty() || said.startsWith("Agora toco")) barText else if (own) said
                else X.fit(said, barText)
        } else if (guide && limit == null) {
            // A pessoa faz: a explicação do provedor, mais onde fica o controle se ela não diz; sem explicação, o passo.
            announce = if (Py.truthy(explain) && !explain!!.startsWith("Agora toco")) {
                if (where != null && Py.search(POSITION, explain) == null) X.fit(explain!!, "Fica $where.") else X.short(explain!!)
            } else {
                val first = say.codePointAt(0)
                Py.upper(String(Character.toChars(first))) + say.substring(Character.charCount(first)) + (if (where != null) ", $where." else ".")
            }
        } else if (limit != null) {
            val first = say.codePointAt(0)
            say = Py.upper(String(Character.toChars(first))) + say.substring(Character.charCount(first)) + ", ou eu toco daqui a pouco."
            announce = if (Py.truthy(explain) && !explain!!.startsWith("Agora toco")) "$explain $say" else say
        } else {
            announce = if (Py.truthy(explain)) "$explain Sua vez: $say." else "Sua vez: $say."
        }
        if (Py.truthy(announce) && announce == lastSaid) announce = if (name == "swipe") X.AGAIN_SCROLL else null
        else if (Py.truthy(announce)) lastSaid = announce  // o "mais um pouco" não conta (como no Python)
        offNames = namesOffScreen(announce)
        highlight = element?.bounds
        cacheable = false
        waiting = linkedMapOf("step" to step, "why" to why, "tool" to tool, "guess" to guess, "blind" to blind, "now" to now,
            "labels" to labels.toMutableList(), "bounds" to highlight, "since" to clock(), "limit" to limit,
            "started" to clock(), "guide" to guide, "gesture" to gesture, "redo" to redo, "button" to button, "label" to label,
            "switches" to switches(), "switch" to if (element != null && element.checked != null) switchName(element) else null,
            "state" to if (facts != null) LinkedHashMap(readState()) else null, "slider" to slider)
        return "Waiting for the owner to do this step." to call("wait", "duration" to "1.0")
    }

    /** O toque da pessoa foi em outro lugar, e não no que o passo pedia: o motivo da ajuda, ou null (como no Python). */
    fun wrongTouch(waiting: MutableMap<String, Any?>): Pair<String, String>? {
        if (touchedAt == null) return null
        val started = (waiting["started"] as Number).toDouble()
        val fresh = (touchedTextAt ?: 0.0) > started
        val text = if (!touchedText.isNullOrEmpty() && fresh) touchedText!! else ""
        val box = if (!touchedBox.isNullOrEmpty() && touchedBox!!.any { it != 0L } && fresh) touchedBox else null
        val own = waiting["switch"] as String?
        // O toque foi na chave do passo, no lugar novo dela (como no Python).
        if (box != null && own != null && box == (switches()[own]?.get(1) as List<*>? ?: emptyList<Any>())) return null
        val offer = waiting["button"] as Map<*, *>?
        if (offer != null) {
            if (pressedAt != null && pressedAt!! > started) return null
            val where = if (text.isNotEmpty()) "«$text»" else "something else"
            return "lose" to ("instead of the button «${Py.str(offer["text"] ?: "")}» on the strip, they touched $where " +
                "and the screen changed. Bring them back to the way")
        }
        val label = Py.str(waiting["label"] ?: "")
        if (Py.truthy(waiting["redo"])) return null
        val before = (waiting["labels"] as List<*>).map { it as String }.toSet()
        val other = before.isNotEmpty() && (before intersect labels.toSet()).size * 10 < before.size * 3
        val bounds = waiting["bounds"] as List<*>?
        if (box != null && !bounds.isNullOrEmpty()) {
            val b = bounds.map { (it as Number).toLong() }
            if (box[0] < b[2] && b[0] < box[2] && box[1] < b[3] && b[1] < box[3]) return null
            if (other) return "lose" to ("instead of «${label.ifEmpty { "the highlighted control" }}» they touched " +
                "«${text.ifEmpty { "another place" }}», and another screen opened. Bring them back to the way")
            if (elements.none { it.bounds == box }) {
                // O que ela tocou não está na tela lida: espera a tela mostrar o toque; sem isso, não diz que ela errou.
                val reads = ((waiting["unseen_reads"] as Number?)?.toLong() ?: 0L) + 1
                waiting["unseen_reads"] = reads
                return if (reads < X.TOUCH_READS) "wait" to "" else null
            }
            return "fix" to text
        }
        if (label.isEmpty() || text.isEmpty()) return null
        val wanted = plain(label)
        val got = plain(text)
        if (wanted in got || got in wanted || !other) return null
        return "lose" to "instead of «$label» they touched «$text», and another screen opened. Bring them back to the way"
    }

    /** Um toque fora do destaque, na mesma tela: o mesmo passo, com o destaque, e a correção na hora (como no Python). */
    fun pointAgain(waiting: MutableMap<String, Any?>, touched: String): Tool {
        val label = Py.str(waiting["label"] ?: "")
        changedSwitch(waiting)?.let { (name, state, box) -> return undo(waiting, name, state, box) }  // sem a chave do passo
        announce = if (touched.isNotEmpty() && label.isNotEmpty()) pyFormat(X.WRONG_SPOT, linkedMapOf("touched" to touched, "label" to label))
            else pyFormat(X.WRONG_SPOT_BLIND, linkedMapOf("label" to if (label.isNotEmpty()) ": «$label»" else ""))
        waiting["now"] = now
        waiting["labels"] = labels.toMutableList()
        waiting["started"] = clock()
        waiting["since"] = clock()
        waiting["reminded"] = false
        waiting.remove("changed")
        this.waiting = waiting
        highlight = waiting["bounds"] as List<Long>?
        gesture = waiting["gesture"] as String?
        button = waiting["button"] as Map<String, Any?>?
        return "The owner touched outside the highlight: show the place again." to call("wait", "duration" to "1.0")
    }

    /** Uma chave que mudou desde que o passo foi mostrado e não é a do passo: (nome, estado, limites), ou null. */
    fun changedSwitch(waiting: Map<String, Any?>): Triple<String, Boolean, List<Long>>? {
        val before = waiting["switches"] as Map<String, List<Any?>>? ?: emptyMap()
        val bounds = (waiting["bounds"] as List<*>?)?.map { (it as Number).toLong() }
        for ((name, now) in switches()) {
            val was = before[name] ?: continue
            val state = now[0] as Boolean
            if (was[0] == null || state == was[0]) continue
            val box = now[1] as List<Long>
            if (!bounds.isNullOrEmpty() && box[0] < bounds[2] && bounds[0] < box[2] && box[1] < bounds[3] && bounds[1] < box[3]) continue
            val step = waiting["step"] as Map<*, *>?
            val targets = (listOf(waiting["label"], waiting["switch"]) + Py.iter(Py.or(step?.get("target"), emptyList<Any?>())))
                .filter { Py.truthy(it) }.map { plain(Py.str(it)) }.toSet()
            if (plain(name) in targets) continue  // a chave do passo, que mudou de lugar ao mudar (como no Python)
            return Triple(name, state, box)
        }
        return null
    }

    /** A chave de um controle que não é chave: a que tem o nome do texto dele, ou a única na mesma linha. */
    fun switchFor(element: Element): Element? {
        val text = if (element.text.isNotEmpty()) plain(element.text) else ""
        for (other in elements) {
            if (other.checked != null && other.bounds.isNotEmpty() && text.isNotEmpty() && plain(switchName(other)) == text) return other
        }
        if (element.bounds.isNotEmpty()) {
            val top = element.bounds[1]
            val bottom = element.bounds[3]
            val row = elements.filter { it.checked != null && it.bounds.isNotEmpty() && it.bounds[1] < bottom && top < it.bounds[3] }
            if (row.size == 1) return row[0]
        }
        return null
    }

    /** Um controle da metade de baixo da tela quase todo embaixo de outro desenhado por cima (como no Python). */
    fun covered(element: Element, bottom: Long): Boolean {
        val (x1, y1, x2, y2) = element.bounds
        if (y1 < bottom / 2.0) return false
        val area = maxOf(1L, (x2 - x1) * (y2 - y1))
        for (other in elements) {
            if (other.index <= element.index || other.bounds.isEmpty()) continue
            val (ox1, oy1, ox2, oy2) = other.bounds
            if (ox1 >= x1 && oy1 >= y1 && ox2 <= x2 && oy2 <= y2) continue  // dentro dele
            val width = minOf(x2, ox2) - maxOf(x1, ox1)
            val height = minOf(y2, oy2) - maxOf(y1, oy1)
            if (width > 0 && height > 0 && width * height >= area * X.COVERED) return true
        }
        return false
    }

    /** Uma opção já escolhida: o botão de opção dela marcado (o próprio alvo, ou o logo abaixo dele; como no Python). */
    fun chosen(target: Element, elements: List<Element>): Boolean {
        if ("radio" in target.cls.lowercase()) return target.checked == true
        if (target.bounds.isEmpty()) return false
        val x1 = target.bounds[0]
        val x2 = target.bounds[2]
        val bottom = target.bounds[3]
        for (other in elements) {
            if ("radio" !in other.cls.lowercase() || other.bounds.isEmpty()) continue
            val gap = other.bounds[1] - bottom
            if (gap >= 0 && gap <= X.SLIDER_GAP && minOf(x2, other.bounds[2]) - maxOf(x1, other.bounds[0]) > 0) return other.checked == true
        }
        return false
    }

    /** O plano acabou e o objetivo pede um volume que ainda não veio: os passos até a barra dele, uma vez (como no Python). */
    /** O objetivo da resposta; o provedor às vezes o põe dentro de um passo: vale o primeiro deles (como no Python). */
    fun planGoal(answer: Map<String, Any?>): Any? {
        val goal = answer["goal"]
        if (goal is Map<*, *> && goal.isNotEmpty()) return goal
        for (s in Py.iter(Py.or(answer["steps"], emptyList<Any?>()))) {
            val g = (s as? Map<*, *>)?.get("goal")
            if (g is Map<*, *> && g.isNotEmpty()) return g
        }
        return goal
    }

    /** O passo `read` lê o nível de uma barra que está na tela (o nome dela, ou o título logo acima dela). */
    fun readsBar(step: Map<String, Any?>, elements: List<Element>): Boolean {
        val t = step["target"]
        val names = (if (t is List<*>) t else listOf(t)).map { plain(Py.str(it)) }.toSet()
        return elements.any { it.text.isNotEmpty() && plain(it.text) in names && ("seekbar" in it.cls.lowercase() || sliderFor(it) != null) }
    }

    /** Para onde vai a barra do guia: (true, o nível de agora ou null) quando o objetivo pede todos os níveis menores
     *  ("down", ou um número abaixo do lido agora); (false, null) nos outros casos. Como `slider_way` do Python. */
    fun sliderWay(): Pair<Boolean, Double?> {
        val fact = (goal ?: emptyMap<String, Any?>())["fact"] as? Map<String, Any?> ?: return Pair(false, null)
        val ways = mutableListOf<Boolean>()
        var now: Double? = null
        for ((key, wanted) in fact) {
            val raw = state[key]
            val current = if (raw is Number && raw !is Boolean) raw.toDouble() else null
            if (key !in Facts.LEVELS) continue
            if (Py.plain(Py.str(wanted)) in Facts.CHANGES) {
                ways.add(Facts.CHANGES.getValue(Py.plain(Py.str(wanted))) < 0)
            } else if (wanted is Number && current != null) {
                ways.add(wanted.toDouble() < current)
            } else {
                continue
            }
            now = current
        }
        if (ways.isNotEmpty() && ways.all { it }) return Pair(true, if (ways.size == 1) now else null)
        return Pair(false, null)
    }

    fun levelSteps(elements: List<Element>): List<Step> {
        val fact = (goal ?: emptyMap<String, Any?>())["fact"] as? Map<String, Any?> ?: return emptyList()
        if ((plan ?: emptyList()).any { Py.truthy(it["level"]) }) return emptyList()
        for ((key, wanted) in fact) {
            if (key in X.SET_ROUTES && key in Facts.LEVELS && Py.plain(Py.str(wanted)) in Facts.CHANGES &&
                Facts.met(linkedMapOf(key to wanted), state, startState) == false) {
                val bar = X.SET_ROUTES.getValue(key).second.last()
                val names = bar.map { plain(it) }.toSet()
                val steps: List<Map<String, Any?>> = if (elements.any { plain(it.text) in names && sliderFor(it) != null }) {
                    listOf(linkedMapOf("action" to "tap", "target" to bar.toMutableList()))
                } else {
                    val up = Facts.CHANGES.getValue(Py.plain(Py.str(wanted))) > 0
                    guided(listOf(linkedMapOf("action" to "set", "target" to listOf(key), "value" to if (up) 100L else 0L))).map { it as Map<String, Any?> }
                }
                return steps.map { (LinkedHashMap(it) + ("level" to true)).toMutableMap() as Step }
            }
        }
        return emptyList()
    }

    /** O botão que abre inteiro o painel de atalhos compacto («Expandir»), ou null. */
    fun expander(elements: List<Element>): Element? = elements.firstOrNull { plain(it.text) in X.EXPANDERS }

    /** Os painéis separados da One UI 7 em diante (a descrição do aparelho traz a versão). */
    fun splitShade(): Boolean {
        val found = Py.search(X.SPLIT_SHADE, device) ?: return false
        return found.group(1).toInt() >= 7
    }

    /** O título de uma barra: o texto logo acima dela, na mesma coluna (até SLIDER_GAP px). Vazio se não há. */
    fun sliderTitle(slider: Element): String {
        val x1 = slider.bounds[0]
        val top = slider.bounds[1]
        val x2 = slider.bounds[2]
        for (other in elements) {
            if (other.text.isEmpty() || "seekbar" in other.cls.lowercase() || other.bounds.isEmpty()) continue
            val gap = top - other.bounds[3]
            if (gap >= 0 && gap <= X.SLIDER_GAP && minOf(x2, other.bounds[2]) - maxOf(x1, other.bounds[0]) > 0) return other.text
        }
        return ""
    }

    /** A barra logo abaixo de um controle que não é barra, na mesma coluna (até SLIDER_GAP px). Null se não há. */
    fun sliderFor(element: Element): Element? {
        if (element.bounds.isEmpty()) return null
        val x1 = element.bounds[0]
        val x2 = element.bounds[2]
        val bottom = element.bounds[3]
        for (other in elements) {
            if ("seekbar" !in other.cls.lowercase() || other.bounds.isEmpty()) continue
            val gap = other.bounds[1] - bottom
            if (gap >= 0 && gap <= X.SLIDER_GAP && minOf(x2, other.bounds[2]) - maxOf(x1, other.bounds[0]) > 0) return other  // basta encostar
        }
        return null
    }

    /** O nome de uma chave: o texto dela, ou, se ele é só o estado ("Ativado"), o rótulo mais à esquerda da linha. */
    fun switchName(element: Element): String {
        if (element.text.isNotEmpty() && plain(element.text) !in X.STATE_WORDS) return element.text
        val top = element.bounds[1]
        val bottom = element.bounds[3]
        val row = elements.filter { it !== element && it.text.isNotEmpty() && it.bounds.isNotEmpty() && it.bounds[1] < bottom &&
            top < it.bounds[3] && plain(it.text) !in X.STATE_WORDS }
        return row.minWithOrNull(compareBy<Element>({ it.bounds[0] }, { it.index }))?.text ?: element.text
    }

    /** As chaves da tela: {nome: [ligada, limites]}. */
    /** A página das Configurações já está na tela: o título dela (o nome no menu) no alto (como no Python). */
    /** Na tela do passo, o último toque foi num controle visível fora do destaque: o nome dele, para a correção na hora;
     *  null se não foi isso ou não se sabe (como `touched_elsewhere` no Python). */
    fun touchedElsewhere(waiting: Map<String, Any?>): String? {
        val bounds = (waiting["bounds"] as List<*>?)?.map { (it as Number).toLong() }
        val box = touchedBox
        val at = touchedTextAt
        if (waiting["button"] != null || Py.truthy(waiting["redo"]) || bounds.isNullOrEmpty() || box.isNullOrEmpty() ||
            box.all { it == 0L } || at == null) return null
        if (at <= (waiting["started"] as Number).toDouble() || (touchedAt ?: 0.0) > at + X.TOUCH_GAP) return null
        if (box[0] < bounds[2] && bounds[0] < box[2] && box[1] < bounds[3] && bounds[1] < box[3]) return null
        val own = waiting["switch"] as String?
        if (own != null && box == (switches()[own]?.get(1) as List<*>? ?: emptyList<Any>())) return null
        if (elements.none { it.bounds == box }) return null
        return touchedText ?: ""
    }

    /** A tela ficou igual depois do toque: o passo conta só se o aparelho mediu uma mudança desde que ele foi mostrado
     *  (a letra, um volume, o brilho); sem o estado, como antes (como `unseen_change` no Python). */
    fun unseenChange(waiting: Map<String, Any?>): Boolean {
        @Suppress("UNCHECKED_CAST")
        val before = waiting["state"] as Map<String, Any?>?
        if (facts == null || before.isNullOrEmpty()) return true
        val current = readState()
        // O que muda sozinho não é efeito do toque: o que está tocando, e o brilho automático (como no Python).
        val alone = setOf("media_playing") + (if (Py.truthy(before["auto_brightness"]) && !Py.truthy(waiting["slider"])) setOf("brightness") else emptySet())
        return before.any { (key, value) -> key !in alone && !Py.eq(current[key], value) }
    }

    fun pageOpen(page: String): Boolean {
        val way = X.SETTINGS_WAY[page]
        val app = Py.splitlines(raw).firstOrNull { "**App:**" in it } ?: ""
        if (way.isNullOrEmpty() || "com.android.settings" !in app) return false
        val bottom = elements.maxOfOrNull { it.bounds[3] } ?: 0L
        return elements.any { plain(it.text) == plain(way.last()) && it.bounds[3] * 100 <= bottom * 10 }
    }

    /** O controle destacado mudou de lugar com os mesmos textos na tela: o destaque vai junto (como no Python). */
    fun follow(waiting: MutableMap<String, Any?>) {
        val bounds = (waiting["bounds"] as List<*>?)?.map { (it as Number).toLong() }
        if (bounds.isNullOrEmpty()) return
        val own = waiting["switch"] as String?
        val new: List<Long>? = if (own != null) {
            (switches()[own]?.get(1) as List<*>?)?.map { (it as Number).toLong() }
        } else {
            val label = plain(Py.str(waiting["label"] ?: ""))
            val same = elements.filter { e -> label.isNotEmpty() && e.bounds.isNotEmpty() && plain(e.text) == label &&
                e.bounds[2] - e.bounds[0] == bounds[2] - bounds[0] && e.bounds[3] - e.bounds[1] == bounds[3] - bounds[1] }
            if (same.size == 1) same[0].bounds.toList() else null
        }
        if (!new.isNullOrEmpty() && new != bounds) waiting["bounds"] = new
    }

    fun switches(): Map<String, List<Any?>> {
        val out = LinkedHashMap<String, List<Any?>>()
        for (element in elements) {
            if (element.checked != null && element.bounds.isNotEmpty()) {
                val name = switchName(element)
                if (name.isNotEmpty() && name !in out) out[name] = listOf(element.checked, element.bounds.toList())
            }
        }
        return out
    }

    /** Um toque errado mudou a chave `name`: antes de seguir, a pessoa a desfaz (como no Python). */
    fun undo(waiting: MutableMap<String, Any?>, name: String, state: Boolean, bounds: List<Long>): Tool {
        val fix = LinkedHashMap(waiting)
        fix["label"] = name
        fix["bounds"] = bounds
        fix["undo"] = linkedMapOf("name" to name, "state" to !state)
        fix["resume"] = waiting
        fix["now"] = now
        fix["labels"] = labels.toMutableList()
        fix["started"] = clock()
        fix["since"] = clock()
        fix["reminded"] = false
        fix["button"] = null
        fix["gesture"] = null
        fix.remove("changed")
        this.waiting = fix
        highlight = bounds
        gesture = null
        button = null
        announce = pyFormat(X.UNDO, linkedMapOf("did" to if (state) "ligou" else "desligou", "name" to name,
            "undo" to if (state) "desligar" else "ligar"))
        lastSaid = null
        return "The owner changed a switch by mistake: undo it first." to call("wait", "duration" to "1.0")
    }

    /** Depois do toque na chave mudada sem querer: desfeita, o passo de antes volta; senão, o pedido continua. */
    fun undone(fix: MutableMap<String, Any?>): Tool {
        val undo = fix["undo"] as Map<String, Any?>
        val state = switches()[undo["name"] as String]?.get(0)
        if (state != null && state != undo["state"]) {  // a chave sumiu da tela: o passo de antes volta (como no Python)
            fix["now"] = now
            fix["labels"] = labels.toMutableList()
            fix["started"] = clock()
            fix["since"] = clock()
            fix.remove("changed")
            this.waiting = fix
            highlight = fix["bounds"] as List<Long>?
            return "Waiting for the owner to undo the switch." to call("wait", "duration" to "1.0")
        }
        val resume = fix["resume"] as MutableMap<String, Any?>
        resume["now"] = now
        resume["labels"] = labels.toMutableList()
        resume["started"] = clock()
        resume["since"] = clock()
        resume["reminded"] = false
        resume["switches"] = switches()
        resume.remove("changed")
        this.waiting = resume
        highlight = resume["bounds"] as List<Long>?
        gesture = resume["gesture"] as String?
        button = resume["button"] as Map<String, Any?>?
        announce = pyFormat(X.UNDONE, linkedMapOf("label" to Py.str(Py.or(resume["label"], "o destaque"))))
        lastSaid = null
        return "The switch is back: show the step again." to call("wait", "duration" to "1.0")
    }

    /** A pessoa saiu do caminho: a faixa pede para esperar já; a ajuda vem na leitura seguinte (`lost`). */
    fun lose(reason: String): Tool {
        lost = reason
        rerouting = true
        highlight = null
        gesture = null
        button = null
        announce = X.LOST_WAIT
        lastSaid = null
        return "The owner left the way: ask them to wait." to call("wait", "duration" to "0.5")
    }

    fun ownerProgress(): Tool? {
        val waiting = this.waiting!!
        val limit = waiting["limit"]
        if (!owner && !Py.truthy(limit) && !Py.truthy(waiting["guide"])) {
            this.waiting = null
            return null
        }
        // Ela tocou depois de o passo ser mostrado, e a tela ficou igual: o passo conta (o «A» grande, uma barra).
        val touchedNow = touchedAt
        val quiet = now == waiting["now"] && touchedNow != null && touchedNow > (waiting["started"] as Number).toDouble() &&
            clock() - touchedNow >= X.OWNER_QUIET && waiting["button"] == null &&  // num botão, a página tem de abrir
            (Py.truthy(waiting["redo"]) || unseenChange(waiting))  // e um estado medido mudou (num passo de rolar, não precisa)
        if (now == waiting["now"] && !quiet) {
            val elsewhere = touchedElsewhere(waiting)
            if (elsewhere != null) {
                this.waiting = null
                return pointAgain(waiting, elsewhere)
            }
            val touchedDead = touchedAt
            if (touchedDead != null && touchedDead > (waiting["started"] as Number).toDouble() && waiting["button"] == null &&
                waiting["gesture"] == null && clock() - touchedDead > X.DEAD_TOUCH && !unseenChange(waiting)) {
                // Tocou, e nada mudou: o destaque não reage a toque; a ajuda acha o controle que faz (como no Python).
                this.waiting = null
                val stop = help(raw, "the owner tapped the highlighted «${Py.str(waiting["label"] ?: "")}» and nothing " +
                    "changed on the screen nor in the state: it does not react to a tap. Point to " +
                    "the control on this screen that does it, or take another way")
                return stop ?: step(message)
            }
            val offered = waiting["button"] as Map<*, *>?
            val pressed = pressedAt
            if (offered != null && pressed != null && pressed > (waiting["started"] as Number).toDouble() &&
                clock() - pressed > X.BUTTON_DEAD) {
                // O botão não abriu a página: o caminho pelos menus (como no Python).
                this.waiting = null
                noButtons = true
                val deadPage = offered["open_settings"]
                val dead = trail.indexOfLast { it["action"] == "open_settings" && Py.eq(it["target"], listOf(deadPage)) }
                if (Py.truthy(deadPage) && dead >= 0) trail.removeAt(dead)  // a página não abriu: o caminho do fim não passa por ela
                lost = "they pressed the button «${Py.str(offered["text"] ?: "")}» on the strip, and the page " +
                    "did not open on this phone. Guide them from this screen through the menus, one tap per " +
                    "step, with no \"open_settings\" or \"open_app\" step"
                rerouting = true
                highlight = null
                gesture = null
                button = null
                announce = X.BUTTON_DEAD_SAY
                lastSaid = null
                return "The strip's button did not open the page: ask for the way through the menus." to call("wait", "duration" to "0.5")
            }
            if (Py.truthy(limit) && speaking) waiting["since"] = clock()
            if (Py.truthy(limit) && clock() - (waiting["since"] as Number).toDouble() > (limit as Number).toDouble()) {
                this.waiting = null
                val done = advance(waiting["step"] as Step, waiting["why"] as String, waiting["tool"] as String,
                    waiting["guess"] as Boolean, waiting["blind"] as Boolean)
                announce = null
                return done
            }
            if (Py.truthy(waiting["guide"]) && !Py.truthy(limit) && !Py.truthy(waiting["reminded"]) &&
                remindedStep != i && clock() - (waiting["since"] as Number).toDouble() > GUIDE_REMIND) {
                waiting["reminded"] = true
                remindedStep = i  // uma vez por passo (como no Python)
                announce = if (actsOnPhone) GUIDE_REMINDER
                    else if (offered != null) pyFormat(X.GUIDE_REMINDER_BUTTON, linkedMapOf("button" to Py.str(offered["text"] ?: "")))
                    else X.GUIDE_REMINDER_GESTURE[waiting["gesture"]] ?: X.GUIDE_REMINDER_ONLY  // um gesto não tem destaque
            }
            if (clock() - (waiting["since"] as Number).toDouble() > OWNER_LIMIT) {
                this.waiting = null
                markNoop()
                result = "esperou o dono"
                return "The owner did not do the step." to complete(true,
                    "Fiquei esperando você fazer o passo. Quando quiser continuar, é só me chamar.")
            }
            follow(waiting)
            highlight = waiting["bounds"] as List<Long>?
            gesture = waiting["gesture"] as String?
            button = waiting["button"] as Map<String, Any?>?
            return "Waiting for the owner to do this step." to call("wait", "duration" to "1.0")
        }
        val touched = touchedAt
        // Num passo de voltar, a tecla de voltar não chega como toque: a tela mudar é o passo dela (como no Python).
        if (touched != null && touched < (waiting["started"] as Number).toDouble() && (waiting["step"] as Map<*, *>)["action"] != "back") {
            val changed = (waiting.getOrPut("changed") { clock() } as Number).toDouble()
            val reads = ((waiting["late_reads"] as Number?)?.toLong() ?: 0L) + 1
            waiting["late_reads"] = reads
            if (clock() - changed < X.TOUCH_LATE || reads < X.TOUCH_READS) {
                // O toque dela chega na leitura seguinte da faixa, depois da tela: espera por ele (como no Python).
                highlight = null
                gesture = null
                button = waiting["button"] as Map<String, Any?>?  // o botão da faixa continua: a tela de baixo pode mudar sozinha
                return "Waiting for the owner's touch to arrive." to call("wait", "duration" to "0.5")
            }
            // A tela mudou sem um toque da pessoa: não é o passo dela; o passo é decidido de novo nesta tela.
            this.waiting = null
            guideWaited = null
            val before = (waiting["labels"] as List<*>).map { it as String }.toSet()
            if (before.isNotEmpty() && (before intersect labels.toSet()).size * 10 < before.size * 3) {
                // Outra tela: a pessoa voltou ou tocou em outro lugar sem querer; a ajuda mostra o caminho de volta.
                val step = waiting["step"] as Step
                val target = Py.str(Py.iter(Py.or(step["target"], listOf<Any?>(""))).first())
                return lose("while you waited for the owner to touch «$target», the screen changed to another " +
                    "one without their tap on it: they probably went back or touched something else by " +
                    "mistake. Bring them back to the way")
            }
            return null
        }
        this.waiting = null
        if (waiting["undo"] != null) return undone(waiting)
        changedSwitch(waiting)?.let { (name, state, box) -> return undo(waiting, name, state, box) }
        if (waiting["button"] != null && !(pressedAt != null && pressedAt!! > (waiting["started"] as Number).toDouble())) {
            // O aviso do toque no botão ainda não chegou: espera por ele um pouco (como no Python).
            if ("pressed_late" !in waiting) waiting["pressed_late"] = clock()
            val reads = ((waiting["late_reads"] as Number?)?.toLong() ?: 0L) + 1
            waiting["late_reads"] = reads
            if (clock() - (waiting["pressed_late"] as Number).toDouble() < X.TOUCH_LATE || reads < X.TOUCH_READS) {
                this.waiting = waiting
                button = waiting["button"] as Map<String, Any?>?
                return "Waiting for the touch on the strip's button to arrive." to call("wait", "duration" to "0.5")
            }
        }
        val own = waiting["switch"] as String?
        val was = (waiting["switches"] as Map<String, List<Any?>>?)?.get(own)
        val nowState = if (own != null) switches()[own]?.get(0) else null
        val moved = was != null && nowState != null && nowState != was[0]  // a chave do passo mudou: o passo foi feito
        if (!moved) wrongTouch(waiting)?.let { (kind, said) ->
            if (kind == "wait") {
                // A tela lida ainda não mostra o toque: espera por ela (como no Python).
                this.waiting = waiting
                highlight = waiting["bounds"] as List<Long>?
                gesture = waiting["gesture"] as String?
                button = waiting["button"] as Map<String, Any?>?
                return "Waiting for the screen to show the owner's touch." to call("wait", "duration" to "0.5")
            }
            return if (kind == "fix") pointAgain(waiting, said) else lose(said)
        }
        if (Py.truthy(waiting["redo"])) {
            val before = (waiting["labels"] as List<*>).map { it as String }.toSet()
            if (before.isNotEmpty() && (before intersect labels.toSet()).size * 10 < before.size * 3) {
                // Era para rolar (ou confirmar) nesta tela, e ela virou outra: a pessoa saiu do caminho (como no Python).
                val step = waiting["step"] as Step
                val target = Py.str(Py.iter(Py.or(step["target"], listOf<Any?>(""))).first())
                return lose("while they were scrolling to find «$target», the screen changed to another one: " +
                    "they probably went back or touched something else by mistake. Bring them back to the way")
            }
            ownerSteps += 1
            by = "dono"
            return null  // rolou ou confirmou: o passo do plano é decidido (ou conferido) de novo nesta tela
        }
        val now = this.now
        val labels = this.labels
        this.now = waiting["now"] as List<Any?>?
        this.labels = waiting["labels"] as List<String>
        advance(waiting["step"] as Step, waiting["why"] as String, waiting["tool"] as String, waiting["guess"] as Boolean,
            waiting["blind"] as Boolean, byOwner = true)
        this.now = now
        this.labels = labels
        by = "dono"
        ownerSteps += 1
        if (quiet) pending = null  // nada na tela para conferir: segue, e o fim confere
        return null
    }

    fun help(raw: String, reason: String, owner: Boolean = false, review: Boolean = false): Tool? {
        var reason = reason
        helps += if (owner || review) 0 else 1
        by = "provedor"
        if (seen.isNotEmpty()) {
            // O que passou pela tela enquanto rolava: o controle procurado pode ter outro nome neste aparelho.
            reason = "$reason. While scrolling for this step, these were on the screen (what you look for may have " +
                "another name on this phone: use one of these exact names): ${seen.joinToString("; ")}"
            seen = ArrayList()
        }
        val step: Map<String, Any?> = if (i < plan_.size) plan_[i] else linkedMapOf("action" to "reach the goal")
        val key = Json.dumps(listOf(step["action"], step["text"], Py.iter(Py.or(step["target"], listOf<Any?>(null))).first()))
        stuck[key] = ((stuck[key] as Number?)?.toInt() ?: 0) + if (owner || review) 0 else 1
        val stuckHere = (stuck[key] as Number).toInt()
        val last = helps > MAX_HELP || stuckHere > MAX_SAME_HELP
        if (last && canAsk && questions < MAX_QUESTIONS) {
            reason += "." + ASK_NOW
        } else if (helps > MAX_HELP) {
            return fail("Too many requests for help.", "Não consegui terminar: tentei vários caminhos e nenhum deu certo.")
        } else if (stuckHere > MAX_SAME_HELP) {
            return fail("Stuck on the same step.", "Não consegui terminar: fiquei preso no mesmo passo mesmo depois de tentar outro caminho.")
        }
        val executed = trail.map { entry -> linkedMapOf<String, Any?>().apply { for (k in listOf("action", "target", "text")) if (k in entry) put(k, entry[k]) } }
        val answer = askJson(pyFormat(HELP_PROMPT, linkedMapOf(
            "device" to device, "task" to requestText(help = true), "history" to history,
            "goal" to if (Py.truthy(goal)) Json.dumps(goal) else "none",
            "state" to stateLine(),
            "done" to Json.dumps(executed),
            "step" to Json.dumps(step), "reason" to reason,
            "tried" to if (tried.isNotEmpty()) Json.dumps(tried) else "none",
            "screen" to "<device_state>\n${X.redact(raw)}\n</device_state>", "ask" to if (canAsk) ASK else "",
            "close" to X.closeNames(task, labels), "guide" to if (guide) GUIDE_HELP else "")))
        if (answer == null || !(answer["steps"] is List<*> || answer["finish"] is Map<*, *> || answer["ask"] is Map<*, *>)) {
            return fail("The provider's answer could not be used.", "O provedor respondeu algo que não entendi; parei aqui.")
        }
        correct(planGoal(answer))
        val ask = answer["ask"]
        if (canAsk && ask is Map<*, *> && Py.truthy(ask["question"])) {
            stuck[key] = 0L
            helps = minOf(helps, MAX_HELP - 2)
            return askOwner(linkedMapOf("question" to Py.str(ask["question"]), "secret" to Py.truthy(ask["secret"]),
                "options" to Py.iter(Py.or(ask["options"], emptyList<Any?>())).map { Py.str(it) }.take(4)))
        }
        if (last && "finish" !in answer) {
            return fail("Too many requests for help.", "Não consegui terminar: tentei vários caminhos e nenhum deu certo.")
        }
        if ("finish" in answer) {
            val end = answer["finish"] as Map<String, Any?>
            if (!Py.truthy(end["success"])) return fail("The provider ended the task.", Py.str(end["message"] ?: ""))
            return finish(goalState(elements, labels) == true, Py.str(end["message"] ?: ""), seen = assistant)
        }
        tried.add(Json.parse(Json.dumps(answer["steps"])))
        val rest = adopt(answer["steps"])
        while (plan_.size > i) plan_.removeAt(plan_.size - 1)
        plan_.addAll(rest)
        scrolls = 0
        focused = null
        guideWaited = null  // um passo novo no mesmo lugar do plano: no guia, a vez da pessoa vale de novo
        return null
    }

    fun correct(goal: Any?) {
        if (goal !is Map<*, *>) return
        val g = goal as Map<String, Any?>
        var texts: Any? = Py.or(g["shows"], emptyList<Any?>())
        texts = if (texts is String) listOf(texts) else texts
        val gone = Py.or(g["gone"], emptyList<Any?>())
        if (Py.truthy(gone) && !(Py.truthy(g["on"]) || Py.truthy(g["off"]) || Py.truthy(g["fact"]) || Py.truthy(texts))) {
            this.goal = LinkedHashMap(this.goal ?: emptyMap()).apply { put("gone", if (gone is String) mutableListOf(gone) else Py.iter(gone).toMutableList()) }
            return
        }
        if (Py.truthy(g["on"]) || Py.truthy(g["off"]) || g["fact"] is Map<*, *> ||
            Py.truthy(texts) && Py.iter(texts).none { text -> labels.any { X.matches(text, it) } }) {
            adopt(emptyList<Any?>(), g)
        }
    }

    fun read(step: Map<String, Any?>, labels: List<String>): String? {
        val words = Py.iter(Py.or(step["target"], emptyList<Any?>())).map { plain(it) }.distinct().ifEmpty { listOf("") }
        val pattern = try {
            Py.compile(Py.or(step["pattern"] as String?, ".+"))
        } catch (e: java.util.regex.PatternSyntaxException) {
            return null
        }
        val title = Py.split(words.joinToString(" ")).toSet()
        var best: Pair<List<Int>, String>? = null
        for ((n, label) in labels.withIndex()) {
            val found = words.filter { it in plain(label) }
            val reaches = if (found.isEmpty()) emptyList() else if (title.containsAll(Py.split(plain(label)))) listOf(1) else listOf(0, 1)
            for (reach in reaches) {
                val text = labels.subList(minOf(n + reach, labels.size), minOf(n + reach + 1, labels.size)).joinToString(" ")
                val match = pattern.matcher(text)
                if (match.find()) {
                    val score = listOf(found.size, found.maxOf { Py.len(it) }, -reach, -n)
                    val candidate = score to match.group()
                    if (best == null || compareScores(candidate, best) > 0) best = candidate
                    break
                }
            }
        }
        return best?.second
    }

    private fun compareScores(a: Pair<List<Int>, String>, b: Pair<List<Int>, String>): Int {
        for (k in a.first.indices) if (a.first[k] != b.first[k]) return a.first[k].compareTo(b.first[k])
        return Py.ORDER.compare(a.second, b.second)
    }

    fun visible(texts: List<Any?>, labels: List<String>) = texts.any { text -> text is String && labels.any { X.mentions(text, it) } }

    fun find(step: Map<String, Any?>, elements: List<Element>): Element? = Companion.find(step, elements)
    fun control(target: Element, elements: List<Element>): Element? = Companion.control(target, elements)
    fun flips(target: Element, elements: List<Element>): Element? = Companion.flips(target, elements)
    fun checked(target: Element, elements: List<Element>): Boolean? = Companion.checked(target, elements)

    companion object {
        private val INVOKE = Py.re("invoke name=\"(\\w+)\"")
        private val LETTER = Py.re("[^\\W\\d_]")
        private val INDEX = Py.re("<parameter name=\"index\">(\\d+)</parameter>")
        private val PARAMETER = Py.re("<parameter name=\"(\\w+)\">(.*?)</parameter>", "s")

        /** No guia, um ajuste que o sistema mudaria direto (`set`) vai pelas telas. */
        fun guided(steps: Any?): List<Any?> {
            val out = ArrayList<Any?>()
            for (step in Py.iter(steps)) {
                val target = (step as? Map<*, *>)?.get("target")
                val first = if (target is List<*> && target.isNotEmpty()) target[0] else Py.or(target, "")
                val name = plain(Py.str(first)).replace(" ", "_")
                if (step is Map<*, *> && step["action"] == "set" && name in SET_SCREENS) {
                    val (page, labels) = SET_SCREENS.getValue(name)
                    out.add(linkedMapOf("action" to "open_settings", "target" to mutableListOf(page), "explain" to "Abro as Configurações, na página desse ajuste."))
                    val on = Py.truthy(if ("value" in step) step["value"] else true)
                    val choice = !on && name in X.SET_SCREENS_OFF  // desligar é marcar a outra opção (Claro)
                    // Sem a frase do `set`: ela foi escrita para o agente fazer, e o passo é da pessoa (como no Python).
                    out.add(linkedMapOf<String, Any?>("action" to if (on || choice) "turn_on" else "turn_off",
                        "target" to (if (choice) X.SET_SCREENS_OFF.getValue(name) else labels).toMutableList(), "if_missing" to "help"))
                } else if (step is Map<*, *> && step["action"] == "set" && name in X.SET_ROUTES) {
                    val (page, routeTaps) = X.SET_ROUTES.getValue(name)
                    val taps = if (name == "sound_mode") listOf(X.SOUND_MODES[plain(Py.str(step["value"]))] ?: X.SOUND_MODES.getValue("som")) else routeTaps
                    // O plano já toca na barra: o `set` depois dela mandava refazer o caminho todo (como no Python).
                    val bar = if (taps.isNotEmpty() && name != "sound_mode") taps.last().map { plain(it) }.toSet() else emptySet()
                    if (bar.isNotEmpty() && out.any { s ->
                            s is Map<*, *> && s["action"] == "tap" && run {
                                val t = s["target"]
                                (if (t is List<*>) t else listOf(t)).any { plain(Py.str(it)) in bar }
                            }
                        }) continue
                    out.add(linkedMapOf("action" to "open_settings", "target" to mutableListOf(page), "explain" to "Abro as Configurações, na página desse ajuste."))
                    for (labels in taps) out.add(linkedMapOf<String, Any?>("action" to "tap", "target" to labels.toMutableList(), "if_missing" to "scroll"))
                } else {
                    out.add(step)
                }
            }
            return out
        }

        fun find(step: Map<String, Any?>, elements: List<Element>): Element? {
            val turn = step["action"] in setOf("turn_on", "turn_off")
            val targets = Py.iter(Py.or(step["target"], emptyList<Any?>()))
            for (target in targets) {
                val hits = elements.filter { plain(target).isNotEmpty() && plain(it.text) == plain(target) }
                if (hits.isNotEmpty()) return if (turn) hits[0] else hits.filter { it.checked == null }.ifEmpty { hits }.last()
            }
            for (target in targets) {
                val words = Py.split(plain(target))
                val hits = elements.filter { e ->
                    X.isIdentifier(e.text) && words.isNotEmpty() &&
                        Py.casefold(e.text).split("_").let { parts -> parts.takeLast(words.size) } == words
                }
                if (hits.isNotEmpty()) return hits.last()
            }
            // O mesmo nome com outra terminação, e um rótulo só na tela (como no Python).
            for (target in targets) {
                val hits = elements.filter { it.text.isNotEmpty() && plain(it.text) !in X.STATE_WORDS && near(Py.str(target), it.text) }
                if (hits.isNotEmpty() && hits.map { plain(it.text) }.toSet().size == 1) {
                    return if (turn) hits[0] else hits.filter { it.checked == null }.ifEmpty { hits }.last()
                }
            }
            return null
        }

        /** Dois nomes iguais a menos da terminação das palavras (NEAR_PREFIX, NEAR_TAIL); iguais não contam. */
        fun near(a: String, b: String): Boolean {
            val wa = Py.split(plain(a))
            val wb = Py.split(plain(b))
            if (wa.isEmpty() || wa.size != wb.size || wa == wb) return false
            for ((x, y) in wa.zip(wb)) {
                if (x == y) continue
                var common = 0
                while (common < minOf(x.length, y.length) && x[common] == y[common]) common++
                if (common < X.NEAR_PREFIX || maxOf(x.length, y.length) - common > X.NEAR_TAIL) return false
            }
            return true
        }

        private fun area(e: Element) = (e.bounds[2] - e.bounds[0]) * (e.bounds[3] - e.bounds[1])

        private fun inside(e: Element, box: Element) = box.bounds[0] <= e.bounds[0] && box.bounds[1] <= e.bounds[1] &&
            e.bounds[2] <= box.bounds[2] && e.bounds[3] <= box.bounds[3]

        fun control(target: Element, elements: List<Element>): Element? {
            if (target.checked != null) return target
            val marks = elements.filter { it.checked != null }
            val named = marks.filter { target.text.isNotEmpty() && plain(it.text) == plain(target.text) }
            if (named.isNotEmpty()) return named[0]
            val x = (target.bounds[0] + target.bounds[2]) / 2.0
            val y = (target.bounds[1] + target.bounds[3]) / 2.0
            val around = marks.filter { it.bounds[0] <= x && x <= it.bounds[2] && it.bounds[1] <= y && y <= it.bounds[3] }
            if (around.isNotEmpty()) return around.minByOrNull { area(it) }
            val screen = elements.maxOfOrNull { area(it) } ?: 0L
            for (box in elements.filter { it !== target && inside(target, it) && area(it) * 4 <= screen }.sortedBy { area(it) }) {
                val marked = marks.filter { inside(it, box) }
                if (marked.isNotEmpty()) return if (marked.size == 1) marked[0] else null
            }
            return null
        }

        fun flips(target: Element, elements: List<Element>): Element? {
            val control = control(target, elements)
            if (control == null || control.cls.endsWith("RadioButton") || "Tab" in control.cls) return null
            val x = (target.bounds[0] + target.bounds[2]) / 2.0
            val y = (target.bounds[1] + target.bounds[3]) / 2.0
            val inside = control.bounds[0] <= x && x <= control.bounds[2] && control.bounds[1] <= y && y <= control.bounds[3]
            // E cabe inteiro nela (como no Python): um botão desenhado por cima da borda dela não é parte dela.
            val s = X.FLIP_SLACK
            val fits = control.bounds[0] - s <= target.bounds[0] && target.bounds[2] <= control.bounds[2] + s &&
                control.bounds[1] - s <= target.bounds[1] && target.bounds[3] <= control.bounds[3] + s
            return if (control === target || inside && fits) control else null
        }

        fun checked(target: Element, elements: List<Element>): Boolean? = control(target, elements)?.checked
    }
}
