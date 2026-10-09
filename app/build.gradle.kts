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
        versionCode = 3
        versionName = "1.2"
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
        version = "3.12"
        pip {
            install("fastapi==0.115.0")
            install("uvicorn")
            install("h11")
            install("SQLAlchemy==2.0.35")
            install("python-multipart==0.0.9")
            install("jinja2")
            install("python-dotenv")
            install("aiofiles")
            install("jdatetime")
            install("python-jose")
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.biometric:biometric:1.1.0")
}
