package com.aster.app

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper

/**
 * 前台传输服务和 Activity 之间的轻量通道。
 *
 * 通知上的「取消」只能通过 PendingIntent 触发，广播接收器把取消请求交回
 * [TransferBus]，再由 MainActivity 调用网页的 `window.AsterTransfer.cancel()`。
 */
object TransferBus {

    const val ACTION_CANCEL = "com.aster.app.action.CANCEL_TRANSFER"

    private const val REQUEST_CODE = 42_831

    private val main = Handler(Looper.getMainLooper())

    @Volatile
    private var listener: (() -> Unit)? = null

    fun register(callback: () -> Unit) {
        listener = callback
    }

    fun unregister() {
        listener = null
    }

    /** 返回是否已把取消请求交给存活的 Activity。 */
    fun dispatchCancel(): Boolean {
        val current = listener ?: return false
        main.post { current() }
        return true
    }

    fun cancelPendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, TransferCancelReceiver::class.java)
            .setAction(ACTION_CANCEL)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getBroadcast(context, REQUEST_CODE, intent, flags)
    }
}

/**
 * 只负责转发的广播接收器。Activity 已销毁（任务被划掉等）时直接停掉传输服务。
 */
class TransferCancelReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != TransferBus.ACTION_CANCEL) return
        if (!TransferBus.dispatchCancel()) {
            TransferService.cancelNow(context)
        }
    }
}
