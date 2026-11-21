package com.aster.app

import android.net.http.SslCertificate
import java.security.MessageDigest

/** 自签名证书展示与指纹工具。 */
object CertUtil {

    private const val X509_KEY = "x509-certificate"

    fun derBytes(certificate: SslCertificate?): ByteArray? {
        if (certificate == null) return null
        return try {
            SslCertificate.saveState(certificate).getByteArray(X509_KEY)
        } catch (_: Exception) {
            null
        }
    }

    fun sha256Hex(data: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(data)
        return digest.joinToString(":") { "%02X".format(it) }
    }

    fun issuer(certificate: SslCertificate?): String =
        certificate?.issuedBy?.cName?.takeIf { it.isNotBlank() } ?: "—"
}
