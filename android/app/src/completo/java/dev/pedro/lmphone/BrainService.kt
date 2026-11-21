package dev.pedro.lmphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * O cérebro no celular atendendo o PC, para a suíte (etapa 3 de docs/plano-app-android.md: "a suíte roda com o cérebro
 * no celular, o PC só dispara os casos e confere"). O PC o liga com `am start-foreground-service` (só o adb tem a
 * permissão que o protege) e manda cada caso por `/tarefa`, com a mesma senha do AgentService; o pedido roda aqui, do
 * começo ao fim, como se viesse do painel. O PC lê o registro (files/cerebro/logs/) por `run-as`.
 */
class BrainService : Service() {
    private var server: LocalServer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Cérebro (suíte)", NotificationManager.IMPORTANCE_LOW))
        startForeground(3, Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentTitle("lm_phone")
            .setContentText("O cérebro do celular atende o PC")
            .setOngoing(true)
            .build(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        server = LocalServer(PORT, AgentService.token(this), ::handle).also { it.start() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_NOT_STICKY

    override fun onDestroy() {
        server?.stop()
        server = null
        super.onDestroy()
    }

    private fun handle(path: String, body: JSONObject): JSONObject = when (path) {
        "/ping" -> JSONObject().put("ok", true)
        "/parar" -> JSONObject().put("ok", true).also { stopSelf() }
        "/tarefa" -> {
            val lines = ArrayList<String>()
            val conversation = body.optString("conversa").ifEmpty { "suite-" + UUID.randomUUID().toString().take(8) }
            body.optString("modelo").takeIf { it.isNotEmpty() }?.let { OnDevice.agent(applicationContext).model = it }
            val result = OnDevice.send(applicationContext, body.getString("task"), {}, body.optBoolean("continuo"), conversation,
                useCache = body.optBoolean("cache", true), ask = body.optBoolean("perguntar", false), lines = lines)
            JSONObject().put("ok", result.ok).put("mensagem", result.message).put("linhas", JSONArray(lines))
        }
        else -> throw IllegalArgumentException("caminho desconhecido: $path")
    }

    companion object {
        const val PORT = 8083  // 8081: AgentService; 8082: ModelService
        private const val CHANNEL = "cerebro"
    }
}
