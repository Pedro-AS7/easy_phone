package dev.pedro.lmphone.cerebro

import java.io.File
import java.util.Timer
import java.util.UUID
import kotlin.concurrent.schedule

/** A faixa do live mode no app: o que hoje o PC pede por `/live` e lê por `/events` (AgentService). */
interface Strip {
    /** O que a faixa mostra, diz, destaca, de quem é a vez (o corpo do `/live`). */
    fun send(body: Map<String, Any?>)

    /** O que o usuário fez desde a última vez e o estado da faixa (o `/events`). */
    fun poll(): Map<String, Any?>
}

/** O usuário interrompeu a tarefa (ou a pausa passou do limite). */
class Stopped(message: String) : Exception(message)

/**
 * A tradução de `lmphone/live.py`: o live mode do lado do cérebro. Antes de cada ação, `gate` pergunta à faixa o que o
 * usuário fez (pausar, interromper, uma instrução, toques, um pedido novo no modo contínuo) e espera ou repassa;
 * `show` muda o texto da faixa; `ask` mostra uma pergunta e espera a resposta. Tudo vai para live/<sessão>.jsonl
 * (valores reais, só no aparelho).
 */
class LiveMode(private val strip: Strip, val session: String, private val directory: File,
               private val banks: () -> Set<String>, private val keyboard: () -> String?) {
    private var lastStatus: String? = null
    @Volatile var owner = false
    @Volatile var speaking = false
    @Volatile var pressedAt: Double? = null  // quando a pessoa tocou no botão da faixa (só guia)
    @Volatile var touchedText: String? = null  // o texto do último controle em que ela tocou no app de baixo
    @Volatile var touchedTextAt: Double? = null
    @Volatile var touchedBox: List<Long>? = null  // os limites desse controle
    @Volatile var touchedAt = 0.0  // quando o dono tocou na tela (o relógio do executor): o guia conta o passo dele por isso
    @Volatile var guideAgent = false  // opção do app: no guia, o agente toca depois de um prazo
    @Volatile var continuous = false

    fun record(kind: String, fields: Map<String, Any?> = emptyMap()) {
        try {
            directory.mkdirs()
            val entry = linkedMapOf<String, Any?>("ts" to System.currentTimeMillis() / 1000.0, "tipo" to kind) + fields
            File(directory, "$session.jsonl").appendText(Json.dumps(entry) + "\n")
        } catch (e: Exception) {
            // o registro não pode parar a tarefa
        }
    }

    private fun send(where: String, body: Map<String, Any?>) {
        try {
            strip.send(body)
        } catch (e: Exception) {
            record("erro", linkedMapOf("onde" to where, "erro" to e.toString()))
        }
    }

    /** Se a faixa sabe que o pedido é um guia (o toque da pessoa não pausa). */
    var guiding = false

    fun start(task: String, continuous: Boolean = false, guide: Boolean = false) {
        record("pedido", linkedMapOf<String, Any?>("texto" to task).apply { if (continuous) put("continuo", true) })
        this.continuous = continuous
        guiding = guide
        val keyboard = try {
            keyboard()
        } catch (e: Exception) {
            null
        }
        send("start", linkedMapOf<String, Any?>("status" to "Entendendo o pedido…", "nova_tarefa" to true, "guia" to guide,
            "bancos" to banks().sorted()).apply {
            if (keyboard != null) put("teclado", keyboard)
            if (continuous) put("continuo", true)
        })
    }

    fun show(text: String, speak: Boolean = false, open: Boolean = false) {
        if (text == lastStatus && !speak) return
        lastStatus = text
        record(if (speak) "fala" else "status", linkedMapOf("texto" to text))
        send("show", linkedMapOf<String, Any?>("status" to text).apply {
            if (speak) put("fala", text)
            if (open) put("abrir", true)
        })
    }

    /** `owner`: é o dono quem deve tocar no destaque (a vez dele, ou o prazo dele no guia); o toque dele não pausa. */
    fun highlight(bounds: List<Long>?, owner: Boolean = false) {
        record("destaque", linkedMapOf<String, Any?>("limites" to bounds).apply { if (bounds != null && owner) put("dono", true) })
        send("highlight", linkedMapOf("destaque" to bounds, "destaque_dono" to (bounds != null && owner)))
    }

    /** Mostra animado o gesto que o dono deve fazer ("puxar", "rolar"); null tira. */
    fun button(offer: Map<String, Any?>?) {
        record("botao", linkedMapOf("texto" to offer?.get("texto")))
        send("botao", linkedMapOf("botao" to offer))
    }

    fun reroute(on: Boolean) {
        record("recalculando", linkedMapOf("ligado" to on))
        send("recalculando", linkedMapOf("recalculando" to on))
    }

    fun guide(on: Boolean) {
        guiding = on
        record("guia", linkedMapOf("ligado" to on))
        send("guia", linkedMapOf("guia" to on))
    }

    fun gesture(kind: String?) {
        record("gesto", linkedMapOf("gesto" to kind))
        send("gesture", linkedMapOf("gesto" to kind))
    }

    fun passTurn(owner: Boolean) {
        this.owner = owner
        record("vez", linkedMapOf("dono" to owner))
        send("vez", linkedMapOf("vez" to if (owner) "dono" else "agente", "status" to if (owner) "Sua vez: eu acompanho." else "Deixa comigo."))
    }

    /** Se a decisão demorar (o provedor pensando), a faixa diz isso. Cancelar no fim. */
    fun thinking(): Timer = Timer(true).also { it.schedule((THINKING_AFTER * 1000).toLong()) { show("Pensando…") } }

    @Suppress("UNCHECKED_CAST")
    fun poll(): Map<String, Any?> {
        val state = try {
            strip.poll()
        } catch (e: Exception) {
            record("erro", linkedMapOf("onde" to "events", "erro" to e.toString()))
            return linkedMapOf("paused" to false, "stopped" to false, "typing" to false, "events" to emptyList<Any?>())
        }
        val events = (state["events"] as List<*>? ?: emptyList<Any?>()).map { it as MutableMap<String, Any?> }
        for (event in events) {
            val kind = Py.str(event["tipo"] ?: "?")
            if (kind == "toque" || kind == "toque_longo") {
                event["duvidoso"] = ((event["ms_desde_agente"] as Number?)?.toLong() ?: AGENT_WINDOW_MS) < AGENT_WINDOW_MS
            }
            // A hora do toque, não a da leitura (como `live.event_time`): a leitura menos a idade dele no relógio do app.
            val agora = state["agora"] as Number?
            val t = event["t"] as Number?
            val read = System.nanoTime() / 1e9
            val whenAt = if (agora != null && t != null) read - maxOf(0.0, (agora.toDouble() - t.toDouble()) / 1000) else read
            if (kind == "toque_tela" || (kind == "toque" || kind == "toque_longo") && !Py.truthy(event["duvidoso"])) {
                touchedAt = maxOf(touchedAt, whenAt)
            }
            if ((kind == "toque" || kind == "toque_longo") && !Py.truthy(event["duvidoso"]) && Py.truthy(event["texto"])) {
                touchedText = Py.str(event["texto"])
                touchedTextAt = whenAt
                touchedBox = (event["limites"] as List<*>?)?.map { (it as Number).toLong() }
            }
            if (kind == "botao_tocado") pressedAt = whenAt
            val fields = LinkedHashMap(event.filterKeys { it != "tipo" })
            if (Py.truthy(fields["segredo"])) fields["texto"] = "[segredo]"
            record("usuario_$kind", fields)
        }
        if ("dono" in state) owner = Py.truthy(state["dono"])
        speaking = Py.truthy(state["falando"])
        guideAgent = state["guia"] == "agente"
        if (events.any { it["tipo"] == "continuo" }) continuous = true
        return state
    }

    /** Mostra a pergunta do agente e espera a resposta. Levanta `Stopped` se o usuário interromper ou não responder. */
    @Suppress("UNCHECKED_CAST")
    fun ask(question: String, options: List<String>, secret: Boolean): String {
        val qid = UUID.randomUUID().toString().replace("-", "").take(8)
        record("pergunta", linkedMapOf("id" to qid, "texto" to question, "opcoes" to options, "segredo" to secret))
        strip.send(linkedMapOf("pergunta" to linkedMapOf("id" to qid, "texto" to question, "opcoes" to options, "segredo" to secret)))
        val started = System.nanoTime()
        while (true) {
            val state = poll()
            for (event in state["events"] as List<*>? ?: emptyList<Any?>()) {
                event as Map<String, Any?>
                if (event["tipo"] == "resposta" && event["id"] == qid && Py.truthy(event["texto"])) return event["texto"] as String
            }
            if (Py.truthy(state["stopped"])) throw Stopped("interrompida pelo usuário")
            if ((System.nanoTime() - started) / 1e9 > ASK_LIMIT) {
                strip.send(linkedMapOf("pergunta" to null, "status" to "Sem resposta: parei."))
                throw Stopped("sem resposta à pergunta")
            }
            Thread.sleep((POLL * 1000).toLong())
        }
    }

    /** Antes de cada ação: espera enquanto o usuário pausou, escreve ou toca; devolve as instruções que ele mandou. */
    @Suppress("UNCHECKED_CAST")
    fun gate(): List<String> {
        val instructions = ArrayList<String>()
        val started = System.nanoTime()
        var touched: Long? = null
        while (true) {
            val state = poll()
            for (event in state["events"] as List<*>? ?: emptyList<Any?>()) {
                event as Map<String, Any?>
                val kind = event["tipo"]
                if (kind == "instrucao" && Py.truthy(event["texto"])) {
                    val text = event["texto"] as String
                    if (Py.search(OWNER_ON, text) != null) passTurn(true)
                    else if (Py.search(OWNER_OFF, text) != null && owner) passTurn(false)
                    else instructions.add(text)
                } else if ((kind == "toque" || kind == "toque_longo") && !Py.truthy(event["duvidoso"])) {
                    touched = System.nanoTime()
                } else if (kind == "novo_pedido") {
                    throw Stopped(NEW_REQUEST)
                }
            }
            if (Py.truthy(state["stopped"])) throw Stopped("interrompida pelo usuário")
            val waiting = Py.truthy(state["paused"]) || Py.truthy(state["typing"]) ||
                (touched != null && (System.nanoTime() - touched) / 1e9 < USER_QUIET)
            if (!waiting) return instructions
            val limit = if (Py.truthy(state["paused"])) PAUSE_LIMIT else TYPING_LIMIT
            if ((System.nanoTime() - started) / 1e9 > limit) throw Stopped("pausa longa demais")
            Thread.sleep((POLL * 1000).toLong())
        }
    }

    companion object {
        private const val M = "live"
        val POLL = Consts.d(M, "POLL")
        val PAUSE_LIMIT = Consts.d(M, "PAUSE_LIMIT")
        val TYPING_LIMIT = Consts.d(M, "TYPING_LIMIT")
        val ASK_LIMIT = Consts.d(M, "ASK_LIMIT")
        val USER_QUIET = Consts.d(M, "USER_QUIET")
        val AGENT_WINDOW_MS = Consts.i(M, "AGENT_WINDOW_MS").toLong()
        val THINKING_AFTER = Consts.d(M, "THINKING_AFTER")
        val OWNER_ON = Consts.re(M, "OWNER_ON")
        val OWNER_OFF = Consts.re(M, "OWNER_OFF")
        val NEW_REQUEST = Consts.s(M, "NEW_REQUEST")

        /** O que a faixa mostra para uma ação do agente, em português. */
        fun describe(name: String?, params: Map<String, String>, elements: List<Map<String, Any?>>): String = when (name) {
            "open_app" -> "Abrindo ${params["text"] ?: "o app"}"
            "click" -> {
                val index = params["index"]?.toLongOrNull() ?: -1L
                val label = Py.str(elements.firstOrNull { Py.eq(it["index"], index) }?.get("text") ?: "")
                if (label.isNotEmpty()) "Tocando em “${Py.head(label, 40)}”" else "Tocando na tela"
            }
            "type" -> "Digitando"
            "swipe" -> "Rolando a tela"
            "wait" -> "Esperando a tela carregar"
            "system_button" -> mapOf("back" to "Voltando", "home" to "Indo para a tela inicial", "enter" to "Confirmando",
                "quick_settings" to "Abrindo o painel rápido")[Py.lower(params["button"] ?: "")] ?: "Apertando um botão"
            else -> "Trabalhando…"
        }
    }
}
