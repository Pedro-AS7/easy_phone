package dev.pedro.lmphone

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * O caminho do app até o cérebro no PC: o pedido escrito no painel do assistente vai ao serviço do lmphone (POST
 * /task), que o celular alcança em 127.0.0.1:8789 pelo `adb reverse` que o serviço mantém (lmphone/bridge.py).
 *
 * Qualquer app do aparelho alcança essa porta: o serviço só aceita o pedido com a senha que ele mesmo grava no app
 * (files/pc_token, por `run-as`). Sem ela, outro app mandaria o agente usar o celular.
 *
 * A conversa (o id) dura 10 min parada, como no serviço: o assistente lembra os pedidos anteriores dela.
 *
 * Com o cérebro no celular escolhido na tela do app (OnDevice), `send` e `live` não vão ao PC.
 */
object Brain {
    private const val TASK_URL = "http://127.0.0.1:8789/task"
    private const val LIVE_URL = "http://127.0.0.1:8789/live"
    private const val CONVERSATION_IDLE_MS = 10 * 60 * 1000L
    const val NO_PC = "Não consegui falar com o PC. Ele está ligado, com o celular no USB e o lmphone no ar (run --celular)?"

    class Result(val ok: Boolean, val message: String)

    private fun token(context: Context) = try { File(context.filesDir, "pc_token").readText().trim() } catch (e: Exception) { "" }

    private fun open(url: String, token: String, timeout: Int) = (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = "POST"
        doOutput = true
        connectTimeout = 3000
        readTimeout = timeout
        setRequestProperty("Content-Type", "application/json")
        setRequestProperty("X-Lmphone-Token", token)
    }

    /**
     * Manda o pedido e espera o fim. `onLine` recebe cada linha de andamento (o que o assistente diz enquanto age).
     * `continuous`: o pedido é do live mode contínuo, e o PC deixa a acessibilidade ligada depois dele.
     */
    fun send(context: Context, text: String, onLine: (String) -> Unit = {}, continuous: Boolean = false): Result {
        running.incrementAndGet()
        try {
            return sendNow(context, text, onLine, continuous)
        } finally {
            running.decrementAndGet()
        }
    }

    /** Pedidos em curso (a palavra de ativação não ouve durante eles). */
    val running = AtomicInteger()

    private fun sendNow(context: Context, text: String, onLine: (String) -> Unit, continuous: Boolean): Result {
        // Com o cérebro no celular (a escolha da tela do app), o pedido nem sai do aparelho para o PC.
        if (OnDevice.enabled(context)) return OnDevice.send(context, text, onLine, continuous, conversation(context))
        val token = token(context)
        if (token.isEmpty()) return Result(false, NO_PC)
        val body = JSONObject().put("task", text).put("conversa", conversation(context)).put("perguntar", true)
            .put("continuo", continuous)
        val connection = open(TASK_URL, token, 600_000)
        return try {
            connection.outputStream.use { it.write(body.toString().toByteArray()) }
            when (connection.responseCode) {
                200 -> {
                    var result: Result? = null
                    connection.inputStream.bufferedReader().forEachLine { line ->
                        when {
                            line.startsWith("Goal achieved:") -> result = Result(true, line.removePrefix("Goal achieved:").trim())
                            line.startsWith("Goal failed:") -> result = Result(false, line.removePrefix("Goal failed:").trim())
                            line.startsWith("Assistente: ") -> onLine(line.removePrefix("Assistente: "))
                        }
                    }
                    result ?: Result(false, "O PC parou antes de terminar o pedido.")
                }
                409 -> Result(false, "O agente ainda está fazendo outra coisa no celular. Tenta de novo daqui a pouco.")
                401 -> Result(false, "O PC recusou o pedido: a senha do app está velha (rode run --celular).")
                else -> Result(false, "O PC recusou o pedido (${connection.responseCode}).")
            }
        } catch (e: Exception) {
            Result(false, NO_PC)
        } finally {
            connection.disconnect()
        }
    }

    /**
     * O live mode contínuo no PC: "iniciar" liga a acessibilidade e a deixa ligada (a faixa aparece como um círculo, já
     * ouvindo); "encerrar" a desliga, ou deixa para o fim do pedido em curso.
     */
    fun live(context: Context, action: String): Result {
        if (OnDevice.enabled(context)) return OnDevice.live(context, action)
        val token = token(context)
        if (token.isEmpty()) return Result(false, NO_PC)
        val connection = open(LIVE_URL, token, 60_000)
        return try {
            connection.outputStream.use { it.write(JSONObject().put("acao", action).toString().toByteArray()) }
            when (connection.responseCode) {
                200 -> Result(true, "")
                409 -> Result(false, "O agente ainda está fazendo outra coisa no celular. Tenta de novo daqui a pouco.")
                401 -> Result(false, "O PC recusou o pedido: a senha do app está velha (rode run --celular).")
                else -> Result(false, try {
                    JSONObject(connection.errorStream.bufferedReader().readText()).optString("error", "O PC recusou o modo contínuo.")
                } catch (e: Exception) {
                    "O PC recusou o modo contínuo (${connection.responseCode})."
                })
            }
        } catch (e: Exception) {
            Result(false, NO_PC)
        } finally {
            connection.disconnect()
        }
    }

    /** O id da conversa em curso, ou um novo se a última ficou 10 min parada. */
    internal fun conversation(context: Context): String {
        val prefs = context.getSharedPreferences("assistente", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val id = prefs.getString("conversa", null)?.takeIf { now - prefs.getLong("em", 0) < CONVERSATION_IDLE_MS }
            ?: "celular-" + UUID.randomUUID().toString().take(8)
        prefs.edit().putString("conversa", id).putLong("em", now).apply()
        return id
    }
}
