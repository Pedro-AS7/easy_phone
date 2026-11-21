package dev.pedro.lmphone

import kotlin.math.abs

/** Distâncias em dp, medidas pelo dedo antes de limitar a posição da janela. */
internal object PanelGesture {
    enum class Action { NONE, MINIMIZE, CLOSE }

    fun action(dx: Float, dy: Float, bottomOverflow: Float): Action = when {
        dy > 0 && dy > abs(dx) * 1.5f && bottomOverflow >= 56f -> Action.CLOSE
        abs(dx) >= 72f && abs(dx) > abs(dy) * 1.5f -> Action.MINIMIZE
        else -> Action.NONE
    }
}
