package dev.pedro.lmphone

import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.speech.ModelDownloadListener
import android.speech.RecognitionListener
import android.speech.RecognitionSupport
import android.speech.RecognitionSupportCallback
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.os.Handler
import android.os.Looper
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import android.util.Log
import java.util.Locale

/**
 * A voz do assistente (etapa 4 de docs/plano-assistente.md), sob a regra do projeto: dado pessoal não sai do aparelho
 * sem máscara. A fala traz nomes e mensagens, e a resposta já vem com os valores reais.
 *
 * - Reconhecimento só pelo reconhecedor do próprio aparelho (`createOnDeviceSpeechRecognizer`), em português. Sem ele,
 *   não há voz: o reconhecedor comum pode mandar o áudio para a nuvem.
 * - Resposta lida só com uma voz em português que sintetiza no aparelho (sem `isNetworkConnectionRequired`).
 */
class Listener(
    private val context: Context,
    private val onPartial: (String) -> Unit,
    private val onFinal: (String) -> Unit,
    private val onProblem: (String) -> Unit,
    private val onSilence: (() -> Unit)? = null,  // nada foi dito (no modo contínuo, só volta a ouvir); sem ele, onProblem
) {
    private var recognizer: SpeechRecognizer? = null
    private var audio: ParcelFileDescriptor? = null  // o som que a palavra de ativação passa adiante; null: o microfone
    private var lastPartial: String? = null
    private var incarnation = 0
    var listening = false
        private set(value) {
            if (value != field) {
                if (audio == null) {
                    // A palavra de ativação (Wake.kt) solta o microfone enquanto algum reconhecedor do app o usa.
                    if (value) {
                        active.incrementAndGet()
                        Wake.handOver()
                    } else {
                        active.decrementAndGet()
                    }
                } else if (!value) {
                    Wake.endStream()
                    try {
                        audio?.close()
                    } catch (e: Exception) {
                    }
                    audio = null
                }
            }
            field = value
        }

    private fun intent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, LANGUAGE)
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        putStringArrayListExtra(RecognizerIntent.EXTRA_BIASING_STRINGS, Vocabulary.of(context))
        audio?.let {
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, it)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, Wake.RATE)
        }
    }

    /**
     * Começa a ouvir. Chamar na thread principal. `audio`: o som que veio logo depois da palavra de ativação
     * (`Wake.takeStream`), para "Alexa, pausa" dito de uma vez; sem ele, o reconhecedor abre o microfone.
     */
    fun start(audio: ParcelFileDescriptor? = null) {
        if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(context)) {
            if (audio != null) {
                Wake.endStream()
                audio.close()
            }
            onProblem("Este celular não reconhece fala no próprio aparelho; escreve o pedido.")
            return
        }
        val recognizer = recognizer ?: SpeechRecognizer.createOnDeviceSpeechRecognizer(context).also {
            it.setRecognitionListener(callbacks(++incarnation))
            recognizer = it
        }
        this.audio = audio
        lastPartial = null
        if (audio == null) Wake.testHeard = false
        listening = true
        Log.i("lmphone", "voz: ouvindo${if (audio != null) " o cano da palavra de ativação" else " o microfone"}")
        recognizer.startListening(intent())
    }

    fun stop() {
        listening = false
        // Trocar para texto cancela a fala; stopListening entregava um resultado final atrasado sobre a edição.
        incarnation++
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }

    fun destroy() {
        stop()
    }

    /** Se o português ainda não está baixado no reconhecedor do aparelho, pede o download (uma vez). */
    private fun downloadLanguage() {
        val recognizer = recognizer ?: return
        recognizer.checkRecognitionSupport(intent(), context.mainExecutor, object : RecognitionSupportCallback {
            override fun onSupportResult(support: RecognitionSupport) {
                val installed = support.installedOnDeviceLanguages.any { it.equals(LANGUAGE, true) }
                Log.i("lmphone", "voz: português no aparelho instalado=$installed, a baixar=${support.supportedOnDeviceLanguages}")
                if (!installed) recognizer.triggerModelDownload(intent(), context.mainExecutor, object : ModelDownloadListener {
                    override fun onProgress(completedPercent: Int) {}
                    override fun onSuccess() { onProblem("Baixei o reconhecimento de fala em português. Toca no microfone de novo.") }
                    override fun onScheduled() { onProblem("O reconhecimento de fala em português vai ser baixado; por enquanto, escreve.") }
                    override fun onError(error: Int) { onProblem("Não consegui baixar o reconhecimento de fala em português ($error).") }
                })
            }

            override fun onError(error: Int) {
                onProblem("O reconhecedor do aparelho não respondeu ($error).")
            }
        })
    }

    private fun callbacks(id: Int) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) { Log.i("lmphone", "voz: pronto") }
        override fun onBeginningOfSpeech() { Log.i("lmphone", "voz: começou a fala") }
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {
            if (id != incarnation || !listening) return
            Log.i("lmphone", "voz: fim da fala")
            // Pelo cano, o reconhecedor só dá o resultado quando o som acaba: o fim da fala fecha o cano (antes, o
            // resultado esperava o cano fechar sozinho, 9 s depois).
            if (audio != null) Wake.endStream()
        }
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onPartialResults(partialResults: Bundle?) {
            if (id != incarnation || !listening) return
            best(partialResults)?.takeIf { it.isNotBlank() }?.let {
                lastPartial = it
                onPartial(it)
            }
        }

        override fun onResults(results: Bundle?) {
            if (id != incarnation || !listening) return
            // Com o som pelo cano, o reconhecedor do Google entende (as parciais vêm certas), mas o resultado final
            // chega vazio (S23+, One UI 9, 2026-10-26): vale a última parcial.
            val text = best(results)?.takeIf { it.isNotBlank() } ?: lastPartial
            Log.i("lmphone", "voz: resultado (${text?.length ?: 0} caracteres)")
            listening = false
            when {
                !text.isNullOrBlank() -> onFinal(text)
                onSilence != null -> onSilence.invoke()
                else -> onProblem("Não entendi. Toca no microfone e fala de novo.")
            }
        }

        override fun onError(error: Int) {
            if (id != incarnation || !listening) return
            listening = false
            Log.i("lmphone", "voz: erro do reconhecedor $error")
            val silent = error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
            if (silent && onSilence != null) return onSilence.invoke()
            when (error) {
                SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE, SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> downloadLanguage()
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> onProblem("Não ouvi nada. Toca no microfone e fala.")
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> onProblem("O lm_phone não tem permissão de usar o microfone (abre o app uma vez).")
                else -> onProblem("O reconhecimento de fala falhou ($error); escreve o pedido.")
            }
        }
    }

    private fun best(bundle: Bundle?) = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()

    companion object {
        const val LANGUAGE = "pt-BR"
        val active = AtomicInteger()  // reconhecedores do app ouvindo agora
    }
}

