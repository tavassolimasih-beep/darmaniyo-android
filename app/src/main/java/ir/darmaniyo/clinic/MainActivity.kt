package ir.darmaniyo.clinic

import android.annotation.SuppressLint
import android.content.res.AssetManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.view.Gravity
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.chaquo.python.Python
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    companion object {
        @Volatile private var serverStarted = false
        private const val HOME = "http://127.0.0.1:8000/"
        private const val TAG = "Darmaniyo"
    }

    private lateinit var webView: WebView
    private lateinit var status: TextView
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val callback = fileCallback ?: return@registerForActivityResult
            fileCallback = null
            if (result.resultCode != RESULT_OK) {
                callback.onReceiveValue(null)
                return@registerForActivityResult
            }
            val data = result.data
            val uris: Array<Uri>? = when {
                data?.clipData != null -> {
                    val clip = data.clipData!!
                    Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
                }
                data?.data != null -> arrayOf(data.data!!)
                else -> null
            }
            callback.onReceiveValue(uris)
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // --- UI برنامه‌ای ---
        val root = FrameLayout(this)
        webView = WebView(this)
        root.addView(
            webView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        status = TextView(this).apply {
            setBackgroundColor(0xCC000000.toInt())
            setTextColor(0xFFFFFFFF.toInt())
            text = "در حال راه‌اندازی..."
            gravity = Gravity.CENTER
            visibility = View.GONE
        }
        root.addView(
            status,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply { gravity = Gravity.BOTTOM }
        )

        setContentView(root)

        // --- تنظیمات WebView ---
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            cacheMode = WebSettings.LOAD_DEFAULT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean = false
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = filePathCallback
                return try {
                    val intent = fileChooserParams?.createIntent()
                    if (intent != null) {
                        fileChooserLauncher.launch(intent)
                        true
                    } else {
                        fileCallback = null
                        false
                    }
                } catch (e: Exception) {
                    fileCallback = null
                    false
                }
            }
        }

        authenticateThenStart()
    }

    private fun authenticateThenStart() {
        val manager = BiometricManager.from(this)
        val can = manager.canAuthenticate(
            BiometricManager.Authenticators.BIOMETRIC_WEAK or
                BiometricManager.Authenticators.DEVICE_CREDENTIAL
        )
        if (can != BiometricManager.BIOMETRIC_SUCCESS) {
            startPythonServerAndLoad()
            return
        }

        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(
                    result: BiometricPrompt.AuthenticationResult
                ) {
                    super.onAuthenticationSucceeded(result)
                    startPythonServerAndLoad()
                }

                override fun onAuthenticationError(
                    errorCode: Int,
                    errString: CharSequence
                ) {
                    super.onAuthenticationError(errorCode, errString)
                    startPythonServerAndLoad()
                }

                override fun onAuthenticationFailed() {
                    super.onAuthenticationFailed()
                }
            }
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("ورود به درمانیو")
            .setSubtitle("برای ورود، هویت خود را تأیید کنید")
            .setAllowedAuthenticators(
                BiometricManager.Authenticators.BIOMETRIC_WEAK or
                    BiometricManager.Authenticators.DEVICE_CREDENTIAL
            )
            .build()
        prompt.authenticate(info)
    }

    private fun startPythonServerAndLoad() {
        showStatus("در حال آماده‌سازی سرور...")
        Thread {
            try {
                // ۱) کپی فایل‌های اپ وب از assets به filesDir (فقط بار اول)
                val webDir = File(filesDir, "web")
                if (!webDir.exists() || webDir.list().isNullOrEmpty()) {
                    showStatus("در حال استخراج فایل‌ها...")
                    copyAssets("web", webDir)
                }

                // ۲) اجرای سرور پایتون
                if (!serverStarted) {
                    val py = Python.getInstance()
                    val module = py.getModule("server")
                    val dbPath = File(filesDir, "darmaniyo.db").absolutePath
                    module.callAttr("start", webDir.absolutePath, dbPath)
                    serverStarted = true
                }

                // ۳) انتظار برای بالا آمدن سرور
                val ok = waitForServer(20, 500)
                Log.d(TAG, "server ready=$ok")

                runOnUiThread {
                    hideStatus()
                    webView.loadUrl(HOME)
                }
            } catch (t: Throwable) {
                Log.e(TAG, "server start failed", t)
                runOnUiThread {
                    showStatus("خطا در راه‌اندازی سرور: ${t.message}")
                }
            }
        }.start()
    }

    /** چند بار تلاش می‌کند تا سرور جواب بدهد */
    private fun waitForServer(tries: Int, delayMs: Long): Boolean {
        repeat(tries) {
            if (pingServer()) return true
            SystemClock.sleep(delayMs)
        }
        return false
    }

    private fun pingServer(): Boolean {
        return try {
            val conn = URL(HOME).openConnection() as HttpURLConnection
            conn.connectTimeout = 1000
            conn.readTimeout = 1000
            conn.requestMethod = "GET"
            val ok = conn.responseCode in 200..499
            conn.disconnect()
            ok
        } catch (_: Exception) {
            false
        }
    }

    /** کپی بازگشتی از assets به فایل سیستم */
    private fun copyAssets(assetPath: String, destDir: File) {
        val am: AssetManager = assets
        val children = am.list(assetPath) ?: emptyArray()
        if (children.isEmpty()) {
            // فایل
            destDir.parentFile?.mkdirs()
            am.open(assetPath).use { input ->
                FileOutputStream(destDir).use { output -> input.copyTo(output) }
            }
        } else {
            destDir.mkdirs()
            for (child in children) {
                copyAssets("$assetPath/$child", File(destDir, child))
            }
        }
    }

    private fun showStatus(msg: String) {
        runOnUiThread {
            status.text = msg
            status.visibility = View.VISIBLE
        }
    }

    private fun hideStatus() {
        status.visibility = View.GONE
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
