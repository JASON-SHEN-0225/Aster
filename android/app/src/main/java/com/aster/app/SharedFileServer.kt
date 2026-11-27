package com.aster.app

import android.util.Log
import java.io.BufferedReader
import java.io.FileInputStream
import java.io.InputStreamReader
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * 只监听 127.0.0.1 的临时 HTTP 服务，供 Aster 网页用 fetch 读取共享暂存文件。
 *
 * - 端口随机（bind 0），路径带随机 token，只有暂存区里存在的 entry 才能访问；
 * - 允许跨域（网页和本地服务不同端口），但只暴露 GET/HEAD/OPTIONS；
 * - 不写磁盘、不接受请求体，仅按需把暂存文件回给本机网页。
 */
class SharedFileServer(private val inbox: SharedInbox) {

    private val lock = Any()
    private val random = SecureRandom()
    private val closed = AtomicBoolean(true)
    private val token: String = buildToken()

    @Volatile
    private var server: ServerSocket? = null

    @Volatile
    private var executor: ExecutorService? = null

    @Volatile
    private var acceptThread: Thread? = null

    /** 启动（幂等），返回实际监听端口；失败返回 -1。 */
    fun ensureStarted(): Int = synchronized(lock) {
        server?.let { return it.localPort }
        return try {
            val socket = ServerSocket()
            socket.reuseAddress = true
            socket.bind(InetSocketAddress(InetAddress.getByName(LOOPBACK), 0), 8)
            val pool = Executors.newFixedThreadPool(WORKERS) { runnable ->
                Thread(runnable, "aster-share-http").also { it.isDaemon = true }
            }
            server = socket
            executor = pool
            closed.set(false)
            acceptThread = Thread({ acceptLoop(socket, pool) }, "aster-share-accept").also {
                it.isDaemon = true
                it.start()
            }
            socket.localPort
        } catch (error: Exception) {
            Log.w(TAG, "start share server failed", error)
            -1
        }
    }

    fun baseUrl(): String? {
        val port = ensureStarted()
        if (port <= 0) return null
        return "http://$LOOPBACK:$port/$token"
    }

    fun stop() {
        synchronized(lock) {
            closed.set(true)
            try {
                server?.close()
            } catch (_: Exception) {
                // ignore
            }
            server = null
            acceptThread = null
            try {
                executor?.shutdownNow()
            } catch (_: Exception) {
                // ignore
            }
            executor = null
        }
    }

    private fun acceptLoop(socket: ServerSocket, pool: ExecutorService) {
        while (!closed.get() && !socket.isClosed) {
            val client = try {
                socket.accept()
            } catch (_: Exception) {
                break
            }
            try {
                pool.execute { handleClient(client) }
            } catch (_: Exception) {
                try {
                    client.close()
                } catch (_: Exception) {
                    // ignore
                }
            }
        }
    }

