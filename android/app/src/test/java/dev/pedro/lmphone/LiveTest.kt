package dev.pedro.lmphone

import org.junit.After
import org.junit.Assert.*
import org.junit.Test

class LiveTest {
    @After fun reset() = Live.reset()

    @Test fun draggingBlocksActionsWithoutClearingTheWritingState() {
        Live.reset()
        Live.dragging = true
        assertNotNull(Live.blocked())
        Live.typing = true
        Live.dragging = false
        assertNotNull(Live.blocked())
        Live.typing = false
        assertNull(Live.blocked())
    }

    @Test fun resetReleasesAnInterruptedDrag() {
        Live.dragging = true
        Live.reset()
        assertNull(Live.blocked())
    }
}
