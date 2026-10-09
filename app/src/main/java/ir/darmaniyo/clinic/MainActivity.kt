package ir.darmaniyo.clinic

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
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
import java.util.zip.ZipInputStream

class MainActivity : AppCompatActivity() {

    companion object {
        @Volatile private var serverStarted = false
        private const val HOME = "http://127.0.0.1:8000/"
    }

    private lateinit var webView: WebView
    private lateinit var status: TextView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private lateinit var lockView: View
    private var authenticating = false
    private var lastStop = 0L

    private val fileChooser =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            fileCallback?.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
            )
            fileCallback = null
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this)
        webView = WebView(this).apply {
            visibility = View.INVISIBLE
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.cacheMode = WebSettings.LOAD_DEFAULT
            settings.setSupportZoom(false)
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url
                    if (url.host == "127.0.0.1" || url.host == "localhost") return false
                    startActivity(Intent(Intent.ACTION_VIEW, url))
                    return true
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams
                ): Boolean {
                    fileCallback?.onReceiveValue(null)
                    fileCallback = callback
                    return try {
                        fileChooser.launch(params.createIntent())
                        true
                    } catch (e: Exception) {
                        fileCallback = null
                        false
                    }
                }
            }
        }
        status = TextView(this).apply {
            text = "در حال راه‌اندازی درمانیو…\nبار اول چند ثانیه طول می‌کشد"
            textSize = 16f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#082F46"))
        }
        root.addView(webView, FrameLayout.LayoutParams(-1, -1))
        root.addView(status, FrameLayout.LayoutParams(-1, -1))
        lockView = buildLockView()
        root.addView(lockView, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        showLock()

        startServerOnce()
        waitForServer()
    }

    private fun startServerOnce() {
        if (serverStarted) return
        serverStarted = true
        val work = File(filesDir, "clinic")
        copyAssetsIfNeeded(work)
        val db = File(filesDir, "clinic.db").absolutePath
        Thread {
            try {
                Python.getInstance().getModule("server")
                    .callAttr("start", work.absolutePath, db)
            } catch (e: Throwable) {
                serverStarted = false
                runOnUiThread { status.text = "خطا در راه‌اندازی:\n${e.message}" }
            }
        }.start()
    }

    private fun waitForServer() {
        Thread {
            repeat(240) {
                try {
                    val c = URL(HOME + "login").openConnection() as HttpURLConnection
                    c.connectTimeout = 800
                    c.readTimeout = 800
                    if (c.responseCode in 200..399) {
                        runOnUiThread {
                            webView.loadUrl(HOME)
                            webView.visibility = View.VISIBLE
                            status.visibility = View.GONE
                        }
                        return@Thread
                    }
                } catch (_: Exception) {
                }
                Thread.sleep(500)
            }
            runOnUiThread { status.text = "سرور برنامه بالا نیامد. برنامه را ببندید و دوباره باز کنید." }
        }.start()
    }

    // templates و static از clinic.zip داخل APK به حافظه برنامه باز می‌شوند (فقط وقتی نسخه عوض شود)
    private fun copyAssetsIfNeeded(work: File) {
        val version = packageManager.getPackageInfo(packageName, 0).versionName ?: "0"
        val marker = File(work, ".version")
        if (marker.exists() && marker.readText() == version) return
        // فایل‌های آپلودشده کاربران (static/uploads) هنگام به‌روزرسانی پاک نمی‌شوند
        File(work, "templates").deleteRecursively()
        File(work, "static").listFiles()?.filter { it.name != "uploads" }?.forEach { it.deleteRecursively() }
        work.mkdirs()
        unzipAsset("clinic.zip", work)
        File(work, "static/uploads").mkdirs()
        marker.writeText(version)
    }

    private fun unzipAsset(name: String, dest: File) {
        assets.open(name).use { raw ->
            ZipInputStream(raw).use { zis ->
                var entry = zis.nextEntry
                while (entry != null) {
                    val out = File(dest, entry.name)
                    if (!out.canonicalPath.startsWith(dest.canonicalPath)) throw SecurityException("bad zip entry")
                    if (entry.isDirectory) {
                        out.mkdirs()
                    } else {
                        out.parentFile?.mkdirs()
                        FileOutputStream(out).use { zis.copyTo(it) }
                    }
                    entry = zis.nextEntry
                }
            }
        }
    }

    // ---------- قفل با اثر انگشت ----------
    // اگر روی گوشی اثر انگشت/قفل صفحه تنظیم نشده باشد، قفلی اعمال نمی‌شود تا کاربر بیرون نماند.
    private fun authenticators(): Int =
        if (Build.VERSION.SDK_INT >= 30)
            BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        else
            BiometricManager.Authenticators.BIOMETRIC_WEAK

    private fun canLock(): Boolean =
        BiometricManager.from(this).canAuthenticate(authenticators()) == BiometricManager.BIOMETRIC_SUCCESS

    private fun buildLockView(): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#082F46"))
            isClickable = true // لمس‌ها به صفحه زیرین نرسد
            visibility = View.GONE
            setPadding(48, 48, 48, 48)
        }
        box.addView(TextView(this).apply {
            text = "درمانیو"
            textSize = 26f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
        })
        box.addView(TextView(this).apply {
            text = "برنامه قفل است"
            textSize = 15f
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#B8CDDC"))
            setPadding(0, 12, 0, 36)
        })
        box.addView(Button(this).apply {
            text = "باز کردن با اثر انگشت"
            setOnClickListener { promptAuth() }
        })
        return box
    }

    private fun showLock() {
        lockView.visibility = if (canLock()) View.VISIBLE else View.GONE
    }

    private fun promptAuth() {
        if (authenticating || lockView.visibility != View.VISIBLE) return
        authenticating = true
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("درمانیو")
            .setSubtitle("برای ورود، انگشت خود را روی حسگر بگذارید")
            .setAllowedAuthenticators(authenticators())
            .apply { if (Build.VERSION.SDK_INT < 30) setNegativeButtonText("انصراف") }
            .build()
        BiometricPrompt(this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    authenticating = false
                    lockView.visibility = View.GONE
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    authenticating = false // قفل می‌ماند؛ با دکمه می‌شود دوباره تلاش کرد
                }
            }).authenticate(info)
    }

    override fun onResume() {
        super.onResume()
        if (lockView.visibility == View.VISIBLE) promptAuth()
    }

    override fun onStop() {
        super.onStop()
        lastStop = SystemClock.elapsedRealtime()
    }

    override fun onStart() {
        super.onStart()
        // بعد از بیش از ۳۰ ثانیه در پس‌زمینه بودن، دوباره قفل شود
        if (lastStop > 0 && SystemClock.elapsedRealtime() - lastStop > 30_000) showLock()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (lockView.visibility == View.VISIBLE) { moveTaskToBack(true); return }
        // اگر منوی کشویی باز است، اول همان بسته شود
        webView.evaluateJavascript(
            "(function(){return !!(window.closeMenuIfOpen && window.closeMenuIfOpen());})()"
        ) { closed ->
            if (closed != "true") {
                if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
            }
        }
    }
}
