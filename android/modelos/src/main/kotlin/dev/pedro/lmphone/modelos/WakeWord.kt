package dev.pedro.lmphone.modelos

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.nio.FloatBuffer

/**
 * A palavra de ativação ("Alexa"), com os modelos do openWakeWord (https://github.com/dscripka/openWakeWord): o
 * espectrograma mel do som, o `speech_embedding` do Google sobre as últimas 76 linhas dele e o detector da palavra
 * sobre os últimos 16 embeddings. É a tradução do caminho em tempo real da biblioteca do Python
 * (`AudioFeatures._streaming_features` e `Model.predict`, versão 0.6.0) para pedaços de exatamente 80 ms (1.280
 * amostras a 16 kHz, 16 bits): `tools/app/escuta.py referencia` grava as notas dela, e `:modelos:conferirEscuta` as
 * compara com as daqui.
 *
 * Diferença de propósito: a biblioteca começa os embeddings com 4 s de ruído aleatório; aqui a nota é 0 até haver 16
 * embeddings do som de verdade (1,28 s depois de começar). Daí em diante as notas são as mesmas.
 *
 * O som não fica guardado: cada pedaço vira números e é descartado.
 */
class WakeWord(file: (String) -> File) : AutoCloseable {
    constructor(directory: File) : this({ File(directory, it) })

    // Sem telemetria, como em Models.
    private val env = OrtEnvironment.getEnvironment().also { it.setTelemetry(false) }
    private val mel = session(file("melspectrogram.onnx"))
    private val embedding = session(file("embedding_model.onnx"))
    private val detector = session(file("palavra.onnx"))
    private val detectorInput = detector.inputNames.first()

    private var tail = ShortArray(0)  // as últimas amostras do pedaço anterior (o espectrograma olha 30 ms para trás)
    private val spectrum = ArrayDeque<FloatArray>()  // as últimas linhas do espectrograma, 32 faixas cada
    private val features = ArrayDeque<FloatArray>()  // os últimos embeddings, 96 números cada
    val nanos = LongArray(3)  // tempo gasto no espectrograma, no embedding e no detector (para medir no aparelho)

    init {
        reset()
    }

    private fun session(file: File): OrtSession {
        val options = OrtSession.SessionOptions()
        options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        // Um núcleo, como a biblioteca: são modelos de 1 MB, e o celular fica ouvindo o tempo todo.
        options.setIntraOpNumThreads(1)
        options.setInterOpNumThreads(1)
        return env.createSession(file.path, options)
    }

    /** Volta ao começo (depois de uma pausa no microfone): o espectrograma com 1 nas 76 linhas, como a biblioteca. */
    fun reset() {
        tail = ShortArray(0)
        spectrum.clear()
        repeat(WINDOW) { spectrum.addLast(FloatArray(BANDS) { 1f }) }
        features.clear()
    }

    /** A nota da palavra (0 a 1) depois deste pedaço de `CHUNK` amostras. */
    fun score(chunk: ShortArray): Float {
        require(chunk.size == CHUNK) { "a palavra de ativação lê pedaços de $CHUNK amostras" }
        val samples = tail + chunk
        tail = samples.copyOfRange(maxOf(0, samples.size - LOOK_BACK), samples.size)
        var started = System.nanoTime()
        for (row in melRows(samples)) {
            spectrum.addLast(row)
            if (spectrum.size > WINDOW) spectrum.removeFirst()
        }
        started = lap(0, started)
        features.addLast(embed())
        if (features.size > FRAMES) features.removeFirst()
        started = lap(1, started)
        if (features.size < FRAMES) return 0f
        val input = FloatArray(FRAMES * FEATURES)
        features.forEachIndexed { k, row -> row.copyInto(input, k * FEATURES) }
        val score = OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, FRAMES.toLong(), FEATURES.toLong())).use { tensor ->
            detector.run(mapOf(detectorInput to tensor)).use { (it.get(0) as OnnxTensor).floatBuffer.get(0) }
        }
        lap(2, started)
        return score
    }

    private fun lap(part: Int, started: Long): Long {
        val now = System.nanoTime()
        nanos[part] += now - started
        return now
    }

    /** As linhas novas do espectrograma, com a mesma transformação da biblioteca (x / 10 + 2). */
    private fun melRows(samples: ShortArray): List<FloatArray> {
        val input = FloatArray(samples.size) { samples[it].toFloat() }
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, samples.size.toLong())).use { tensor ->
            mel.run(mapOf("input" to tensor)).use { result ->
                val buffer = (result.get(0) as OnnxTensor).floatBuffer
                List(buffer.remaining() / BANDS) { FloatArray(BANDS) { buffer.get() / 10f + 2f } }
            }
        }
    }

    private fun embed(): FloatArray {
        val input = FloatArray(WINDOW * BANDS)
        spectrum.forEachIndexed { k, row -> row.copyInto(input, k * BANDS) }
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, WINDOW.toLong(), BANDS.toLong(), 1)).use { tensor ->
            embedding.run(mapOf("input_1" to tensor)).use { result ->
                val buffer = (result.get(0) as OnnxTensor).floatBuffer
                FloatArray(FEATURES) { buffer.get() }
            }
        }
    }

    override fun close() {
        mel.close()
        embedding.close()
        detector.close()
    }

    companion object {
        const val RATE = 16000
        const val CHUNK = 1280  // 80 ms
        private const val LOOK_BACK = 480  // 160 * 3 amostras, como a biblioteca
        private const val BANDS = 32
        private const val WINDOW = 76  // linhas do espectrograma por embedding
        private const val FEATURES = 96
        private const val FRAMES = 16  // embeddings que o detector lê
    }
}
