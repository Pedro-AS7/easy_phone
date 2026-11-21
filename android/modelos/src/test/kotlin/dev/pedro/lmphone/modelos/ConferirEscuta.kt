package dev.pedro.lmphone.modelos

import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.system.exitProcess

/**
 * A conferência da palavra de ativação (`android\gradlew.bat :modelos:conferirEscuta`, na raiz do projeto): lê as
 * frases e as notas que `tools/app/escuta.py referencia` gravou (frases fictícias, faladas pelas vozes do Windows) e
 * refaz as notas com o `WakeWord`, com o onnxruntime da JVM. As primeiras `FROM` notas não contam: a biblioteca as tira
 * de um começo aleatório, e o `WakeWord` as deixa em 0.
 */
private const val DIR = "data/modelos/escuta"
private const val TESTS = "data/escuta/teste"
private const val REFERENCE = "data/escuta/referencia.json"
private const val FROM = 15
private const val TOLERANCE = 1e-4
private const val THRESHOLD = 0.5

/** As amostras de um WAV de 16 bits, mono (o pedaço "data"). */
private fun samples(file: File): ShortArray {
    val bytes = file.readBytes()
    var at = 12
    while (at + 8 <= bytes.size) {
        val id = String(bytes, at, 4, Charsets.US_ASCII)
        val size = ByteBuffer.wrap(bytes, at + 4, 4).order(ByteOrder.LITTLE_ENDIAN).int
        if (id == "data") {
            val buffer = ByteBuffer.wrap(bytes, at + 8, size).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
            return ShortArray(buffer.remaining()).also { buffer.get(it) }
        }
        at += 8 + size + (size and 1)
    }
    error("${file.name}: sem o pedaço data")
}

fun main() {
    val files = mapOf(
        "melspectrogram.onnx" to File("$DIR/melspectrogram.onnx"),
        "embedding_model.onnx" to File("$DIR/embedding_model.onnx"),
        "palavra.onnx" to File("$DIR/alexa_v0.1.onnx"),
    )
    val reference = JSONObject(File(REFERENCE).readText(Charsets.UTF_8))
    val clips = reference.getJSONArray("clipes")
    var compared = 0
    var different = 0
    var worst = 0.0
    var agree = 0
    var chunks = 0
    var nanos = 0L
    WakeWord({ files.getValue(it) }).use { wake ->
        for (k in 0 until clips.length()) {
            val clip = clips.getJSONObject(k)
            val expected = clip.getJSONArray("notas")
            val audio = samples(File(TESTS, clip.getString("nome") + ".wav"))
            wake.reset()
            var best = 0.0
            var bestExpected = 0.0
            for (i in 0 until expected.length()) {
                val chunk = audio.copyOfRange(i * WakeWord.CHUNK, (i + 1) * WakeWord.CHUNK)
                val started = System.nanoTime()
                val score = wake.score(chunk).toDouble()
                nanos += System.nanoTime() - started
                chunks++
                if (i < FROM) continue
                val want = expected.getDouble(i)
                val diff = abs(score - want)
                compared++
                if (diff > TOLERANCE) different++
                worst = maxOf(worst, diff)
                best = maxOf(best, score)
                bestExpected = maxOf(bestExpected, want)
            }
            if ((best >= THRESHOLD) == (bestExpected >= THRESHOLD)) agree++
            else println("${clip.getString("nome")}: detecção diferente (Kotlin ${"%.3f".format(best)}, Python ${"%.3f".format(bestExpected)}) «${clip.getString("texto")}»")
        }
    }
    println("notas: $compared comparadas, $different acima de $TOLERANCE, maior diferença ${"%.2e".format(worst)}")
    println("frases com a mesma detecção (limiar $THRESHOLD): $agree de ${clips.length()}")
    println("tempo na JVM: ${"%.2f".format(nanos / 1e6 / chunks)} ms por pedaço de 80 ms")
    if (different > 0 || agree != clips.length()) exitProcess(1)
}
