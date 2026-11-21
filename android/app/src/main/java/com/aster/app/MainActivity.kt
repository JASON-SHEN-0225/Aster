package com.aster.app

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.Message
import android.provider.DocumentsContract
import android.util.Base64
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.google.zxing.integration.android.IntentIntegrator
import java.util.Locale
import android.net.http.SslError
import android.webkit.SslErrorHandler

class MainActivity : Activity() {

    private lateinit var prefs: Prefs
    private lateinit var root: FrameLayout
    private lateinit var connectView: View
    private lateinit var webLayer: View
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var errorView: View
    private lateinit var errorTitle: TextView
    private lateinit var errorDetail: TextView
    private lateinit var errorAddress: TextView
    private lateinit var addressInput: EditText
    private lateinit var httpsSwitch: Switch
    private lateinit var protocolLabel: TextView
    private lateinit var portHint: TextView
    private lateinit var connectStatus: TextView
    private lateinit var connectButton: Button

    private var current: Endpoint? = null
    private var pageFailed = false
    private var lastThemeKey = ""
    private var suppressSwitchEvent = false
    private var pendingFileCallback: ValueCallback<Array<Uri>>? = null
    private val pendingDownloads = ArrayDeque<PendingDownload>()
    private var storagePermissionAsked = false
    private var notificationPermissionAsked = false
    private var autoScanTriggered = false
    private var scanRequestInFlight = false
    private var sslDialog: AlertDialog? = null
    private val sslQueue = mutableListOf<SslErrorHandler>()
    private var sslCertKey: String? = null
    private var sslCertDer: ByteArray? = null
    private var sslCertSha: String? = null
    private var sslCertIssuer: String? = null
    private var sslCertDisplay: String? = null
    private var tempWindow: WebView? = null
    private var backProbePending = false

    private val ui = Handler(Looper.getMainLooper())

    private val timeoutRunnable = Runnable {
        if (webLayer.visibility != View.VISIBLE || pageFailed) return@Runnable
        pageFailed = true
        webView.stopLoading()
        showError(
            getString(R.string.error_title_timeout),
            getString(R.string.error_detail_timeout),
            current?.origin(),
        )
    }

    private val themeRunnable = object : Runnable {
        override fun run() {
            if (isFinishing || isDestroyed) return
            if (webLayer.visibility != View.VISIBLE || errorView.visibility == View.VISIBLE) return
            webView.evaluateJavascript(THEME_PROBE_JS) { value ->
                if (!isFinishing && !isDestroyed) {
                    applyThemeFromProbe(value)
                    if (webLayer.visibility == View.VISIBLE && errorView.visibility != View.VISIBLE) {
                        ui.postDelayed(this, THEME_POLL_MS)
                    }
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        setContentView(R.layout.activity_main)

        prefs = Prefs(this)
        bindViews()
        applyInsets()
        setupWebView()
        setupConnectUi()

        // 启动先停在连接页，并自动进入扫码；不再自动连接上次地址。
        showConnectScreen()
        autoScanIfPossible()
    }

    private fun bindViews() {
        root = findViewById(R.id.root)
        connectView = findViewById(R.id.connect_view)
        webLayer = findViewById(R.id.web_layer)
        webView = findViewById(R.id.web_view)
        progressBar = findViewById(R.id.web_progress)
        errorView = findViewById(R.id.error_view)
        errorTitle = findViewById(R.id.error_title)
        errorDetail = findViewById(R.id.error_detail)
        errorAddress = findViewById(R.id.error_address)
        addressInput = findViewById(R.id.address_input)
        httpsSwitch = findViewById(R.id.https_switch)
        protocolLabel = findViewById(R.id.protocol_label)
        portHint = findViewById(R.id.port_hint)
        connectStatus = findViewById(R.id.connect_status)
        connectButton = findViewById(R.id.connect_button)
    }

    private fun applyInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            WindowInsetsCompat.CONSUMED
        }
        ViewCompat.requestApplyInsets(root)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        if ((applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true)
        }

        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = true
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.setSupportMultipleWindows(true)
        settings.setSupportZoom(false)
        settings.builtInZoomControls = false
        settings.displayZoomControls = false
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = false
        settings.mediaPlaybackRequiresUserGesture = true
        settings.setGeolocationEnabled(false)
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.textZoom = 100

        webView.setBackgroundColor(ContextCompat.getColor(this, R.color.aster_bg))
        webView.isVerticalScrollBarEnabled = false
        webView.isHorizontalScrollBarEnabled = false
        webView.overScrollMode = View.OVER_SCROLL_NEVER

        val cookies = CookieManager.getInstance()
        cookies.setAcceptCookie(true)
        cookies.setAcceptThirdPartyCookies(webView, false)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean {
                if (!request.isForMainFrame) return false
                return routeNavigation(request.url)
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                if (url == null || url == "about:blank") return
                progressBar.visibility = View.VISIBLE
                errorView.visibility = View.GONE
                pageFailed = false
                ui.removeCallbacks(timeoutRunnable)
                ui.postDelayed(timeoutRunnable, LOAD_TIMEOUT_MS)
            }

            override fun onPageFinished(view: WebView, url: String?) {
                if (url == null || url == "about:blank") return
                ui.removeCallbacks(timeoutRunnable)
                progressBar.visibility = View.GONE
                if (pageFailed) return

                val parsed = AddressParser.parse(url)
                if (parsed is AddressResult.Success) {
                    val endpoint = parsed.endpoint.copy(pair = null)
                    current = endpoint
                    prefs.saveEndpoint(endpoint)
                    fillEndpoint(endpoint)
                    connectStatus.visibility = View.VISIBLE
                    connectStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.aster_muted))
                    connectStatus.text = getString(R.string.status_connected, endpoint.display())
                }
                startThemePolling()
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (!request.isForMainFrame) return
                pageFailed = true
                ui.removeCallbacks(timeoutRunnable)
                progressBar.visibility = View.GONE
                val code = error.errorCode
                val title: String
                val detail: String
                when (code) {
                    WebViewClient.ERROR_HOST_LOOKUP -> {
                        title = getString(R.string.error_title_connect)
                        detail = getString(R.string.error_detail_host)
                    }
                    WebViewClient.ERROR_TIMEOUT -> {
                        title = getString(R.string.error_title_timeout)
                        detail = getString(R.string.error_detail_timeout)
                    }
                    WebViewClient.ERROR_FAILED_SSL_HANDSHAKE -> {
                        title = getString(R.string.error_title_ssl)
                        detail = getString(R.string.error_detail_ssl)
                    }
                    WebViewClient.ERROR_CONNECT,
                    WebViewClient.ERROR_IO,
                    WebViewClient.ERROR_UNKNOWN -> {
                        title = getString(R.string.error_title_connect)
                        detail = getString(R.string.error_detail_connect)
                    }
                    WebViewClient.ERROR_UNSUPPORTED_SCHEME,
                    WebViewClient.ERROR_BAD_URL,
                    WebViewClient.ERROR_UNSAFE_RESOURCE -> {
                        title = getString(R.string.error_title_connect)
                        detail = getString(R.string.address_invalid)
                    }
                    else -> {
                        title = getString(R.string.error_title_connect)
                        detail = getString(R.string.error_detail_network)
                    }
                }
                showError(
                    title,
                    "$detail（${getString(R.string.error_code, code)}）",
                    request.url?.toString(),
                )
            }

