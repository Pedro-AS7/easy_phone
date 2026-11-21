package dev.pedro.lmphone.modelos

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.LongBuffer
import kotlin.math.exp

/**
 * Os dois modelos pequenos no onnxruntime, com a API de `lmphone/modelo_server.py` (`answer`): `/entities`, `/judge`,
 * `/pick` e `/private`, nas mesmas respostas JSON. A pasta tem o que `tools/app/modelos.py enviar` copia:
 * `marcacao.onnx`, `escolha.onnx`, os `modelo.json` de cada um (como `marcacao.json` e `escolha.json`) e o
 * `tokenizador.bin`, que os dois usam.
 */
class Models(file: (String) -> File, private val threads: Int = 0) : AutoCloseable {
    constructor(directory: File, threads: Int = 0) : this({ File(directory, it) }, threads)

    // Sem telemetria: no Android o onnxruntime 1.31 tenta mandar eventos de uso à Microsoft (só não manda quando falta
    // o cliente HTTP dele, como hoje), e nada do aparelho sai sem passar pela máscara.
    private val env = OrtEnvironment.getEnvironment().also { it.setTelemetry(false) }
    val tokenizer = Tokenizer.load(file("tokenizador.bin"))
    val marker: Marker
    val picker: Picker

    init {
        val marking = JSONObject(file("marcacao.json").readText())
        val labels = marking.getJSONArray("rotulos").let { list -> List(list.length()) { list.getString(it) } }
        val intents = marking.getJSONArray("intencoes").let { list -> List(list.length()) { list.getString(it) } }
        require(labels == Modelo.LABELS && intents == Modelo.INTENTS && marking.getInt("bloco") == Modelo.BLOCK) {
            "o modelo de marcação não é o desta versão do Modelo.kt"
        }
        marker = Marker(session(file("marcacao.onnx")), tokenizer, marking.getInt("max_tokens"))
        val choosing = JSONObject(file("escolha.json").readText())
        picker = Picker(session(file("escolha.onnx")), tokenizer, choosing.getInt("max_tokens"),
            choosing.getDouble("limiar"))
    }

    private fun session(file: File): OrtSession {
        val options = OrtSession.SessionOptions()
        options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        // Sem a reserva de memória do onnxruntime: com entradas de tamanhos variados ela só cresce (no PC, 1,3 GB).
        options.setCPUArenaAllocator(false)
        if (threads > 0) options.setIntraOpNumThreads(threads)  // 0: o padrão do onnxruntime, um por núcleo
        return env.createSession(file.path, options)
    }

    /** A resposta de `modelo_server` para `path`, sem o "seconds" (quem chama mede). null: caminho desconhecido. */
    fun answer(path: String, body: JSONObject): JSONObject? = when (path) {
        "/entities" -> {
            // Como a Gemma na tela: só pessoa e usuário. E-mail, telefone e documento vão como usuário.
            val items = JSONArray()
            for (item in marker.mark(body.getString("text")).first) {
                if (item.kind !in Modelo.PRIVATE) continue
                items.put(JSONObject().put("texto", item.text).put("tipo", if (item.kind == "pessoa") "pessoa" else "usuario"))
            }
            JSONObject().put("itens", items)
        }
        "/judge" -> {
            val (items, intent) = marker.mark(body.getString("text"))
            val entities = JSONArray()
            for (item in items) {
                entities.put(JSONObject().put("texto", item.text).put("tipo", item.kind.trimEnd('+'))
                    .put("precisa_pesquisa", item.kind.endsWith("+")))
            }
            JSONObject().put("intencao", intent ?: JSONObject.NULL).put("entidades", entities)
        }
        "/pick" -> {
            val wanted = body.getJSONArray("wanted").let { list -> List(list.length()) { list.getString(it) } }
            val labels = body.getJSONArray("labels").let { list -> List(list.length()) { list.getString(it) } }
            val pick = picker.pick(wanted, labels)
            val ranking = JSONArray()
            for ((label, p) in pick.ranking) ranking.put(JSONArray().put(label ?: JSONObject.NULL).put(p))
            JSONObject().put("label", pick.label ?: JSONObject.NULL).put("p", pick.p).put("ranking", ranking)
        }
        "/private" -> {
            val count = body.getJSONArray("fragments").length()
            JSONObject().put("p", JSONArray().apply { repeat(count) { put(1.0) } })
        }
        else -> null
    }

    override fun close() {
        marker.close()
        picker.close()
    }

    /** Os rótulos de token em blocos de `Modelo.BLOCK` caracteres, como no treino, e a intenção (do primeiro bloco). */
    class Marker(private val session: OrtSession, private val tokenizer: Tokenizer, private val maxTokens: Int) : AutoCloseable {
        class Item(val text: String, val kind: String)

