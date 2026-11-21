package dev.pedro.lmphone.cerebro

import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/**
 * O `Agent` de ponta a ponta no PC, com um celular e um provedor de mentira e os modelos de verdade: o caminho todo
 * (julgar, mascarar, pedir o plano, ler a tela, agir, conferir) e o que fica no registro. Dados fictícios.
 */
object AgentCheck {
    /** Uma tela: o app e as linhas (classe, texto, marcado), uma embaixo da outra. */
    private fun state(app: String, rows: List<Triple<String, String, Boolean?>>): Map<String, Any?> {
        val children = rows.mapIndexed { i, (cls, text, checked) ->
            linkedMapOf<String, Any?>("className" to "android.widget.$cls", "text" to text, "resourceId" to "",
                "boundsInScreen" to linkedMapOf("left" to 0L, "top" to (300L + i * 150), "right" to 1080L, "bottom" to (440L + i * 150)),
                "isCheckable" to (checked != null), "isChecked" to (checked == true), "children" to emptyList<Any?>())
        }
        return linkedMapOf("a11y_tree" to linkedMapOf<String, Any?>("className" to "android.widget.FrameLayout",
            "boundsInScreen" to linkedMapOf("left" to 0L, "top" to 0L, "right" to 1080L, "bottom" to 2340L), "children" to children),
            "phone_state" to linkedMapOf("currentApp" to app, "packageName" to "pkg.$app", "isEditable" to false),
            "device_context" to linkedMapOf("screen_bounds" to linkedMapOf("width" to 1080L, "height" to 2340L)))
    }

    private class FakePhone : Phone {
        var dark = false
        var page = "home"
        val taps = ArrayList<Pair<Long, Long>>()
        override fun state(): Map<String, Any?> = when (page) {
            "display" -> state("Settings", listOf(Triple("TextView", "Display", null), Triple("Switch", "Dark mode", dark)))
            else -> state("Launcher", listOf(Triple("TextView", "Início", null), Triple("TextView", "Mensagens", null)))
        }
        override fun tap(x: Long, y: Long): String? {
            taps.add(x to y)
            if (page == "display" && y in 450..590) dark = !dark
            return null
        }
        override fun swipe(x1: Long, y1: Long, x2: Long, y2: Long, ms: Long): String? = null
        override fun type(text: String, clear: Boolean): String? = null
        override fun key(name: String): String? = null
        override fun apps() = listOf(linkedMapOf<String, Any?>("label" to "Settings", "packageName" to "com.android.settings"),
            linkedMapOf<String, Any?>("label" to "Messages", "packageName" to "com.samsung.android.messaging"))
        override fun launch(packageName: String) = true
        override fun openSettings(action: String): Boolean {
            page = if (action == "android.settings.DISPLAY_SETTINGS") "display" else page
            return true
        }
        override fun openUrl(url: String, packageName: String?) = true
        override fun facts(): Map<String, Any?> = linkedMapOf("wifi" to "on, not connected", "airplane_mode" to false, "bluetooth" to false,
            "do_not_disturb" to false, "location" to true, "dark_mode" to dark, "media_playing" to "nothing")
        override fun foreground() = "pkg.Launcher"
        override fun smsDefault(): String? = null
        override fun deviceInfo() = mapOf("model" to "SM-S916B", "android" to "17", "oneui" to "90000", "locale" to "en-US")
        override fun accessibilityOn() = true
        override fun accessibilityOff() {}
        override fun keyboardOn() {}
        override fun keyboardBack() {}
        override fun strip(): Strip? = null
    }

    private fun completion(content: String) = Json.dumps(linkedMapOf("choices" to listOf(linkedMapOf("message" to
        linkedMapOf("role" to "assistant", "content" to content))), "usage" to linkedMapOf("prompt_tokens" to 10L))).toByteArray()

    fun check(models: dev.pedro.lmphone.modelos.Models): Boolean {
        var ok = true
        val root = File("data/trilhas/agente").also { it.deleteRecursively(); it.mkdirs() }
        val store = Storage(root)
        store.vault.parentFile.mkdirs()
        store.vault.writeText(Json.dumps(linkedMapOf("name" to listOf("lívia", "bastos"), "email" to emptyList<String>(),
            "literal" to emptyList<String>(), "phone" to emptyList<String>())))

        // 1. O modo escuro, pelas telas (no celular não há o `set` direto).
        run {
            val phone = FakePhone()
            val sent = ArrayList<String>()
            val answers = ArrayDeque(listOf(Json.dumps(linkedMapOf("say" to "Vou ligar o modo escuro.",
                "steps" to listOf(linkedMapOf("action" to "set", "target" to listOf("dark_mode"), "value" to true)),
                "goal" to linkedMapOf("fact" to linkedMapOf("dark_mode" to true))))))
            val agent = Agent(phone, { _, body -> sent.add(body); 200 to completion(answers.removeFirst()) }, LocalAi(models), store)
            val lines = ArrayList<String>()
            val result = agent.run("liga o modo escuro", { lines.add(it) }, AtomicBoolean(false))
            val good = result == (true to "Pronto: modo escuro ligado.") && phone.dark && sent.size == 1 &&
                agent.executor?.result == "confirmado"
            println("agente, modo escuro pelas telas: ${if (good) "ok" else "FALHOU: $result, escuro=${phone.dark}, pedidos=${sent.size}, ${agent.executor?.result}"}")
            if (!good) lines.forEach { println("    $it") }
            ok = ok && good
        }

        // 2. A máscara: o nome do contato não chega ao provedor nem ao registro; a resposta volta com o nome real.
        run {
            val phone = FakePhone()
            val sent = ArrayList<String>()
            val agent = Agent(phone, { _, body ->
                sent.add(body)
                // O nome falso inteiro, como chegou no pedido mascarado (desde 2026-11-12 os falsos vêm das listas de
                // nomes, e procurar por terminações às vezes pegava o falso do sobrenome).
                val fake = Regex("oi pra ([^\\\\\".,]+)").find(body)?.groupValues?.get(1)?.trim() ?: "?"
                200 to completion(Json.dumps(linkedMapOf("reply" to "Falei com $fake.")))
            }, LocalAi(models), store)
            val result = agent.run("Manda um oi pra Lívia Bastos", {}, AtomicBoolean(false))
            val log = store.log.readText()
            val good = sent.size == 1 && "Lívia" !in sent[0] && "Bastos" !in sent[0] && "Lívia" !in log && "Bastos" !in log &&
                result == (true to "Falei com Lívia Bastos.")
            println("agente, máscara: ${if (good) "ok" else "FALHOU: $result; nome no envio=${"Lívia" in sent.getOrElse(0) { "" }}, no registro=${"Lívia" in log}"}")
            ok = ok && good
        }
        return ok
    }
}
