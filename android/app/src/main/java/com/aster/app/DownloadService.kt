package com.aster.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.io.FileOutputStream
import java.io.IOException
import java.io.InterruptedIOException
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.ArrayDeque
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * HTTPS 自签名证书页面的下载走这里：DownloadManager 不信任 Aster 的自签名证书，
 * 所以用已确认的证书指纹做 TLS pinning，把文件写入系统 Downloads/Aster。
 *
 * 新版网页在「接收」后会自动连续触发多个下载；这里用一个前台服务队列依次处理，
 * 避免并发写同一个通知/互相 stopSelf，也避免只保存第一个文件。
 */
class DownloadService : Service() {

    private val mainHandler = Handler(Looper.getMainLooper())
    private val lock = Any()
    private val queue = ArrayDeque<DownloadJob>()

    private var processing = false
    private var worker: Thread? = null

    @Volatile
    private var activeConnection: HttpURLConnection? = null

    @Volatile
    private var cancelled = false

    @Volatile
    private var lastNotification: Notification? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        cancelled = false
        val data = intent
        val url = data?.getStringExtra(EXTRA_URL)
        val rawName = data?.getStringExtra(EXTRA_FILENAME)
        if (data == null || url.isNullOrBlank() || rawName.isNullOrBlank()) {
            val existing = lastNotification
            if (existing != null) {
                startForeground(NOTIFICATION_ID, existing)
            } else {
                startForeground(
                    NOTIFICATION_ID,
                    buildProgressNotification(getString(R.string.download_notification_title), 0L, -1L),
                )
                stopSelf()
            }
            return START_NOT_STICKY
        }

        val job = DownloadJob(
            url = url,
            filename = DownloadNames.sanitize(rawName),
            mime = data.getStringExtra(EXTRA_MIME) ?: "application/octet-stream",
            pin = data.getStringExtra(EXTRA_PIN),
            userAgent = data.getStringExtra(EXTRA_USER_AGENT),
        )
        val starting = buildProgressNotification(job.filename, 0L, -1L)

        val startWorker: Boolean
        synchronized(lock) {
            queue.addLast(job)
            startWorker = !processing
            if (startWorker) processing = true
        }

        // 已经在前台下载时保留当前进度通知；新任务开始时再切换。
        val notification = if (startWorker) starting else (lastNotification ?: starting)
        lastNotification = notification
        startForeground(NOTIFICATION_ID, notification)

