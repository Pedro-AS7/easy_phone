package dev.pedro.lmphone

import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.TextView

/**
 * O teclado do agente: fica como teclado ativo só durante a tarefa (o PC o liga e devolve o de antes no fim, como o
 * do Portal). Não tem teclas; o agente escreve por ele quando o campo não aparece na árvore de acessibilidade (a
 * busca do YouTube Music, o corpo de uma página do Notion), onde `ACTION_SET_TEXT` não tem em que agir.
 */
class Keyboard : InputMethodService() {
    override fun onCreate() {
        super.onCreate()
        current = this
    }

    override fun onDestroy() {
        if (current === this) current = null
        super.onDestroy()
    }

    /** Uma faixa fina no lugar das teclas: mostra que o agente está com o teclado. */
    override fun onCreateInputView(): View = TextView(this).apply {
        text = "lm_phone está digitando"
        gravity = Gravity.CENTER
        setPadding(0, 16, 0, 16)
        setBackgroundColor(Color.parseColor("#263238"))
        setTextColor(Color.WHITE)
    }

    /** Escreve na conexão ativa. `clear` apaga antes o que o campo tem. Devolve o erro, ou null. */
    fun write(text: String, clear: Boolean): String? {
        val connection = currentInputConnection ?: return "the agent keyboard has no field connected"
        if (clear) {
            connection.performContextMenuAction(android.R.id.selectAll)
            connection.commitText("", 1)
        }
        return if (connection.commitText(text, 1)) null else "the field did not accept the text"
    }

    /** A ação do Enter do campo (buscar, ir, enviar) ou, se ele não tem, a tecla Enter. */
    fun enter(): String? {
        val connection = currentInputConnection ?: return "the agent keyboard has no field connected"
        val action = (currentInputEditorInfo?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED && connection.performEditorAction(action)) {
            return null
        }
        connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
        connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        return null
    }

    companion object {
        /** O teclado no ar, se ele é o ativo (mesmo processo do serviço de acessibilidade). */
        @Volatile
        var current: Keyboard? = null
    }
}
