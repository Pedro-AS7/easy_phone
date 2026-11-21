import java.util.zip.ZipFile

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "dev.pedro.lmphone"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.pedro.lmphone"
        minSdk = 34
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        // Só a biblioteca nativa do onnxruntime do S23+ (sem ela, as quatro arquiteturas somam dezenas de MB no APK).
        ndk { abiFilters += "arm64-v8a" }
    }

    // Duas variantes do mesmo app (docs/plano-play-store.md): `completo`, a de sempre (o agente age, o PC pelo adb,
    // depuração), e `loja`, a da Play Store, que só ensina. O que a loja não pode ter fica em src/completo/.
    flavorDimensions += "versao"
    productFlavors {
        create("completo") {
            dimension = "versao"
            buildConfigField("String", "SERVIDOR", "\"\"")
        }
        create("loja") {
            dimension = "versao"
            // Provisório (decisão do Pedro, 2026-11-16): o definitivo vem antes da fase 5; depois de publicado, não muda.
            applicationId = "dev.pedro.lmphone.guia"
            // O servidor do provedor (servidor/). Sem `-PservidorLoja=https://.../v1`, o do PC pelo
            // `adb reverse tcp:8792 tcp:8792` (só o build de depuração aceita HTTP sem TLS, e só em 127.0.0.1).
            val servidor = (project.findProperty("servidorLoja") as String?) ?: "http://127.0.0.1:8792/v1"
            buildConfigField("String", "SERVIDOR", "\"$servidor\"")
        }
    }

    buildTypes {
        release {
            // A loja publica o build minificado; as regras do onnxruntime ficam em proguard-rules.pro.
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    // Os modelos pequenos da loja chegam pela Play num pacote de recursos (docs/plano-play-store.md, fase 3).
    assetPacks += listOf(":modelos_pack")
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.06.01")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation(project(":modelos"))
    implementation(project(":cerebro"))
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.31.0")  // a mesma versão do .venv-modelo
    "lojaImplementation"("com.google.android.play:asset-delivery:2.2.2")  // os modelos pelo pacote de recursos da Play
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}

// A conferência da variante `loja` (docs/plano-play-store.md): o código e os recursos que ela compila não podem ter
// nenhuma API de ação da acessibilidade. Roda antes de todo build da `loja`; uma ocorrência faz o build falhar.
val forbidden = listOf("dispatchGesture", "GestureDescription", "performAction", "performGlobalAction", "ACTION_SET_TEXT",
    "canPerformGestures", "canTakeScreenshot", "takeScreenshot", "switchToInputMethod", "flagInputMethodEditor",
    "WRITE_SECURE_SETTINGS", "PACKAGE_USAGE_STATS", "QUERY_ALL_PACKAGES", "READ_CONTACTS", "ACCESS_FINE_LOCATION")
val conferirLoja by tasks.registering {
    group = "verification"
    description = "Falha se a variante loja compila alguma API de ação da acessibilidade ou permissão que ela não pode ter."
    val roots = listOf("src/main", "src/loja", "src/lojaDebug", "src/lojaRelease").map { file(it) }
    inputs.files(roots.map { fileTree(it) })
    doLast {
        val hits = roots.filter { it.exists() }.flatMap { root ->
            root.walkTopDown().filter { it.isFile && it.extension in setOf("kt", "java", "xml") }.flatMap { source ->
                source.readLines().withIndex()
                    .filter { (_, line) -> !line.trimStart().startsWith("//") && !line.trimStart().startsWith("*") }
                    .flatMap { (n, line) -> forbidden.filter { it in line }.map { "${source.relativeTo(projectDir)}:${n + 1}: $it" } }
            }
        }
        if (hits.isNotEmpty()) throw GradleException("A variante loja não pode agir no aparelho:\n" + hits.joinToString("\n"))
        println("conferirLoja: nenhuma API de ação nem permissão proibida em ${roots.count { it.exists() }} pastas")
    }
}
tasks.matching { it.name.startsWith("preLoja") && it.name.endsWith("Build") }.configureEach { dependsOn(conferirLoja) }

// A mesma conferência no APK pronto (o código das bibliotecas também entra): nenhum método de agir em outro app. O
// `performAction` não entra aqui: o Compose o usa para receber ações de leitores de tela nas telas do próprio app.
val forbiddenInApk = listOf("dispatchGesture", "GestureDescription", "performGlobalAction", "takeScreenshot", "switchToInputMethod")
afterEvaluate {
    tasks.matching { it.name.startsWith("assembleLoja") }.configureEach {
        doLast {
            fileTree(layout.buildDirectory.dir("outputs/apk")).matching { include("loja/**/*.apk") }.forEach { apk ->
                val found = ZipFile(apk).use { zip ->
                    zip.entries().toList().filter { it.name.endsWith(".dex") }.flatMap { entry ->
                        val text = String(zip.getInputStream(entry).readBytes(), Charsets.ISO_8859_1)
                        forbiddenInApk.filter { it in text }
                    }.distinct()
                }
                if (found.isNotEmpty()) throw GradleException("O APK da loja tem método de agir em outro app: $found (${apk.name})")
                println("conferirLoja: ${apk.name} sem ${forbiddenInApk.joinToString(", ")}")
            }
        }
    }
}
