# 本项目 release 不启用混淆；规则保留给后续需要时使用。
-keep class com.aster.app.** { *; }
-keep class com.journeyapps.barcodescanner.** { *; }
-keep class com.google.zxing.** { *; }
-dontwarn androidx.activity.**
-dontwarn androidx.core.**
