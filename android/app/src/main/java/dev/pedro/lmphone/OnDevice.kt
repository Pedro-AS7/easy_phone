package dev.pedro.lmphone

import android.content.Context
import android.util.Log
import dev.pedro.lmphone.cerebro.Agent
import dev.pedro.lmphone.cerebro.LocalAi
import dev.pedro.lmphone.cerebro.Py
import dev.pedro.lmphone.cerebro.Storage
import dev.pedro.lmphone.modelos.Models
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * O cérebro no celular (etapa 3 de docs/plano-app-android.md): o `Agent` do módulo `cerebro` (a tradução de
 * lmphone/proxy.py e service.py) com o aparelho, a faixa, os modelos pequenos e o provedor daqui mesmo. É o caminho do
 * `Brain` quando o dono escolhe "celular" na tela do app; com "PC", tudo vai ao PC como antes.
 *
 * Os modelos carregam no primeiro pedido (1 a 5 s) e ficam `IDLE_MS` depois do último; os arquivos do cérebro (o
 * registro, o cofre, o cache, as preferências) ficam em files/cerebro/, com os nomes do PC (logs/, data/).
 */
object OnDevice {
    private const val IDLE_MS = 10 * 60 * 1000L
    private const val BUSY_WAIT_S = 30L  // service.BUSY_WAIT
    private var agent: Agent? = null
    private var models: Models? = null
    private var used = 0L
    private val lock = Any()

    fun prefs(context: Context) = context.getSharedPreferences("cerebro", Context.MODE_PRIVATE)

    /** O dono escolheu o cérebro no celular (a tela inicial do app). Na `loja` não há PC: é sempre no celular. */
    fun enabled(context: Context) = !Flavor.ACTS || prefs(context).getString("cerebro", "pc") == "celular"

    fun choose(context: Context, phone: Boolean) = prefs(context).edit().putString("cerebro", if (phone) "celular" else "pc").apply()

    fun root(context: Context) = File(context.filesDir, "cerebro")

    /** O agente, criado na primeira vez (com os modelos carregados, se faltarem). */
    fun agent(context: Context): Agent = synchronized(lock) {
        val app = context.applicationContext
        val directory = Flavor.modelsDir(app) ?: throw IllegalStateException("os modelos ainda não estão no celular")
        val loaded = models ?: Models(directory).also {
            models = it
            Log.i("lmphone", "cérebro no celular: modelos carregados")
        }
        used = System.currentTimeMillis()
        agent?.let { return it }
        val store = Storage(root(app))
        lateinit var made: Agent
        made = Agent(PhoneImpl(app) { made.banks() }, Flavor.upstream(app) { made.session }, LocalAi(loaded), store)
        made.acts = Flavor.ACTS  // na `loja`, só guia
        made.recording = BuildConfig.DEBUG  // as rodadas gravadas para o simulador do PC (tests/gravacao.py)
        prefs(app).getString("modelo", null)?.let { made.model = it }
        agent = made
        thread(isDaemon = true, name = "lmphone-contatos") {
            try {
                val stoplist = try { Py.split(store.stoplist.readText()) } catch (e: Exception) { emptyList() }
                val count = Flavor.refreshVault(app, store.vault, stoplist)
                if (count > 0) Log.i("lmphone", "cofre pelos contatos: $count itens")
            } catch (e: Exception) {
                Log.w("lmphone", "o cofre não leu os contatos", e)
            }
        }
        made
    }

    /** Solta os modelos depois de `IDLE_MS` sem pedidos (o app não fica com eles fora das tarefas). */
    private fun releaseLater() {
        thread(isDaemon = true, name = "lmphone-soltar-modelos") {
            Thread.sleep(IDLE_MS + 1000)
            synchronized(lock) {
                val current = agent
                if (System.currentTimeMillis() - used >= IDLE_MS && (current == null || !current.busy.isLocked) && !(current?.continuous ?: false)) {
                    models?.close()
                    models = null
                    agent = null
                    Log.i("lmphone", "cérebro no celular: modelos soltos")
                }
            }
        }
    }

    /** O pedido, do começo ao fim, como o `/task` do serviço no PC. */
    /** Pedidos em curso no cérebro do celular (do painel, da faixa ou do `DebugTask`). */
    val running = java.util.concurrent.atomic.AtomicInteger()

