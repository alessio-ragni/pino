package dev.pino.app

import dev.pino.app.Wake.Verdict
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WakeTest {
    private fun partial(text: String) = Wake.verdict("""{"partial":"$text"}""")

    private fun final(vararg words: Pair<String, Double>) = Wake.verdict(
        words.joinToString(",", """{"result":[""", "]}") { (w, c) -> """{"word":"$w","conf":$c}""" },
    )

    @Test
    fun grammarIsClosed() {
        val g = Wake.grammar()
        assertTrue(g.contains("\"pino\""))
        assertTrue(g.contains("\"ciao\""))
        assertTrue(g.contains("\"[unk]\""))
        assertTrue(g.startsWith("[") && g.endsWith("]"))
    }

    @Test
    fun nameFollowedBySomethingWakes() {
        assertEquals(Verdict.YES, partial("pino ciao"))
        assertEquals(Verdict.YES, partial("ciao pino hey"))
        assertEquals(Verdict.YES, partial("ehi pino pino"))
    }

    @Test
    fun greetingsInFrontAreAllowed() {
        assertEquals(Verdict.YES, final("hey" to 0.9, "pino" to 0.9))
        assertEquals(Verdict.YES, final("hi" to 0.5, "pino" to 0.8))
        assertEquals(Verdict.YES, final("ciao" to 1.0, "pino" to 0.7))
        assertEquals(Verdict.YES, final("pino" to 0.52))
    }

    @Test
    fun nameAloneIsMaybeUntilFinal() {
        assertEquals(Verdict.MAYBE, partial("pino"))
        assertEquals(Verdict.MAYBE, partial("ehi pino"))
        assertEquals(Verdict.YES, final("pino" to 0.9))
    }

    @Test
    fun nameNotFirstOrWeakDoesNot() {
        assertEquals(Verdict.NO, partial("vino pino hey"))
        assertEquals(Verdict.NO, partial("pinoli pino"))
        assertEquals(Verdict.NO, partial("[unk] pino"))
        assertEquals(Verdict.NO, partial(""))
        assertEquals(Verdict.NO, final("pino" to 0.3))
    }

    @Test
    fun decoyRightAfterTheNameDoesNot() {
        assertEquals(Verdict.NO, partial("pino pinoli"))
        assertEquals(Verdict.NO, partial("hi pino vino hei"))
        assertEquals(Verdict.NO, final("pino" to 0.99, "pinocchio" to 0.9))
    }

    @Test
    fun rmsOfSilenceIsZero() {
        assertTrue(Ears.rms(ByteArray(3200)) == 0.0)
    }
}
