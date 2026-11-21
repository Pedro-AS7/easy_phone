package dev.pedro.lmphone

import org.json.JSONArray
import org.json.JSONObject

/**
 * O estado do live mode no aparelho (docs/plano-live-mode.md): pausado, interrompido, o usuário escrevendo na faixa, e
 * a fila do que o usuário fez desde a última vez que o cérebro perguntou (`/events`).
 *
 * Pausar e interromper valem aqui, na hora: com eles, o serviço recusa gestos, teclas e digitação, sem esperar o
 * cérebro (no PC, ele só vê o pedido na leitura seguinte).
 */
object Live {
    @Volatile var paused = false
    @Volatile var stopped = false
    @Volatile var typing = false  // o usuário está escrevendo na faixa: o agente não digita nem toca
    @Volatile var dragging = false  // a alça está sendo arrastada: não disputa a tela com o dono
    @Volatile var owner = false  // a vez é do dono ("Deixa que eu faço", o botão da mão): o agente mostra os passos e espera, sem agir
    @Volatile var ownerTarget = false  // o destaque na tela é para o dono tocar (guia, vez do dono): o toque dele não pausa
    @Volatile var ownerGesture = false  // a faixa mostra um gesto para o dono fazer (puxar o painel, rolar): o toque dele é o passo
    @Volatile var task = false  // o cérebro já anunciou o pedido ("nova_tarefa"): antes disso a faixa só aparece, sem tarefa
    @Volatile var guide = false  // o pedido é um guia ("como eu faço..."): o toque da pessoa na tela não pausa
    @Volatile var guideAgent = false  // opção do app: no guia, o agente toca (depois de uns segundos) em vez de esperar a pessoa
    @Volatile var awaitingService = false  // um pedido espera a pessoa ligar a acessibilidade pelo atalho (a `loja`)
    @Volatile var ownerTargetUntil = 0L  // o destaque do dono acabou de sair: um toque dele que chega atrasado ainda vale como dele

    /** Um toque do dono agora é o passo que o agente espera (a vez dele, o destaque dele ou logo depois dele), não uma pausa. */
    fun ownerTouchExpected() = owner || ownerTarget || ownerGesture || System.currentTimeMillis() < ownerTargetUntil
    @Volatile var gesturing = false  // um gesto do agente está em curso
    @Volatile var agentActedAt = 0L  // fim do último gesto ou tecla do agente: separa os toques dele dos do usuário
    @Volatile var agentPoint: Pair<Int, Int>? = null  // onde foi o último toque do agente
    @Volatile var previousIme: String? = null  // o teclado do usuário, para ele escrever na faixa
    // Live mode contínuo (2026-10-24): o microfone fica aberto e cada fala é um pedido novo, até "finalizar" ou o X.
    // Entre um pedido e outro o serviço continua ligado, e estes valores passam de um para o outro.
    @Volatile var continuous = false
    @Volatile var requesting = false  // um pedido mandado pela faixa (modo contínuo) ainda não acabou
    @Volatile var banks: Set<String> = emptySet()  // apps de banco (o PC manda): com um deles na frente, o serviço se desliga

    private val events = mutableListOf<JSONObject>()

    // Um toque do usuário que chega até este tempo depois de um gesto do agente pode ser efeito do gesto.
    const val AGENT_WINDOW_MS = 1500L

    fun reset() {
        paused = false; stopped = false; typing = false; dragging = false; owner = false; ownerTarget = false; ownerGesture = false; ownerTargetUntil = 0L; previousIme = null
        continuous = false; requesting = false; task = false; guide = false
        synchronized(events) { events.clear() }
    }

    /**
     * O começo de um pedido no modo contínuo: o serviço não foi religado, e a pausa e a vez do anterior não valem mais.
     * Um "novo_pedido" ainda na fila era para o pedido anterior (que acabou antes de ler): não pode parar este.
     */
    fun newTask() {
        paused = false; stopped = false; owner = false; task = true
        synchronized(events) { events.removeAll { it.optString("tipo") == "novo_pedido" } }
    }

    fun event(kind: String, fields: JSONObject = JSONObject()) {
        synchronized(events) { events.add(fields.put("tipo", kind).put("t", System.currentTimeMillis())) }
    }

    /** O que o usuário fez desde a última chamada, e o estado atual. */
    fun poll(): JSONObject {
        val out = JSONArray()
        synchronized(events) { events.forEach { out.put(it) }; events.clear() }
        // "falando": a faixa ainda lê algo em voz alta (no guia, o prazo do dono para tocar só conta depois).
        return JSONObject().put("paused", paused).put("stopped", stopped).put("typing", typing || dragging).put("dono", owner)
            .put("falando", Speaker.speaking).put("guia", if (guideAgent) "agente" else "pessoa").put("events", out)
            .put("agora", System.currentTimeMillis())  // a idade de cada evento ("t"): o cérebro sabe a hora de cada toque
    }

    /** null se o agente pode agir agora; senão, o motivo (vai ao cérebro como erro da ação). */
    fun blocked(): String? = when {
        stopped -> "stopped by the user"
        paused -> "paused by the user"
        typing -> "the user is writing to the agent"
        dragging -> "paused by the user (moving the panel)"
        owner -> "the owner is doing this step"
        else -> null
    }
}
