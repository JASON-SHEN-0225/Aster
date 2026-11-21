package com.aster.app

import java.net.URI
import java.net.URISyntaxException
import java.net.URLDecoder
import java.util.Locale

/**
 * 一台电脑的访问目标。scheme 只能是 http/https，host 不含方括号（IPv6 展示时补上）。
 */
data class Endpoint(
    val scheme: String,
    val host: String,
    val port: Int,
    val pair: String? = null,
) {
    val isHttps: Boolean
        get() = scheme.equals("https", ignoreCase = true)

    fun origin(): String = "$scheme://${displayHost()}:$port"

    fun browseUrl(): String =
        if (pair.isNullOrEmpty()) {
            "${origin()}/"
        } else {
            "${origin()}/?pair=$pair"
        }

    /** 192.168.1.5:47820 / [fe80::1]:47820 */
    fun displayHost(): String = if (host.contains(':')) "[$host]" else host

    fun display(): String = "${displayHost()}:$port"

    companion object {
        fun normalizedHost(raw: String): String {
            var host = raw.trim()
            if (host.startsWith("[")) host = host.removePrefix("[")
            if (host.endsWith("]")) host = host.removeSuffix("]")
            return host.lowercase(Locale.ROOT)
        }
    }
}

sealed interface AddressResult {
    data class Success(val endpoint: Endpoint) : AddressResult
    data class Error(val message: String) : AddressResult
}

/**
 * 解析手动输入或扫码得到的电脑地址。
 *
 * 支持：
 *  - 192.168.1.5
 *  - 192.168.1.5:47820
 *  - http://192.168.1.5:47820/?pair=123456
 *  - https://[fe80::1]:47821/
 *  - aster-pc:47820
 */
object AddressParser {
    const val DEFAULT_HTTP_PORT = 47820
    const val DEFAULT_HTTPS_PORT = 47821

    private val invalidHostChars = Regex("[\\s/\\\\?#@]")
    private val ipv6Chars = Regex("^[0-9a-fA-F:.%]+$")
    private val hostChars = Regex("^[A-Za-z0-9._-]+$")

    fun parse(rawInput: String, preferHttps: Boolean = false): AddressResult {
        val raw = rawInput.trim()
        if (raw.isEmpty()) return AddressResult.Error("请输入电脑地址")

        val withScheme = if (raw.contains("://")) raw else {
            val scheme = if (preferHttps) "https" else "http"
            "$scheme://$raw"
        }

        val uri: URI = try {
            URI(withScheme)
        } catch (_: URISyntaxException) {
            return AddressResult.Error("地址格式不正确")
        }

        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return AddressResult.Error("地址格式不正确")
        if (scheme != "http" && scheme != "https") {
            return AddressResult.Error("仅支持 http 或 https")
        }

        var host = uri.host
        var port = uri.port
        if (host.isNullOrBlank()) {
            val fallback = parseAuthority(uri.rawAuthority)
                ?: return AddressResult.Error("无法识别 IP 或主机名")
            host = fallback.first
            if (port == -1) port = fallback.second
        }

        host = Endpoint.normalizedHost(host)
        if (host.isEmpty() || invalidHostChars.containsMatchIn(host)) {
            return AddressResult.Error("无法识别 IP 或主机名")
        }
        val looksLikeIpv6 = host.contains(':')
        if (looksLikeIpv6) {
            if (!ipv6Chars.matches(host)) return AddressResult.Error("无法识别 IP 或主机名")
        } else if (!hostChars.matches(host) || !host.any { it.isLetterOrDigit() }) {
            return AddressResult.Error("无法识别 IP 或主机名")
        }

        if (port == -1) {
            port = if (scheme == "https") DEFAULT_HTTPS_PORT else DEFAULT_HTTP_PORT
        }
        if (port !in 1..65535) return AddressResult.Error("端口应在 1-65535")

        val pair = extractPair(uri.rawQuery)
        return AddressResult.Success(Endpoint(scheme, host, port, pair))
    }

    /** URI.host 在主机名含下划线等情况下会是 null，这里做一次保守回退解析。 */
    private fun parseAuthority(authority: String?): Pair<String, Int>? {
        if (authority.isNullOrBlank()) return null
        var value = authority
        val at = value.lastIndexOf('@')
        if (at >= 0) value = value.substring(at + 1)
        if (value.startsWith("[")) {
            val end = value.indexOf(']')
            if (end <= 1) return null
            val host = value.substring(1, end)
            val rest = value.substring(end + 1)
            val port = if (rest.startsWith(":")) rest.substring(1).toIntOrNull() ?: -1 else -1
            return host to port
        }
        val firstColon = value.indexOf(':')
        val lastColon = value.lastIndexOf(':')
        if (lastColon > 0 && firstColon == lastColon) {
            val maybePort = value.substring(lastColon + 1)
            if (maybePort.isNotEmpty() && maybePort.all { it.isDigit() }) {
                return value.substring(0, lastColon) to (maybePort.toIntOrNull() ?: -1)
            }
        }
        return value to -1
    }

    private fun extractPair(rawQuery: String?): String? {
        if (rawQuery.isNullOrEmpty()) return null
        for (part in rawQuery.split('&')) {
            val index = part.indexOf('=')
            if (index <= 0) continue
            val key = part.substring(0, index)
            if (!key.equals("pair", ignoreCase = true)) continue
            val value = try {
                URLDecoder.decode(part.substring(index + 1), "UTF-8")
            } catch (_: Exception) {
                part.substring(index + 1)
            }
            if (value.length == 6 && value.all { it.isDigit() }) return value
        }
        return null
    }
}
