package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import org.json.JSONObject
import java.io.File
import java.security.SecureRandom

/**
 * O serviço de acessibilidade do agente: lê a tela e age. Como o do Portal na pv1, só fica ligado durante uma tarefa
 * (apps de banco bloqueiam o aparelho quando veem um serviço de acessibilidade de fora da loja ligado); na `completo`,
 * quem liga e desliga é o cérebro (`lmphone/access.py`, com LMPHONE_DEVICE=app); na `loja`, a pessoa liga pelo atalho
 * dos botões de volume, e o serviço se desliga sozinho (`switchOff`).
 *
 * Enquanto está ligado, atende o cérebro do PC num servidor local (ver LocalServer):
 * - GET /state: a tela no formato `state_full` do Portal
 * - GET /apps: os apps da tela inicial, [{label, packageName}], como o `packages` do Portal
 * - POST /tap {x, y}, /swipe {x1, y1, x2, y2, ms}, /type {text, clear}, /key {name: back|home|enter}
 * - POST /live {status, teclado, pergunta, fala, destaque, vez, abrir, nova_tarefa, bancos, continuo}: o que a faixa
 *   do live mode mostra (Overlay), o que ela lê em voz alta (Speaker), o controle que ela destaca, de quem é a vez, o
 *   começo de um pedido, os apps de banco e o modo contínuo; GET /events: o que o usuário fez (Live.poll). Pausado ou
 *   interrompido pelo usuário, ou na vez dele, as ações são recusadas aqui mesmo.
 * - Um app de banco na frente desliga o serviço na hora (disableSelf), sem esperar o PC.
 */
class AgentService : AccessibilityService() {
    internal fun panelGeometry() = overlay?.geometry()
    internal fun previewControls() { overlay?.previewOnly = true }
    internal fun previewBitmap() = overlay?.previewBitmap()
    private var server: AutoCloseable? = null
    @Volatile private var overlay: Overlay? = null

    private val main = android.os.Handler(android.os.Looper.getMainLooper())

    override fun onServiceConnected() {
        instance = this
        Speaker.init(this)
        // Na `completo`, quem liga é o cérebro, e a faixa aparece com a ligação. Na `loja`, quem liga é a pessoa, pelo
        // atalho dos botões de volume, e a faixa só aparece quando um guia começa (`startTask`).
        if (!Flavor.PERSON_SWITCHES) startTask() else switchedOnByPerson()
        server = Flavor.serve(this)
        Log.i("lmphone", "serviço ligado" + if (server != null) "; servidor na porta $PORT" else "")
    }

    /**
     * A `loja` ligada pela pessoa. Se um pedido esperava por isso, o aviso do painel sai da frente (o guia vai ler a tela
     * de baixo). Se não, ela ligou para pedir ajuda: o painel abre já ouvindo, um pouco depois (um pedido que chega
     * nesse meio tempo, como o da suíte pelo `DebugTask`, segue sem o painel). Ligada e sem guia, ela se desliga sozinha
     * depois de `IDLE_MS`.
     */
    private fun switchedOnByPerson() {
        getSharedPreferences("loja", MODE_PRIVATE).edit().putBoolean("atalho_ok", true).apply()
        if (Live.awaitingService) {
            AssistService.close()
        } else {
            main.postDelayed({
                if (instance === this && idle()) {
                    if (!AssistService.open()) Speaker.speak(this, "O Guia está ligado. Abra o Guia do Celular para pedir ajuda.")
                }
            }, PANEL_DELAY_MS)
        }
        main.postDelayed(idleCheck, IDLE_MS)
    }

    /** Sem guia na tela e sem pedido em curso ou esperando o serviço. */
    private fun idle() = overlay == null && !Live.awaitingService && OnDevice.running.get() == 0 && Brain.running.get() == 0

    private val idleCheck = object : Runnable {
        override fun run() {
            if (instance !== this@AgentService) return
            if (idle()) switchOff("parado") else main.postDelayed(this, IDLE_MS)
        }
    }

    /** A `loja` se desliga (no fim do guia, com um app de banco na frente, parada): a pessoa religa pelo atalho. */
    internal fun switchOff(why: String) {
        Log.i("lmphone", "o serviço se desliga: $why")
        main.removeCallbacks(idleCheck)
        endTask()
        disableSelf()
    }

    /** O começo de uma tarefa: a faixa na tela e o serviço em primeiro plano. Na `completo`, é a própria ligação. */
    internal fun startTask() {
        if (overlay != null) return
        Live.reset()
        overlay = Overlay(this).also {
            try {
                it.show()
            } catch (e: Exception) {
                Log.w("lmphone", "não consegui mostrar a faixa", e)
            }
        }
        try {
            TaskService.start(this)
        } catch (e: Exception) {
            Log.w("lmphone", "não consegui ficar em primeiro plano", e)
        }
    }