        fun mark(text: String): Pair<List<Item>, String?> {
            val found = ArrayList<Item>()
            var intent: String? = null
            for (block in Modelo.blocks(text.split(Modelo.SEPARATOR))) {
                val encoding = tokenizer.encode(block, maxTokens)
                val (labels, intents) = run(encoding)
                for (span in Modelo.decode(encoding.starts, encoding.ends, labels, block)) {
                    found.add(Item(Modelo.strip(block.substring(span.start, span.end)), span.kind))
                }
                if (intent == null) intent = Modelo.INTENTS[argmax(intents, 0, intents.size)]
            }
            return found to intent
        }

        /** O rótulo de cada token e as notas das intenções. */
        fun run(encoding: Tokenizer.Encoding): Pair<IntArray, FloatArray> {
            val env = OrtEnvironment.getEnvironment()
            val size = encoding.ids.size.toLong()
            val ids = LongArray(encoding.ids.size) { encoding.ids[it].toLong() }
            val mask = LongArray(encoding.ids.size) { 1L }
            OnnxTensor.createTensor(env, LongBuffer.wrap(ids), longArrayOf(1, size)).use { idsTensor ->
                OnnxTensor.createTensor(env, LongBuffer.wrap(mask), longArrayOf(1, size)).use { maskTensor ->
                    session.run(mapOf("input_ids" to idsTensor, "attention_mask" to maskTensor)).use { result ->
                        val tokens = (result.get("tokens").get() as OnnxTensor).floatBuffer
                        val intents = (result.get("intencao").get() as OnnxTensor).floatBuffer
                        val width = Modelo.LABELS.size
                        val scores = FloatArray(tokens.remaining()).also { tokens.get(it) }
                        val labels = IntArray(encoding.ids.size) { argmax(scores, it * width, width) }
                        return labels to FloatArray(intents.remaining()).also { intents.get(it) }
                    }
                }
            }
        }

        override fun close() = session.close()
    }

    /** A escolha de controle: nota de cada rótulo para o pedido, mais a opção "nenhum", num softmax. */
    class Picker(
        private val session: OrtSession,
        private val tokenizer: Tokenizer,
        private val maxTokens: Int,
        val threshold: Double,
    ) : AutoCloseable {
        class Pick(val label: String?, val p: Double, val ranking: List<Pair<String?, Double>>)

        fun probabilities(wanted: List<String>, labels: List<String>): DoubleArray {
            val query = Modelo.query(wanted)
            val encodings = (labels + Modelo.NONE_LABEL).map { tokenizer.encodePair(query, it, maxTokens) }
            val width = encodings.maxOf { it.ids.size }
            val ids = LongArray(encodings.size * width) { tokenizer.padId.toLong() }
            val mask = LongArray(encodings.size * width)
            for ((row, encoding) in encodings.withIndex()) {
                for (k in encoding.ids.indices) {
                    ids[row * width + k] = encoding.ids[k].toLong()
                    mask[row * width + k] = 1
                }
            }
            val env = OrtEnvironment.getEnvironment()
            val shape = longArrayOf(encodings.size.toLong(), width.toLong())
            val scores = OnnxTensor.createTensor(env, LongBuffer.wrap(ids), shape).use { idsTensor ->
                OnnxTensor.createTensor(env, LongBuffer.wrap(mask), shape).use { maskTensor ->
                    session.run(mapOf("input_ids" to idsTensor, "attention_mask" to maskTensor)).use { result ->
                        val buffer = (result.get(0) as OnnxTensor).floatBuffer
                        DoubleArray(buffer.remaining()) { buffer.get().toDouble() }
                    }
                }
            }
            val max = scores.max()
            val e = DoubleArray(scores.size) { exp(scores[it] - max) }
            val sum = e.sum()
            return DoubleArray(e.size) { e[it] / sum }
        }

        fun pick(wanted: List<String>, labels: List<String>): Pick {
            if (labels.isEmpty()) return Pick(null, 0.0, emptyList())
            val probabilities = probabilities(wanted, labels)
            // O ranking leva a opção nenhum junto (como null); a nota vai arredondada, e é ela que se compara ao limiar.
            val ranking = (labels + listOf(null)).zip(probabilities.map { Modelo.round3(it) }).sortedByDescending { it.second }
            val (best, p) = ranking[0]
            return Pick(if (best != null && p >= threshold) best else null, p, ranking.take(10))
        }

        override fun close() = session.close()
    }

    companion object {
        /** O primeiro maior valor, como o `argmax` do numpy. */
        fun argmax(values: FloatArray, from: Int, count: Int): Int {
            var best = 0
            for (k in 1 until count) if (values[from + k] > values[from + best]) best = k
            return best
        }
    }
}
