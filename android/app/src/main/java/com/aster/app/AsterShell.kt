package com.aster.app

import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface

/**
 * 暴露给 Aster 网页的 JavaScript 桥，全局名必须是 `AsterShell`。
 *
 * `addJavascriptInterface` 必须在 WebView.loadUrl 之前调用。
 * 有返回值的同步方法只做轻量读取（SharedPreferences / 内存快照）；
 * 涉及 UI 和 Service 的调用统一 post 到主线程，避免桥线程直接操作界面。
 */
class AsterShell(private val activity: MainActivity) {

    private val ui = Handler(Looper.getMainLooper())

    @JavascriptInterface
    fun clientType(): String = "apk"

    @JavascriptInterface
    fun deviceName(): String = try {
        activity.currentDeviceName()
    } catch (_: Exception) {
        // 极少数机型读不到系统名/Preference 时也不能把所有手机都叫同一个名字。
        DeviceName.randomName()
    }

    @JavascriptInterface
    fun setDeviceName(name: String?): String = try {
        activity.saveDeviceName(name)
    } catch (_: Exception) {
        activity.currentDeviceName()
    }

    @JavascriptInterface
    fun appVersion(): String = try {
        activity.currentAppVersion()
    } catch (_: Exception) {
        ""
    }

    @JavascriptInterface
    fun takeSharedFiles(): String = try {
        activity.takeSharedFilesJson()
    } catch (_: Exception) {
        "{\"files\":[],\"texts\":[]}"
    }

    @JavascriptInterface
    fun ackSharedFiles(idsJson: String?) {
        val raw = idsJson?.trim().orEmpty()
        // WebView 的 Java 桥会把 JS 数组/对象强转成字符串 "undefined"。
        // 网页端代码对「传数组」做了 JSON.stringify 的 catch 回退，这里主动抛错触发回退。
        if (!raw.startsWith("[") && !raw.startsWith("{")) {
            throw IllegalArgumentException("ackSharedFiles expects a JSON array string")
        }
        try {
            activity.ackSharedFiles(raw)
        } catch (_: Exception) {
            // 桥调用不能把异步处理异常抛回网页
        }
    }

    @JavascriptInterface
    fun startTransfer(title: String?, total: Double) {
        ui.post { activity.onBridgeStartTransfer(title, total.toLong()) }
    }

    @JavascriptInterface
    fun updateTransfer(done: Double, total: Double, speed: Double, name: String?) {
        ui.post {
            activity.onBridgeUpdateTransfer(done.toLong(), total.toLong(), speed.toLong(), name)
        }
    }

    @JavascriptInterface
    fun finishTransfer(success: Boolean, message: String?) {
        ui.post { activity.onBridgeFinishTransfer(success, message) }
    }

    @JavascriptInterface
    fun openUrl(url: String?) {
        ui.post { activity.onBridgeOpenUrl(url) }
    }

    @JavascriptInterface
    fun checkUpdate() {
        ui.post { activity.onBridgeCheckUpdate() }
    }
}
