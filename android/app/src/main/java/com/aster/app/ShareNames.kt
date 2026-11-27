package com.aster.app

/**
 * 系统共享进来文件的文件名清洗。
 *
 * 共享文件会落到应用私有目录 `filesDir/shared/<entryId>/<name>`，因此必须去掉路径分隔符、
 * 控制字符和文件系统保留字符，避免目录穿越或非法文件名。纯字符串逻辑，可在 JVM 单测验证。
 */
object ShareNames {

    const val DEFAULT_NAME = "共享文件"

    private const val MAX_NAME = 160
    private val invalidChars = Regex("[\\\\/:*?\"<>|\\u0000-\\u001F\\u007F]")
    private val whitespace = Regex("\\s+")

    fun sanitize(raw: String?, fallback: String = DEFAULT_NAME): String {
        if (raw == null) return fallback
        var name = raw.trim().removePrefix("\uFEFF")
        name = name.substringAfterLast('/').substringAfterLast('\\')
        name = invalidChars.replace(name, "_")
        name = whitespace.replace(name, " ").trim()
        name = name.trim('.', ' ')
        if (name.isEmpty() || name == "." || name == "..") return fallback
        if (name.length > MAX_NAME) {
            val dot = name.lastIndexOf('.')
            val extension = if (dot > 0 && name.length - dot <= 16) name.substring(dot) else ""
            val base = if (extension.isEmpty()) name else name.dropLast(extension.length)
            val keep = (MAX_NAME - extension.length).coerceAtLeast(1)
            name = base.take(keep).trimEnd() + extension
        }
        return name.ifEmpty { fallback }
    }
}
