package com.aster.app

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.URLEncoder
import java.security.SecureRandom
import java.util.Locale

/**
 * 系统「分享/用其他应用打开」进来的文件暂存区。
 *
 * - 立即复制到 `filesDir/shared/<entryId>/<safeName>`，原始 content URI 只在复制期间有效；
 * - 元数据写在 `filesDir/shared/index.json`，进程重启后仍可被网页取走；
 * - 只保留 24 小时，网页消费后通过 ack 删除对应文件；
 * - 同时暂存 ACTION_SEND 附带的纯文本，随 take 一起返回。
 *
 * 所有公开方法线程安全；文件复制本身可能较慢，调用方应放在后台线程。
 */
class SharedInbox(context: Context) {

    private val appContext = context.applicationContext
    private val lock = Any()
    private val root = File(appContext.filesDir, ROOT_DIR)
    private val indexFile = File(root, INDEX_FILE)
    private val random = SecureRandom()

    private var loaded = false
    private val files = LinkedHashMap<String, Entry>()
    private val texts = ArrayList<TextEntry>()

    data class Entry(
        val id: String,
        val name: String,
        val size: Long,
        val mime: String,
        val addedAt: Long,
        val file: File,
    )

    data class Snapshot(
        val files: List<Entry>,
        val texts: List<String>,
    )

    private data class TextEntry(val text: String, val addedAt: Long)

    fun pendingFiles(): Int = synchronized(lock) {
        ensureLoadedLocked()
        pruneExpiredLocked()
        files.size
    }

    fun pendingTexts(): Int = synchronized(lock) {
        ensureLoadedLocked()
        pruneExpiredLocked()
        texts.size
    }

    fun snapshot(): Snapshot = synchronized(lock) {
        ensureLoadedLocked()
        pruneExpiredLocked()
        Snapshot(files.values.toList(), texts.map { it.text })
    }

    fun entry(id: String): Entry? = synchronized(lock) {
        if (!ID_PATTERN.matches(id)) return@synchronized null
        ensureLoadedLocked()
        val entry = files[id] ?: return@synchronized null
        if (entry.file.isFile) entry else null
    }

    fun ingestUris(uris: List<Uri>, fallbackMime: String?): Int {
        if (uris.isEmpty()) return 0
        var added = 0
        for (uri in uris) {
            try {
                val entry = copyOne(uri, fallbackMime) ?: continue
                synchronized(lock) {
                    ensureLoadedLocked()
                    files[entry.id] = entry
                    pruneExpiredLocked()
                    saveIndexLocked()
                }
                added++
            } catch (error: Exception) {
                Log.w(TAG, "copy shared file failed", error)
            }
        }
        return added
    }

    fun ingestTexts(values: List<String>): Int {
        if (values.isEmpty()) return 0
        var added = 0
        synchronized(lock) {
            ensureLoadedLocked()
            pruneExpiredLocked()
            for (raw in values) {
                val text = raw.trim().take(MAX_TEXT_CHARS)
                if (text.isEmpty()) continue
                if (texts.any { it.text == text }) continue
                if (texts.size >= MAX_TEXTS) texts.removeAt(0)
                texts.add(TextEntry(text, System.currentTimeMillis()))
                added++
            }
            if (added > 0) saveIndexLocked()
        }
        return added
    }

    /**
     * 网页消费完共享内容后确认。删除对应文件，并清空本次已读取的文本。
     * 文本没有 id，因此随 ack 一并清空，避免下次 pull 重复加入。
     */
    fun ack(ids: Set<String>): Int = synchronized(lock) {
        ensureLoadedLocked()
        var removed = 0
        for (id in ids) {
            val entry = files.remove(id) ?: continue
            deleteEntry(entry)
            removed++
        }
        val hadTexts = texts.isNotEmpty()
        texts.clear()
        if (removed > 0 || hadTexts) saveIndexLocked()
        removed
    }

