package dev.pedro.lmphone

import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.Matrix
import android.graphics.Outline
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.Window
import android.view.WindowManager
import android.util.Half
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.roundToInt

/**
 * Desfoque real, inclusive na One UI que não oferece cross-window blur. A fonte vem da janela abaixo da faixa ou
 * do screenshot entregue pelo próprio assistente Android. Nunca passa pelo cérebro, por arquivo ou pelo provedor.
 */
internal class FrostedGlass(private val window: Window) {
    private val manager = window.context.getSystemService(WindowManager::class.java)
    private val generation = AtomicInteger()
    private val drawable = GlassDrawable()
    var enabled = Ui.blurEnabled(window.context)
        private set
    var native = enabled && manager.isCrossWindowBlurEnabled
        private set
    val hasSource get() = drawable.bitmap != null
    val format get() = drawable.bitmap?.config?.name
    private var dragging = false
    private var pending: Pair<Bitmap?, Rect>? = null
    private val main = Handler(Looper.getMainLooper())
    private var opening = false
    private var openingFallback = false
    private val openingTimeout = Runnable { unavailable() }
    private var backgroundShown = true

    private fun updateNative(available: Boolean) {
        native = enabled && available
        window.setBackgroundBlurRadius(if (backgroundShown && native) Ui.dp(window.context, BLUR_RADIUS_DP) else 0)
        drawable.invalidateSelf()
        if (native) reveal()
    }

    fun showBackground(show: Boolean) {
        backgroundShown = show
        window.setBackgroundDrawable(if (show) drawable else android.graphics.drawable.ColorDrawable(android.graphics.Color.TRANSPARENT))
        window.setBackgroundBlurRadius(if (show && native) Ui.dp(window.context, BLUR_RADIUS_DP) else 0)
    }

    /** Mostra conteúdo e fundo juntos, sem um quadro sólido antes de o blur terminar. */
    fun beginOpening() {
        clear()
        enabled = Ui.blurEnabled(window.context)
        updateNative(manager.isCrossWindowBlurEnabled)
        openingFallback = false
        opening = enabled && !native
        window.attributes = window.attributes.apply { alpha = if (opening) 0f else 1f }
        if (opening) main.postDelayed(openingTimeout, 1200)
    }

    private fun reveal() {
        main.removeCallbacks(openingTimeout)
        if (!opening) return
        opening = false
        window.attributes = window.attributes.apply { alpha = 1f }
    }

    /** Se a captura não vier, abre sólido e mantém esse fundo até a próxima abertura. */
    fun unavailable() {
        if (opening) openingFallback = true
        clearSource()
        reveal()
    }

    fun setDragging(value: Boolean) {
        dragging = value
        if (!value) pending?.let { pending = null; applySource(it.first, it.second) }
    }

