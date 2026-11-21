package dev.pedro.lmphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Debug
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import dev.pedro.lmphone.modelos.Models
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * O modo de depuração dos modelos pequenos no aparelho (etapa 2 de docs/plano-app-android.md): carrega os dois modelos
 * de files/modelos/ (que `tools/app/modelos.py enviar` copia) e atende, num servidor local com a mesma senha do
 * AgentService, as chamadas de `lmphone/modelo_server.py` (`/`, `/entities`, `/judge`, `/pick`, `/private`), mais
 * `/memoria`. O PC o liga com `am start-foreground-service` (só o adb tem a permissão que o protege) e chega a ele pela
 * ponte de `tools/app/modelos.py ponte`, para o `tests.eval_base --novo` rodar contra o celular.
 *
 * Os modelos ficam carregados só enquanto o serviço está ligado: `/parar` (ou `am stopservice`) os solta.
 */
class ModelService : Service() {
    private var server: LocalServer? = null
    private var models: Models? = null
    private var failure: String? = null
    private var loadSeconds = 0.0
    private var threads = -1  // -1: ainda não carregou
    private val loaded = CountDownLatch(1)
    private val lock = Any()  // uma chamada por vez, como no PC: cada sessão já usa os núcleos

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Modelos (depuração)", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentTitle("lm_phone")
            .setContentText("Modelos carregados para conferência")
            .setOngoing(true)
            .build()
        startForeground(2, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        server = LocalServer(PORT, AgentService.token(this), ::handle).also { it.start() }
    }

    /** Carrega os modelos na primeira vez; `--ei threads N` escolhe quantos núcleos cada modelo usa (0: todos). */
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (threads >= 0) return START_NOT_STICKY
        threads = intent?.getIntExtra("threads", 0) ?: 0
        thread(name = "lmphone-modelos") {
            val started = SystemClock.elapsedRealtime()
            try {
                models = Models(File(filesDir, "modelos"), threads)
            } catch (e: Throwable) {
                failure = e.toString()
                Log.w("lmphone", "os modelos não carregaram", e)
            }
            loadSeconds = (SystemClock.elapsedRealtime() - started) / 1000.0
            loaded.countDown()
            Log.i("lmphone", "modelos: ${if (failure == null) "carregados" else "falharam"} em $loadSeconds s, threads $threads")
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        synchronized(lock) {
            models?.close()
            models = null
        }
        super.onDestroy()
    }

    private fun handle(path: String, body: JSONObject): JSONObject {
        when (path) {
            "/ping" -> return JSONObject().put("ok", true)
            "/memoria" -> return memory()
            "/parar" -> {
                stopSelf()
                return JSONObject().put("ok", true)
            }
        }
        if (!loaded.await(5, TimeUnit.MINUTES)) throw IllegalStateException("os modelos ainda estão carregando")
        val ready = models ?: throw IllegalStateException("os modelos não carregaram: $failure")
        if (path == "/") {
            return JSONObject().put("model", "modelos pequenos (app)").put("min_p", ready.picker.threshold)
                .put("carga_s", loadSeconds).put("threads", threads)
        }
        synchronized(lock) {
            val started = SystemClock.elapsedRealtimeNanos()
            val answer = ready.answer(path, body) ?: throw IllegalArgumentException("caminho desconhecido: $path")
            return answer.put("seconds", Math.round((SystemClock.elapsedRealtimeNanos() - started) / 1e6) / 1000.0)
        }
    }

    /** A memória do processo (PSS, em MB): o total e a parte nativa, onde fica o onnxruntime. */
    private fun memory(): JSONObject {
        val info = Debug.MemoryInfo().also { Debug.getMemoryInfo(it) }
        return JSONObject().put("pss_mb", info.totalPss / 1024).put("nativo_mb", info.nativePss / 1024)
            .put("java_mb", info.dalvikPss / 1024).put("carregado", models != null)
    }

    companion object {
        const val PORT = 8082  // a 8081 é a do AgentService
        private const val CHANNEL = "modelos"
    }
}
