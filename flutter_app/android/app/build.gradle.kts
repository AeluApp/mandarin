plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.aelu.aelu"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "com.aelu.aelu"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            val keystoreFile = System.getenv("AELU_KEYSTORE_FILE") ?: findProperty("AELU_KEYSTORE_FILE")?.toString()
            if (keystoreFile != null) {
                storeFile = file(keystoreFile)
                storePassword = System.getenv("AELU_KEYSTORE_PASSWORD") ?: findProperty("AELU_KEYSTORE_PASSWORD")?.toString() ?: ""
                keyAlias = System.getenv("AELU_KEY_ALIAS") ?: findProperty("AELU_KEY_ALIAS")?.toString() ?: ""
                keyPassword = System.getenv("AELU_KEY_PASSWORD") ?: findProperty("AELU_KEY_PASSWORD")?.toString() ?: ""
            }
        }
    }

    buildTypes {
        release {
            // SECURITY: Enable R8/ProGuard minification and shrinking (OWASP M9, CIS 7.1).
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // Use release signing config when a keystore is configured;
            // fall back to debug signing for local development builds.
            signingConfig = if (signingConfigs.findByName("release")?.storeFile != null) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}
