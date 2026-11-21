package dev.pedro.lmphone

/**
 * Os botões da interface ditos em voz alta (pedido do Pedro, 2026-10-26): "Alexa, live mode", "Alexa, pausa", "Alexa,
 * para"... Valem no painel do assistente, na faixa e no modo contínuo, e são reconhecidos aqui, sem o provedor.
 *
 * Um comando é a fala inteira (sem acentos, pontuação nem a palavra de ativação): "para" sozinho encerra a tarefa, mas
 * "abre o Waze para casa" continua sendo um pedido. Quem decide o que cada um faz é quem ouviu: sem tarefa em curso,
 * "pausa" e "para" vão ao assistente como pedido (pausar a música, como numa Alexa).
 */
enum class Command { LIVE, FINISH, STOP, CLOSE, PAUSE, RESUME, OWNER, AGENT, MINIMIZE, EXPAND, MOVE, MUTE, UNMUTE, REPEAT, SLOWER, FASTER, WRITE }

object Commands {
    private val TABLE: List<Pair<Command, Regex>> = listOf(
        Command.LIVE to "((liga|ligar|ativa|ativar|abre|abrir|entra|entrar|inicia|iniciar|comeca|comecar) )?((o|no) )?" +
            "(live|laive|(live|laive|laiv|lai|love) ?(mode|mod|moud|modi|modo)|modo (continuo|ao vivo|live|laive))",
        Command.FINISH to "(pode )?(finaliza|finalizar|finalize|encerra|encerrar|encerre|termina|terminar|termine|sair|sai|" +
            "tchau)( (o )?(live( mode)?|modo( continuo| live)?|tudo|isso))?",
        Command.STOP to "(pode )?(para|pare|parar|chega|interrompe|interromper|interrompa)( (a tarefa|tudo|isso|ai|por favor))?",
        Command.CLOSE to "(fecha|fechar|feche|cancela|cancelar|cancele|deixa (pra|para) la|esquece|esqueca|nada|nao e nada)",
        Command.PAUSE to "(pausa|pausar|pause|espera|espere|aguarda|aguarde)( ai| um pouco| um pouquinho| a tarefa)?",
        Command.RESUME to "(continua|continuar|continue|pode continuar|segue|pode seguir|retoma|retomar|retome)( a tarefa)?",
        Command.OWNER to "(deixa (que )?eu (faco|fazer)|eu faco|deixa comigo|minha vez|eu mesmo faco|eu quero fazer)",
        Command.AGENT to "(faz voce|faca voce|pode fazer|sua vez|faz (pra|para) mim|faca (pra|para) mim)",
        Command.MINIMIZE to "(minimiza|minimizar|minimize|esconde|esconder|esconda|diminui|diminuir|recolhe)( a faixa)?",
        Command.EXPAND to "(abre|mostra|mostrar|aumenta|expande|expandir) a faixa|mostra|expande",
        Command.MOVE to "(muda|mudar|troca|trocar) (a faixa )?de lado|(sobe|desce) a faixa",
        Command.MUTE to "(silencio|fica quiet[oa]|nao fala|para de falar|desliga a voz|sem voz|mudo|modo silencioso)",
        Command.UNMUTE to "(liga a voz|fala comigo|com voz|pode falar|volta a falar)",
        // No guia (docs/plano-tutor.md): quem não entendeu pede de novo, e mais devagar.
        Command.REPEAT to "(repete|repetir|repita|fala de novo|o que voce disse|nao entendi|como assim|nao ouvi|" +
            "hein|pode repetir|repete (pra|para) mim)",
        Command.SLOWER to "((fala|falar|fale) )?(mais )?(devagar|devagarinho|com calma)|(fala|fale) mais (devagar|baixo e devagar)",
        Command.FASTER to "((fala|falar|fale) )?mais (rapido|depressa|ligeiro)",
        Command.WRITE to "(escrever|quero escrever|vou escrever|teclado|abre o teclado)",
    ).map { (command, pattern) -> command to Regex("^($pattern)$") }

    // A palavra de ativação no começo da fala, e o pedaço dela que o reconhecedor às vezes pega ("xa pausa").
    private val WAKE_WORDS = Regex("^((ei|oi|ok|hey|e|o|a) )?(alexa|alexia|aleksa|alexsa|lexa|exa|xa|sa)( |$)")
    private val WAKE_TEXT = Regex("^\\s*((ei|oi|ok|hey)[,!.]?\\s+)?alexa\\b[,!.:]?\\s*", RegexOption.IGNORE_CASE)

    fun plain(text: String) = java.text.Normalizer.normalize(text.lowercase(), java.text.Normalizer.Form.NFD)
        .replace(Regex("\\p{M}+"), "").replace(Regex("[^a-z0-9 ]"), " ").trim().replace(Regex(" +"), " ")

    /** O comando que a fala inteira é, ou null. */
    fun parse(text: String): Command? {
        val words = plain(text).replace(WAKE_WORDS, "").removeSuffix(" por favor").trim()
        if (words.isEmpty()) return null
        return TABLE.firstOrNull { (_, pattern) -> pattern.matches(words) }?.first
    }

    /** A fala é só a palavra de ativação (ou o pedaço dela): o pedido ainda não veio. */
    fun onlyWake(text: String) = plain(text).replace(WAKE_WORDS, "").isBlank()

    /** A fala sem a palavra de ativação na frente ("Alexa, abre o Waze" vira "abre o Waze"): ela não vai ao provedor. */
    fun withoutWake(text: String) = text.replace(WAKE_TEXT, "").trim()
}
