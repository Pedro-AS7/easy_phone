package dev.pedro.lmphone

import kotlin.math.roundToInt

/** Três filtros de caixa aproximam um gaussiano. Só pixels reduzidos em memória; não grava nem transmite imagens. */
internal object GlassBlur {
    fun blur(pixels: IntArray, width: Int, height: Int, radius: Int): IntArray {
        val rgb = blurRgb(pixels, width, height, radius)
        return IntArray(pixels.size) { i ->
            (255 shl 24) or (rgb[i * 3].roundToInt().coerceIn(0, 255) shl 16) or
                (rgb[i * 3 + 1].roundToInt().coerceIn(0, 255) shl 8) or rgb[i * 3 + 2].roundToInt().coerceIn(0, 255)
        }
    }

    /** Mantém frações até o bitmap F16: arredondar após cada filtro cria contornos em fundos escuros. */
    fun blurRgb(pixels: IntArray, width: Int, height: Int, radius: Int): FloatArray {
        require(width > 0 && height > 0 && pixels.size == width * height && radius > 0)
        var source = FloatArray(pixels.size * 3) { i ->
            val shift = 16 - (i % 3) * 8
            ((pixels[i / 3] ushr shift) and 255).toFloat()
        }
        var target = FloatArray(source.size)
        val divisor = radius * 2 + 1
        repeat(3) {
            for (horizontal in listOf(true, false)) {
                val lines = if (horizontal) height else width
                val length = if (horizontal) width else height
                fun index(line: Int, at: Int) = if (horizontal) line * width + at else at * width + line
                for (line in 0 until lines) {
                    var red = 0.0; var green = 0.0; var blue = 0.0
                    fun add(at: Int, sign: Int) {
                        val i = index(line, at.coerceIn(0, length - 1)) * 3
                        red += source[i] * sign
                        green += source[i + 1] * sign
                        blue += source[i + 2] * sign
                    }
                    for (at in -radius..radius) add(at, 1)
                    for (at in 0 until length) {
                        val i = index(line, at) * 3
                        target[i] = (red / divisor).toFloat()
                        target[i + 1] = (green / divisor).toFloat()
                        target[i + 2] = (blue / divisor).toFloat()
                        add(at - radius, -1)
                        add(at + radius + 1, 1)
                    }
                }
                val swap = source; source = target; target = swap
            }
        }
        return source
    }
}