    fun send(context: Context, text: String, onLine: (String) -> Unit, continuous: Boolean, conversation: String,
             useCache: Boolean = true, ask: Boolean = true, lines: MutableList<String>? = null): Brain.Result {
        running.incrementAndGet()
        try {
            return sendNow(context, text, onLine, continuous, conversation, useCache, ask, lines)
        } finally {
            running.decrementAndGet()
        }
    }

    private fun sendNow(context: Context, text: String, onLine: (String) -> Unit, continuous: Boolean, conversation: String,
                        useCache: Boolean, ask: Boolean, lines: MutableList<String>?): Brain.Result {
        Flavor.providerMissing(context)?.let { return Brain.Result(false, it) }
        val agent = try {
            agent(context)
        } catch (e: Exception) {
            Log.w("lmphone", "o cérebro no celular não subiu", e)
            return Brain.Result(false, "Os modelos do cérebro não estão no celular (tools.app.modelos enviar).")
        }
        if (!agent.busy.tryLock(BUSY_WAIT_S, TimeUnit.SECONDS)) {
            return Brain.Result(false, "O agente ainda está fazendo outra coisa no celular. Tenta de novo daqui a pouco.")
        }
        agent.continuous = continuous
        val started = System.nanoTime()
        try {
            val result = agent.run(text, { line ->
                lines?.add(line)
                if (line.startsWith("Assistente: ")) onLine(line.removePrefix("Assistente: "))
            }, AtomicBoolean(false), useCache = useCache, ask = ask, conversation = conversation, continuous = continuous)
            lines?.add("(%.1f s)".format(java.util.Locale.ROOT, (System.nanoTime() - started) / 1e9))
            return if (result == null) Brain.Result(false, "Interrompido.") else Brain.Result(result.first, result.second)
        } catch (e: Exception) {
            Log.w("lmphone", "o cérebro no celular falhou", e)
            return Brain.Result(false, "O cérebro no celular falhou: ${e.message ?: e}")
        } finally {
            // No modo contínuo a acessibilidade fica para o pedido seguinte; só o teclado volta a ser o do dono.
            if (agent.continuous) agent.keyboardBack() else agent.switchOff()
            used = System.currentTimeMillis()
            agent.busy.unlock()
            releaseLater()
        }
    }

    /** O live mode contínuo, como o `/live` do serviço no PC: "iniciar" liga a acessibilidade e a deixa ligada. */
    fun live(context: Context, action: String): Brain.Result {
        val agent = try {
            agent(context)
        } catch (e: Exception) {
            return Brain.Result(false, "Os modelos do cérebro não estão no celular (tools.app.modelos enviar).")
        }
        if (action == "encerrar") {
            agent.continuous = false
            if (agent.busy.tryLock()) {
                try {
                    agent.switchOff()
                } finally {
                    agent.busy.unlock()
                }
            }
            releaseLater()
            return Brain.Result(true, "")
        }
        if (!agent.busy.tryLock(BUSY_WAIT_S, TimeUnit.SECONDS)) {
            return Brain.Result(false, "O agente ainda está fazendo outra coisa no celular. Tenta de novo daqui a pouco.")
        }
        try {
            val phone = PhoneImpl(context.applicationContext) { agent.banks() }
            if (agent.isBank(phone.foreground())) return Brain.Result(false, Agent.BANK_MESSAGE)
            if (!phone.accessibilityOn()) {
                agent.switchOff()
                return Brain.Result(false, "Não consegui ligar a acessibilidade do app.")
            }
            agent.continuous = true
            phone.strip()?.send(linkedMapOf("continuo" to true, "nova_tarefa" to true, "bancos" to agent.banks().sorted(),
                "status" to "Modo contínuo: pode ir pedindo. Diga «finalizar» para encerrar."))
            agent.keyboardBack()
            agent.log(linkedMapOf("continuo" to linkedMapOf("iniciou" to true)))
            return Brain.Result(true, "")
        } catch (e: Exception) {
            agent.continuous = false
            agent.switchOff()
            return Brain.Result(false, e.toString())
        } finally {
            agent.busy.unlock()
        }
    }
}
