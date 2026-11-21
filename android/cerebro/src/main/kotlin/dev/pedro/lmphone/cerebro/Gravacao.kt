package dev.pedro.lmphone.cerebro

import java.io.File

/**
 * O gravador das rodadas no celular, só no build de depuração (`Agent.recording`): tudo o que entra no executor, na
 * ordem em que entra, em `logs/gravacoes/<sessão>.jsonl`, para o PC repetir a rodada no executor do Python e montar o
 * simulador com as telas de verdade (`tests/gravacao.py`). Os valores vão reais, sem máscara (decisão do Pedro,
 * 2026-11-18): as telas lidas, os fatos, os toques da faixa, as respostas do provedor e do modelo de escolha e cada
 * leitura do relógio do executor.
 *
 * Cada linha tem `tipo` e `t` (o relógio do executor, `System.nanoTime` em segundos). Os tipos:
 * - `inicio` e `fim`: o pedido e o resultado;
 * - `executor`: o executor novo, com o que o construtor e o `Agent` lhe deram;
 * - `preparar`: o `prepare()` (o pedido do plano);
 * - `vez`: o que o ciclo copiou da faixa para o executor antes de uma leitura (só quando muda);
 * - `tela`: cada leitura da tela (o texto que o executor recebe; `igual` quando repete a anterior);
 * - `passo` e `decisao`: a mensagem de um `step()` e o que ele decidiu (a chamada, o destaque, o gesto, o botão, a fala);
 * - `cb`: cada coisa que o executor pediu de fora (`clock`, `facts`, `provider`, `pick`, `settings`, `launch`, `setter`,
 *   `searcher`), com o que voltou;
 * - `instrucao`, `resposta`, `confirmacao`: o que a pessoa disse ou escreveu na faixa.
 */
class Gravacao(private val file: File) {
    private var last: String? = null
    private var turn: Map<String, Any?>? = null

    init {
        file.parentFile?.mkdirs()
    }

    @Synchronized
    fun write(kind: String, fields: Map<String, Any?> = emptyMap()) {
        try {
            file.appendText(Json.dumps(linkedMapOf<String, Any?>("tipo" to kind, "t" to System.nanoTime() / 1e9) + fields) + "\n")
        } catch (e: Exception) {
            // a gravação não pode parar a tarefa
        }
    }

    /** Uma leitura da tela: o texto inteiro só quando muda. */
    @Synchronized
    fun screen(text: String, pkg: String?) {
        if (text == last) {
            write("tela", linkedMapOf("igual" to true))
        } else {
            last = text
            write("tela", linkedMapOf("texto" to text, "pacote" to pkg))
        }
    }

    /** O que o ciclo passou da faixa ao executor; só grava quando muda. */
    @Synchronized
    fun turn(fields: Map<String, Any?>) {
        if (fields == turn) return
        turn = LinkedHashMap(fields)
        write("vez", fields)
    }

    fun cb(name: String, ret: Any?, extra: Map<String, Any?> = emptyMap()) =
        write("cb", linkedMapOf<String, Any?>("cb" to name, "ret" to ret) + extra)
}