    private fun handleClient(client: Socket) {
        try {
            client.use { socket ->
                socket.soTimeout = CLIENT_TIMEOUT_MS
                socket.tcpNoDelay = true
                val reader = BufferedReader(
                    InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII)
                )
                val requestLine = readLine(reader, MAX_REQUEST_LINE) ?: return
                val parts = requestLine.trim().split(' ')
                if (parts.size < 2) {
                    writeEmpty(socket, 400)
                    return
                }
                val method = parts[0].uppercase(Locale.ROOT)
                val target = parts[1]
                var headerCount = 0
                while (headerCount < MAX_HEADERS) {
                    val line = readLine(reader, MAX_HEADER_LINE) ?: break
                    if (line.isEmpty()) break
                    headerCount++
                }
                if (method == "OPTIONS") {
                    writeEmpty(socket, 204)
                    return
                }
                if (method != "GET" && method != "HEAD") {
                    writeEmpty(socket, 405)
                    return
                }
                val path = target.substringBefore('?').substringBefore('#')
                val segments = path.split('/').filter { it.isNotEmpty() }
                if (segments.size < 2 || segments[0] != token) {
                    writeEmpty(socket, 403)
                    return
                }
                val entry = inbox.entry(segments[1])
                if (entry == null || !entry.file.isFile) {
                    writeEmpty(socket, 404)
                    return
                }
                val file = entry.file
                val length = file.length()
                val header = buildString {
                    append("HTTP/1.1 200 OK\r\n")
                    append("Content-Type: ").append(safeMime(entry.mime)).append("\r\n")
                    append("Content-Length: ").append(length).append("\r\n")
                    append("Cache-Control: no-store\r\n")
                    append("Content-Disposition: inline\r\n")
                    append("Access-Control-Allow-Origin: *\r\n")
                    append("Access-Control-Allow-Methods: GET, HEAD, OPTIONS\r\n")
                    append("Access-Control-Allow-Headers: *\r\n")
                    append("Access-Control-Allow-Private-Network: true\r\n")
                    append("Access-Control-Expose-Headers: Content-Length\r\n")
                    append("Connection: close\r\n\r\n")
                }
                val output = socket.getOutputStream()
                output.write(header.toByteArray(StandardCharsets.US_ASCII))
                if (method == "GET") {
                    FileInputStream(file).use { input ->
                        val buffer = ByteArray(BUFFER_SIZE)
                        while (true) {
                            val read = input.read(buffer)
                            if (read < 0) break
                            output.write(buffer, 0, read)
                        }
                    }
                }
                output.flush()
            }
        } catch (error: Exception) {
            Log.w(TAG, "serve share request failed", error)
        }
    }

    private fun writeEmpty(socket: Socket, status: Int) {
        try {
            val reason = when (status) {
                204 -> "No Content"
                400 -> "Bad Request"
                403 -> "Forbidden"
                404 -> "Not Found"
                405 -> "Method Not Allowed"
                else -> "Error"
            }
            val header = buildString {
                append("HTTP/1.1 ").append(status).append(' ').append(reason).append("\r\n")
                if (status != 204) append("Content-Length: 0\r\n")
                append("Access-Control-Allow-Origin: *\r\n")
                append("Access-Control-Allow-Methods: GET, HEAD, OPTIONS\r\n")
                append("Access-Control-Allow-Headers: *\r\n")
                append("Access-Control-Allow-Private-Network: true\r\n")
                append("Cache-Control: no-store\r\n")
                append("Connection: close\r\n\r\n")
            }
            val output = socket.getOutputStream()
            output.write(header.toByteArray(StandardCharsets.US_ASCII))
            output.flush()
        } catch (_: Exception) {
            // ignore
        }
    }

    /** 逐字符读一行并限制长度，避免本机恶意请求撑爆内存。 */
    private fun readLine(reader: BufferedReader, limit: Int): String? {
        val builder = StringBuilder()
        while (true) {
            val value = reader.read()
            if (value < 0) return null
            if (value == '\n'.code) break
            if (value == '\r'.code) continue
            if (builder.length >= limit) return null
            builder.append(value.toChar())
        }
        return builder.toString()
    }

    private fun safeMime(raw: String): String {
        val value = raw.trim().lowercase(Locale.ROOT)
        if (value.isEmpty() || value.length > 128) return DEFAULT_MIME
        return if (MIME_PATTERN.matches(value)) value else DEFAULT_MIME
    }

    private fun buildToken(): String {
        val bytes = ByteArray(16)
        random.nextBytes(bytes)
        val builder = StringBuilder(bytes.size * 2)
        for (byte in bytes) builder.append(String.format(Locale.US, "%02x", byte.toInt() and 0xFF))
        return builder.toString()
    }

    companion object {
        private const val TAG = "AsterShareHttp"
        private const val LOOPBACK = "127.0.0.1"
        private const val WORKERS = 2
        private const val CLIENT_TIMEOUT_MS = 5_000
        private const val BUFFER_SIZE = 64 * 1024
        private const val MAX_REQUEST_LINE = 2_048
        private const val MAX_HEADER_LINE = 4_096
        private const val MAX_HEADERS = 100
        private const val DEFAULT_MIME = "application/octet-stream"
        private val MIME_PATTERN = Regex("^[a-z0-9.+_-]+/[a-z0-9.+_-]+$")
    }
}
