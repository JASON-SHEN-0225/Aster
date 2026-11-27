package com.aster.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ShareNamesTest {

    @Test
    fun stripsPathsAndInvalidCharacters() {
        assertEquals("b_c.txt", ShareNames.sanitize("a/b:c.txt"))
        assertEquals("a_b.txt", ShareNames.sanitize("..\\a?b.txt"))
        assertEquals("shared-file", ShareNames.sanitize("   ", "shared-file"))
        assertEquals(ShareNames.DEFAULT_NAME, ShareNames.sanitize("...."))
        assertEquals(ShareNames.DEFAULT_NAME, ShareNames.sanitize("dir/"))
    }

    @Test
    fun keepsUnicodeNames() {
        assertEquals("星流 v3.0.0.png", ShareNames.sanitize("星流 v3.0.0.png"))
    }

    @Test
    fun removesBomAndReplacesControlCharacters() {
        assertEquals("报告_.pdf", ShareNames.sanitize("\uFEFF报告\u0000.pdf"))
        assertEquals("a_b.pdf", ShareNames.sanitize("a\nb.pdf"))
    }

    @Test
    fun longNamesKeepExtension() {
        val sanitized = ShareNames.sanitize("a".repeat(400) + ".zip")
        assertEquals(160, sanitized.length)
        assertTrue(sanitized.endsWith(".zip"))
    }
}
