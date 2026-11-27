package com.aster.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class DeviceNameTest {

    @Test
    fun removesControlCharsAndCollapsesWhitespace() {
        assertEquals("Pixel 8 Pro", DeviceName.sanitize("  Pixel\u0000\t 8   Pro \n"))
    }

    @Test
    fun blankBecomesNull() {
        assertNull(DeviceName.sanitize(null))
        assertNull(DeviceName.sanitize(""))
        assertNull(DeviceName.sanitize(" \t\n "))
    }

    @Test
    fun limitsLength() {
        val clean = DeviceName.sanitize("a".repeat(100))
        assertEquals(32, clean?.length)
    }

    @Test
    fun randomFallbackUsesPhonePrefixAndFourDigits() {
        val name = DeviceName.randomName(Random(7))
        assertTrue(Regex("^手机-\\d{4}$").matches(name))
    }

    @Test
    fun systemNamePrefersGlobalDeviceName() {
        assertEquals("厨房手机", DeviceName.systemName("厨房手机", "Xiaomi", "M2101K9C"))
    }

    @Test
    fun systemNameFallsBackToManufacturerAndModel() {
        assertEquals("Google Pixel 8", DeviceName.systemName("", "Google", "Pixel 8"))
        assertEquals("Pixel 8", DeviceName.systemName(null, null, "Pixel 8"))
        assertEquals("Google", DeviceName.systemName(null, "Google", "  "))
        assertNull(DeviceName.systemName(null, "", ""))
    }
}
