package dev.pedro.lmphone

import org.junit.Assert.assertEquals
import org.junit.Test

class PanelGestureTest {
    @Test fun sidewaysInEitherDirectionMinimizes() {
        assertEquals(PanelGesture.Action.MINIMIZE, PanelGesture.action(90f, 10f, -100f))
        assertEquals(PanelGesture.Action.MINIMIZE, PanelGesture.action(-90f, -10f, -100f))
    }

    @Test fun downwardOnlyClosesAfterPullingPastTheBottom() {
        assertEquals(PanelGesture.Action.NONE, PanelGesture.action(0f, 200f, -5f))
        assertEquals(PanelGesture.Action.NONE, PanelGesture.action(0f, 200f, 55f))
        assertEquals(PanelGesture.Action.CLOSE, PanelGesture.action(0f, 200f, 56f))
    }

    @Test fun smallOrDiagonalMovementDoesNotDismiss() {
        assertEquals(PanelGesture.Action.NONE, PanelGesture.action(30f, 2f, 0f))
        assertEquals(PanelGesture.Action.NONE, PanelGesture.action(100f, 100f, 80f))
    }

    @Test fun upwardMovementNeverClosesAtTheBottom() {
        assertEquals(PanelGesture.Action.NONE, PanelGesture.action(0f, -100f, 60f))
    }
}
