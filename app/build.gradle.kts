plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "ir.darmaniyo.clinic"
    compileSdk = 34

    defaultConfig {
        applicationId = "ir.darmaniyo.clinic"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

chaquopy {
    defaultConfig {
        version = "3.8"
        pip {
            install("fastapi==0.99.1")
            install("uvicorn==0.27.1")
            install("h11==0.14.0")
            install("SQLAlchemy==2.0.35")
            install("python-multipart==0.0.9")
            install("jinja2==3.1.4")
            install("python-dotenv==1.0.1")
            install("aiofiles==23.2.1")
            install("jdatetime==5.0.0")
            install("python-jose==3.3.0")
            install("pydantic<2")
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.biometric:biometric:1.1.0")
}