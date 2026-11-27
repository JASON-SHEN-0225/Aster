package com.aster.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * 手机通过网页向电脑上传文件时的前台服务。
 *
 * 网页（JS 桥）调用 start/update/finish 驱动这里：保持 PARTIAL_WAKE_LOCK，
 * 通知实时显示文件名、百分比和速度，并提供「取消」按钮。
 * 真正的传输仍在 WebView 的 XHR 里，服务只负责保活、通知与取消回调。
 */
class TransferService : Service() {

    private var wakeLock: PowerManager.WakeLock? = null
    private var finished = false

    private var title = ""
    private var fileName = ""
    private var total = 0L
    private var done = 0L
    private var speed = 0L

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_UPDATE -> {
                if (finished) {
                    finished = false
                    fileName = ""
                    done = 0L
                }
                title = clean(intent.getStringExtra(EXTRA_TITLE)).ifEmpty { title }
                fileName = clean(intent.getStringExtra(EXTRA_NAME)).ifEmpty { fileName }
                total = intent.getLongExtra(EXTRA_TOTAL, total).coerceAtLeast(0L)
                done = intent.getLongExtra(EXTRA_DONE, done).coerceAtLeast(0L)
                speed = intent.getLongExtra(EXTRA_SPEED, 0L).coerceAtLeast(0L)
                startForegroundCompat(buildProgressNotification())
                acquireWakeLock()
            }
            ACTION_FINISH -> {
                finished = true
                isRunning = false
                releaseWakeLock()
                val success = intent.getBooleanExtra(EXTRA_SUCCESS, false)
                val message = clean(intent.getStringExtra(EXTRA_MESSAGE))
                finishInternal(success, message)
                return START_NOT_STICKY
            }
            else -> {
                title = clean(intent?.getStringExtra(EXTRA_TITLE))
                fileName = clean(intent?.getStringExtra(EXTRA_NAME))
                total = intent?.getLongExtra(EXTRA_TOTAL, 0L)?.coerceAtLeast(0L) ?: 0L
                done = 0L
                speed = 0L
                finished = false
                startForegroundCompat(buildProgressNotification())
                acquireWakeLock()
            }
        }
        isRunning = true
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // 任务被划掉后 WebView 已销毁，上传不可能继续；避免通知和唤醒锁常驻。
        isRunning = false
        releaseWakeLock()
        try {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } catch (_: Exception) {
            // ignore
        }
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        isRunning = false
        releaseWakeLock()
        if (!finished) {
            try {
                stopForeground(STOP_FOREGROUND_REMOVE)
            } catch (_: Exception) {
                // ignore
            }
        }
        super.onDestroy()
    }

    private fun finishInternal(success: Boolean, message: String) {
        isRunning = false
        releaseWakeLock()
        val notification = buildFinalNotification(success, message)
        try {
            startForegroundCompat(notification)
        } catch (error: Exception) {
            Log.w(TAG, "finish foreground failed", error)
        }
        try {
            // 保留完成/失败通知，服务本身退出。
            stopForeground(STOP_FOREGROUND_DETACH)
        } catch (_: Exception) {
            // ignore
        }
        stopSelf()
    }

    private fun startForegroundCompat(notification: Notification) {
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildProgressNotification(): Notification {
        val percent = if (total > 0L) {
            ((done.coerceIn(0L, total) * 100L) / total).toInt().coerceIn(0, 100)
        } else {
            -1
        }
        val speedText = if (speed > 0L) ByteFormat.speed(speed) else ""
        val text = when {
            percent < 0 && speedText.isNotEmpty() ->
                getString(R.string.transfer_notification_unknown_speed, speedText)
            percent < 0 -> getString(R.string.transfer_notification_unknown)
            speedText.isNotEmpty() ->
                getString(R.string.transfer_notification_progress, percent, speedText)
            else -> getString(R.string.transfer_notification_percent, percent)
        }
        val builder = baseBuilder()
            .setContentTitle(displayName())
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(100, percent.coerceAtLeast(0), percent < 0)
            .setContentIntent(contentIntent())
            .addAction(
                R.drawable.ic_cancel,
                getString(R.string.transfer_notification_cancel),
                TransferBus.cancelPendingIntent(this),
            )
        return builder.build()
    }

    private fun buildFinalNotification(success: Boolean, message: String): Notification {
        val text = when {
            success -> getString(R.string.transfer_notification_done)
            message.isNotBlank() -> message
            else -> getString(R.string.transfer_notification_failed)
        }
        return baseBuilder()
            .setContentTitle(displayName())
            .setContentText(text)
            .setOngoing(false)
            .setAutoCancel(true)
            .setProgress(0, 0, false)
            .setContentIntent(contentIntent())
            .build()
    }

    private fun displayName(): String = fileName.ifBlank {
        title.ifBlank { getString(R.string.transfer_notification_title) }
    }

    private fun baseBuilder(): NotificationCompat.Builder =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_aster)
            .setColor(ContextCompat.getColor(this, R.color.aster_blue))
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setOnlyAlertOnce(true)

    private fun contentIntent(): PendingIntent {
        // 自定义 action：回到已有 Activity 时不要触发「显示连接页」的 LAUNCHER 分支。
        val intent = Intent(this, MainActivity::class.java).apply {
            action = ACTION_OPEN
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(this, REQUEST_CONTENT, intent, flags)
    }

    private fun acquireWakeLock() {
        try {
            val current = wakeLock
            if (current?.isHeld == true) return
            val manager = getSystemService(Context.POWER_SERVICE) as PowerManager
            val lock = current ?: manager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                WAKE_LOCK_TAG,
            ).apply { setReferenceCounted(false) }
            wakeLock = lock
            lock.acquire(WAKE_TIMEOUT_MS)
        } catch (error: Exception) {
            Log.w(TAG, "acquire wake lock failed", error)
        }
    }

    private fun releaseWakeLock() {
        try {
            val current = wakeLock ?: return
            if (current.isHeld) current.release()
        } catch (error: Exception) {
            Log.w(TAG, "release wake lock failed", error)
        } finally {
            wakeLock = null
        }
    }

    private fun ensureChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.transfer_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.transfer_channel_description)
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun clean(value: String?): String =
        value?.replace(controlChars, "")?.trim().orEmpty().take(MAX_TEXT)

    companion object {
        private const val TAG = "AsterTransfer"
        private const val CHANNEL_ID = "aster_transfer"
        private const val NOTIFICATION_ID = 42_830
        private const val REQUEST_CONTENT = 42_832
        private const val WAKE_LOCK_TAG = "Aster:TransferService"
        private const val WAKE_TIMEOUT_MS = 60L * 60L * 1000L
        private const val MAX_TEXT = 96
        private val controlChars = Regex("[\\u0000-\\u001F\\u007F]")

        const val ACTION_START = "com.aster.app.action.TRANSFER_START"
        const val ACTION_UPDATE = "com.aster.app.action.TRANSFER_UPDATE"
        const val ACTION_FINISH = "com.aster.app.action.TRANSFER_FINISH"
        const val ACTION_OPEN = "com.aster.app.action.OPEN_TRANSFER"

        const val EXTRA_TITLE = "title"
        const val EXTRA_TOTAL = "total"
        const val EXTRA_DONE = "done"
        const val EXTRA_SPEED = "speed"
        const val EXTRA_NAME = "name"
        const val EXTRA_SUCCESS = "success"
        const val EXTRA_MESSAGE = "message"

        @Volatile
        var isRunning: Boolean = false

        fun start(context: Context, title: String, total: Long): Boolean {
            val intent = Intent(context, TransferService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_TOTAL, total)
            }
            return try {
                ContextCompat.startForegroundService(context, intent)
                true
            } catch (error: Exception) {
                Log.w(TAG, "start transfer service failed", error)
                false
            }
        }

        fun update(context: Context, done: Long, total: Long, speed: Long, name: String?) {
            val intent = Intent(context, TransferService::class.java).apply {
                action = ACTION_UPDATE
                putExtra(EXTRA_DONE, done)
                putExtra(EXTRA_TOTAL, total)
                putExtra(EXTRA_SPEED, speed)
                putExtra(EXTRA_NAME, name)
            }
            try {
                ContextCompat.startForegroundService(context, intent)
            } catch (error: Exception) {
                Log.w(TAG, "update transfer service failed", error)
            }
        }

        fun finish(context: Context, success: Boolean, message: String?) {
            val intent = Intent(context, TransferService::class.java).apply {
                action = ACTION_FINISH
                putExtra(EXTRA_SUCCESS, success)
                putExtra(EXTRA_MESSAGE, message)
            }
            try {
                ContextCompat.startForegroundService(context, intent)
            } catch (error: Exception) {
                Log.w(TAG, "finish transfer service failed", error)
            }
        }

        fun cancelNow(context: Context) {
            isRunning = false
            try {
                context.stopService(Intent(context, TransferService::class.java))
            } catch (_: Exception) {
                // ignore
            }
            try {
                val manager = context.getSystemService(NotificationManager::class.java)
                manager.cancel(NOTIFICATION_ID)
            } catch (_: Exception) {
                // ignore
            }
        }
    }
}