            override fun onReceivedHttpError(
                view: WebView,
                request: WebResourceRequest,
                errorResponse: WebResourceResponse,
            ) {
                if (!request.isForMainFrame) return
                if (errorResponse.statusCode < 400) return
                pageFailed = true
                ui.removeCallbacks(timeoutRunnable)
                progressBar.visibility = View.GONE
                showError(
                    getString(R.string.error_title_http),
                    getString(R.string.error_detail_http, errorResponse.statusCode),
                    request.url?.toString(),
                )
            }

            override fun onReceivedSslError(
                view: WebView,
                handler: SslErrorHandler,
                error: SslError,
            ) {
                handleSslError(handler, error)
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: WebChromeClient.FileChooserParams?,
            ): Boolean {
                return openFileChooser(filePathCallback, fileChooserParams)
            }

            override fun onCreateWindow(
                view: WebView,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message?,
            ): Boolean {
                return openPopupWindow(resultMsg)
            }
        }

        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            handleDownload(url, userAgent, contentDisposition, mimeType)
        }
    }

    private fun setupConnectUi() {
        protocolLabel.setText(R.string.protocol_http)
        portHint.setText(R.string.port_http)

        httpsSwitch.setOnCheckedChangeListener { _, checked ->
            updateProtocolLabels()
            if (suppressSwitchEvent) return@setOnCheckedChangeListener
            val text = addressInput.text?.toString()?.trim().orEmpty()
            if (text.isEmpty()) return@setOnCheckedChangeListener
            val moved = if (checked) {
                replaceDefaultPort(text, AddressParser.DEFAULT_HTTP_PORT, AddressParser.DEFAULT_HTTPS_PORT)
            } else {
                replaceDefaultPort(text, AddressParser.DEFAULT_HTTPS_PORT, AddressParser.DEFAULT_HTTP_PORT)
            }
            if (moved != null) addressInput.setText(moved)
        }

        connectButton.setOnClickListener { doConnect() }
        findViewById<View>(R.id.scan_button).setOnClickListener { requestScan() }
        findViewById<Button>(R.id.error_retry).setOnClickListener {
            val target = current
            if (target != null) connect(target) else doConnect()
        }
        findViewById<Button>(R.id.error_change).setOnClickListener { showConnectScreen() }

        addressInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_GO || actionId == EditorInfo.IME_ACTION_DONE) {
                doConnect()
                true
            } else {
                false
            }
        }
    }

    private fun updateProtocolLabels() {
        val https = httpsSwitch.isChecked
        protocolLabel.setText(if (https) R.string.protocol_https else R.string.protocol_http)
        portHint.setText(if (https) R.string.port_https else R.string.port_http)
    }

    private fun replaceDefaultPort(text: String, from: Int, to: Int): String? {
        val token = ":$from"
        val index = text.lastIndexOf(token)
        if (index < 0) return null
        val after = text.substring(index + token.length)
        if (after.isNotEmpty() && after != "/" && !after.startsWith("?") && !after.startsWith("#")) return null
        return text.substring(0, index) + ":$to" + after
    }

    private fun fillEndpoint(endpoint: Endpoint) {
        addressInput.setText(endpoint.display())
        setHttpsCheckedSilently(endpoint.isHttps)
    }

    private fun setHttpsCheckedSilently(checked: Boolean) {
        suppressSwitchEvent = true
        httpsSwitch.isChecked = checked
        suppressSwitchEvent = false
        updateProtocolLabels()
    }

    private fun doConnect() {
        val raw = addressInput.text?.toString().orEmpty()
        when (val parsed = AddressParser.parse(raw, httpsSwitch.isChecked)) {
            is AddressResult.Success -> {
                hideKeyboard()
                fillEndpoint(parsed.endpoint)
                connect(parsed.endpoint)
            }
            is AddressResult.Error -> showInlineError(parsed.message)
        }
    }

    private fun showInlineError(message: String) {
        connectStatus.visibility = View.VISIBLE
        connectStatus.setTextColor(ContextCompat.getColor(this, R.color.aster_error))
        connectStatus.text = message
        addressInput.requestFocus()
    }

    private fun connect(endpoint: Endpoint, pair: String? = endpoint.pair) {
        current = endpoint
        prefs.saveEndpoint(endpoint.copy(pair = null))
        pageFailed = false
        lastThemeKey = ""
        errorView.visibility = View.GONE
        connectView.visibility = View.GONE
        webLayer.visibility = View.VISIBLE
        progressBar.visibility = View.VISIBLE
        applyShellColors(
            ContextCompat.getColor(this, R.color.aster_bg),
            lightSystemBars = false,
        )
        connectStatus.visibility = View.VISIBLE
        connectStatus.setTextColor(ContextCompat.getColor(this, R.color.aster_muted))
        connectStatus.text = getString(R.string.status_connecting, endpoint.display())
        ui.removeCallbacks(timeoutRunnable)
        ui.postDelayed(timeoutRunnable, LOAD_TIMEOUT_MS)
        val url = if (pair.isNullOrEmpty()) "${endpoint.origin()}/" else endpoint.copy(pair = pair).browseUrl()
        try {
            webView.loadUrl(url)
        } catch (error: Exception) {
            Log.w(TAG, "loadUrl failed", error)
            pageFailed = true
            showError(
                getString(R.string.error_title_connect),
                getString(R.string.address_invalid),
                endpoint.origin(),
            )
        }
    }

    private fun showConnectScreen() {
        ui.removeCallbacks(timeoutRunnable)
        ui.removeCallbacks(themeRunnable)
        lastThemeKey = ""
        errorView.visibility = View.GONE
        progressBar.visibility = View.GONE
        webLayer.visibility = View.GONE
        connectView.visibility = View.VISIBLE
        applyShellColors(
            ContextCompat.getColor(this, R.color.aster_bg),
            lightSystemBars = false,
        )
        try {
            // 保留已加载的页面与 SSE 连接；真正重新连接时再由 connect() 加载。
            webView.stopLoading()
        } catch (_: Exception) {
            // ignore
        }
        val saved = prefs.endpoint()
        current = saved
        if (saved != null) {
            fillEndpoint(saved)
            connectStatus.visibility = View.VISIBLE
            connectStatus.setTextColor(ContextCompat.getColor(this, R.color.aster_muted))
            connectStatus.text = getString(R.string.status_last, saved.display())
        } else {
            connectStatus.visibility = View.GONE
        }
    }

    private fun showError(title: String, detail: String, address: String?) {
        ui.removeCallbacks(timeoutRunnable)
        ui.removeCallbacks(themeRunnable)
        errorTitle.text = title
        errorDetail.text = detail
        if (address.isNullOrBlank()) {
            errorAddress.visibility = View.GONE
        } else {
            errorAddress.visibility = View.VISIBLE
            errorAddress.text = address
        }
        progressBar.visibility = View.GONE
        errorView.visibility = View.VISIBLE
        webLayer.visibility = View.VISIBLE
        connectView.visibility = View.GONE
        applyShellColors(
            ContextCompat.getColor(this, R.color.aster_bg),
            lightSystemBars = false,
        )
    }

    private fun startThemePolling() {
        ui.removeCallbacks(themeRunnable)
        ui.post(themeRunnable)
    }

    private fun applyThemeFromProbe(raw: String?) {
        if (raw.isNullOrBlank()) return
        val text = raw.trim().removeSurrounding("\"")
        if (text.isEmpty() || text == lastThemeKey) return
        val parts = text.split('|', limit = 2)
        val background = parseCssColor(parts.getOrNull(1)) ?: return
        lastThemeKey = text
        val opaque = Color.rgb(
            Color.red(background),
            Color.green(background),
            Color.blue(background),
        )
        val lightBars = Color.luminance(opaque) > 0.55f
        applyShellColors(opaque, lightBars)
    }

    private fun parseCssColor(value: String?): Int? {
        val text = value?.trim().orEmpty()
        if (text.isEmpty()) return null
        if (text.startsWith("#")) {
            return try {
                Color.parseColor(text)
            } catch (_: IllegalArgumentException) {
                null
            }
        }
        val match = RGBA_PATTERN.find(text) ?: return null
        val r = match.groupValues[1].toIntOrNull()?.coerceIn(0, 255) ?: return null
        val g = match.groupValues[2].toIntOrNull()?.coerceIn(0, 255) ?: return null
        val b = match.groupValues[3].toIntOrNull()?.coerceIn(0, 255) ?: return null
        val a = match.groupValues[4].toFloatOrNull()?.let { (it * 255f).toInt().coerceIn(0, 255) } ?: 255
        return Color.argb(a, r, g, b)
    }

    private fun applyShellColors(background: Int, lightSystemBars: Boolean) {
        root.setBackgroundColor(background)
        webView.setBackgroundColor(background)
        val controller = WindowInsetsControllerCompat(window, root)
        controller.isAppearanceLightStatusBars = lightSystemBars
        controller.isAppearanceLightNavigationBars = lightSystemBars
        if (Build.VERSION.SDK_INT >= 29) {
            window.isStatusBarContrastEnforced = false
            window.isNavigationBarContrastEnforced = false
        }
    }

    private fun routeNavigation(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return false
        if (scheme == "http" || scheme == "https") {
            if (isInternalNavigation(uri)) return false
            openExternal(uri)
            return true
        }
        if (scheme == "about" || scheme == "blob") return false
        return openExternalScheme(uri)
    }

    /**
     * Aster 网页的 HTTPS 开关会整页跳到电脑端计算出的 LAN IP（可能和用户输入的 IP 不同）。
     * 只要目标是内网地址且端口属于 Aster 常见端口，就留在 WebView 内；
     * 其余 http(s) 链接交给系统浏览器。
     */
    private fun isInternalNavigation(uri: Uri): Boolean {
        val host = uri.host ?: return false
        if (current?.host.equals(host, ignoreCase = true)) return true
        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return false
        if (scheme != "http" && scheme != "https") return false
        val port = uri.port
        val knownPorts = mutableSetOf(
            AddressParser.DEFAULT_HTTP_PORT,
            AddressParser.DEFAULT_HTTPS_PORT,
        )
        current?.let { endpoint ->
            knownPorts.add(endpoint.port)
            if (endpoint.port > 1) knownPorts.add(endpoint.port - 1)
            if (endpoint.port < 65535) knownPorts.add(endpoint.port + 1)
        }
        if (port !in knownPorts) return false
        // 电脑的 TLS 端口可能由服务端按 LAN IP 重新拼接；带 6 位 pair 参数的切换也应留在壳内。
        val pair = uri.getQueryParameter("pair")
        if (pair != null && pair.length == 6 && pair.all { it.isDigit() }) return true
        return isPrivateHost(host)
    }

    private fun isPrivateHost(host: String): Boolean {
        val normalized = host.removePrefix("[").removeSuffix("]").lowercase(Locale.ROOT)
        if (normalized == "localhost" || normalized == "::1") return true
        if (normalized.contains(':')) {
            return normalized.startsWith("fe80:") ||
                normalized.startsWith("fc") ||
                normalized.startsWith("fd")
        }
        val parts = normalized.split('.')
        if (parts.size != 4) return false
        val numbers = IntArray(4)
        for (index in parts.indices) {
            numbers[index] = parts[index].toIntOrNull() ?: return false
            if (numbers[index] !in 0..255) return false
        }
        return numbers[0] == 10 ||
            numbers[0] == 127 ||
            (numbers[0] == 192 && numbers[1] == 168) ||
            (numbers[0] == 172 && numbers[1] in 16..31) ||
            (numbers[0] == 169 && numbers[1] == 254) ||
            (numbers[0] == 100 && numbers[1] in 64..127)
    }

    private fun openPopupWindow(resultMsg: Message?): Boolean {
        if (resultMsg == null) return false
        val transport = resultMsg.obj as? WebView.WebViewTransport ?: return false
        val popup = WebView(this)
        popup.setBackgroundColor(ContextCompat.getColor(this, R.color.aster_bg))
        popup.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                val scheme = uri.scheme?.lowercase(Locale.ROOT)
                if (scheme == "http" || scheme == "https") {
                    if (isInternalNavigation(uri)) {
                        webView.loadUrl(uri.toString())
                    } else {
                        openExternal(uri)
                    }
                } else if (scheme != null && scheme != "about" && scheme != "blob") {
                    openExternalScheme(uri)
                }
                view.stopLoading()
                cleanupPopup(view)
                return true
            }
        }
        tempWindow = popup
        root.addView(
            popup,
            FrameLayout.LayoutParams(1, 1),
        )
        transport.webView = popup
        resultMsg.sendToTarget()
        ui.postDelayed({
            if (tempWindow === popup) cleanupPopup(popup)
        }, POPUP_TIMEOUT_MS)
        return true
    }

    private fun cleanupPopup(view: WebView) {
        if (tempWindow === view) tempWindow = null
        (view.parent as? android.view.ViewGroup)?.removeView(view)
        try {
            view.destroy()
        } catch (_: Exception) {
            // ignore
        }
    }

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: ActivityNotFoundException) {
            toast(R.string.external_link_failed)
        } catch (_: Exception) {
            toast(R.string.external_link_failed)
        }
    }

    private fun openExternalScheme(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return true
        if (scheme == "intent") {
            try {
                startActivity(Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME))
            } catch (_: Exception) {
                toast(R.string.external_link_failed)
            }
            return true
        }
        if (scheme == "javascript" || scheme == "file" || scheme == "content") return true
        openExternal(uri)
        return true
    }

    // ------------------------------------------------------------------ 扫码

    /**
     * 启动后自动进扫码页；取消或拒绝相机权限后留在连接页。
     * onNewIntent（从桌面图标再次打开）也会重置为扫码优先。
     */
    private fun autoScanIfPossible() {
        if (autoScanTriggered) return
        autoScanTriggered = true
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)) return
        root.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            if (webLayer.visibility == View.VISIBLE) return@postDelayed
            if (connectView.visibility != View.VISIBLE) return@postDelayed
            requestScan()
        }, AUTO_SCAN_DELAY_MS)
    }

    private fun requestScan() {
        if (scanRequestInFlight) return
        scanRequestInFlight = true
        hideKeyboard()
        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            launchScanner()
        } else {
            requestPermissions(arrayOf(android.Manifest.permission.CAMERA), REQ_CAMERA)
        }
    }

    private fun launchScanner() {
        try {
            IntentIntegrator(this)
                .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                .setPrompt("")
                .setBeepEnabled(false)
                .setOrientationLocked(true)
                .setBarcodeImageEnabled(false)
                .setCaptureActivity(QrScanActivity::class.java)
                .initiateScan()
        } catch (error: Exception) {
            scanRequestInFlight = false
            Log.w(TAG, "scanner failed", error)
            toast(R.string.file_picker_failed)
        }
    }

    private fun handleScanResult(contents: String?) {
        if (contents.isNullOrBlank()) {
            toast(R.string.qr_cancelled)
            return
        }
        if (!contents.contains("://") && !contents.contains('.') && !contents.contains(':')) {
            toast(R.string.qr_invalid)
            return
        }
        when (val parsed = AddressParser.parse(contents, httpsSwitch.isChecked)) {
            is AddressResult.Success -> {
                fillEndpoint(parsed.endpoint)
                connect(parsed.endpoint)
            }
            is AddressResult.Error -> toastMessage(parsed.message.ifBlank { getString(R.string.qr_invalid) })
        }
    }

    // ------------------------------------------------------------------ 上传

    private fun openFileChooser(
        callback: ValueCallback<Array<Uri>>?,
        params: WebChromeClient.FileChooserParams?,
    ): Boolean {
        pendingFileCallback?.onReceiveValue(null)
        pendingFileCallback = callback
        if (callback == null || params == null) {
            pendingFileCallback = null
            return false
        }
        return try {
            // compileSdk 35 的 android.jar 尚未公开 MODE_OPEN_FOLDER（值为 2，API 36 文档已列出）。
            // WebView 在支持 <input webkitdirectory> 时会回传 2；否则按普通文件选择处理。
            if (params.mode == MODE_OPEN_FOLDER) {
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                    addFlags(
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                            Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
                    )
                }
                startActivityForResult(intent, REQ_FOLDER)
            } else {
                val acceptTypes = params.acceptTypes
                    ?.filter { it.isNotBlank() && it != "*/*" }
                    .orEmpty()
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    if (params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    }
                    if (acceptTypes.size == 1) {
                        type = acceptTypes.first()
                    } else {
                        type = "*/*"
                        if (acceptTypes.size > 1) {
                            putExtra(Intent.EXTRA_MIME_TYPES, acceptTypes.toTypedArray())
                        }
                    }
                }
                startActivityForResult(intent, REQ_FILE)
            }
            true
        } catch (error: Exception) {
            Log.w(TAG, "file chooser failed", error)
            pendingFileCallback?.onReceiveValue(null)
            pendingFileCallback = null
            toast(R.string.file_picker_failed)
            false
        }
    }

    private fun collectTreeFiles(treeUri: Uri): List<Uri> {
        val result = ArrayList<Uri>()
        try {
            val rootId = DocumentsContract.getTreeDocumentId(treeUri)
            walkTree(
                treeUri,
                DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, rootId),
                result,
                0,
            )
        } catch (error: Exception) {
            Log.w(TAG, "collectTreeFiles failed", error)
        }
        return result
    }

    private fun walkTree(treeUri: Uri, childrenUri: Uri, result: MutableList<Uri>, depth: Int) {
        if (depth > MAX_FOLDER_DEPTH || result.size >= MAX_FOLDER_FILES) return
        try {
            contentResolver.query(
                childrenUri,
                arrayOf(
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_MIME_TYPE,
                ),
                null,
                null,
                null,
            )?.use { cursor ->
                while (cursor.moveToNext() && result.size < MAX_FOLDER_FILES) {
                    val documentId = cursor.getString(0) ?: continue
                    val mimeType = cursor.getString(1)
                    if (mimeType == DocumentsContract.Document.MIME_TYPE_DIR) {
                        walkTree(
                            treeUri,
                            DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, documentId),
                            result,
                            depth + 1,
                        )
                    } else {
                        result.add(DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId))
                    }
                }
            }
        } catch (error: Exception) {
            Log.w(TAG, "walkTree failed", error)
        }
    }

    // ------------------------------------------------------------------ 下载

    private fun handleDownload(
        url: String,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        val uri = try {
            Uri.parse(url)
        } catch (_: Exception) {
            toast(R.string.download_unavailable)
            return
        }
        val scheme = uri.scheme?.lowercase(Locale.ROOT)
        if (scheme != "http" && scheme != "https") {
            toast(R.string.download_unavailable)
            return
        }
        val host = uri.host
        if (host != null && current?.host != null && !current!!.host.equals(host, ignoreCase = true)) {
            openExternal(uri)
            return
        }

        val headerName = DownloadNames.fromDisposition(contentDisposition)
        val guessed = headerName ?: try {
            URLUtil.guessFileName(url, contentDisposition, mimeType)
        } catch (_: Exception) {
            null
        }
        val filename = DownloadNames.sanitize(guessed ?: "Aster-download")
        val mime = mimeType?.takeIf { it.isNotBlank() } ?: "application/octet-stream"
        val key = current?.let { "${it.host}:${it.port}" } ?: "${uri.host}:${uri.port}"
        val pin = if (scheme == "https") prefs.approvedCertificate(key) else null
        val job = PendingDownload(
            url = url,
            filename = filename,
            mime = mime,
            pin = pin,
            // 电脑发手机和手机发电脑都走同一个网页链路。HTTP 也使用自研前台下载服务：
            // 系统 DownloadManager 在部分机型上会先快后停/限速，且无法统一处理取消与进度。
            useService = true,
            userAgent = userAgent,
        )

        if (Build.VERSION.SDK_INT <= 28 &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.WRITE_EXTERNAL_STORAGE) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            pendingDownloads.addLast(job)
            if (!storagePermissionAsked) {
                storagePermissionAsked = true
                requestPermissions(
                    arrayOf(android.Manifest.permission.WRITE_EXTERNAL_STORAGE),
                    REQ_STORAGE,
                )
            }
            return
        }
        startDownload(job)
    }

    private fun startDownload(job: PendingDownload) {
        if (job.useService) {
            requestNotificationPermission()
            if (startDownloadService(job)) {
                toastMessage(getString(R.string.download_started, job.filename))
                return
            }
        }
        try {
            enqueueDownloadManager(job)
        } catch (error: Exception) {
            Log.w(TAG, "DownloadManager failed, fallback to service", error)
            requestNotificationPermission()
            startDownloadService(job)
        }
        toastMessage(getString(R.string.download_started, job.filename))
    }

    private fun enqueueDownloadManager(job: PendingDownload) {
        val uniqueName = DownloadNames.uniqueName(this, job.filename)
        val request = DownloadManager.Request(Uri.parse(job.url))
            .setTitle(uniqueName)
            .setMimeType(job.mime)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(
                Environment.DIRECTORY_DOWNLOADS,
                "Aster/$uniqueName",
            )
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(true)
        job.userAgent?.takeIf { it.isNotBlank() }?.let {
            request.addRequestHeader("User-Agent", it)
        }
        CookieManager.getInstance().getCookie(job.url)?.let {
            request.addRequestHeader("Cookie", it)
        }
        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        manager.enqueue(request)
    }

    private fun startDownloadService(job: PendingDownload): Boolean {
        val intent = Intent(this, DownloadService::class.java).apply {
            putExtra(DownloadService.EXTRA_URL, job.url)
            putExtra(DownloadService.EXTRA_FILENAME, job.filename)
            putExtra(DownloadService.EXTRA_MIME, job.mime)
            putExtra(DownloadService.EXTRA_PIN, job.pin)
            putExtra(DownloadService.EXTRA_USER_AGENT, job.userAgent)
        }
        return try {
            ContextCompat.startForegroundService(this, intent)
            true
        } catch (error: Exception) {
            Log.w(TAG, "startForegroundService failed", error)
            false
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED &&
            !notificationPermissionAsked
        ) {
            notificationPermissionAsked = true
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFICATIONS)
        }
    }

    // ------------------------------------------------------------------ 证书

    private fun handleSslError(handler: SslErrorHandler, error: SslError) {
        val target = current
        if (target == null) {
            handler.cancel()
            return
        }
        val key = "${target.host}:${target.port}"
        val der = CertUtil.derBytes(error.certificate)
        val sha = der?.let { CertUtil.sha256Hex(it) }
        val approved = prefs.approvedFingerprint(key)
        if (der != null && sha != null && approved != null && sha.equals(approved, ignoreCase = true)) {
            handler.proceed()
            return
        }

        sslQueue.add(handler)
        if (sslDialog != null) return
        sslCertKey = key
        sslCertDer = der
        sslCertSha = sha
        sslCertIssuer = error.certificate?.issuedBy?.cName ?: "—"
        sslCertDisplay = target.origin()
        ui.removeCallbacks(timeoutRunnable)
        sslDialog = AlertDialog.Builder(this)
            .setTitle(R.string.ssl_dialog_title)
            .setMessage(
                getString(
                    R.string.ssl_dialog_message,
                    sslCertDisplay ?: key,
                    sslCertIssuer ?: "—",
                    sha ?: "—",
                )
            )
            .setCancelable(true)
            .setPositiveButton(R.string.ssl_dialog_continue) { _, _ -> approveSsl() }
            .setNegativeButton(R.string.ssl_dialog_cancel) { _, _ -> rejectSsl() }
            .setOnCancelListener { rejectSsl() }
            .show()
    }

    private fun approveSsl() {
        val key = sslCertKey
        val der = sslCertDer
        val sha = sslCertSha
        if (key != null && der != null && sha != null) {
            prefs.approveCertificate(
                key,
                Base64.encodeToString(der, Base64.NO_WRAP),
                sha,
            )
        }
        pageFailed = false
        errorView.visibility = View.GONE
        progressBar.visibility = View.VISIBLE
        val handlers = sslQueue.toList()
        sslQueue.clear()
        clearSslDialog()
        handlers.forEach { runCatching { it.proceed() } }
        ui.removeCallbacks(timeoutRunnable)
        ui.postDelayed(timeoutRunnable, LOAD_TIMEOUT_MS)
    }

    private fun rejectSsl() {
        val handlers = sslQueue.toList()
        sslQueue.clear()
        clearSslDialog()
        handlers.forEach { runCatching { it.cancel() } }
        pageFailed = true
        ui.removeCallbacks(timeoutRunnable)
        progressBar.visibility = View.GONE
        showError(
            getString(R.string.error_title_ssl),
            getString(R.string.error_detail_ssl),
            current?.origin(),
        )
    }

    private fun clearSslDialog() {
        sslDialog?.dismiss()
        sslDialog = null
        sslCertKey = null
        sslCertDer = null
        sslCertSha = null
        sslCertIssuer = null
        sslCertDisplay = null
    }

    // ------------------------------------------------------------------ 生命周期

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQ_FILE || requestCode == REQ_FOLDER) {
            val callback = pendingFileCallback
            pendingFileCallback = null
            if (callback == null) {
                super.onActivityResult(requestCode, resultCode, data)
                return
            }
            if (resultCode != RESULT_OK || data == null) {
                callback.onReceiveValue(null)
                return
            }
            val uris = ArrayList<Uri>()
            if (requestCode == REQ_FOLDER) {
                val tree = data.data
                if (tree != null) {
                    try {
                        contentResolver.takePersistableUriPermission(
                            tree,
                            Intent.FLAG_GRANT_READ_URI_PERMISSION,
                        )
                    } catch (error: Exception) {
                        Log.w(TAG, "persistable permission failed", error)
                    }
                    uris.addAll(collectTreeFiles(tree))
                }
            } else {
                val clip = data.clipData
                if (clip != null) {
                    for (index in 0 until clip.itemCount) {
                        clip.getItemAt(index)?.uri?.let { uris.add(it) }
                    }
                } else {
                    data.data?.let { uris.add(it) }
                }
            }
            callback.onReceiveValue(if (uris.isEmpty()) null else uris.toTypedArray())
            return
        }

        val scanResult = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (scanResult != null) {
            scanRequestInFlight = false
            handleScanResult(scanResult.contents)
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        when (requestCode) {
            REQ_CAMERA -> {
                if (granted) {
                    launchScanner()
                } else {
                    scanRequestInFlight = false
                    toast(R.string.camera_permission_required)
                }
            }
            REQ_STORAGE -> {
                storagePermissionAsked = false
                val jobs = pendingDownloads.toList()
                pendingDownloads.clear()
                if (granted) {
                    jobs.forEach { startDownload(it) }
                } else {
                    toast(R.string.storage_permission_required)
                }
            }
            REQ_NOTIFICATIONS -> {
                // 通知权限被拒绝时下载仍然继续，完成结果用 Toast 提示。
            }
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        if (intent != null &&
            intent.action == Intent.ACTION_MAIN &&
            intent.hasCategory(Intent.CATEGORY_LAUNCHER)
        ) {
            setIntent(intent)
            scanRequestInFlight = false
            autoScanTriggered = false
            showConnectScreen()
            autoScanIfPossible()
        }
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
        if (webLayer.visibility == View.VISIBLE && errorView.visibility != View.VISIBLE) {
            startThemePolling()
        }
    }

    override fun onPause() {
        ui.removeCallbacks(themeRunnable)
        webView.onPause()
        super.onPause()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webLayer.visibility == View.VISIBLE) {
            if (errorView.visibility == View.VISIBLE) {
                showConnectScreen()
                return
            }
            if (webView.canGoBack()) {
                webView.goBack()
                return
            }
            closeSheetOrShowConnect()
            return
        }
        @Suppress("DEPRECATION")
        super.onBackPressed()
    }

    /**
     * 网页内部浮层没有 history 记录；先请求页面关闭浮层，再退回连接页。
     */
    private fun closeSheetOrShowConnect() {
        if (backProbePending) return
        backProbePending = true
        webView.evaluateJavascript(BACK_PROBE_JS) { value ->
            backProbePending = false
            if (value?.trim()?.removeSurrounding("\"") != "1") {
                showConnectScreen()
            }
        }
    }

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        pendingDownloads.clear()
        pendingFileCallback?.onReceiveValue(null)
        pendingFileCallback = null
        if (sslDialog != null) {
            sslQueue.forEach { runCatching { it.cancel() } }
            sslQueue.clear()
            clearSslDialog()
        }
        try {
            webView.stopLoading()
            (webView.parent as? android.view.ViewGroup)?.removeView(webView)
            webView.destroy()
        } catch (_: Exception) {
            // ignore
        }
        super.onDestroy()
    }

    // ------------------------------------------------------------------ 工具

    private fun hideKeyboard() {
        try {
            val manager = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
            manager.hideSoftInputFromWindow(addressInput.windowToken, 0)
        } catch (_: Exception) {
            // ignore
        }
        addressInput.clearFocus()
    }

    private fun toast(resId: Int) {
        Toast.makeText(this, resId, Toast.LENGTH_SHORT).show()
    }

    private fun toastMessage(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private data class PendingDownload(
        val url: String,
        val filename: String,
        val mime: String,
        val pin: String?,
        val useService: Boolean,
        val userAgent: String?,
    )

    companion object {
        private const val TAG = "AsterMain"
        private const val LOAD_TIMEOUT_MS = 15_000L
        private const val THEME_POLL_MS = 1_500L
        private const val AUTO_SCAN_DELAY_MS = 180L
        private const val POPUP_TIMEOUT_MS = 3_000L
        private const val MAX_FOLDER_FILES = 2_000
        private const val MAX_FOLDER_DEPTH = 24
        private const val MODE_OPEN_FOLDER = 2
        private const val REQ_FILE = 1001
        private const val REQ_FOLDER = 1002
        private const val REQ_STORAGE = 2001
        private const val REQ_CAMERA = 2002
        private const val REQ_NOTIFICATIONS = 2003

        private val THEME_PROBE_JS =
            "(function(){try{var h=document.documentElement;" +
                "var b=getComputedStyle(document.body).backgroundColor;" +
                "if(!b||b==='rgba(0, 0, 0, 0)')b=getComputedStyle(h).backgroundColor;" +
                "return (h.getAttribute('data-theme')||'')+'|'+b;}catch(e){return '|';}})()"

        private val BACK_PROBE_JS =
            "(function(){try{if(document.body&&document.body.classList.contains('sheet-open')){" +
                "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));" +
                "return '1';}return '0';}catch(e){return '0';}})()"

        private val RGBA_PATTERN =
            Regex("rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)(?:\\s*,\\s*([0-9.]+))?\\s*\\)")
    }
}
