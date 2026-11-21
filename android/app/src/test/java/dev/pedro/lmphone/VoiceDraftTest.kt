package dev.pedro.lmphone

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceDraftTest {
    @Test fun correctingTextThenDictatingPreservesTheCorrection() {
        val draft = VoiceDraft()
        draft.begin("Texto corrigido  ")
        assertEquals("Texto corrigido mais", draft.join("mais"))
        assertEquals("Texto corrigido mais palavras", draft.join("mais palavras"))
    }

    @Test fun aFreshRequestDoesNotReuseThePreviousDraft() {
        val draft = VoiceDraft()
        draft.begin("Pedido anterior")
        draft.begin("")
        assertEquals("Novo pedido", draft.join("Novo pedido"))
    }
}
