package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** O que o agente faz no aparelho: gestos, digitação no campo em foco e as teclas do sistema. */
object Actions {
    private var lastField: AccessibilityNodeInfo? = null

    /** Um toque em (x, y). Devolve false se o sistema cancelou o gesto. */
    fun tap(service: AccessibilityService, x: Int, y: Int): Boolean =
        gesture(service, Path().apply { moveTo(x.toFloat(), y.toFloat()) }, 50)

    fun swipe(service: AccessibilityService, x1: Int, y1: Int, x2: Int, y2: Int, millis: Long): Boolean =
        gesture(service, Path().apply { moveTo(x1.toFloat(), y1.toFloat()); lineTo(x2.toFloat(), y2.toFloat()) }, millis)

    private fun gesture(service: AccessibilityService, path: Path, millis: Long): Boolean {
        val done = CountDownLatch(1)
        var ok = false
        val stroke = GestureDescription.StrokeDescription(path, 0, millis.coerceAtLeast(1))
        val started = service.dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(),
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(description: GestureDescription?) { ok = true; done.countDown() }
                override fun onCancelled(description: GestureDescription?) { done.countDown() }
            }, null)
        return started && done.await(millis + 3000, TimeUnit.MILLISECONDS) && ok
    }

    /**
     * Escreve no campo em foco, sem teclado: `clear` troca o texto, senão acrescenta ao que já está lá. Devolve o erro,
     * ou null. O Portal digitava pelo próprio teclado, que precisava ficar ativo durante a tarefa.
     */
    fun type(service: AccessibilityService, text: String, clear: Boolean): String? {
        // Sem campo à vista, o último onde se escreveu, se ainda existe: depois de receber o título, o Notion redesenha e
        // nenhum campo fica com o foco; o teclado do Portal continuava ligado ao mesmo campo, e é o que se imita aqui.
        val field = waitForField(service) ?: lastField?.takeIf { it.refresh() && it.isEditable }
            ?: return typeIntoConnection(service, text, clear)
        lastField = field
        val current = if (clear || field.isShowingHintText) "" else field.text?.toString() ?: ""
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, current + text)
        }
        return if (field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) null else "the field refused the text"
    }

    /**
     * Sem campo editável na árvore (o corpo de uma página do Notion), escreve pelo teclado do agente ou, sem ele, na
     * conexão de texto que o serviço de acessibilidade tem desde o Android 13 (flagInputMethodEditor).
     */
    private fun typeIntoConnection(service: AccessibilityService, text: String, clear: Boolean): String? {
        // O teclado do agente, se é o ativo: ligado ao campo pelo sistema, como o do Portal.
        Keyboard.current?.let { keyboard -> keyboard.write(text, clear)?.let { error -> return error } ?: return null }
        val method = service.inputMethod
        val connection = method?.currentInputConnection
            ?: return "no editable field to type into (" + (if (method == null) "no input method" else "no input connection") + ")"
        if (clear) connection.performContextMenuAction(android.R.id.selectAll)
        connection.commitText(text, 1, null)
        return null
    }

    /**
     * O executor manda digitar logo depois de tocar no campo, e o campo às vezes ainda não existe (a busca do X abre
     * uma tela nova com ele): espera até 2 s. Pelo Portal, a própria chamada ao teclado dava esse tempo.
     */
    private fun waitForField(service: AccessibilityService): AccessibilityNodeInfo? {
        val deadline = System.currentTimeMillis() + 2000
        while (true) {
            field(service)?.let { return it }
            if (System.currentTimeMillis() > deadline) return null
            Thread.sleep(150)
        }
    }

    /**
     * O campo onde digitar: o de foco de entrada, se aceita texto; senão (o editor do Notion às vezes não informa o
     * foco, às vezes informa um elemento que não é editável), o editável focado, ou o único editável da tela.
     */
    private fun field(service: AccessibilityService): AccessibilityNodeInfo? {
        // Todas as janelas na tela, menos a do teclado: com o teclado aberto, a "janela ativa" pode ser a dele, e o
        // campo do app não estava nela (as buscas do Instagram, do YouTube Music e do X falhavam assim).
        // Nem a da faixa do live mode (Overlay), que tem um campo de texto do próprio usuário.
        val roots = service.windows
            .filter { it.type != android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD &&
                it.type != android.view.accessibility.AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY }
            .mapNotNull { it.root }
            .ifEmpty { listOfNotNull(service.rootInActiveWindow) }
        roots.firstNotNullOfOrNull { it.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { node -> node.isEditable } }
            ?.let { return it }
        val editable = mutableListOf<AccessibilityNodeInfo>()
        fun walk(node: AccessibilityNodeInfo) {
            if (node.isEditable && node.isVisibleToUser) editable.add(node)
            for (i in 0 until node.childCount) node.getChild(i)?.let(::walk)
        }
        roots.forEach(::walk)
        return editable.firstOrNull { it.isFocused } ?: editable.singleOrNull()
    }

    /** back, home, quick_settings ou enter (o "enviar"/"buscar" do campo em foco). Devolve o erro, ou null. */
    fun key(service: AccessibilityService, name: String): String? = when (name.lowercase()) {
        "back" -> if (service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)) null else "back failed"
        "home" -> if (service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)) null else "home failed"
        "quick_settings" -> if (service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS)) null
            else "quick settings failed"
        "enter" -> {
            val field = field(service) ?: lastField?.takeIf { it.refresh() && it.isEditable }
            val enter = AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
            val connection = service.inputMethod?.currentInputConnection
            val keyboard = Keyboard.current
            when {
                field != null && field.performAction(enter) -> null
                keyboard != null -> keyboard.enter()
                connection != null -> {
                    connection.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, android.view.KeyEvent.KEYCODE_ENTER))
                    connection.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, android.view.KeyEvent.KEYCODE_ENTER))
                    null
                }
                else -> "enter failed (no focused field accepted it)"
            }
        }
        else -> "unknown key: $name"
    }
}