    /** O fim da tarefa (na `loja`, o fim do guia): a faixa sai e o serviço deixa o primeiro plano. */
    internal fun endTask() {
        Live.continuous = false
        Speaker.stop()
        overlay?.hide()
        overlay = null
        TaskService.stop(this)
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        instance = null
        main.removeCallbacksAndMessages(null)
        endTask()
        server?.close()
        server = null
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        server?.close()
        super.onDestroy()
    }

    /**
     * Toques do usuário durante a tarefa, para o registro do live mode: os do agente também geram estes eventos, e o
     * que chega logo depois de um gesto dele pode ser efeito do gesto (vai com a distância no tempo, para o PC julgar).
     */
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            // Um app de banco veio para a frente: o serviço se desliga na hora, sem esperar o PC (no modo contínuo ele
            // fica ligado entre os pedidos, e o banco bloquearia o aparelho ao ver a acessibilidade ligada).
            val app = event.packageName?.toString()
            if (app != null && app in Live.banks) {
                Live.stopped = true
                Live.continuous = false
                // Nas duas variantes o serviço se desliga (na `loja`, o guia acaba e a faixa sai antes).
                switchOff("app de banco na frente")
            }
            return
        }
        // Sem tarefa (a `loja` ligada pelo atalho, antes do guia), os toques da pessoa não são guardados.
        if (overlay == null) return
        if (event.packageName == packageName) return
        val kind = when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_CLICKED -> "toque"
            AccessibilityEvent.TYPE_VIEW_LONG_CLICKED -> "toque_longo"
            else -> return
        }
        val since = System.currentTimeMillis() - Live.agentActedAt
        // O clique do próprio toque do agente chega uns 300 ms depois do gesto: é o que cai no ponto onde ele tocou.
        val point = Live.agentPoint
        val bounds = android.graphics.Rect().also { event.source?.getBoundsInScreen(it) }
        if (since < 300 || since < 3000 && point != null && bounds.contains(point.first, point.second)) return
        val text = event.text.joinToString(" ").ifBlank { event.contentDescription?.toString() ?: "" }
        Live.event(kind, JSONObject()
            .put("pacote", event.packageName?.toString() ?: "")
            .put("classe", event.className?.toString() ?: "")
            .put("texto", text)
            .put("id", event.source?.viewIdResourceName ?: "")
            .put("ms_desde_agente", since)
            .put("limites", org.json.JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom))))
    }

    override fun onInterrupt() {}

    internal fun handle(path: String, body: JSONObject): JSONObject = when (path) {
        "/ping" -> JSONObject().put("ok", true)
        "/state" -> Screen.state(this)
        "/apps" -> JSONObject().put("result", apps())
        "/events" -> Live.poll()
        "/live" -> {
            if (body.optBoolean("nova_tarefa")) {
                startTask()
                Live.guideAgent = Flavor.ACTS && Ui.guideAgent(this)
                overlay?.newTask()
            }
            if (body.has("botao")) overlay?.offer(body.optJSONObject("botao"))
            if (body.has("recalculando")) overlay?.reroute(body.optBoolean("recalculando"))
            if (body.has("guia")) Live.guide = body.optBoolean("guia")
            body.optJSONArray("bancos")?.let { list -> Live.banks = (0 until list.length()).map { list.getString(it) }.toSet() }
            if (body.optBoolean("continuo")) overlay?.startContinuous()
            body.optString("teclado").takeIf { it.isNotEmpty() }?.let { Live.previousIme = it }
            body.optString("status").takeIf { it.isNotEmpty() }?.let { overlay?.status(it) }
            if (body.optBoolean("abrir")) overlay?.open()
            if (body.has("pergunta")) {
                val ask = body.optJSONObject("pergunta")
                val choices = ask?.optJSONArray("opcoes")?.let { list -> (0 until list.length()).map { list.getString(it) } } ?: emptyList()
                overlay?.ask(ask?.optString("id"), ask?.optString("texto") ?: "", choices, ask?.optBoolean("segredo") ?: false)
            }
            body.optString("fala").takeIf { it.isNotEmpty() }?.let { text -> overlay?.say(text) ?: Speaker.speak(this, text) }
            if (body.has("destaque")) {
                val box = body.optJSONArray("destaque")
                // O destaque é para o dono tocar (a vez dele, ou o prazo dele no guia): o toque dele é o passo, não uma pausa.
                val forOwner = box != null && body.optBoolean("destaque_dono")
                if (Live.ownerTarget && !forOwner) {
                    Live.ownerTargetUntil = System.currentTimeMillis() + 2500
                    // O passo da pessoa acabou (o destaque dela saiu): o que ainda se dizia sobre ele para (pedido do
                    // Pedro, 2026-11-17: o agente seguia falando depois de ela já ter feito o passo).
                    Speaker.stop()
                }
                Live.ownerTarget = forOwner
                overlay?.highlight(box?.let { android.graphics.Rect(it.getInt(0), it.getInt(1), it.getInt(2), it.getInt(3)) })
            }
            body.optString("vez").takeIf { it.isNotEmpty() }?.let { overlay?.turn(it == "dono") }
            if (body.has("gesto")) {
                // O gesto que o dono deve fazer (docs/plano-tutor.md): animado na tela; o toque dele não pausa.
                val kind = if (body.isNull("gesto")) null else body.optString("gesto").ifEmpty { null }
                if (Live.ownerGesture && kind == null) Live.ownerTargetUntil = System.currentTimeMillis() + 2500
                Live.ownerGesture = kind != null
                overlay?.gesture(kind)
            }
            JSONObject().put("ok", true)
        }
        "/tap", "/swipe", "/type", "/key" -> Live.blocked()?.let { done(it) } ?: act(path, body)
        else -> throw IllegalArgumentException("unknown path $path")
    }

    private fun act(path: String, body: JSONObject): JSONObject {
        val pass = overlay
        // O ponto do gesto (o começo, na rolagem): a faixa sai da frente se ele cairia nela.
        val x = body.optInt("x", body.optInt("x1", -1)).takeIf { it >= 0 }
        val y = body.optInt("y", body.optInt("y1", -1)).takeIf { it >= 0 }
        fun <T> gesture(block: () -> T): T {
            Live.agentActedAt = System.currentTimeMillis()
            Live.gesturing = true
            try {
                return pass?.passThrough(x, y, block) ?: block()
            } finally {
                Live.gesturing = false
            }
        }
        try {
            return when (path) {
                "/tap" -> {
                    Live.agentPoint = body.getInt("x") to body.getInt("y")
                    done(if (gesture { Flavor.tap(this, body.getInt("x"), body.getInt("y")) }) null else "the tap was cancelled")
                }
                "/swipe" -> done(if (gesture { Flavor.swipe(this, body.getInt("x1"), body.getInt("y1"), body.getInt("x2"),
                        body.getInt("y2"), body.optLong("ms", 300)) }) null else "the swipe was cancelled")
                "/type" -> done(Flavor.type(this, body.getString("text"), body.optBoolean("clear")))
                else -> done(Flavor.key(this, body.getString("name")))
            }
        } finally {
            Live.agentActedAt = System.currentTimeMillis()
        }
    }

    internal fun apps(): org.json.JSONArray {
        val launcher = android.content.Intent(android.content.Intent.ACTION_MAIN).addCategory(android.content.Intent.CATEGORY_LAUNCHER)
        val out = org.json.JSONArray()
        packageManager.queryIntentActivities(launcher, android.content.pm.PackageManager.ResolveInfoFlags.of(0))
            .distinctBy { it.activityInfo.packageName }
            .forEach { out.put(JSONObject().put("label", it.loadLabel(packageManager).toString()).put("packageName", it.activityInfo.packageName)) }
        return out
    }

    private fun done(error: String?) = if (error == null) JSONObject().put("ok", true) else JSONObject().put("ok", false).put("error", error)

    companion object {
        const val PORT = 8081  // no aparelho; o Portal usa a 8080
        private const val PANEL_DELAY_MS = 3000L  // a `loja` ligada pelo atalho sem pedido: o painel abre depois disto
        private const val IDLE_MS = 3 * 60 * 1000L  // a `loja` ligada e sem guia se desliga depois disto
        @Volatile var instance: AgentService? = null
            private set

        /** A faixa está na tela (uma tarefa ou o modo contínuo): a palavra de ativação pode chamar por ela. */
        fun stripShown() = instance?.overlay?.shown == true

        /** O dono disse a palavra de ativação durante uma tarefa: a faixa ouve o comando. false sem a faixa. */
        fun wake(): Boolean {
            val overlay = instance?.overlay ?: return false
            if (!overlay.shown) return false
            overlay.wake()
            return true
        }

        /** A resposta de um pedido do painel, mostrada na faixa quando o dono ligou o modo contínuo durante ele. */
        fun showAnswer(message: String): Boolean {
            val overlay = instance?.overlay ?: return false
            overlay.showAnswer(message)
            return true
        }

        /** A senha do servidor local: gerada uma vez, guardada no armazenamento privado do app (o PC lê por run-as). */
        fun token(context: Context): String {
            val file = File(context.filesDir, "token")
            if (!file.exists()) {
                val bytes = ByteArray(24).also { SecureRandom().nextBytes(it) }
                file.writeText(bytes.joinToString("") { "%02x".format(it) })
            }
            return file.readText().trim()
        }
    }
}