    fun snapshotJson(baseUrl: String): String {
        val snapshot = snapshot()
        val filesJson = JSONArray()
        for (entry in snapshot.files) {
            filesJson.put(
                JSONObject().apply {
                    put("id", entry.id)
                    put("name", entry.name)
                    put("size", entry.size)
                    put("mime", entry.mime)
                    put("url", "$baseUrl/${entry.id}/${encodePath(entry.name)}")
                }
            )
        }
        val textsJson = JSONArray()
        for (text in snapshot.texts) textsJson.put(text)
        return JSONObject().apply {
            put("files", filesJson)
            put("texts", textsJson)
        }.toString()
    }

    // ------------------------------------------------------------------ 内部

    private fun ensureLoadedLocked() {
        if (loaded) return
        loaded = true
        try {
            root.mkdirs()
        } catch (error: Exception) {
            Log.w(TAG, "create shared dir failed", error)
        }
        loadIndexLocked()
        pruneExpiredLocked()
        // 上次进程被杀死时可能留下没有索引的目录；超过 24h 的孤儿一起清掉。
        try {
            root.listFiles()?.forEach { child ->
                if (!child.isDirectory) return@forEach
                if (files.containsKey(child.name)) return@forEach
                if (System.currentTimeMillis() - child.lastModified() > MAX_AGE_MS) {
                    child.deleteRecursively()
                }
            }
        } catch (error: Exception) {
            Log.w(TAG, "clean orphan dirs failed", error)
        }
    }

    private fun loadIndexLocked() {
        if (!indexFile.isFile) return
        val rootJson = try {
            JSONObject(indexFile.readText(Charsets.UTF_8))
        } catch (error: Exception) {
            Log.w(TAG, "read share index failed", error)
            return
        }
        val filesJson = rootJson.optJSONArray("files")
        if (filesJson != null) {
            for (index in 0 until filesJson.length()) {
                val item = filesJson.optJSONObject(index) ?: continue
                val id = item.optString("id")
                if (!ID_PATTERN.matches(id)) continue
                val name = ShareNames.sanitize(item.optString("name").ifEmpty { null })
                val file = File(File(root, id), name)
                if (!file.isFile) {
                    File(root, id).deleteRecursively()
                    continue
                }
                val added = item.optLong("added", 0L).takeIf { it > 0L } ?: file.lastModified()
                files[id] = Entry(
                    id = id,
                    name = name,
                    size = file.length(),
                    mime = normalizeMime(item.optString("mime")),
                    addedAt = added,
                    file = file,
                )
            }
        }
        val textsJson = rootJson.optJSONArray("texts")
        if (textsJson != null) {
            for (index in 0 until textsJson.length()) {
                if (texts.size >= MAX_TEXTS) break
                val item = textsJson.optJSONObject(index)
                val raw = if (item == null) textsJson.optString(index) else item.optString("text")
                val text = raw?.trim()?.take(MAX_TEXT_CHARS).orEmpty()
                if (text.isEmpty()) continue
                val added = item?.optLong("added", 0L)?.takeIf { it > 0L } ?: System.currentTimeMillis()
                texts.add(TextEntry(text, added))
            }
        }
    }

    private fun pruneExpiredLocked(): Boolean {
        val cutoff = System.currentTimeMillis() - MAX_AGE_MS
        var changed = false
        val iterator = files.entries.iterator()
        while (iterator.hasNext()) {
            val entry = iterator.next().value
            if (entry.addedAt < cutoff || !entry.file.isFile) {
                deleteEntry(entry)
                iterator.remove()
                changed = true
            }
        }
        if (texts.removeAll { it.addedAt < cutoff }) changed = true
        if (changed) saveIndexLocked()
        return changed
    }

    private fun deleteEntry(entry: Entry) {
        try {
            entry.file.parentFile?.deleteRecursively() ?: entry.file.delete()
        } catch (error: Exception) {
            Log.w(TAG, "delete shared entry failed", error)
        }
    }

    private fun saveIndexLocked() {
        val filesJson = JSONArray()
        for (entry in files.values) {
            filesJson.put(
                JSONObject().apply {
                    put("id", entry.id)
                    put("name", entry.name)
                    put("size", entry.size)
                    put("mime", entry.mime)
                    put("added", entry.addedAt)
                }
            )
        }
        val textsJson = JSONArray()
        for (text in texts) {
            textsJson.put(
                JSONObject().apply {
                    put("text", text.text)
                    put("added", text.addedAt)
                }
            )
        }
        val payload = JSONObject().apply {
            put("files", filesJson)
            put("texts", textsJson)
        }.toString()
        try {
            root.mkdirs()
            val temp = File(root, "$INDEX_FILE.tmp")
            temp.writeText(payload, Charsets.UTF_8)
            if (!temp.renameTo(indexFile)) {
                indexFile.writeText(payload, Charsets.UTF_8)
                temp.delete()
            }
        } catch (error: Exception) {
            Log.w(TAG, "save share index failed", error)
        }
    }

