package dev.pedro.lmphone

import android.app.NotificationManager
import android.app.UiModeManager
import android.content.Context
import android.content.Intent
import android.location.LocationManager
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import android.provider.Telephony
import dev.pedro.lmphone.cerebro.Json
import dev.pedro.lmphone.cerebro.Phone
import dev.pedro.lmphone.cerebro.Strip
import org.json.JSONObject
import java.util.Locale

/**
 * O aparelho para o cérebro no celular (dev.pedro.lmphone.cerebro.Agent): o que o PC faz pelo adb, aqui pelo próprio
 * app. A tela e as ações vão direto ao `AgentService` (os mesmos caminhos que o servidor local atende), os fatos vêm das
 * APIs do Android, e ligar e desligar a acessibilidade e o teclado do agente é escrever nas configurações seguras
 * (`WRITE_SECURE_SETTINGS`, dada uma vez pelo adb: `pm grant dev.pedro.lmphone android.permission.WRITE_SECURE_SETTINGS`).
 */
class PhoneImpl(private val context: Context, private val banks: () -> Set<String>) : Phone {
    private val resolver = context.contentResolver

    private fun service() = AgentService.instance ?: throw IllegalStateException("o serviço de acessibilidade do app está desligado")

    private fun json(value: JSONObject): Map<String, Any?> {
        @Suppress("UNCHECKED_CAST")
        return Json.parse(value.toString()) as Map<String, Any?>
    }

    private fun act(path: String, body: JSONObject): String? {
        val answer = service().handle(path, body)
        return if (answer.optBoolean("ok", false)) null else answer.optString("error", "o app recusou")
    }

    override fun state(): Map<String, Any?> = json(Screen.state(service()))
    override fun tap(x: Long, y: Long) = act("/tap", JSONObject().put("x", x).put("y", y))
    override fun swipe(x1: Long, y1: Long, x2: Long, y2: Long, ms: Long) =
        act("/swipe", JSONObject().put("x1", x1).put("y1", y1).put("x2", x2).put("y2", y2).put("ms", ms))
    override fun type(text: String, clear: Boolean) = act("/type", JSONObject().put("text", text).put("clear", clear))
    override fun key(name: String) = act("/key", JSONObject().put("name", name))

    @Suppress("UNCHECKED_CAST")
    override fun apps(): List<Map<String, Any?>> = (Json.parse(service().apps().toString()) as List<Any?>).map { it as Map<String, Any?> }

    private fun start(intent: Intent): Boolean = try {
        context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (e: Exception) {
        false
    }

    override fun launch(packageName: String): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return false
        return start(intent)
    }

    override fun openSettings(action: String) = start(Intent(action))

    override fun openUrl(url: String, packageName: String?) =
        start(Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply { if (packageName != null) setPackage(packageName) })

    /** O estado do sistema, nas chaves de `lmphone/facts.py`. A rede só tem nome com a localização (o Android a esconde). */
    override fun facts(): Map<String, Any?> {
        val out = LinkedHashMap<String, Any?>()
        val wifi = context.getSystemService(WifiManager::class.java)
        if (wifi != null) {
            out["wifi"] = if (!wifi.isWifiEnabled) "off" else network() ?: "on, not connected"
        }
        out["airplane_mode"] = Settings.Global.getInt(resolver, Settings.Global.AIRPLANE_MODE_ON, 0) != 0
        out["bluetooth"] = Settings.Global.getInt(resolver, Settings.Global.BLUETOOTH_ON, 0) != 0
        out["do_not_disturb"] = context.getSystemService(NotificationManager::class.java)
            ?.currentInterruptionFilter?.let { it != NotificationManager.INTERRUPTION_FILTER_ALL && it != NotificationManager.INTERRUPTION_FILTER_UNKNOWN } ?: false
        out["location"] = context.getSystemService(LocationManager::class.java)?.isLocationEnabled ?: false
        out["dark_mode"] = context.getSystemService(UiModeManager::class.java)?.nightMode == UiModeManager.MODE_NIGHT_YES
        // O app que toca precisaria do acesso às notificações; sem ele, só se algo toca.
        out["media_playing"] = if (context.getSystemService(AudioManager::class.java)?.isMusicActive == true) "some app" else "nothing"
        // Os níveis e a letra, como `facts.levels` lê pelo adb (docs/plano-tutor.md): o guia mede o que mudou ("letra maior").
        context.getSystemService(AudioManager::class.java)?.let { audio ->
            for ((name, stream) in listOf("media_volume" to AudioManager.STREAM_MUSIC, "ring_volume" to AudioManager.STREAM_RING)) {
                val low = audio.getStreamMinVolume(stream)
                val high = audio.getStreamMaxVolume(stream)
                out[name] = if (high > low) Math.rint((audio.getStreamVolume(stream) - low) * 100.0 / (high - low)).toLong() else 0L
            }
        }
        try {
            out["brightness"] = minOf(100L, Math.rint(Settings.System.getInt(resolver, Settings.System.SCREEN_BRIGHTNESS) * 100.0 / BRIGHTNESS_MAX).toLong())
            out["auto_brightness"] = Settings.System.getInt(resolver, Settings.System.SCREEN_BRIGHTNESS_MODE) == 1
        } catch (_: Settings.SettingNotFoundException) {
        }
        out["font_scale"] = Settings.System.getFloat(resolver, Settings.System.FONT_SCALE, 1f).toString().toDouble()
        // A rotação automática e o tempo para a tela apagar, como `facts.levels` (a tela não mostra o estado deles).
        out["auto_rotate"] = Settings.System.getInt(resolver, Settings.System.ACCELEROMETER_ROTATION, 0) == 1
        out["screen_timeout"] = Settings.System.getInt(resolver, Settings.System.SCREEN_OFF_TIMEOUT, 0).toLong() / 1000
        // O modo de som (facts.SOUND_MODES): em vibrar ou mudo, as barras do toque e das notificações ficam no zero.
        context.getSystemService(AudioManager::class.java)?.ringerMode?.let {
            out["sound_mode"] = when (it) { AudioManager.RINGER_MODE_SILENT -> "mudo"; AudioManager.RINGER_MODE_VIBRATE -> "vibrar"; else -> "som" }
        }
        return out
    }

