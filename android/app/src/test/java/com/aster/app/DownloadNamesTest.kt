package com.aster.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DownloadNamesTest {

    @Test
    fun readsUtf8ExtendedDisposition() {
        val header = "attachment; filename=\"download\"; filename*=UTF-8''%E6%98%9F%E6%B5%81%20a.txt"
        assertEquals("星流 a.txt", DownloadNames.fromDisposition(header))
    }

    @Test
    fun readsQuotedDisposition() {
        val header = "attachment; filename=\"hello world.txt\""
        assertEquals("hello world.txt", DownloadNames.fromDisposition(header))
    }

    @Test
    fun readsUnquotedDisposition() {
        assertEquals("a.bin", DownloadNames.fromDisposition("attachment; filename=a.bin"))
    }

    @Test
    fun invalidDispositionReturnsNull() {
        assertNull(DownloadNames.fromDisposition(null))
        assertNull(DownloadNames.fromDisposition("attachment"))
        assertNull(DownloadNames.fromDisposition(""))
    }

    @Test
    fun sanitizesPathsAndInvalidCharacters() {
        assertEquals("b_c.txt", DownloadNames.sanitize("a/b:c.txt"))
        assertEquals("a_b.txt", DownloadNames.sanitize("..\\a?b.txt"))
        assertEquals("Aster-download", DownloadNames.sanitize("   "))
        assertEquals("Aster-download", DownloadNames.sanitize("...."))
        assertEquals("Aster-download", DownloadNames.sanitize("dir/"))
    }

    @Test
    fun keepsUnicodeNames() {
        assertEquals("星流 v2.0.0.png", DownloadNames.sanitize("星流 v2.0.0.png"))
    }

    @Test
    fun addsCollisionSuffixBeforeExtension() {
        assertEquals("a.txt", DownloadNames.withSuffix("a.txt", 0))
        assertEquals("a (1).txt", DownloadNames.withSuffix("a.txt", 1))
        assertEquals("README (2)", DownloadNames.withSuffix("README", 2))
    }

    @Test
    fun longNamesKeepExtension() {
        val longName = "a".repeat(400) + ".zip"
        val sanitized = DownloadNames.sanitize(longName)
        assertEquals(180, sanitized.length)
        assertTrue(sanitized.endsWith(".zip"))
    }
}
