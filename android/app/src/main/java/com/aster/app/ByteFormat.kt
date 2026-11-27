package com.aster.app

import java.util.Locale

/**
 * 传输/下载通知里的字节与速度格式化。纯函数，JVM 单元测试可直接调用。
 */
object ByteFormat {

    private val units = arrayOf("B", "KB", "MB", "GB", "TB")

    fun bytes(value: Long): String {
        var size = value.coerceAtLeast(0L).toDouble()
        if (size < 1024.0) return "${size.toLong()} B"
        var index = 0
        while (size >= 1024.0 && index < units.lastIndex) {
            size /= 1024.0
            index += 1
        }
        val text = when {
            size >= 100.0 -> String.format(Locale.US, "%.0f", size)
            size >= 10.0 -> String.format(Locale.US, "%.1f", size)
            else -> String.format(Locale.US, "%.2f", size)
        }
        return "$text ${units[index]}"
    }

    fun speed(bytesPerSecond: Long): String = "${bytes(bytesPerSecond)}/s"
}
