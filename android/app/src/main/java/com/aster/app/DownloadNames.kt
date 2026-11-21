package com.aster.app

import android.content.ContentResolver
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.net.URLDecoder

/**
 * 下载文件名解析、清洗与去重。纯字符串逻辑的部分可以在 JVM 单元测试里直接验证。
 */
object DownloadNames {

    private val invalidChars = Regex("[\\\\/:*?\"<>|\\u0000-\\u001F\\u007F]")
    private val whitespace = Regex("\\s+")
    private val starPattern = Regex("(?i)filename\\*\\s*=\\s*(?:\"([^\"]*)\"|([^;]+))")
    private val plainPattern = Regex("(?i)filename\\s*=\\s*(?:\"([^\"]*)\"|([^;]+))")

    fun fromDisposition(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val star = starPattern.find(header)?.let { match ->
            match.groupValues[1].ifEmpty { match.groupValues[2] }
        }?.trim()?.trim('"')
        if (!star.isNullOrBlank()) {
            val parts = star.split('\'', limit = 3)
            val encoded = if (parts.size == 3) parts[2] else star
            val charset = if (parts.size == 3 && parts[0].isNotBlank()) parts[0] else "UTF-8"
            val decoded = try {
                URLDecoder.decode(encoded.replace("+", "%2B"), charset)
            } catch (_: Exception) {
                encoded
            }
            if (decoded.isNotBlank()) return decoded
        }
        val plain = plainPattern.find(header)?.let { match ->
            match.groupValues[1].ifEmpty { match.groupValues[2] }
        }?.trim()?.trim('"')
        if (!plain.isNullOrBlank()) {
            return plain.replace("\\\"", "\"").replace("\\\\", "\\")
        }
        return null
    }

    fun sanitize(raw: String): String {
        var name = raw.trim().substringAfterLast('/').substringAfterLast('\\')
        name = invalidChars.replace(name, "_")
        name = whitespace.replace(name, " ").trim()
        name = name.trim('.', ' ')
        if (name.isEmpty() || name == "." || name == "..") return "Aster-download"
        if (name.length > MAX_NAME) {
            val dot = name.lastIndexOf('.')
            val extension = if (dot > 0 && name.length - dot <= 16) name.substring(dot) else ""
            val base = if (extension.isNotEmpty()) name.dropLast(extension.length) else name
            val keep = (MAX_NAME - extension.length).coerceAtLeast(1)
            name = base.take(keep).trimEnd() + extension
        }
        return name.ifEmpty { "Aster-download" }
    }

    fun withSuffix(name: String, index: Int): String {
        if (index <= 0) return name
        val dot = name.lastIndexOf('.')
        val hasExtension = dot > 0 && name.length - dot <= 16
        return if (hasExtension) {
            name.substring(0, dot) + " ($index)" + name.substring(dot)
        } else {
            "$name ($index)"
        }
    }

    fun downloadsDir(): File =
        File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Aster")

    fun ensureDownloadsDir(): File {
        val dir = downloadsDir()
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    fun uniqueFile(dir: File, desired: String): File {
        val base = sanitize(desired)
        for (index in 0 until MAX_COLLISIONS) {
            val candidate = File(dir, withSuffix(base, index))
            if (!candidate.exists()) return candidate
        }
        return File(dir, withSuffix(base, (System.currentTimeMillis() / 1000).toInt()))
    }

    fun uniqueName(context: Context, desired: String): String {
        val base = sanitize(desired)
        if (Build.VERSION.SDK_INT < 29) {
            val dir = downloadsDir()
            for (index in 0 until MAX_COLLISIONS) {
                val candidate = withSuffix(base, index)
                if (!File(dir, candidate).exists()) return candidate
            }
            return withSuffix(base, (System.currentTimeMillis() / 1000).toInt())
        }
        val resolver = context.contentResolver
        for (index in 0 until MAX_COLLISIONS) {
            val candidate = withSuffix(base, index)
            if (!existsInMediaStore(resolver, candidate)) return candidate
        }
        return withSuffix(base, (System.currentTimeMillis() / 1000).toInt())
    }

    fun newMediaStoreEntry(
        resolver: ContentResolver,
        displayName: String,
        mime: String,
    ): Uri? {
        if (Build.VERSION.SDK_INT < 29) return null
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, displayName)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/Aster",
            )
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        return try {
            resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
        } catch (_: Exception) {
            null
        }
    }

    private fun existsInMediaStore(resolver: ContentResolver, displayName: String): Boolean {
        if (Build.VERSION.SDK_INT < 29) return false
        return try {
            resolver.query(
                MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                arrayOf(MediaStore.MediaColumns._ID),
                "${MediaStore.MediaColumns.DISPLAY_NAME}=? AND ${MediaStore.MediaColumns.RELATIVE_PATH} LIKE ?",
                arrayOf(displayName, Environment.DIRECTORY_DOWNLOADS + "/Aster/%"),
                null,
            )?.use { it.moveToFirst() } ?: false
        } catch (_: Exception) {
            false
        }
    }

    private const val MAX_NAME = 180
    private const val MAX_COLLISIONS = 100
}