    private fun copyOne(uri: Uri, fallbackMime: String?): Entry? {
        val name = ShareNames.sanitize(queryDisplayName(uri))
        val id = newEntryId()
        val dir = File(root, id)
        if (!dir.exists() && !dir.mkdirs()) throw IOException("mkdir $dir failed")
        val target = File(dir, name)
        val safeParent = target.parentFile?.canonicalFile
        if (safeParent == null || safeParent != dir.canonicalFile) {
            throw IOException("unsafe share name")
        }
        val mime = normalizeMime(readMime(uri) ?: fallbackMime)
        try {
            val input = appContext.contentResolver.openInputStream(uri)
                ?: throw IOException("open share stream failed")
            var copied = 0L
            input.use { source ->
                FileOutputStream(target).use { output ->
                    val buffer = ByteArray(BUFFER_SIZE)
                    while (true) {
                        val read = source.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        copied += read.toLong()
                    }
                    output.flush()
                }
            }
            return Entry(
                id = id,
                name = name,
                size = copied,
                mime = mime,
                addedAt = System.currentTimeMillis(),
                file = target,
            )
        } catch (error: Exception) {
            target.delete()
            dir.delete()
            throw error
        }
    }

    private fun queryDisplayName(uri: Uri): String? {
        var name: String? = null
        try {
            appContext.contentResolver.query(
                uri,
                arrayOf(OpenableColumns.DISPLAY_NAME),
                null,
                null,
                null,
            )?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (column >= 0) name = cursor.getString(column)
                }
            }
        } catch (error: Exception) {
            Log.w(TAG, "query display name failed", error)
        }
        if (name.isNullOrBlank()) {
            name = uri.lastPathSegment?.substringAfterLast('/')
        }
        return name
    }

    private fun readMime(uri: Uri): String? = try {
        appContext.contentResolver.getType(uri)
    } catch (error: Exception) {
        Log.w(TAG, "query mime failed", error)
        null
    }

    private fun newEntryId(): String {
        repeat(16) {
            val bytes = ByteArray(8)
            random.nextBytes(bytes)
            val builder = StringBuilder(bytes.size * 2)
            for (byte in bytes) builder.append(String.format(Locale.US, "%02x", byte.toInt() and 0xFF))
            val candidate = builder.toString()
            synchronized(lock) {
                ensureLoadedLocked()
                if (!files.containsKey(candidate) && !File(root, candidate).exists()) return candidate
            }
        }
        return System.currentTimeMillis().toString(16).padStart(16, '0').take(16)
    }

    private fun encodePath(name: String): String = try {
        URLEncoder.encode(name, "UTF-8").replace("+", "%20")
    } catch (_: Exception) {
        "shared-file"
    }

    private fun normalizeMime(raw: String?): String {
        val value = raw?.trim()?.lowercase(Locale.ROOT).orEmpty()
        if (value.isEmpty() || value.length > 128) return DEFAULT_MIME
        return if (MIME_PATTERN.matches(value)) value else DEFAULT_MIME
    }

    companion object {
        private const val TAG = "AsterShare"
        private const val ROOT_DIR = "shared"
        private const val INDEX_FILE = "index.json"
        private const val MAX_AGE_MS = 24L * 60L * 60L * 1000L
        private const val BUFFER_SIZE = 64 * 1024
        private const val MAX_TEXTS = 50
        private const val MAX_TEXT_CHARS = 20_000
        private const val DEFAULT_MIME = "application/octet-stream"
        private val ID_PATTERN = Regex("^[a-f0-9]{16}$")
        private val MIME_PATTERN = Regex("^[a-z0-9.+_-]+/[a-z0-9.+_-]+$")
    }
}
