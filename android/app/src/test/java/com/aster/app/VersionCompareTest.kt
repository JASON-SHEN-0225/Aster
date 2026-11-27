package com.aster.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VersionCompareTest {

    @Test
    fun comparesNumericSegments() {
        assertTrue(AppVersion.isNewer("3.0.0", "2.9.9"))
        assertFalse(AppVersion.isNewer("2.0.0", "3.0.0"))
        assertFalse(AppVersion.isNewer("3.0.0", "3.0.0"))
    }

    @Test
    fun missingSegmentsCountAsZero() {
        assertFalse(AppVersion.isNewer("3.0", "3.0.0"))
        assertTrue(AppVersion.isNewer("3.0.1", "3.0"))
    }

    @Test
    fun ignoresPrefixAndSuffix() {
        assertTrue(AppVersion.isNewer("v3.0.0", "2.0.0"))
        assertTrue(AppVersion.isNewer("V3.0.0", " 2.0.0 "))
        assertFalse(AppVersion.isNewer("3.0.0-beta", "3.0.0"))
    }

    @Test
    fun invalidVersionsAreNeverNewer() {
        assertFalse(AppVersion.isNewer("", "3.0.0"))
        assertFalse(AppVersion.isNewer("latest", "3.0.0"))
        assertFalse(AppVersion.isNewer("3.0.0", ""))
        assertFalse(AppVersion.isNewer(null, "3.0.0"))
    }

    @Test
    fun comparesMultiDigitSegmentsNumerically() {
        assertTrue(AppVersion.isNewer("3.10.0", "3.9.9"))
        assertFalse(AppVersion.isNewer("3.9.9", "3.10.0"))
    }
}
