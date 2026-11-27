package com.aster.app

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.concurrent.Executors
import android.os.Handler
import android.os.Looper

/**
 * 检查更新：官网 version.json 优先，失败回退 GitHub Releases。
 *
 * 只负责网络读取和版本比较，不自动安装；由 MainActivity 决定弹窗/静默。
 * version.json 的 android 段缺字段时回退到顶层 version / 下载页。
 */
object UpdateChecker {

    const val UPDATE_URL = "https://asterdrop.cn/version.json"
    const val GITHUB_API = "https://api.github.com/repos/JASON-SHEN-0225/Aster/releases/latest"
    const val DOWNLOAD_PAGE = "https://asterdrop.cn/download.html"

    private const val TAG = "AsterUpdate"
    private const val USER_AGENT = "Aster-Android"
    private const val TIMEOUT_MS = 6_000
    private const val MAX_BYTES = 1024 * 1024
    private const val MAX_NOTES = 4_000

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "aster-update").also { it.isDaemon = true }
    }
    private val main = Handler(Looper.getMainLooper())

    fun check(currentVersion: String, callback: (UpdateCheckResult) -> Unit) {
        executor.execute {
            val result = try {
                runCheck(currentVersion)
            } catch (error: Exception) {
                Log.w(TAG, "check update failed", error)
                UpdateCheckResult.Failed(error.message ?: "检查更新失败")
            }
            main.post { callback(result) }
        }
    }

    private fun runCheck(currentVersion: String): UpdateCheckResult {
        val website = fetchJson(UPDATE_URL)
        if (website != null) {
            val info = parseWebsite(website)
            if (info != null) return evaluate(currentVersion, info)
        }
        val github = fetchJson(GITHUB_API)
        if (github != null) {
            val info = parseGithub(github)
            if (info != null) return evaluate(currentVersion, info)
        }
        return UpdateCheckResult.Failed("无法连接更新服务器")
    }

    private fun evaluate(currentVersion: String, info: UpdateInfo): UpdateCheckResult =
        if (AppVersion.isNewer(info.version, currentVersion)) {
            UpdateCheckResult.Available(info)
        } else {
            UpdateCheckResult.UpToDate
        }

    private fun parseWebsite(data: JSONObject): UpdateInfo? {
        val android = data.optJSONObject("android")
        var version = android?.optString("version").orEmpty().trim()
        if (version.isEmpty()) version = data.optString("version").trim()
        version = version.removePrefix("v").removePrefix("V").trim()
        if (version.isEmpty()) return null

        var notes = data.optString("notes").trim()
        if (notes.isEmpty()) notes = android?.optString("notes").orEmpty().trim()
        var downloadUrl = android?.optString("url").orEmpty().trim()
        if (downloadUrl.isEmpty()) downloadUrl = data.optString("android_url").trim()
        var pageUrl = data.optString("download_page").trim()
        if (pageUrl.isEmpty()) pageUrl = data.optString("page").trim()
        if (pageUrl.isEmpty()) pageUrl = DOWNLOAD_PAGE
        return UpdateInfo(
            version = version,
            notes = notes.take(MAX_NOTES),
            downloadUrl = downloadUrl,
            pageUrl = pageUrl,
            released = data.optString("released").trim(),
            source = "website",
        )
    }

    private fun parseGithub(data: JSONObject): UpdateInfo? {
        var version = data.optString("tag_name").trim()
        if (version.isEmpty()) version = data.optString("name").trim()
        version = version.removePrefix("v").removePrefix("V").trim()
        if (version.isEmpty()) return null

        var apkUrl = ""
        val assets = data.optJSONArray("assets")
        if (assets != null) {
            for (index in 0 until assets.length()) {
                val asset = assets.optJSONObject(index) ?: continue
                val name = asset.optString("name").lowercase(Locale.ROOT)
                val url = asset.optString("browser_download_url").trim()
                if (url.isEmpty()) continue
                if (name.endsWith(".apk")) {
                    apkUrl = url
                    break
                }
            }
        }
        var pageUrl = data.optString("html_url").trim()
        if (pageUrl.isEmpty()) pageUrl = DOWNLOAD_PAGE
        return UpdateInfo(
            version = version,
            notes = data.optString("body").trim().take(MAX_NOTES),
            downloadUrl = apkUrl,
            pageUrl = pageUrl,
            released = data.optString("published_at").trim().take(10),
            source = "github",
        )
    }

    private fun fetchJson(url: String): JSONObject? {
        var connection: HttpURLConnection? = null
        return try {
            connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = TIMEOUT_MS
            connection.readTimeout = TIMEOUT_MS
            connection.instanceFollowRedirects = true
            connection.requestMethod = "GET"
            connection.setRequestProperty("User-Agent", USER_AGENT)
            connection.setRequestProperty(
                "Accept",
                if (url == GITHUB_API) "application/vnd.github+json" else "application/json, text/plain, */*",
            )
            val code = connection.responseCode
            if (code !in 200..299) return null
            val bytes = connection.inputStream.use { readLimited(it, MAX_BYTES) }
            if (bytes.isEmpty()) return null
            JSONObject(String(bytes, StandardCharsets.UTF_8))
        } catch (error: Exception) {
            Log.w(TAG, "fetch update url failed", error)
            null
        } finally {
            try {
                connection?.disconnect()
            } catch (_: Exception) {
                // ignore
            }
        }
    }

    private fun readLimited(input: InputStream, limit: Int): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(16 * 1024)
        var total = 0
        while (total < limit) {
            val read = input.read(buffer)
            if (read < 0) break
            val allowed = minOf(read, limit - total)
            output.write(buffer, 0, allowed)
            total += allowed
        }
        return output.toByteArray()
    }
}

data class UpdateInfo(
    val version: String,
    val notes: String,
    val downloadUrl: String,
    val pageUrl: String,
    val released: String,
    val source: String,
)

sealed interface UpdateCheckResult {
    data class Available(val info: UpdateInfo) : UpdateCheckResult
    data object UpToDate : UpdateCheckResult
    data class Failed(val message: String) : UpdateCheckResult
}

/**
 * 版本号比较：只比较数字段，忽略前缀 v/V 和 -beta 之类的后缀。
 * 纯函数，供 JVM 单元测试覆盖。
 */
object AppVersion {

    private val versionPattern = Regex("^\\s*[vV]?(\\d+(?:\\.\\d+)*)")

    fun parse(value: String?): List<Int> {
        val matched = versionPattern.find(value ?: "") ?: return emptyList()
        return matched.groupValues[1].split('.').mapNotNull { it.toIntOrNull() }
    }

    fun isNewer(latest: String?, current: String?): Boolean {
        val left = parse(latest)
        val right = parse(current)
        if (left.isEmpty() || right.isEmpty()) return false
        val width = maxOf(left.size, right.size)
        for (index in 0 until width) {
            val a = left.getOrElse(index) { 0 }
            val b = right.getOrElse(index) { 0 }
            if (a != b) return a > b
        }
        return false
    }
}
