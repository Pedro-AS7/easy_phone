package dev.pedro.lmphone

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.ToneGenerator
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.VibrationEffect
import android.os.Vibrator
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import android.util.Log
import dev.pedro.lmphone.modelos.WakeWord
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.concurrent.thread
import kotlin.math.abs

/**
 * Chamar o assistente pela voz: "Alexa" abre o painel já ouvindo, como o toque longo na tecla lateral; durante uma
 * tarefa, a faixa ouve um comando ("Alexa, pausa", Commands.kt) ou uma instrução ao agente. A palavra é achada no
 * próprio aparelho (WakeWord, com os modelos do openWakeWord em files/escuta/, copiados pelo adb com
 * `tools/app/escuta.py enviar`); o som vira números a cada 80 ms e é descartado, sem ser gravado nem sair do celular.
 *
 * O que vem logo depois da palavra vai direto ao reconhecedor de fala do aparelho, por um cano (`takeStream`, o
 * `EXTRA_AUDIO_SOURCE` do Android): "Alexa, pausa" pode ser dito de uma vez, sem esperar o painel abrir. O aviso de
 * que ouviu é uma vibração curta (um bipe entraria no som do pedido).
 *
 * Um app comum não tem o microfone de baixo consumo que o "Ok Google" e o Bixby usam (o do sistema, só para apps da
 * fábrica): o microfone fica aberto num serviço em primeiro plano, com a notificação e o ponto verde do Android.
 *
 * O microfone fecha enquanto outra coisa do app o usa (o reconhecedor do painel e da faixa, `Listener.active`; o live
 * mode contínuo, que já ouve tudo) e enquanto o app fala. Durante um pedido ou com o agente usando o celular ele só
 * ouve se a faixa está na tela: sem ela, a chamada abriria o painel por cima do app que o agente está lendo.
 */
object Wake {
    private const val PREFS = "assistente"
    private const val KEY = "palavra"
    const val WORD = "Alexa"
    const val RATE = WakeWord.RATE
    private val FILES = listOf("melspectrogram.onnx", "embedding_model.onnx", "palavra.onnx")

    // O reconhecedor ouviu o cano de um arquivo de teste (WakeTest, frases fictícias): só então o texto vai ao logcat.
    // Um reconhecedor que abre o microfone desfaz a marca (ele pode ouvir gente de verdade).
    @Volatile var testHeard = false

    fun enabled(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY, false)

    fun directory(context: Context) = File(context.filesDir, "escuta")

    fun modelsPresent(context: Context) = FILES.all { File(directory(context), it).exists() }

    fun microphone(context: Context) = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun setEnabled(context: Context, on: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY, on).apply()
        if (on) start(context) else context.stopService(Intent(context, WakeService::class.java))
    }

    /** Liga o serviço, se a escolha está ligada e há o que ele precisa. Fora do app (o assistente ao ligar o celular),
     *  o Android pode recusar; fica no registro. */
    fun start(context: Context) {
        if (!enabled(context) || !modelsPresent(context) || !microphone(context)) return
        try {
            context.startForegroundService(Intent(context, WakeService::class.java))
        } catch (e: Exception) {
            Log.w("lmphone", "escuta: o Android não deixou ligar ($e)")
        }
    }

    /** Fecha o microfone já (o reconhecedor de fala vai abrir o dele), sem esperar o próximo pedaço de som. */
    fun handOver() {
        WakeService.current?.yieldMicrophone()
    }

    /** O som de depois da palavra, para o reconhecedor (uma vez por chamada), ou null. Quem pega fecha. */
    fun takeStream(): ParcelFileDescriptor? = WakeService.current?.takeStream()

    /** O reconhecedor terminou: o som para de ir, e a escuta volta a procurar a palavra. */
    fun endStream() {
        WakeService.current?.endStream("o reconhecedor terminou")
    }

    /** O que uma fala virou. Só números no logcat, a menos que o som seja de um arquivo de teste. */
    fun report(where: String, text: String, command: Command?) {
        val said = if (testHeard) "«$text»" else "${text.length} caracteres"
        testHeard = false
        Log.i("lmphone", "voz ($where): ${command ?: "pedido"}, $said")
    }
}

