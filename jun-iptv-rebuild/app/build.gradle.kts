plugins {
    id("com.android.application")
}

android {
    namespace = "jp.jun.iptv"
    compileSdk = 36

    defaultConfig {
        applicationId = "jp.jun.iptv"
        minSdk = 23
        targetSdk = 36
        versionCode = 5
        versionName = "0.3.0-rebuild-alpha1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.media3:media3-exoplayer:1.11.0")
    implementation("androidx.media3:media3-exoplayer-hls:1.11.0")
    implementation("androidx.media3:media3-ui:1.11.0")
}
