package dev.pedro.lmphone

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Rect
import android.view.Gravity
import android.view.Choreographer
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.Window
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.LinearLayout
import kotlin.math.abs
import kotlin.math.min

/** Posiciona a janela inteira, incluindo o vidro. A alça nunca captura toques destinados ao app de baixo. */
@SuppressLint("RtlHardcoded") // x/y são coordenadas físicas da tela, inclusive quando o idioma é RTL.
internal class FloatingPanel(
    private val window: Window,
    private val panel: ViewGroup,
    handle: View,
    private val allowed: () -> Boolean = { true },
    private val onDrag: (Boolean) -> Unit = {},
    private val onMinimizeGesture: () -> Unit = {},
    private val onCloseGesture: () -> Unit = {},
) {
    private val actionHandle = handle
    private val context = panel.context
    private val prefs = context.getSharedPreferences("painel-flutuante", Context.MODE_PRIVATE)
    private val position = PanelPosition(prefs.getFloat("x", .5f), prefs.getFloat("y", 1f))
    private var dragging = false
    private var updating = false
    private var lastArea = Rect()
    private var dragArea = Rect()
    private var dragSize = 0 to 0
    private var downX = 0f
    private var downY = 0f
    private var startX = 0
    private var startY = 0
    private var moved = false
    private var pendingX = 0
    private var pendingY = 0
    private var framePending = false
    private var receivedMoves = 0
    private var appliedFrames = 0
    private var lastFrameNanos = 0L
    private var maxFrameGapMs = 0.0
    var compact = false
        set(value) { field = value; update() }
    private var touchedHandle: View? = null
    private val choreographer = Choreographer.getInstance()
    private val dragFrame = Choreographer.FrameCallback {
        framePending = false
        if (dragging) applyDragPosition()
    }
    private val manager = context.getSystemService(WindowManager::class.java)
    internal fun diagnostics() = org.json.JSONObject().put("moves", receivedMoves).put("frames", appliedFrames)
        .put("max_gap_ms", maxFrameGapMs)

    init {
        window.setGravity(Gravity.TOP or Gravity.LEFT)
        window.setDecorFitsSystemWindows(false)
        window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN)
        window.attributes = window.attributes.apply { setFitInsetsTypes(0) }
        panel.addOnLayoutChangeListener { _, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom ->
            // Mover a janela também dispara layout. Só uma mudança de TAMANHO exige recalcular a âncora.
            if (!dragging && (right - left != oldRight - oldLeft || bottom - top != oldBottom - oldTop)) update()
        }
        panel.setOnApplyWindowInsetsListener { _, insets ->
            if (!dragging) panel.post { update() }
            insets
        }
        bind(handle)
        val previous = window.callback
        if (previous != null) window.callback = object : Window.Callback by previous {
            override fun dispatchTouchEvent(event: MotionEvent): Boolean {
                // VoiceInteractionWindow recorta MOVE fora da janela. Aqui os rawX/rawY ainda são os do dedo.
                val action = event.actionMasked
                if (dragging && (action == MotionEvent.ACTION_MOVE || action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL)) {
                    drag(event)
                    return true
                }
                return previous.dispatchTouchEvent(event)
            }
        }
    }

    private fun area(): Rect {
        // Insets da TELA, nunca os recortados pela janela flutuante: estes mudam conforme ela se move e causam laço.
        val metrics = manager.maximumWindowMetrics
        val insets = metrics.windowInsets
        val bars = insets.getInsetsIgnoringVisibility(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
        val keyboard = insets.getInsets(WindowInsets.Type.ime())
        val gap = Ui.dp(context, 12)
        return Rect(metrics.bounds.left + bars.left + gap, metrics.bounds.top + bars.top + gap,
            metrics.bounds.right - bars.right - gap, metrics.bounds.bottom - maxOf(bars.bottom, keyboard.bottom) - gap)
    }

    fun update() {
        if (dragging) { applyDragPosition(); return }
        if (updating) return
        updating = true
        try {
            val area = if (dragging) dragArea else area()
            lastArea = area
            val width = min(Ui.dp(context, if (compact) 56 else 360), area.width()).coerceAtLeast(1)
            val height = (if (dragging) dragSize.second else panel.height).coerceAtMost(area.height()).coerceAtLeast(1)
            val (x, y) = position.place(area.left, area.top, area.right, area.bottom, width, height)
            // Reserva a alça e as duas linhas de controles antes de distribuir a altura para os textos.
            fun scrolls(view: View): List<CappedScroll> = when (view) {
                is CappedScroll -> if (view.visibility == View.GONE) emptyList() else listOf(view)
                is ViewGroup -> (0 until view.childCount).flatMap { scrolls(view.getChildAt(it)) }
                else -> emptyList()
            }
            val scrolls = scrolls(panel)
            val textHeight = (area.height() - Ui.dp(context, 120)).coerceAtLeast(0) / scrolls.size.coerceAtLeast(1)
            scrolls.forEach { it.limitHeight(textHeight) }
            val attrs = window.attributes
            if (attrs.x != x || attrs.y != y || attrs.width != width || attrs.height != ViewGroup.LayoutParams.WRAP_CONTENT) {
                window.attributes = attrs.apply {
                    this.x = x; this.y = y; this.width = width; this.height = ViewGroup.LayoutParams.WRAP_CONTENT
                }
                window.decorView.invalidate() // o vidro amostra a posição nova no fundo já desfocado
            }
        } finally {
            updating = false
        }
    }

    fun moveTo(top: Boolean) {
        position.vertical = if (top) 0f else 1f
        update()
    }

    /** Sai do alvo só durante o gesto; a escolha do dono continua valendo depois dele. */
    fun avoid(x: Int, y: Int): () -> Unit {
        val previous = position.horizontal to position.vertical
        val area = lastArea
        val width = panel.width
        val height = panel.height
        val candidates = listOf(0f to 0f, 1f to 0f, 0f to 1f, 1f to 1f)
        val target = candidates.firstOrNull { (horizontal, vertical) ->
            val (left, top) = PanelPosition(horizontal, vertical).place(area.left, area.top, area.right, area.bottom, width, height)
            !Rect(left, top, left + width, top + height).contains(x, y)
        }
        if (target != null) {
            position.horizontal = target.first
            position.vertical = target.second
            update()
        }
        return {
            position.horizontal = previous.first
            position.vertical = previous.second
            update()
        }
    }

    /** Como `avoid(x, y)`, para uma área (o destaque do guia): o canto da tela em que a faixa não a cobre. */
    fun avoid(area: Rect): () -> Unit {
        val previous = position.horizontal to position.vertical
        val screen = lastArea
        val width = panel.width
        val height = panel.height
        val candidates = listOf(previous.first to (1f - previous.second), 0f to 0f, 1f to 0f, 0f to 1f, 1f to 1f, .5f to 0f, .5f to 1f)
        val target = candidates.firstOrNull { (horizontal, vertical) ->
            val (left, top) = PanelPosition(horizontal, vertical).place(screen.left, screen.top, screen.right, screen.bottom, width, height)
            !Rect.intersects(Rect(left, top, left + width, top + height), area)
        }
        if (target != null) {
            position.horizontal = target.first
            position.vertical = target.second
            update()
        }
        return {
            position.horizontal = previous.first
            position.vertical = previous.second
            update()
        }
    }

    fun restore() {
        position.horizontal = prefs.getFloat("x", .5f)
        position.vertical = prefs.getFloat("y", 1f)
        update()
    }

    val atTop get() = position.vertical < .5f

    private fun save() {
        prefs.edit().putFloat("x", position.horizontal).putFloat("y", position.vertical).apply()
    }

    @SuppressLint("ClickableViewAccessibility")
    fun bind(handle: View) {
        handle.isClickable = true
        // Um toque sem arraste não muda de lado; esse atalho tem seu próprio botão acessível no cabeçalho.
        handle.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (!allowed()) return@setOnTouchListener false
                    touchedHandle = handle
                    downX = event.rawX; downY = event.rawY
                    startX = window.attributes.x; startY = window.attributes.y
                    pendingX = startX; pendingY = startY
                    moved = false
                    receivedMoves = 0; appliedFrames = 0; lastFrameNanos = 0; maxFrameGapMs = 0.0
                    dragArea = area()
                    dragSize = panel.width to panel.height
                    window.attributes = window.attributes.apply { width = dragSize.first; height = dragSize.second }
                    dragging = true
                    onDrag(true)
                }
                else -> if (dragging) drag(event)
            }
            true
        }
    }

    private fun drag(event: MotionEvent) {
        val dx = event.rawX - downX
        val dy = event.rawY - downY
        val slop = ViewConfiguration.get(context).scaledTouchSlop
        if (event.actionMasked != MotionEvent.ACTION_CANCEL && (moved || abs(dx) > slop || abs(dy) > slop)) {
            moved = true
            pendingX = (startX + dx.toInt()).coerceIn(dragArea.left, maxOf(dragArea.left, dragArea.right - dragSize.first))
            pendingY = (startY + dy.toInt()).coerceIn(dragArea.top, maxOf(dragArea.top, dragArea.bottom - dragSize.second))
        }
        if (event.actionMasked == MotionEvent.ACTION_MOVE) {
            receivedMoves++
            if (!framePending) { framePending = true; choreographer.postFrameCallback(dragFrame) }
        } else if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
            val clicked = !moved && event.actionMasked == MotionEvent.ACTION_UP
            val action = if (moved && event.actionMasked == MotionEvent.ACTION_UP &&
                touchedHandle === actionHandle && Ui.headerMenu(context)) {
                val density = context.resources.displayMetrics.density
                val bottom = maxOf(dragArea.top, dragArea.bottom - dragSize.second)
                PanelGesture.action(dx / density, dy / density, (startY + dy - bottom) / density)
            } else PanelGesture.Action.NONE
            choreographer.removeFrameCallback(dragFrame)
            framePending = false
            applyDragPosition()
            dragging = false
            onDrag(false)
            position.move(pendingX, pendingY, dragArea.left, dragArea.top, dragArea.right, dragArea.bottom, dragSize.first, dragSize.second)
            save()
            update()
            if (clicked) touchedHandle?.performClick()
            touchedHandle = null
            when (action) {
                PanelGesture.Action.MINIMIZE -> onMinimizeGesture()
                PanelGesture.Action.CLOSE -> onCloseGesture()
                PanelGesture.Action.NONE -> Unit
            }
        }
    }

    /** Caminho do gesto: só coordenadas em pixels. Não mede textos, consulta insets ou percorre a árvore. */
    private fun applyDragPosition() {
        val attrs = window.attributes
        if (attrs.x == pendingX && attrs.y == pendingY) return
        val now = System.nanoTime()
        if (lastFrameNanos != 0L) maxFrameGapMs = maxOf(maxFrameGapMs, (now - lastFrameNanos) / 1e6)
        lastFrameNanos = now
        appliedFrames++
        window.attributes = attrs.apply { x = pendingX; y = pendingY }
        window.decorView.invalidate()
    }

    fun cancelDrag() {
        choreographer.removeFrameCallback(dragFrame)
        framePending = false
        if (dragging) { dragging = false; onDrag(false) }
    }
}
