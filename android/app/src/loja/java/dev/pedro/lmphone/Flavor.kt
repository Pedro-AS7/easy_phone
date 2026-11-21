package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.content.Context
import com.google.android.play.core.assetpacks.AssetPackManagerFactory
import dev.pedro.lmphone.cerebro.Upstream
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/**
 * A variante `loja` (docs/plano-play-store.md): o app só ensina. Nada aqui age no aparelho: sem gestos, sem digitar,
 * sem teclas, sem trocar o teclado, sem captura de tela, sem servidor local, sem ligar a própria acessibilidade (a
 * pessoa a liga pelo atalho dos botões de volume; o app só a desliga) e sem ler os contatos. `:app:conferirLoja` falha
 * se uma API de ação aparecer no código que esta variante compila.
 */
object Flavor {
    const val ACTS = false

    /**
     * A acessibilidade fica ligada só durante um guia, e quem a liga é a pessoa, pelo atalho do Android (segurar os
     * dois botões de volume): o app não tem como se ligar sozinho. Ele se desliga sozinho no fim do guia, quando um app
     * de banco vem para a frente e depois de uns minutos parado (apps de banco bloqueiam o aparelho quando veem um
     * serviço de acessibilidade ligado: o Inter bloqueou o S23+ em 2026-11-21 com a loja ligada o tempo todo).
     */
    const val PERSON_SWITCHES = true

    /** O que o app diz quando um guia precisa da tela e a acessibilidade está desligada. */
    const val SWITCH_ON = "Para eu ver a tela, segure os dois botões de volume juntos, o de aumentar e o de diminuir, " +
        "por 3 segundos."


    private const val REFUSED = "this app only guides: it never acts on the phone"

    fun serve(service: AgentService): AutoCloseable? = null

    fun tap(service: AccessibilityService, x: Int, y: Int) = false
    fun swipe(service: AccessibilityService, x1: Int, y1: Int, x2: Int, y2: Int, ms: Long) = false
    fun type(service: AccessibilityService, text: String, clear: Boolean): String? = REFUSED
    fun key(service: AccessibilityService, name: String): String? = REFUSED

    /** Sem captura: a faixa usa o fundo fechado. */
    fun screenshot(service: AccessibilityService, windowId: Int, callback: AccessibilityService.TakeScreenshotCallback) = false

    fun agentKeyboard(context: Context): String? = null
    fun switchKeyboard(service: AccessibilityService, id: String) {}

    // --- o cérebro no celular ---

    fun upstream(context: Context, request: () -> String): Upstream = LmServer(context, BuildConfig.SERVIDOR, request)

    fun providerMissing(context: Context): String? = null

    /**
     * Onde estão os modelos pequenos: no pacote de recursos "modelos" que a Play baixa logo depois de instalar
     * (`android/modelos_pack`); no build de depuração, também em files/modelos (copiados por `tools.app.modelos enviar`).
     * null enquanto não chegaram (e pede o pacote à Play, se ela ainda não começou).
     */
    fun modelsDir(context: Context): File? {
        File(context.filesDir, "modelos").takeIf { File(it, "marcacao.onnx").exists() }?.let { return it }
        return try {
            val manager = AssetPackManagerFactory.getInstance(context)
            val location = manager.getPackLocation(PACK)
            if (location == null) {
                manager.fetch(listOf(PACK))
                null
            } else File(location.assetsPath() ?: return null, "modelos").takeIf { it.isDirectory }
        } catch (e: Exception) {
            null
        }
    }

    private const val PACK = "modelos"

    /** A denúncia de uma resposta (AssistSession): só o texto dela, ao servidor do app. false se não foi. */
    fun report(context: Context, text: String): Boolean = try {
        val connection = (URL(BuildConfig.SERVIDOR + "/denuncia").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("X-Lmphone-Instalacao", installation(context))
        }
        try {
            connection.outputStream.use { it.write(org.json.JSONObject().put("texto", text.take(4000)).toString().toByteArray()) }
            connection.responseCode == 200
        } finally {
            connection.disconnect()
        }
    } catch (e: IOException) {
        false
    }

    /** Sem contatos: a máscara fica nas regras, no modelo pequeno e nos nomes vistos na tela. */
    fun refreshVault(context: Context, vault: File, stoplist: List<String>): Int = 0

    /** Quem liga é a pessoa: o painel volta e diz como (`PhoneImpl` espera o serviço). */
    fun accessibilityOn(context: Context) {
        AssistService.notice(context, SWITCH_ON)
    }

    /** O fim do guia: a faixa sai e a acessibilidade se desliga (a pessoa religa pelo atalho no próximo). */
    fun accessibilityOff(context: Context) {
        AgentService.instance?.switchOff("fim do guia")
    }

    fun keyboardOn(context: Context) {}
    fun keyboardBack(context: Context) {}

    /** Com a acessibilidade desligada, não há como saber o app da frente (sem estatísticas de uso). */
    fun foreground(context: Context): String? = null

    /** A identidade da instalação no servidor (um número sorteado, sem nada da pessoa). */
    fun installation(context: Context): String {
        val prefs = context.getSharedPreferences("loja", Context.MODE_PRIVATE)
        return prefs.getString("instalacao", null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("instalacao", it).apply() }
    }
}

/**
 * O caminho até o provedor pelo servidor do lm_phone (`servidor/`, docs/plano-play-store.md fase 2): a chave fica lá.
 * Vai o texto já mascarado, a instalação e o pedido (para o limite de pedidos por mês). Uma ligação caída antes da
 * resposta é tentada mais uma vez.
 */
class LmServer(private val context: Context, private val base: String, private val request: () -> String) : Upstream {
    override fun post(path: String, body: String): Pair<Int, ByteArray> {
        var attempt = 0
        while (true) {
            val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 15_000
                readTimeout = 300_000
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("X-Lmphone-Instalacao", Flavor.installation(context))
                setRequestProperty("X-Lmphone-Pedido", request())
            }
            try {
                connection.outputStream.use { it.write(body.toByteArray()) }
                val status = connection.responseCode
                val stream = if (status < 400) connection.inputStream else connection.errorStream
                return status to (stream?.use { it.readBytes() } ?: ByteArray(0))
            } catch (e: IOException) {
                if (attempt++ >= 1) throw e
                Thread.sleep(1000)
            } finally {
                connection.disconnect()
            }
        }
    }
}
