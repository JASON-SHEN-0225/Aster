package com.aster.app

import android.content.Context

/**
 * 连接页与证书信任状态。只保存电脑地址、协议和已确认过的证书，不写死任何 IP。
 */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("aster_shell", Context.MODE_PRIVATE)

    fun endpoint(): Endpoint? {
        val host = sp.getString(KEY_HOST, null)?.takeIf { it.isNotBlank() } ?: return null
        val port = sp.getInt(KEY_PORT, 0).takeIf { it in 1..65535 } ?: return null
        val https = sp.getBoolean(KEY_HTTPS, false)
        return Endpoint(if (https) "https" else "http", host, port, null)
    }

    fun saveEndpoint(endpoint: Endpoint) {
        sp.edit()
            .putString(KEY_HOST, endpoint.host)
            .putInt(KEY_PORT, endpoint.port)
            .putBoolean(KEY_HTTPS, endpoint.isHttps)
            .apply()
    }

    fun approvedCertificate(key: String): String? = sp.getString("cert:$key", null)

    fun approvedFingerprint(key: String): String? = sp.getString("fingerprint:$key", null)

    fun approveCertificate(key: String, derBase64: String, fingerprintSha256: String) {
        sp.edit()
            .putString("cert:$key", derBase64)
            .putString("fingerprint:$key", fingerprintSha256)
            .apply()
    }

    fun forgetCertificate(key: String) {
        sp.edit()
            .remove("cert:$key")
            .remove("fingerprint:$key")
            .apply()
    }

    // ---------------------------------------------------------------- 设备名

    fun customDeviceName(): String? = sp.getString(KEY_DEVICE_NAME, null)

    fun saveCustomDeviceName(name: String) {
        sp.edit().putString(KEY_DEVICE_NAME, name).apply()
    }

    fun clearCustomDeviceName() {
        sp.edit().remove(KEY_DEVICE_NAME).apply()
    }

    fun fallbackDeviceName(): String? = sp.getString(KEY_DEVICE_FALLBACK, null)

    fun saveFallbackDeviceName(name: String) {
        sp.edit().putString(KEY_DEVICE_FALLBACK, name).apply()
    }

    companion object {
        private const val KEY_HOST = "last_host"
        private const val KEY_PORT = "last_port"
        private const val KEY_HTTPS = "last_https"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_DEVICE_FALLBACK = "device_name_fallback"
    }
}
