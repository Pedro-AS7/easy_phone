// Os modelos pequenos do app da loja (docs/plano-play-store.md, fase 3), num pacote de recursos da Play (Play Asset
// Delivery, "fast-follow"): a Play os baixa sozinha logo depois de instalar o app, e eles ficam como arquivos comuns
// no aparelho (o onnxruntime os abre pelo caminho). Os arquivos vêm de data/modelos/ (fora do git), com os nomes que o
// app lê, os mesmos que `tools.app.modelos enviar` copia pelo adb na variante completo.
plugins {
    id("com.android.asset-pack")
}

assetPack {
    packName.set("modelos")
    dynamicDelivery {
        deliveryType.set("fast-follow")
    }
}

val data = rootProject.file("../data/modelos")
// O pacote lê src/main/assets/ (o único lugar que o plugin aceita): os modelos são copiados para lá antes de empacotar,
// e a pasta fica fora do git (.gitignore).
val assets = file("src/main/assets/modelos")
val prepararModelos by tasks.registering(Copy::class) {
    description = "Junta os modelos pequenos e o tokenizador do app no pacote de recursos."
    from(data.resolve("marcacao/modelo-tabela.onnx")) { rename { "marcacao.onnx" } }
    from(data.resolve("marcacao/modelo.json")) { rename { "marcacao.json" } }
    from(data.resolve("escolha/modelo-tabela.onnx")) { rename { "escolha.onnx" } }
    from(data.resolve("escolha/modelo.json")) { rename { "escolha.json" } }
    from(data.resolve("app/tokenizador.bin"))
    into(assets)
}
tasks.configureEach { if (name != "prepararModelos" && name != "clean") dependsOn(prepararModelos) }
