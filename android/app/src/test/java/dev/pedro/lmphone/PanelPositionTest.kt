package dev.pedro.lmphone

import org.junit.Assert.assertEquals
import org.junit.Test

class PanelPositionTest {
    @Test fun dragCannotLoseTheHandleAtAnyEdge() {
        val position = PanelPosition()
        position.move(-200, -500, 12, 40, 388, 760, 300, 160)
        assertEquals(12 to 40, position.place(12, 40, 388, 760, 300, 160))
        position.move(1000, 2000, 12, 40, 388, 760, 300, 160)
        assertEquals(88 to 600, position.place(12, 40, 388, 760, 300, 160))
    }

    @Test fun keyboardAndLongerTextKeepThePanelInsideAndRestoreItsPosition() {
        val position = PanelPosition(.5f, 1f)
        assertEquals(50 to 600, position.place(0, 0, 400, 800, 300, 200))
        assertEquals(50 to 300, position.place(0, 0, 400, 500, 300, 200))
        assertEquals(50 to 180, position.place(0, 0, 400, 500, 300, 320))
        assertEquals(50 to 600, position.place(0, 0, 400, 800, 300, 200))
    }

    @Test fun rotationKeepsRelativePosition() {
        val position = PanelPosition()
        position.move(100, 250, 0, 0, 400, 800, 300, 300)
        assertEquals(500 to 50, position.place(0, 0, 800, 400, 300, 300))
    }

    @Test fun noRoomToMoveKeepsThePreviousPreference() {
        val position = PanelPosition(.75f, .25f)
        position.move(99, 99, 10, 20, 310, 120, 300, 200)
        assertEquals(10 to 20, position.place(10, 20, 310, 120, 300, 200))
        assertEquals(.75f, position.horizontal, 0f)
        assertEquals(.25f, position.vertical, 0f)
    }
}