class WakeService : Service() {
    @Volatile private var running = false
    private val lock = Any()
    private var record: AudioRecord? = null
    private val main = Handler(Looper.getMainLooper())
    // O cano do som de depois da palavra: a ponta de leitura espera quem a pegue; a de escrita recebe cada pedaço.
    private var reader: ParcelFileDescriptor? = null
    private var writer: ParcelFileDescriptor? = null
    private var streamStarted = 0L
    private var streamFromTest = false
    private var blocked = 0  // pedaços seguidos que o reconhecedor não leu
    @Volatile private var fresh = false  // a escuta volta do cano: o estado da palavra recomeça
    @Volatile private var test: ShortArray? = null  // o som de um arquivo no lugar do microfone (WakeTest)
    private var testAt = 0
    private var testStarted = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == STOP) {
            Wake.setEnabled(this, false)
            return START_NOT_STICKY
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Chamar pela voz", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, WakeService::class.java).setAction(STOP), PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_mic)
            .setContentTitle("Ouvindo \"${Wake.WORD}\"")
            .setContentText("O som fica no celular e não é gravado.")
            .setContentIntent(open)
            .addAction(Notification.Action.Builder(null, "Desligar", stop).build())
            .setOngoing(true)
            .build()
        try {
            startForeground(3, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } catch (e: Exception) {
            Log.w("lmphone", "escuta: sem o serviço em primeiro plano ($e)")
            stopSelf()
            return START_NOT_STICKY
        }
        if (!running) {
            running = true
            current = this
            thread(name = "lmphone-escuta") { loop() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        current = null
        yieldMicrophone()
        endStream("desligado")
        super.onDestroy()
    }

    /** Agora não: outra parte do app usa o microfone ou fala, ou o agente trabalha sem a faixa na tela. */
    private fun quiet(): Boolean {
        // Um pedido em curso sem a faixa na tela: a chamada abriria o painel por cima do app que o agente lê. A
        // acessibilidade ligada sem pedido (o modo contínuo que acabou mal, 2026-10-27) não cala a escuta.
        return Listener.active.get() > 0 || Live.continuous || Speaker.speaking ||
            (Brain.running.get() > 0 && !AgentService.stripShown())
    }

    private fun loop() {
        val wake = try {
            WakeWord(Wake.directory(this))
        } catch (e: Exception) {
            Log.w("lmphone", "escuta: os modelos não abriram ($e)")
            running = false
            main.post { stopSelf() }
            return
        }
        val chunk = ShortArray(WakeWord.CHUNK)
        var last = 0L
        var count = 0
        var best = 0f
        var loudest = 0
        try {
            while (running) {
                if (test == null && !streaming() && quiet()) {
                    closeMicrophone()
                    Thread.sleep(QUIET_MS)
                    continue
                }
                if (!read(chunk, wake)) continue
                if (streaming()) {
                    feed(chunk)
                    continue
                }
                if (fresh) {
                    fresh = false
                    wake.reset()
                }
                val score = wake.score(chunk)
                best = maxOf(best, score)
                for (sample in chunk) loudest = maxOf(loudest, abs(sample.toInt()))
                if (++count % REPORT == 0) {
                    // Só números: o tempo de cada parte, a maior nota e o pico do som (de 0 a 32767) no último minuto.
                    val parts = wake.nanos.joinToString(" + ") { "%.1f".format(it / 1e6 / REPORT) }
                    Log.i("lmphone", "escuta: $parts ms por pedaço, maior nota ${"%.2f".format(best)}, pico $loudest")
                    wake.nanos.fill(0)
                    best = 0f
                    loudest = 0
                }
                val now = System.currentTimeMillis()
                if (score >= THRESHOLD && now - last > AGAIN_MS) {
                    last = now
                    // O pedaço da palavra vai junto: o pedido pode ter começado nele.
                    val streamed = openStream(chunk)
                    Log.i("lmphone", "escuta: \"${Wake.WORD}\" (nota ${"%.2f".format(score)}${if (streamed) "" else ", sem o cano"})")
                    if (!streamed) closeMicrophone()
                    main.post { woke(streamed) }
                    if (!streamed) Thread.sleep(AFTER_WAKE_MS)  // o painel abre e o reconhecedor pega o microfone
                }
            }
        } catch (e: InterruptedException) {
            // desligado
        } finally {
            closeMicrophone()
            endStream("desligado")
            wake.close()
        }
    }

    /** O próximo pedaço de som: do arquivo de teste, no ritmo do microfone, ou do microfone. */
    private fun read(chunk: ShortArray, wake: WakeWord): Boolean {
        val samples = test
        if (samples != null) {
            closeMicrophone()
            if (testAt == 0) {
                wake.reset()
                testStarted = System.nanoTime()
            }
            if (testAt + chunk.size > samples.size) {
                test = null
                testAt = 0
                endStream("fim do arquivo")  // o fim do arquivo é o fim do som para o reconhecedor
                return false
            }
            samples.copyInto(chunk, 0, testAt, testAt + chunk.size)
            testAt += chunk.size
            val wait = (testStarted + testAt * 1_000_000_000L / WakeWord.RATE - System.nanoTime()) / 1_000_000
            if (wait > 0) Thread.sleep(wait)
            return true
        }
        val record = synchronized(lock) { record } ?: openMicrophone(wake)
        if (record == null) {
            Thread.sleep(RETRY_MS)
            return false
        }
        if (!fill(record, chunk)) {
            closeMicrophone()
            return false
        }
        return true
    }

    /** Lê um pedaço inteiro; false se o microfone foi fechado no meio (o reconhecedor de fala o pediu). */
    private fun fill(record: AudioRecord, chunk: ShortArray): Boolean {
        var at = 0
        while (at < chunk.size) {
            val read = record.read(chunk, at, chunk.size - at)
            if (read <= 0) return false
            at += read
        }
        return true
    }

    @SuppressLint("MissingPermission")  // Wake.start só liga o serviço com a permissão dada
    private fun openMicrophone(wake: WakeWord): AudioRecord? {
        val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(WakeWord.RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO).build()
        val minimum = AudioRecord.getMinBufferSize(WakeWord.RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        return try {
            val opened = AudioRecord.Builder().setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                .setAudioFormat(format).setBufferSizeInBytes(maxOf(minimum, WakeWord.CHUNK * 2 * 4)).build()
            if (opened.state != AudioRecord.STATE_INITIALIZED) {
                opened.release()
                Log.w("lmphone", "escuta: o microfone não abriu")
                return null
            }
            opened.startRecording()
            wake.reset()  // o som de antes da pausa não emenda com o de agora
            synchronized(lock) { record = opened }
            opened
        } catch (e: Exception) {
            Log.w("lmphone", "escuta: o microfone não abriu ($e)")
            null
        }
    }

    private fun closeMicrophone() {
        synchronized(lock) {
            val opened = record ?: return
            record = null
            try {
                opened.stop()
            } catch (e: Exception) {
            }
            opened.release()
        }
    }

    /** Para a leitura em curso (ela volta sem o pedaço); o laço fecha o microfone e espera enquanto `quiet`. */
    fun yieldMicrophone() {
        synchronized(lock) {
            try {
                record?.stop()
            } catch (e: Exception) {
            }
        }
    }

    private fun streaming() = synchronized(lock) { writer != null }

    private fun openStream(first: ShortArray): Boolean {
        if (!STREAM) return false
        return try {
            val (read, write) = ParcelFileDescriptor.createPipe()
            synchronized(lock) {
                reader = read
                writer = write
                streamStarted = System.currentTimeMillis()
                streamFromTest = test != null
                blocked = 0
            }
            Log.i("lmphone", "escuta: cano aberto")
            feed(first)
            true
        } catch (e: Exception) {
            Log.w("lmphone", "escuta: o cano não abriu ($e)")
            false
        }
    }

    fun takeStream(): ParcelFileDescriptor? = synchronized(lock) {
        if (reader != null) Wake.testHeard = streamFromTest
        reader.also { reader = null }
    }

    /**
     * Um pedaço para o reconhecedor. Nunca espera: se o cano está cheio (o reconhecedor não lê, ou não aceita o som de
     * fora e abriu o microfone dele), o pedaço é perdido, e um segundo assim encerra o cano.
     */
    private fun feed(chunk: ShortArray) {
        val (out, started, waiting) = synchronized(lock) { Triple(writer ?: return, streamStarted, reader != null) }
        val age = System.currentTimeMillis() - started
        if (age > STREAM_MS || (waiting && age > TAKE_MS)) return endStream(if (waiting) "ninguém pegou" else "tempo")
        val bytes = ByteBuffer.allocate(chunk.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        bytes.asShortBuffer().put(chunk)
        try {
            val poll = StructPollfd().apply {
                fd = out.fileDescriptor
                events = OsConstants.POLLOUT.toShort()
            }
            Os.poll(arrayOf(poll), 0)
            if (poll.revents.toInt() and (OsConstants.POLLERR or OsConstants.POLLHUP) != 0) return endStream("o reconhecedor fechou")
            if (poll.revents.toInt() and OsConstants.POLLOUT == 0) {
                if (++blocked * WakeWord.CHUNK >= WakeWord.RATE) endStream("o reconhecedor não leu")
                return
            }
            blocked = 0
            // Um pedaço (2.560 bytes) cabe inteiro num cano com espaço para escrever (PIPE_BUF, 4.096): não espera.
            Os.write(out.fileDescriptor, bytes.array(), 0, bytes.capacity())
        } catch (e: Exception) {
            endStream("erro ao escrever: $e")
        }
    }

    fun endStream(why: String) {
        synchronized(lock) {
            if (writer == null && reader == null) return
            Log.i("lmphone", "escuta: cano fechado ($why, ${System.currentTimeMillis() - streamStarted} ms)")
            listOf(writer, reader).forEach {
                try {
                    it?.close()
                } catch (e: Exception) {
                }
            }
            writer = null
            reader = null
        }
        fresh = true
    }

    /** Toca um arquivo WAV (16 kHz, 16 bits, mono) no lugar do microfone: a conferência pelo adb (WakeTest). */
    fun test(file: File) {
        val bytes = file.readBytes()
        var at = 12
        while (at + 8 <= bytes.size) {
            val id = String(bytes, at, 4, Charsets.US_ASCII)
            val size = ByteBuffer.wrap(bytes, at + 4, 4).order(ByteOrder.LITTLE_ENDIAN).int
            if (id == "data") {
                val samples = ByteBuffer.wrap(bytes, at + 8, size).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                testAt = 0
                test = ShortArray(samples.remaining()).also { samples.get(it) }
                Log.i("lmphone", "escuta: teste com ${file.name}")
                return
            }
            at += 8 + size + (size and 1)
        }
        Log.w("lmphone", "escuta: ${file.name} não é um WAV")
    }

    /** A palavra foi dita: o aviso, e quem ouve o pedido (a faixa, numa tarefa; senão, o painel do assistente). */
    private fun woke(streamed: Boolean) {
        try {
            if (streamed) {
                getSystemService(Vibrator::class.java).vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK))
            } else {
                ToneGenerator(AudioManager.STREAM_SYSTEM, 60).apply {
                    startTone(ToneGenerator.TONE_PROP_BEEP, 150)
                    main.postDelayed({ release() }, 400)
                }
            }
        } catch (e: Exception) {
        }
        if (AgentService.wake()) return
        if (!AssistService.open()) {
            Log.w("lmphone", "escuta: o lm_phone não é o assistente digital; o painel não abre")
            endStream("sem o painel")
        }
    }

    companion object {
        @Volatile var current: WakeService? = null
            private set
        private const val CHANNEL = "escuta"
        private const val STOP = "dev.pedro.lmphone.escuta.DESLIGAR"
        private const val STREAM = true  // o som de depois da palavra vai ao reconhecedor pelo cano
        private const val THRESHOLD = 0.5f  // o padrão do openWakeWord
        private const val AGAIN_MS = 2000L
        private const val QUIET_MS = 250L
        private const val RETRY_MS = 2000L
        private const val AFTER_WAKE_MS = 1500L
        private const val TAKE_MS = 3000L  // o painel ou a faixa tem este tempo para pegar o cano
        private const val STREAM_MS = 8000L  // o cano fecha depois disto, mesmo sem o reconhecedor terminar
        private const val REPORT = 750  // um resumo no logcat a cada minuto ouvindo
    }
}

/**
 * Só para a conferência pelo adb (a permissão DUMP é do shell): `am broadcast -n dev.pedro.lmphone/.WakeTest --es
 * arquivo teste/x.wav` toca o arquivo de files/escuta/ no lugar do microfone (`tools/app/escuta.py testar`); `--ez
 * fechar true` fecha o painel.
 */
class WakeTest : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.getBooleanExtra("fechar", false)) return AssistService.close()
        intent.getStringExtra("reconhecer")?.let { return recognize(context, File(Wake.directory(context), it)) }
        val name = intent.getStringExtra("arquivo") ?: return
        val service = WakeService.current ?: return run { Log.w("lmphone", "escuta: o serviço não está ligado") }
        service.test(File(Wake.directory(context), name))
    }

    /** Só o reconhecedor, sem tela: o arquivo (fictício) vai pelo cano, no ritmo do microfone, e o texto ao logcat. */
    private fun recognize(context: Context, file: File) {
        val bytes = file.readBytes()
        val data = (12 until bytes.size - 8).first { String(bytes, it, 4, Charsets.US_ASCII) == "data" }
        val (read, write) = ParcelFileDescriptor.createPipe()
        lateinit var listener: Listener
        listener = Listener(context,
            onPartial = { Log.i("lmphone", "teste: parcial «$it»") },
            onFinal = { Log.i("lmphone", "teste: final «$it», ${Commands.parse(it) ?: "pedido"}"); listener.destroy() },
            onProblem = { Log.i("lmphone", "teste: problema «$it»"); listener.destroy() })
        thread(name = "lmphone-teste") {
            ParcelFileDescriptor.AutoCloseOutputStream(write).use { out ->
                var at = data + 8
                while (at < bytes.size) {
                    val end = minOf(bytes.size, at + WakeWord.CHUNK * 2)
                    try {
                        out.write(bytes, at, end - at)
                    } catch (e: Exception) {
                        Log.i("lmphone", "teste: o reconhecedor fechou o cano ($e)")
                        break
                    }
                    at = end
                    Thread.sleep(80)
                }
            }
            Log.i("lmphone", "teste: fim do arquivo")
        }
        listener.start(read)
    }
}