    /** O nome da rede Wi-Fi conectada, ou null (desconectado, ou o nome escondido pelo sistema). */
    private fun network(): String? {
        val connectivity = context.getSystemService(ConnectivityManager::class.java) ?: return null
        val caps = connectivity.getNetworkCapabilities(connectivity.activeNetwork) ?: return null
        if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return null
        val ssid = (caps.transportInfo as? WifiInfo)?.ssid?.removeSurrounding("\"") ?: return "connected (name hidden)"
        return if (ssid.isEmpty() || ssid == WifiManager.UNKNOWN_SSID.removeSurrounding("<", ">") || ssid.startsWith("<")) "connected (name hidden)" else ssid
    }

    /** O app em primeiro plano: pelo serviço, se ligado; senão, como a variante sabe (na `completo`, pelas estatísticas de uso). */
    override fun foreground(): String? {
        AgentService.instance?.rootInActiveWindow?.packageName?.let { return it.toString() }
        return Flavor.foreground(context)
    }

    override fun smsDefault(): String? = Telephony.Sms.getDefaultSmsPackage(context)

    override fun deviceInfo(): Map<String, String> {
        val oneui = try {
            Class.forName("android.os.SystemProperties").getMethod("get", String::class.java).invoke(null, "ro.build.version.oneui") as String
        } catch (e: Throwable) {
            ""
        }
        return mapOf("model" to Build.MODEL, "android" to Build.VERSION.RELEASE, "oneui" to oneui, "locale" to Locale.getDefault().toLanguageTag())
    }

    // --- acessibilidade e teclado, como lmphone/access.py (na `loja`, a acessibilidade é da pessoa e não há teclado) ---

    override fun accessibilityOn(): Boolean {
        Live.banks = banks()
        if (AgentService.instance != null) return true
        // Na `loja`, quem liga é a pessoa, pelo atalho dos botões de volume: o app pede (`Flavor.accessibilityOn`) e espera.
        Live.awaitingService = true
        try {
            Flavor.accessibilityOn(context)
            val limit = SystemClock.elapsedRealtime() + READY_MS
            while (AgentService.instance == null && SystemClock.elapsedRealtime() < limit) Thread.sleep(100)
        } finally {
            Live.awaitingService = false
        }
        return AgentService.instance != null
    }

    override val personSwitches get() = Flavor.PERSON_SWITCHES

    override fun accessibilityReady() = AgentService.instance != null

    override fun accessibilityOff() = Flavor.accessibilityOff(context)

    override fun keyboardOn() = Flavor.keyboardOn(context)

    override fun keyboardBack() = Flavor.keyboardBack(context)

    override fun strip(): Strip? {
        val service = AgentService.instance ?: return null
        return object : Strip {
            override fun send(body: Map<String, Any?>) {
                service.handle("/live", JSONObject(Json.dumps(body)))
            }

            @Suppress("UNCHECKED_CAST")
            override fun poll(): Map<String, Any?> = Json.parse(Live.poll().toString()) as Map<String, Any?>
        }
    }

    companion object {
        private const val BRIGHTNESS_MAX = 255.0  // facts.BRIGHTNESS_MAX
        // Na `loja`, a pessoa liga a acessibilidade pelo atalho depois de ouvir o pedido: a espera é a dela.
        private val READY_MS = if (Flavor.PERSON_SWITCHES) 60_000L else 8000L  // service.READY_LIMIT
    }
}
