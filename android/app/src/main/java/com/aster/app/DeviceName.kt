package com.aster.app

import android.content.Context
import android.os.Build
import android.provider.Settings
import kotlin.random.Random

/**
 * 手机端设备名。
 *
 * 优先级：用户自定义名 > 系统设备名（Settings.Global.DEVICE_NAME）
 * > 厂商 + 型号 > 持久化的随机名 `手机-XXXX`。
 *
 * sanitize / systemName / randomName 是纯函数，供 JVM 单元测试覆盖。
 */
object DeviceName {

    private const val MAX_LENGTH = 32
    private const val PREFIX = "手机-"
    private val GENERIC_NAMES = setOf(
        "android",
        "android device",
        "unknown",
        "unknown device",
        "手机",
        "我的手机",
        "我的 android 手机",
    )
    private val controlChars = Regex("[\\u0000-\\u001F\\u007F]")
    private val whitespace = Regex("\\s+")

    fun sanitize(raw: String?): String? {
        if (raw == null) return null
        var name = controlChars.replace(raw, "")
        name = whitespace.replace(name, " ").trim()
        if (name.isEmpty()) return null
        if (name.length > MAX_LENGTH) name = name.take(MAX_LENGTH).trimEnd()
        return name.ifEmpty { null }
    }

    /** 系统名优先；读不到时用「厂商 型号」拼一个。 */
    fun systemName(globalName: String?, manufacturer: String?, model: String?): String? {
        // 部分 ROM 把系统名固定成 Android / unknown，这种名字对用户没有区分度，继续看型号。
        val generic = sanitize(globalName)?.takeIf { it.lowercase() !in GENERIC_NAMES }
        if (generic != null) return generic
        val brand = sanitize(manufacturer)
        val device = sanitize(model)
        return when {
            brand != null && device != null -> sanitize("$brand $device")
            device != null -> device
            brand != null -> brand
            else -> null
        }
    }

    fun randomName(random: Random = Random.Default): String {
        val suffix = buildString {
            repeat(4) { append(random.nextInt(0, 10)) }
        }
        return PREFIX + suffix
    }

    /** 当前最终设备名；随机名只在首次生成时持久化一次。 */
    fun current(context: Context, prefs: Prefs): String {
        sanitize(prefs.customDeviceName())?.let { return it }
        val global = try {
            Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME)
        } catch (_: Exception) {
            null
        }
        systemName(global, Build.MANUFACTURER, Build.MODEL)?.let { return it }
        sanitize(prefs.fallbackDeviceName())?.let { return it }
        val generated = randomName()
        prefs.saveFallbackDeviceName(generated)
        return generated
    }

    /** 网页里改名：空白表示恢复系统名。返回保存后的最终名字。 */
    fun saveCustom(context: Context, prefs: Prefs, raw: String?): String {
        val clean = sanitize(raw)
        if (clean == null) {
            prefs.clearCustomDeviceName()
        } else {
            prefs.saveCustomDeviceName(clean)
        }
        return current(context, prefs)
    }
}
