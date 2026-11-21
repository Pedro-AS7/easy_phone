package dev.pedro.lmphone

import android.content.Context
import android.os.ParcelFileDescriptor

/**
 * Na variante `loja` não há palavra de ativação (decisão do Pedro, 2026-11-16, docs/plano-play-store.md): o app abre
 * pelo botão lateral, pelo ícone ou por um atalho. Este objeto tem só o que o código comum chama, sem microfone aberto.
 */
object Wake {
    const val WORD = ""
    const val RATE = 16000
    @Volatile var testHeard = false

    fun start(context: Context) {}
    fun handOver() {}
    fun takeStream(): ParcelFileDescriptor? = null
    fun endStream() {}
    fun report(where: String, text: String, command: Command?) {}
}
