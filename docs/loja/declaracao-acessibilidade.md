# Declaração da acessibilidade no Play Console (rascunho)

Fase 5 de `docs/plano-play-store.md`. O app **não** é declarado ferramenta de acessibilidade (`isAccessibilityTool`
fica de fora: o propósito principal é ensinar a usar o celular, não apoiar pessoas com deficiência).

## Descrição do uso (o formulário)

> O Guia do Celular ensina pessoas que têm dificuldade com o celular, como idosos. A pessoa pergunta como se faz algo
> ("como eu aumento a letra?"). O serviço de acessibilidade lê o texto da tela para saber onde estão os controles e
> ouve os toques da pessoa para saber que ela fez o passo. O app destaca na tela onde tocar, explica em voz alta e
> espera. **O app nunca executa ações**: o serviço não declara `canPerformGestures` nem `canTakeScreenshot`, não usa
> `dispatchGesture`, `performAction` em outros apps nem `performGlobalAction`, e não troca o teclado. Quem toca, rola e
> digita é sempre a pessoa. Abrir um app ou uma página das Configurações só acontece quando a pessoa toca num botão do
> próprio app.
>
> Sim, dados são compartilhados pela acessibilidade: o texto da tela (Interações no app), enviado ao servidor do app e
> a um provedor de IA durante um guia que a pessoa pediu, com nomes, telefones, e-mails e documentos trocados por
> dados falsos antes de sair do aparelho. Nada disso é guardado no servidor.

## Roteiro do vídeo (até 2 min, tela do celular gravada)

1. Abrir o app pela primeira vez: o aviso em destaque, ler até o fim, tocar em "Concordo, continuar".
2. Nas Configurações de acessibilidade, ligar o Guia do Celular (mostrar a descrição do serviço).
3. Voltar ao app, "Pedir ajuda agora", dizer "Como eu aumento a letra do celular?".
4. A faixa mostra "Toque no botão «Abrir as Configurações»": a pessoa toca no botão; as Configurações abrem.
5. O destaque amarelo em "Tamanho e estilo da fonte" e a explicação falada: **a pessoa toca** (deixar o dedo visível
   com "Mostrar toques" das Opções do desenvolvedor).
6. O destaque no "A" maior: a pessoa toca; "Pronto: letra maior. Para fazer de novo sozinho: …".
7. Mostrar que, sem o toque da pessoa, nada acontece (esperar uns 20 s num passo: só o lembrete).
8. Denunciar uma resposta no painel.

Deixar ligado "Mostrar toques" durante toda a gravação: o revisor vê que cada toque é de um dedo.

## Evidência técnica (para um recurso, se houver)

- `android/app/build.gradle.kts`, `conferirLoja`: o build da loja falha se o código ou os recursos tiverem uma API de
  ação ou uma permissão proibida, e se o APK pronto tiver `dispatchGesture`, `GestureDescription`,
  `performGlobalAction`, `takeScreenshot` ou `switchToInputMethod`.
- `android/app/src/loja/res/xml/accessibility.xml`: só `canRetrieveWindowContent`.