/**
 * Palavras que o reconhecedor deve preferir: os nomes dos apps do aparelho ("Sofascore" saía "sofá escola", e o
 * YouTube Music, que o aparelho chama de "YT Music", também se fala pelo nome inteiro). Ficam no aparelho, como a fala.
 */
object Vocabulary {
    private val EXTRA = listOf("YouTube Music", "Waze", "Sofascore", "Instagram", "WhatsApp", "Spotify")
    @Volatile private var words: ArrayList<String>? = null

    fun of(context: Context): ArrayList<String> = words ?: run {
        val manager = context.packageManager
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val labels = try {
            manager.queryIntentActivities(launcher, android.content.pm.PackageManager.ResolveInfoFlags.of(0))
                .map { it.loadLabel(manager).toString() }
        } catch (e: Exception) {
            emptyList()
        }
        ArrayList((labels + EXTRA).filter { it.isNotBlank() }.distinct()).also { words = it }
    }
}

/** A resposta lida em voz alta, só com voz do próprio aparelho. Um por app: a resposta pode chegar com o painel fechado. */
object Speaker {
    private var tts: TextToSpeech? = null
    private var ready = false
    private val main = Handler(Looper.getMainLooper())
    private val after = ConcurrentHashMap<String, () -> Unit>()  // o que fazer quando cada fala termina
    private val ids = AtomicInteger()

    fun init(context: Context) {
        if (tts != null) return
        val app = context.applicationContext
        tts = TextToSpeech(app) { status ->
            val engine = tts ?: return@TextToSpeech
            if (status != TextToSpeech.SUCCESS) return@TextToSpeech
            val local = engine.voices.orEmpty().filter {
                it.locale.language == "pt" && it.locale.country == "BR" && !it.isNetworkConnectionRequired &&
                    TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features
            }.minByOrNull { it.latency }
            if (local != null) {
                engine.voice = local
                ready = true
            }
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) { finished(utteranceId) }
                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) { finished(utteranceId) }
                override fun onStop(utteranceId: String?, interrupted: Boolean) { after.remove(utteranceId) }
            })
            Log.i("lmphone", "voz: leitura em voz alta com ${local?.name ?: "nenhuma voz pt-BR no aparelho"}")
        }
    }

    fun enabled(context: Context) =
        context.getSharedPreferences("assistente", Context.MODE_PRIVATE).getBoolean("falar", true)

    // O ritmo da fala (1 é o normal da voz): começa um pouco mais devagar, para quem tem dificuldade acompanhar, e muda
    // com "mais devagar" e "mais rápido" (docs/plano-tutor.md).
    private const val NORMAL_RATE = 0.9f
    private val RATES = listOf(0.6f, 0.75f, NORMAL_RATE, 1.0f, 1.15f)

    fun rate(context: Context) =
        context.getSharedPreferences("assistente", Context.MODE_PRIVATE).getFloat("ritmo", NORMAL_RATE)

    /** Um passo mais devagar (`slower`) ou mais rápido; devolve se mudou. */
    fun changeRate(context: Context, slower: Boolean): Boolean {
        val now = rate(context)
        val index = RATES.indexOfFirst { it >= now - 0.01f }.let { if (it < 0) RATES.size - 1 else it }
        val next = (if (slower) index - 1 else index + 1).coerceIn(0, RATES.size - 1)
        if (next == index) return false
        context.getSharedPreferences("assistente", Context.MODE_PRIVATE).edit().putFloat("ritmo", RATES[next]).apply()
        return true
    }

    fun setEnabled(context: Context, on: Boolean) {
        context.getSharedPreferences("assistente", Context.MODE_PRIVATE).edit().putBoolean("falar", on).apply()
        if (!on) stop()
    }

    /** Lê `text`; `then` roda (na thread principal) quando a leitura termina, ou já, se não há leitura. */
    fun speak(context: Context, text: String, then: (() -> Unit)? = null) {
        val engine = tts
        if (!ready || engine == null || !enabled(context)) {
            then?.let { main.post(it) }
            return
        }
        val id = "fala-${ids.incrementAndGet()}"
        then?.let { after[id] = it }
        engine.setSpeechRate(rate(context))
        engine.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), id)
    }

    private fun finished(id: String?) {
        after.remove(id ?: return)?.let { main.post(it) }
    }

    fun stop() {
        tts?.stop()
    }

    val speaking get() = tts?.isSpeaking == true
}
