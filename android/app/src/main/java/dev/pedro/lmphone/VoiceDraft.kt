package dev.pedro.lmphone

/** Trocar texto por voz preserva o que já foi corrigido ou digitado. Parciais substituem só a nova fala. */
internal class VoiceDraft {
    private var prefix = ""
    fun begin(text: String) { prefix = text.trimEnd() }
    fun join(spoken: String): String = if (prefix.isBlank()) spoken else "$prefix ${spoken.trimStart()}"
}
