package dev.pedro.lmphone

import kotlin.math.roundToInt

/** Posição relativa ao espaço disponível: crescer, girar a tela e abrir o teclado não perdem a alça. */
internal class PanelPosition(var horizontal: Float = .5f, var vertical: Float = 1f) {
    fun place(left: Int, top: Int, right: Int, bottom: Int, width: Int, height: Int): Pair<Int, Int> =
        left + ((right - left - width).coerceAtLeast(0) * horizontal.coerceIn(0f, 1f)).roundToInt() to
            top + ((bottom - top - height).coerceAtLeast(0) * vertical.coerceIn(0f, 1f)).roundToInt()

    fun move(x: Int, y: Int, left: Int, top: Int, right: Int, bottom: Int, width: Int, height: Int) {
        val dx = right - left - width
        val dy = bottom - top - height
        if (dx > 0) horizontal = ((x - left).toFloat() / dx).coerceIn(0f, 1f)
        if (dy > 0) vertical = ((y - top).toFloat() / dy).coerceIn(0f, 1f)
    }
}
