package com.aster.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AddressParserTest {

    private fun success(raw: String, https: Boolean = false): Endpoint {
        val result = AddressParser.parse(raw, https)
        assertTrue("expected success for $raw, got $result", result is AddressResult.Success)
        return (result as AddressResult.Success).endpoint
    }

    private fun error(raw: String, https: Boolean = false): String {
        val result = AddressParser.parse(raw, https)
        assertTrue("expected error for $raw, got $result", result is AddressResult.Error)
        return (result as AddressResult.Error).message
    }

    @Test
    fun plainIpUsesHttpDefaultPort() {
        val endpoint = success("192.168.1.5")
        assertEquals("http", endpoint.scheme)
        assertEquals("192.168.1.5", endpoint.host)
        assertEquals(47820, endpoint.port)
        assertEquals("http://192.168.1.5:47820/", endpoint.browseUrl())
    }

    @Test
    fun plainIpWithHttpsPreferenceUsesHttpsPort() {
        val endpoint = success("192.168.1.5", https = true)
        assertEquals("https", endpoint.scheme)
        assertEquals(47821, endpoint.port)
        assertEquals("https://192.168.1.5:47821/", endpoint.browseUrl())
    }

    @Test
    fun explicitPortWins() {
        val endpoint = success("192.168.1.5:9000")
        assertEquals(9000, endpoint.port)
        assertEquals("http", endpoint.scheme)
    }

    @Test
    fun urlWithPairCode() {
        val endpoint = success("http://192.168.1.5:47820/?pair=123456")
        assertEquals("123456", endpoint.pair)
        assertEquals("http://192.168.1.5:47820/?pair=123456", endpoint.browseUrl())
        assertEquals("192.168.1.5:47820", endpoint.display())
    }

    @Test
    fun pairCodeMustBeSixDigits() {
        val endpoint = success("http://192.168.1.5:47820/?pair=12ab56")
        assertNull(endpoint.pair)
        val noPair = success("http://192.168.1.5:47820/?x=1")
        assertNull(noPair.pair)
    }

    @Test
    fun hostnameAndIpv6() {
        val hostname = success("aster-pc:47820")
        assertEquals("aster-pc", hostname.host)
        assertEquals(47820, hostname.port)

        val ipv6 = success("[fe80::1]:47820")
        assertEquals("fe80::1", ipv6.host)
        assertEquals(47820, ipv6.port)
        assertEquals("[fe80::1]:47820", ipv6.display())
        assertEquals("http://[fe80::1]:47820/", ipv6.browseUrl())
    }

    @Test
    fun httpsUrlOverridesSwitch() {
        val endpoint = success("https://192.168.1.5", https = false)
        assertEquals("https", endpoint.scheme)
        assertEquals(47821, endpoint.port)
    }

    @Test
    fun whitespaceIsTrimmed() {
        val endpoint = success("  192.168.1.5  ")
        assertEquals("192.168.1.5", endpoint.host)
    }

    @Test
    fun invalidInputsReturnErrors() {
        error("")
        error("ftp://192.168.1.5")
        error("192.168.1.5:70000")
        error("http://")
        error("http://192.168.1.5:0")
    }

    @Test
    fun pathAndQueryAreIgnoredForBaseUrl() {
        val endpoint = success("http://192.168.1.5:47820/anything?x=1&pair=654321")
        assertEquals("654321", endpoint.pair)
        assertEquals("http://192.168.1.5:47820/", endpoint.copy(pair = null).browseUrl())
        assertEquals("http://192.168.1.5:47820/?pair=654321", endpoint.browseUrl())
    }
}