    init {
        window.setBackgroundDrawable(drawable)
        updateNative(manager.isCrossWindowBlurEnabled)
        val listener = java.util.function.Consumer<Boolean> { updateNative(it) }
        window.decorView.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(view: View) = manager.addCrossWindowBlurEnabledListener(window.context.mainExecutor, listener)
            override fun onViewDetachedFromWindow(view: View) {
                manager.removeCrossWindowBlurEnabledListener(listener)
                clear()
            }
        })
    }

    /** `release` solta o buffer da API de acessibilidade mesmo se a janela fechar no meio do processamento. */
    fun source(bitmap: Bitmap, frame: Rect, release: () -> Unit = {}) {
        if (!enabled || openingFallback) { release(); return }
        val mine = generation.incrementAndGet()
        worker.execute {
            val result = try {
                val scale = minOf(1f, 720f / maxOf(bitmap.width, bitmap.height))
                // Canvas pode reduzir um bitmap HARDWARE em uma superfície de software só após copiar para ARGB.
                val software = if (bitmap.config == Bitmap.Config.HARDWARE) bitmap.copy(Bitmap.Config.ARGB_8888, false) else bitmap
                val small = Bitmap.createScaledBitmap(software, (bitmap.width * scale).roundToInt().coerceAtLeast(1),
                    (bitmap.height * scale).roundToInt().coerceAtLeast(1), true)
                val pixels = IntArray(small.width * small.height)
                small.getPixels(pixels, 0, small.width, 0, 0, small.width, small.height)
                val radius = (Ui.dp(window.context, BLUR_RADIUS_DP) * scale).roundToInt().coerceAtLeast(1)
                val rgb = GlassBlur.blurRgb(pixels, small.width, small.height, radius)
                val buffer = ByteBuffer.allocateDirect(pixels.size * 8).order(ByteOrder.nativeOrder())
                for (i in pixels.indices) {
                    for (channel in 0..2) buffer.putShort(Half.toHalf((rgb[i * 3 + channel] / 255f).coerceIn(0f, 1f)))
                    buffer.putShort(Half.toHalf(1f))
                }
                buffer.rewind()
                Bitmap.createBitmap(small.width, small.height, Bitmap.Config.RGBA_F16).apply { copyPixelsFromBuffer(buffer) }
                    .also {
                        if (small !== bitmap) small.recycle()
                        if (software !== bitmap && software !== small) software.recycle()
                    }
            } catch (_: Exception) {
                null
            } finally {
                release()
            }
            window.context.mainExecutor.execute {
                if (generation.get() != mine) { result?.recycle(); return@execute }
                if (dragging) {
                    pending?.first?.recycle()
                    pending = result to Rect(frame)
                } else applySource(result, frame)
            }
        }
    }

    private fun applySource(bitmap: Bitmap?, frame: Rect) {
        drawable.bitmap = bitmap
        drawable.frame = Rect(frame)
        drawable.shader = bitmap?.let { BitmapShader(it, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP) }
        drawable.invalidateSelf()
        if (bitmap == null && opening) openingFallback = true
        reveal()
    }

    fun clear() {
        main.removeCallbacks(openingTimeout)
        opening = false
        clearSource()
    }

    private fun clearSource() {
        generation.incrementAndGet()
        pending?.first?.recycle()
        pending = null
        drawable.bitmap = null
        drawable.shader = null
        drawable.invalidateSelf()
    }

    private inner class GlassDrawable : Drawable() {
        var bitmap: Bitmap? = null
        var frame = Rect()
        var shader: BitmapShader? = null
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG or Paint.DITHER_FLAG)
        private val matrix = Matrix()
        private val rect = RectF()
        private val radius = Ui.dp(window.context, 24).toFloat()

        override fun draw(canvas: Canvas) {
            rect.set(bounds)
            val image = bitmap
            val background = shader
            if (!native && image != null && background != null) {
                matrix.setScale(frame.width().toFloat() / image.width, frame.height().toFloat() / image.height)
                matrix.postTranslate((frame.left - window.attributes.x).toFloat(), (frame.top - window.attributes.y).toFloat())
                background.setLocalMatrix(matrix)
                paint.color = android.graphics.Color.WHITE
                paint.shader = background
                canvas.drawRoundRect(rect, radius, radius, paint)
            }
            paint.shader = null
            paint.style = Paint.Style.FILL
            // Só blur e escurecimento neutro para leitura, sem tonalização ou contorno de vidro.
            paint.color = when {
                !enabled -> 0xB3202024.toInt()
                native || image != null -> 0x40000000
                else -> 0xF0242428.toInt()
            }
            canvas.drawRoundRect(rect, radius, radius, paint)
        }

        override fun getOutline(outline: Outline) = outline.setRoundRect(bounds, radius)
        override fun setAlpha(alpha: Int) {}
        override fun setColorFilter(colorFilter: ColorFilter?) {}
        @Deprecated("Deprecated in Java") override fun getOpacity() = PixelFormat.TRANSLUCENT
    }

    companion object {
        private const val BLUR_RADIUS_DP = 12
        private val worker = Executors.newSingleThreadExecutor { task -> Thread(task, "lmphone-vidro").apply { isDaemon = true } }
    }
}
