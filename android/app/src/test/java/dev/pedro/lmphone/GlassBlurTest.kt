package dev.pedro.lmphone

import org.junit.Assert.*
import org.junit.Test

class GlassBlurTest {
    @Test fun darkGradientKeepsSubByteStepsUntilRendering() {
        val pixels = IntArray(81 * 3) { i -> val v = (i % 81) / 10; (255 shl 24) or (v shl 16) or (v shl 8) or v }
        val rgb = GlassBlur.blurRgb(pixels, 81, 3, 4)
        val row = (0 until 81).map { rgb[(81 + it) * 3] }
        assertTrue(row.zipWithNext().all { (a, b) -> a <= b })
        assertTrue(row.toSet().size > 30)
        assertTrue(row.any { it > 0 && it < 1 })
    }
    @Test fun uniformBackgroundKeepsItsColorAndDoesNotMutateSource() {
        val original = IntArray(35) { 0xFF4682A1.toInt() }
        assertArrayEquals(original, GlassBlur.blur(original, 5, 7, 8))
        assertTrue(original.all { it == 0xFF4682A1.toInt() })
    }

    @Test fun sharpEdgesActuallyBecomeBlurred() {
        val original = IntArray(21 * 3) { if (it % 21 < 10) 0xFF000000.toInt() else 0xFFFFFFFF.toInt() }
        val blurred = GlassBlur.blur(original, 21, 3, 3)
        val nearEdge = blurred[21 + 10] and 255
        assertTrue(nearEdge in 1..254)
        assertTrue((blurred[21] and 255) < (blurred[41] and 255))
        assertEquals(0xFFFFFFFF.toInt(), original[21 + 10])
    }
}
