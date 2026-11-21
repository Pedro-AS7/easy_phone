package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.view.inputmethod.InputMethodManager
import dev.pedro.lmphone.cerebro.Agent
import dev.pedro.lmphone.cerebro.Upstream
import java.io.File

/**
 * O que só a variante `completo` faz (docs/plano-play-store.md): o agente age (gestos, digitação, teclas), atende o PC
 * pelo servidor local, liga e desliga a própria acessibilidade e o teclado dele (`WRITE_SECURE_SETTINGS`, dada pelo
 * adb), lê o app da frente pelas estatísticas de uso, captura a tela para o desfoque e lê os contatos para o cofre. A
 * variante `loja` tem um `Flavor` com as mesmas funções, sem nada disso.
 */
object Flavor {
    /** O agente pode agir no aparelho; na `loja`, só guia. */
    const val ACTS = true

    /** A acessibilidade fica ligada só durante a tarefa, e quem a liga e desliga é o cérebro (não a pessoa). */
    const val PERSON_SWITCHES = false

    fun serve(service: AgentService): AutoCloseable =
        LocalServer(AgentService.PORT, AgentService.token(service), service::handle).also { it.start() }.let { server -> AutoCloseable { server.stop() } }

    fun tap(service: AccessibilityService, x: Int, y: Int) = Actions.tap(service, x, y)
    fun swipe(service: AccessibilityService, x1: Int, y1: Int, x2: Int, y2: Int, ms: Long) = Actions.swipe(service, x1, y1, x2, y2, ms)
    fun type(service: AccessibilityService, text: String, clear: Boolean) = Actions.type(service, text, clear)
    fun key(service: AccessibilityService, name: String) = Actions.key(service, name)

    /** A janela de baixo, para o desfoque da faixa (só na RAM). false se não deu para pedir. */
    fun screenshot(service: AccessibilityService, windowId: Int, callback: AccessibilityService.TakeScreenshotCallback): Boolean {
        service.takeScreenshotOfWindow(windowId, service.mainExecutor, callback)
        return true
    }

    /** O teclado do agente, que digita durante a tarefa. */
    fun agentKeyboard(context: Context): String? = ComponentName(context, Keyboard::class.java).flattenToShortString()

    fun switchKeyboard(service: AccessibilityService, id: String) {
        service.softKeyboardController.switchToInputMethod(id)
    }

    // --- o cérebro no celular ---

    fun upstream(context: Context, request: () -> String): Upstream = OpenRouter(context, Agent.UPSTREAM)

    /** O que falta para o cérebro no celular falar com o provedor, ou null. */
    fun providerMissing(context: Context): String? = if (ProviderKey.present(context)) null else
        "A chave do provedor não está no celular: ponha-a na tela do app ou pelo PC (tools.app.cerebro enviar)."

    /** A denúncia de uma resposta existe só na loja (o servidor do app). */
    fun report(context: Context, text: String) = false

    /** Os modelos pequenos, copiados pelo adb (`tools.app.modelos enviar`); null se não estão lá. */
    fun modelsDir(context: Context): File? = File(context.filesDir, "modelos").takeIf { it.isDirectory }

    /** O cofre pelos contatos do aparelho. Devolve quantos itens leu. */
    fun refreshVault(context: Context, vault: File, stoplist: List<String>): Int = Contacts.refresh(context, vault, stoplist).values.sum()

    private fun services(context: Context): List<String> =
        (Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: "")
            .split(":").filter { it.isNotEmpty() }

    private fun putServices(context: Context, names: List<String>) {
        Settings.Secure.putString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES, names.joinToString(":"))
        Settings.Secure.putInt(context.contentResolver, Settings.Secure.ACCESSIBILITY_ENABLED, if (names.isEmpty()) 0 else 1)
    }

    /** Liga a acessibilidade do app (como lmphone/access.py). Quem espera o serviço subir é o `PhoneImpl`. */
    fun accessibilityOn(context: Context) {
        if (AgentService.instance != null) return
        val names = services(context)
        if (SERVICE !in names) putServices(context, names + SERVICE)
    }

    fun accessibilityOff(context: Context) {
        val names = services(context)
        if (SERVICE in names) putServices(context, names - SERVICE)
    }

    private fun enabledKeyboards(context: Context): List<String> =
        context.getSystemService(InputMethodManager::class.java)?.enabledInputMethodList?.map { it.id } ?: emptyList()

    private fun prefs(context: Context) = context.getSharedPreferences("cerebro", Context.MODE_PRIVATE)

    /**
     * O teclado do agente vira o padrão durante a tarefa. Ele precisa estar ativado (o adb o ativa uma vez, em
     * `tools/app/cerebro.py enviar`): o app não regrava a lista de teclados ativos, porque ela leva os idiomas dos outros
     * teclados e o Android não a deixa ler. Sem ele, a digitação vai só pelo campo (ACTION_SET_TEXT).
     */
    fun keyboardOn(context: Context) {
        val resolver = context.contentResolver
        val current = Settings.Secure.getString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        if (current == KEYBOARD) return
        if (KEYBOARD !in enabledKeyboards(context)) throw IllegalStateException("o teclado do agente não está ativado (ime enable pelo adb)")
        if (current != null) {
            prefs(context).edit().putString("teclado", current).apply()
            Live.previousIme = current
        }
        Settings.Secure.putString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD, KEYBOARD)
    }

    fun keyboardBack(context: Context) {
        val resolver = context.contentResolver
        if (Settings.Secure.getString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD) != KEYBOARD) return
        val enabled = enabledKeyboards(context)
        val other = prefs(context).getString("teclado", null)?.takeIf { it in enabled } ?: enabled.firstOrNull { it != KEYBOARD } ?: return
        Settings.Secure.putString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD, other)
    }

    /** O app em primeiro plano com a acessibilidade desligada: pelas estatísticas de uso (permissão dada pelo adb). */
    fun foreground(context: Context): String? = try {
        val usage = context.getSystemService(UsageStatsManager::class.java)
        val now = System.currentTimeMillis()
        val events = usage.queryEvents(now - 60 * 60 * 1000, now)
        val event = UsageEvents.Event()
        var last: String? = null
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.ACTIVITY_RESUMED) last = event.packageName
        }
        last
    } catch (e: Exception) {
        null
    }

    const val SERVICE = "dev.pedro.lmphone/dev.pedro.lmphone.AgentService"
    const val KEYBOARD = "dev.pedro.lmphone/.Keyboard"
}