        if (startWorker) {
            synchronized(lock) {
                if (processing && worker == null) {
                    worker = Thread({ processQueue() }, "aster-download").also { it.start() }
                }
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        cancelled = true
        mainHandler.removeCallbacksAndMessages(null)
        val currentWorker = synchronized(lock) {
            val thread = worker
            worker = null
            processing = false
            queue.clear()
            thread
        }
        currentWorker?.interrupt()
        activeConnection?.disconnect()
        activeConnection = null
        super.onDestroy()
    }

    private fun processQueue() {
        while (true) {
            val job: DownloadJob?
            synchronized(lock) {
                job = queue.pollFirst()
                if (job == null) {
                    processing = false
                    worker = null
                }
            }
            if (job == null) break

            val starting = buildProgressNotification(job.filename, 0L, -1L)
            lastNotification = starting
            notify(starting)

            val result = runDownload(job)
            postResult(result)
        }

        mainHandler.postDelayed({
            val shouldStop = synchronized(lock) { !processing && queue.isEmpty() }
            if (shouldStop) {
                try {
                    // 保留最后一个完成/失败通知。
                    stopForeground(STOP_FOREGROUND_DETACH)
                } catch (_: Exception) {
                    // ignore
                }
                stopSelf()
            }
        }, STOP_GRACE_MS)
    }

    private fun runDownload(job: DownloadJob): JobResult {
        var output: OutputStream? = null
        var pendingUri: Uri? = null
        var finalName = job.filename
        var success = false
        try {
            val connection = URL(job.url).openConnection() as HttpURLConnection
            activeConnection = connection
            connection.connectTimeout = CONNECT_TIMEOUT_MS
            connection.readTimeout = READ_TIMEOUT_MS
            connection.instanceFollowRedirects = true
            connection.setRequestProperty("User-Agent", job.userAgent ?: DEFAULT_UA)
            connection.setRequestProperty("Accept", "*/*")

            if (connection is HttpsURLConnection && !job.pin.isNullOrBlank()) {
                val pinned = try {
                    Base64.decode(job.pin, Base64.NO_WRAP)
                } catch (_: IllegalArgumentException) {
                    null
                }
                if (pinned != null) {
                    connection.sslSocketFactory = pinnedSocketFactory(pinned)
                    connection.hostnameVerifier = HostnameVerifier { _, session ->
                        try {
                            val certificate = session.peerCertificates.firstOrNull() as? X509Certificate
                            certificate != null && certificate.encoded.contentEquals(pinned)
                        } catch (_: Exception) {
                            false
                        }
                    }
                }
            }

            val code = connection.responseCode
            if (code !in 200..299) throw IOException("HTTP $code")
            val total = connection.contentLengthLong

            val stream: OutputStream
            if (Build.VERSION.SDK_INT >= 29) {
                finalName = DownloadNames.uniqueName(this, job.filename)
                pendingUri = DownloadNames.newMediaStoreEntry(contentResolver, finalName, job.mime)
                    ?: throw IOException("MediaStore insert failed")
                stream = contentResolver.openOutputStream(pendingUri)
                    ?: throw IOException("openOutputStream failed")
                output = stream
            } else {
                if (ContextCompat.checkSelfPermission(
                        this,
                        android.Manifest.permission.WRITE_EXTERNAL_STORAGE,
                    ) != PackageManager.PERMISSION_GRANTED
                ) {
                    throw SecurityException("no storage permission")
                }
                val directory = DownloadNames.ensureDownloadsDir()
                val file = DownloadNames.uniqueFile(directory, job.filename)
                finalName = file.name
                stream = FileOutputStream(file)
                output = stream
            }

            connection.inputStream.use { input ->
                val buffer = ByteArray(BUFFER_SIZE)
                var copied = 0L
                var lastUpdate = 0L
                while (true) {
                    if (cancelled) throw InterruptedIOException("cancelled")
                    val read = input.read(buffer)
                    if (read < 0) break
                    stream.write(buffer, 0, read)
                    copied += read
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastUpdate >= PROGRESS_INTERVAL_MS) {
                        lastUpdate = now
                        updateProgress(finalName, copied, total)
                    }
                }
                stream.flush()
            }
            stream.close()
            output = null

            if (Build.VERSION.SDK_INT >= 29 && pendingUri != null) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.IS_PENDING, 0)
                }
                contentResolver.update(pendingUri, values, null, null)
            }
            success = true
        } catch (error: Exception) {
            Log.w(TAG, "download failed", error)
            try {
                output?.close()
            } catch (_: Exception) {
                // ignore
            }
            if (Build.VERSION.SDK_INT >= 29 && pendingUri != null) {
                try {
                    contentResolver.delete(pendingUri, null, null)
                } catch (_: Exception) {
                    // ignore
                }
            }
        } finally {
            activeConnection?.disconnect()
            activeConnection = null
        }
        return JobResult(finalName, success)
    }

    private fun postResult(result: JobResult) {
        val notification = baseBuilder()
            .setContentText(
                getString(
                    if (result.success) R.string.download_notification_done
                    else R.string.download_notification_failed,
                    result.name,
                )
            )
            .setOngoing(false)
            .setAutoCancel(true)
            .setProgress(0, 0, false)
            .build()
        lastNotification = notification
        notify(notification)
        toast(
            getString(
                if (result.success) R.string.download_saved else R.string.download_failed,
            )
        )
    }

    private fun notify(notification: Notification) {
        try {
            val manager = getSystemService(NotificationManager::class.java)
            manager.notify(NOTIFICATION_ID, notification)
        } catch (_: Exception) {
            // ignore
        }
    }

    private fun updateProgress(name: String, copied: Long, total: Long) {
        try {
            val notification = buildProgressNotification(name, copied, total)
            lastNotification = notification
            notify(notification)
        } catch (_: Exception) {
            // ignore
        }
    }

    private fun buildProgressNotification(name: String, copied: Long, total: Long): Notification {
        val builder = baseBuilder().setOngoing(true)
        if (total > 0) {
            val max = 1000
            val progress = ((copied.toDouble() / total.toDouble()) * max)
                .toInt()
                .coerceIn(0, max)
            builder.setProgress(max, progress, false)
            builder.setContentText(
                getString(R.string.download_notification_progress, name, progress * 100 / max)
            )
        } else {
            builder.setProgress(0, 0, true)
            builder.setContentText(getString(R.string.download_notification_progress_unknown, name))
        }
        return builder.build()
    }

    private fun baseBuilder(): NotificationCompat.Builder =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_aster)
            .setContentTitle(getString(R.string.download_notification_title))
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)

    private fun ensureChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) == null) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.download_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            )
            channel.setShowBadge(false)
            manager.createNotificationChannel(channel)
        }
    }

    private fun pinnedSocketFactory(pinned: ByteArray): SSLSocketFactory {
        val trustManager = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                throw CertificateException("client certificates not accepted")
            }

            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                val leaf = chain?.firstOrNull()
                if (leaf == null || !leaf.encoded.contentEquals(pinned)) {
                    throw CertificateException("certificate pin mismatch")
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val context = SSLContext.getInstance("TLS")
        context.init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
        return context.socketFactory
    }

    private fun toast(message: String) {
        mainHandler.post {
            Toast.makeText(applicationContext, message, Toast.LENGTH_SHORT).show()
        }
    }

    private data class DownloadJob(
        val url: String,
        val filename: String,
        val mime: String,
        val pin: String?,
        val userAgent: String?,
    )

    private data class JobResult(
        val name: String,
        val success: Boolean,
    )

    companion object {
        private const val TAG = "AsterDownload"
        private const val CHANNEL_ID = "aster_downloads"
        private const val NOTIFICATION_ID = 42820
        private const val CONNECT_TIMEOUT_MS = 15_000
        private const val READ_TIMEOUT_MS = 60_000
        private const val BUFFER_SIZE = 256 * 1024
        private const val PROGRESS_INTERVAL_MS = 400L
        private const val STOP_GRACE_MS = 300L
        private val DEFAULT_UA: String =
            System.getProperty("http.agent") ?: "Aster/2.0.0 (Android)"

        const val EXTRA_URL = "url"
        const val EXTRA_FILENAME = "filename"
        const val EXTRA_MIME = "mime"
        const val EXTRA_PIN = "pin"
        const val EXTRA_USER_AGENT = "user_agent"
    }
}
