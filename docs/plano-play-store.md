# Plano: o easy_phone na Play Store

Proposta de 2026-11-16, pedida pelo Pedro depois da decisão do tutor (`docs/plano-tutor.md`). Ao concluir uma fase,
marque aqui e leve as decisões para o `CLAUDE.md`; medições longas vão para o `historico.md`.

## Andamento (2026-11-16)

| Fase | Estado |
|---|---|
| 0. Política e decisões | Feita: decisões abaixo; trechos da política em "O que a política diz" |
| 1. Variante `loja` e executor só guia | Feita no código. Conferido no S23+ com a pessoa simulada (`tests/pessoa_loja.py`): um guia inteiro da letra, **nenhuma ação do agente** no registro. Falta o guia redondo com o Pedro (depois das correções do mesmo dia) |
| 2. Servidor do provedor | Código e testes (`servidor/`); rodou no PC com o app da loja (US$ 0,0003 a 0,001 por chamada). Falta publicar no Cloud Run (`docs/loja/publicar-servidor.md`, precisa da conta do Pedro) e a Play Integrity do lado do app (precisa do número do projeto no Google Cloud) |
| 3. Modelos pela loja | Pacote de recursos `modelos` (fast-follow, 370 MB) no AAB; build de publicação minificado (37 MB) compila. Falta: o teste interno da Play (os modelos chegando sozinhos) e o build minificado rodando no aparelho |
| 4. Primeira abertura e avisos | Tela inicial da loja com o aviso em destaque e "Concordo" antes da acessibilidade, passos grandes até o atalho dos botões de volume (a acessibilidade só durante o guia), assistente digital, microfone e avisos; denúncia de resposta no painel. Falta conferir com alguém do público |
| 5. Material da loja | Rascunhos em `docs/loja/`: política de privacidade, segurança dos dados, declaração da acessibilidade com o roteiro do vídeo, ficha da loja. Falta a página pública e o Play Console (conta do Pedro) |
| 6 e 7 | Dependem da conta de desenvolvedor do Pedro |

**O que ficou decidido (Pedro, 2026-11-16):** variante `loja` no mesmo repositório; sem contatos no cofre; sem palavra
de ativação na primeira versão; pacote e nome provisórios (`dev.pedro.lmphone.guia`, "Guia do Celular"; os
definitivos antes da fase 5); grátis com **150 pedidos por mês** por instalação; servidor no **Google Cloud Run**, com
o **OpenRouter**. Em aberto: a conta de desenvolvedor (pessoal ou de organização) e o nome definitivo.

**O que a política diz** (lida em 2026-11-16, resumo do que vale para a loja; fontes no fim):

- A acessibilidade não pode servir a um app que "autonomously initiate, plan, and execute actions or decisions";
  automação por regras fixas escritas por pessoa continua permitida. Assistentes e ferramentas de automação não são
  ferramentas de acessibilidade. O app da loja não executa nada: o código não tem como (`:app:conferirLoja`).
- `isAccessibilityTool` é só para apps cujo propósito principal é apoiar pessoas com deficiência; "Apps not eligible
  for IsAccessibilityTool may not use the flag". A loja **não** o declara.
- Fora das ferramentas de acessibilidade: aviso em destaque dentro do app, separado de outros avisos, com ação
  explícita de consentimento ("Must require affirmative user action"); sair da tela não vale como consentimento. O
  formulário da Play pergunta se dados pessoais são coletados ou compartilhados pela acessibilidade, e o vídeo tem de
  mostrar o aviso. Mudou o uso da API, preenche de novo.
- "The use of the Accessibility API must be documented in the Google Play listing" (vai na ficha).
- Conteúdo gerado por IA: "Apps that generate content using AI must contain in-app user reporting or flagging
  features", sem sair do app. O assistente conversa com a pessoa: tratamos como dentro da regra (denúncia no painel).
- Serviço em primeiro plano `specialUse`: iniciado ou percebido pela pessoa, que pode pará-lo, e só enquanto a tarefa
  dura; declaração com descrição e vídeo no Console. O `TaskService` da loja só existe durante um guia.
- Conta pessoal criada depois de 13/11/2023: teste fechado com pelo menos 12 testadores por 14 dias seguidos antes da
  produção.

## Como rodar a loja (desenvolvimento)

```sh
android/build.sh loja                                   # compila (com as duas conferências), instala e abre
LMPHONE_APP=dev.pedro.lmphone.guia .venv-modelo/bin/python -m tools.app.modelos enviar   # os modelos, no lugar do pacote da Play
PORT=8792 ARMAZEM=arquivo:data/servidor.json .venv/bin/python -m servidor.servidor        # o servidor no PC
adb reverse tcp:8792 tcp:8792                           # o app de depuração o alcança em 127.0.0.1
.venv/bin/python -m tests.pessoa_loja "Como eu aumento a letra do celular?"              # um guia, com a pessoa simulada
LMPHONE_AGIR=0 .venv/bin/python -m tests.phone_suite guia-letra --pessoa voce            # o mesmo executor só guia, pelo PC
```

A acessibilidade da loja fica ligada só durante um guia (2026-11-21, depois de o Inter bloquear o S23+ com ela ligada
o tempo todo): a pessoa liga pelo atalho dos botões de volume, e o app se desliga sozinho no fim do guia, com um app de
banco na frente ou depois de 3 min parado. Num teste: `adb shell settings put secure
accessibility_shortcut_target_service dev.pedro.lmphone.guia/dev.pedro.lmphone.AgentService` e `adb shell input
keycombination -t 3500 KEYCODE_VOLUME_UP KEYCODE_VOLUME_DOWN` (a primeira vez mostra o aviso do atalho), ou ligue pelo
adb como a suíte faz. Com o serviço desligado, um guia pede o atalho no painel e espera 60 s.

## Objetivo

Publicar na Play Store uma versão do easy_phone que **só ensina**: lê a tela, aponta onde tocar, explica e espera a
pessoa. O agente nunca toca, rola, digita nem muda um ajuste. É o guia da fase 2 do tutor ("você faz, eu aponto")
virando o produto inteiro, para quem tem dificuldade com o celular.

A regra do projeto não muda: **dado pessoal não sai do aparelho sem máscara**.

## Por que só o guia

Desde 2026-03-04, a política "Use of the AccessibilityService API" da Play proíbe o uso da acessibilidade para o app
**iniciar, planejar e executar ações sozinho**. Automação por regras fixas, escritas por uma pessoa, continua
permitida. O easy_phone que faz pela pessoa cai na proibição; ler a tela e apontar, sem executar, não cai. Assistentes e
ferramentas de automação estão na lista da Google do que **não** é ferramenta de acessibilidade.

O que resta de risco é a leitura de quem revisa: "a IA planeja os passos que a pessoa segue" pode ser lido como
planejamento por IA. O plano inteiro serve para que a resposta a essa dúvida seja verificável: o app da loja não tem
como agir, nem por erro.

## Diagnóstico do app de hoje (2026-11-16)

O que no `android/app` impede ou complica a publicação:

| Item | Onde | Problema na loja |
|---|---|---|
| Gestos, digitação e rolagem do agente | `Actions.kt`, `AgentService.kt`, `PhoneImpl.kt`; `canPerformGestures` em `res/xml/accessibility.xml` | O cerne da proibição |
| Teclado do agente | `Keyboard.kt`, `flagInputMethodEditor` | Só serve para o agente digitar |
| No guia, o agente ainda age | `executor.GUIDE_LIMIT` (padrão trocado na fase 2 do tutor), a tela que "sobe" para mostrar o controle, `set`, `open_app`, `search` | Ações iniciadas pela IA |
| Ligar a própria acessibilidade e o teclado | `WRITE_SECURE_SETTINGS` dada pelo adb | Não existe para quem instala pela loja; a pessoa tem de ligar à mão |
| App em primeiro plano (bancos) | `PACKAGE_USAGE_STATS` dada pelo adb | Permissão especial; dá para trocar pelo pacote dos eventos da acessibilidade |
| Lista de apps | `QUERY_ALL_PACKAGES` | Permissão restrita, pede declaração; `<queries>` com o filtro do lançador basta |
| Contatos para o cofre | `READ_CONTACTS` | Sensível, pede justificativa e aviso |
| Nome da rede Wi-Fi | `ACCESS_FINE_LOCATION` | Localização para ler um nome: difícil de justificar |
| Serviços de depuração | `ModelService`, `BrainService`, `WakeTest` (exportados com `DUMP`), `network.xml` com texto claro para 127.0.0.1, `LocalServer.kt` | Não vão para a versão publicada |
| Serviço em primeiro plano `specialUse` | `TaskService` ("o agente opera o celular") | A descrição é justamente a proibida; pede declaração |
| Palavra de ativação "Alexa" | `Wake.kt`, `WakeService` | Marca da Amazon; microfone sempre aberto pede declaração com vídeo |
| Chave do provedor no aparelho | `ProviderKey.kt` (vem pelo adb ou digitada) | Um idoso não cria conta no OpenRouter; a chave não pode ir no APK |
| Modelos fora do APK | `files/modelos/`, copiados pelo adb (346 MB) | Precisam chegar pela loja |
| Captura para o desfoque | `canTakeScreenshot` da acessibilidade | Mais uma capacidade a justificar, só por estética |
| Pacote `dev.pedro.lmphone`, versão 0.1, sem minificação, só arm64 | `app/build.gradle.kts` | O nome do pacote não muda depois de publicado |

## Decisões a tomar (Pedro) (tomadas em 2026-11-16: ver Andamento)

1. **Projeto separado ou variante do mesmo.** Recomendação: **variante (`productFlavor`) `loja` no mesmo
   repositório**, ao lado da `completo` de hoje. O cérebro em Kotlin é conferido contra o Python
   (`:cerebro:conferir`); um projeto separado (`easy_phone2`) teria uma cópia que se afasta a cada mudança. O que a loja
   não pode ter fica em `src/completo/`, e a variante `loja` simplesmente não o compila.
2. **Nome do pacote e da loja.** `applicationId` definitivo (por exemplo, num domínio próprio) e um nome em português
   que não lembre Google, Samsung nem Alexa.
3. **Conta de desenvolvedor: pessoal ou de organização.** A pessoal é mais simples, mas contas pessoais novas
   precisam de um **teste fechado com pelo menos 12 testadores por 14 dias seguidos** antes da produção. A de
   organização pede D-U-N-S e não tem essa exigência. A conferir na fase 0.
4. **Quem paga o provedor e como.** Grátis com limite diário, assinatura, ou chave própria (só como opção avançada).
   Ordem de grandeza: a suíte de 2026-11-16 custou cerca de US$ 0,001 por pedido com o Haiku.
5. **Contatos no cofre.** Sem `READ_CONTACTS`, a máscara fica nas regras, no modelo pequeno e nos nomes vistos na
   tela (169 de 187 pessoas só com as regras; 186 de 187 com o modelo, no conjunto congelado). Recomendação: sem
   contatos na primeira versão.
6. **Palavra de ativação na primeira versão.** Recomendação: não. A primeira versão abre pelo botão lateral
   (assistente digital), por um atalho na tela inicial e pelo ícone. A palavra própria em português ("Rudy" ou outra)
   vem numa versão seguinte, com a declaração do microfone.

## Arquitetura da variante `loja`

```
app (loja)
├── acessibilidade: só lê a árvore e ouve os toques da pessoa
│                   (sem canPerformGestures, sem teclado, sem captura)
├── faixa: destaque, seta e mão animada sobre a tela; fala; botões que a PESSOA toca
│          ("Abrir as Configurações", "Pesquisar no Google")
├── cérebro (Kotlin): modelos ONNX, máscara, executor em modo "só guia"
└── provedor: pelo servidor do easy_phone (a chave fica lá), só texto mascarado
```

Regras da variante:

- **Nenhuma ação pela acessibilidade.** O `Phone` da variante não tem `tap`, `swipe`, `type`, `key` nem `performAction`.
  O executor recebe isso como capacidade (`agir = false`) e todo passo vira passo da pessoa.
- **Abrir app, página das Configurações ou pesquisa** só por um botão que a pessoa toca na faixa ("Quer que eu abra as
  Configurações? [Abrir]"). É um Intent comum, mas iniciado por ela.
- **Rolar e arrastar** viram instrução com animação ("arraste para cima"), a parte de gestos da fase 2 do tutor.
- **Pedidos de fazer pela pessoa** ("manda mensagem pra minha filha") viram guia: "vou te mostrar como".
- **Conferido em código:** um teste da variante falha se aparecer `dispatchGesture`, `performAction`,
  `performGlobalAction`, `ACTION_SET_TEXT` ou `canPerformGestures` no que ela compila.

## Fases

### 0. Política e decisões

- Ler inteiras as páginas atuais da Play: "Use of the AccessibilityService API", "Permissions and APIs that Access
  Sensitive Information", serviços em primeiro plano, "AI-Generated Content", "User Data", "Developer Program Policy";
  anotar aqui os trechos que valem, com a data.
- Requisitos da conta (teste fechado, verificação de identidade), conferidos na própria Central de Ajuda.
- As decisões acima, do Pedro.
- **Saída:** a lista de requisitos com fonte e as decisões escritas aqui.

### 1. A variante `loja` e o executor "só guia"

- `productFlavors { completo; loja }` em `app/build.gradle.kts`; manifest e `res/xml/accessibility.xml` próprios da
  `loja` (`canRetrieveWindowContent` e os eventos de toque; sem gestos, IME nem captura).
- Fora da `loja`: `Actions.kt`, `Keyboard.kt`, `LocalServer.kt`, `ModelService`, `BrainService`, `WakeTest`,
  `WakeService`, `network.xml`, `ProviderKey` pelo adb, e as permissões `WRITE_SECURE_SETTINGS`,
  `PACKAGE_USAGE_STATS`, `QUERY_ALL_PACKAGES`, `READ_CONTACTS`, `ACCESS_FINE_LOCATION`.
- App de banco em primeiro plano pelo pacote dos eventos da acessibilidade, no lugar do `PACKAGE_USAGE_STATS`.
- Executor com `agir = false`, no Python (a referência) e no Kotlin, conferido pelas trilhas: `set`, `tap`, `type`,
  `scroll`, `keep_scrolling` e a "tela que sobe" viram passos da pessoa; `open_app`, `open_settings` e `search` viram
  botão na faixa.
- O teste de "nenhuma ação" da variante.
- **Saída:** `loja` compila, os testes JVM e `:cerebro:conferir` passam, e o APK instalado no S23+ guia um caso sem
  um único gesto do agente (conferido no registro do live mode).

### 2. O servidor do provedor

- Um servidor pequeno (uma rota: recebe o pedido já mascarado, repassa ao provedor, devolve a resposta), com a chave
  só nele.
- Cada instalação se identifica pela **Play Integrity API** (o pedido vem do app verdadeiro, num aparelho íntegro);
  limite por instalação e por dia, e teto de gasto mensal.
- Não grava o conteúdo dos pedidos; só contagens e custos. Isso entra na política de privacidade.
- Provedor: decidir entre o OpenRouter e a API da Anthropic direta (termos de uso para app de consumidor, retenção de
  dados).
- `ProviderKey` continua na variante `completo`; na `loja`, uma chave própria só como opção avançada, se o Pedro quiser.
- **Saída:** o app da variante `loja` faz a suíte do guia pelo servidor, com o custo por pedido medido.

### 3. Modelos pela loja

- Os modelos pequenos (2 × 173 MB) e o tokenizador num **Play Asset Delivery** (pacote de recursos), não no APK nem
  baixados de servidor próprio.
- O app abre e guia sem os modelos enquanto eles chegam? Recomendação: não; sem eles a máscara fica só nas regras.
  O app espera o pacote e explica a espera.
- Conferir: o AAB com 64 bits (arm64; incluir x86_64 só se o emulador de teste pedir), minificação ligada sem quebrar
  o onnxruntime.
- **Saída:** instalação pelo teste interno da Play, com os modelos chegando sozinhos.

### 4. Primeira abertura e avisos

O público é quem tem dificuldade: o caminho de ligar a acessibilidade, que hoje o adb faz, vira um guia do próprio
app.

- **Aviso em destaque** antes de pedir a acessibilidade, no formato que a Play exige: o que é lido (o texto da tela),
  para quê (mostrar onde tocar), o que sai do aparelho (só texto com os dados pessoais trocados por falsos, para o
  servidor do easy_phone e o provedor de IA), e um "Concordo" explícito.
- O app guia a pessoa até o atalho da acessibilidade (os dois botões de volume): abre a página por Intent e mostra os
  passos grandes, e a configuração só termina quando o atalho liga o serviço uma vez (a faixa ainda não existe, porque
  depende da própria acessibilidade).
- O mesmo para o papel de assistente digital (botão lateral) e as permissões de microfone e notificações.
- Botão de **denunciar uma resposta** (exigência da política de conteúdo gerado por IA) na faixa e no painel.
- **Saída:** uma pessoa de fora da família técnica liga tudo sozinha, só com o app (conferir com alguém do público).

### 5. Material da loja

- Política de privacidade numa página pública (o que é lido, o que sai e mascarado como, o que o servidor guarda,
  como apagar).
- Formulário de **Segurança dos dados** coerente com ela.
- **Declaração da acessibilidade** no Play Console, com o vídeo: a pessoa pede, o app destaca, a pessoa toca; o vídeo
  mostra que nenhum toque é do app.
- Declarações das permissões que ficarem (serviço em primeiro plano, microfone se houver palavra de ativação).
- Questionário de classificação, público-alvo (adultos, não crianças), ficha da loja em português, capturas de tela.
- **Saída:** tudo preenchido no Console, sem pendências.

### 6. Testes na Play

- Teste interno (o Pedro).
- Teste fechado (12 ou mais testadores por 14 dias, se a conta for pessoal): de preferência gente do público, com o
  registro de uso que o app já tem (`logs/live/` vira um registro no aparelho, enviado só com o sim da pessoa).
- Medir aqui o que só a loja diz:
  - **Apps de banco.** O Inter bloqueou com um serviço de acessibilidade de fora da loja (2026-10-13 com o Portal;
    2026-11-21 com a `loja` ligada o tempo todo, num pagamento). Desde então a `loja` só fica ligada durante o guia
    (atalho dos botões de volume, `disableSelf` no fim). Testar com os bancos dos testadores, sem abrir o app do banco
    durante um guia.
  - **Proteção Avançada do Android 17:** com ela ligada a acessibilidade do app fica desligada. O app tem de dizer
    isso em vez de falhar calado.
  - Se a pessoa entende e lembra o atalho dos botões de volume.
- **Saída:** o relatório do teste fechado e as correções; a resposta às perguntas da Play para liberar a produção.

### 7. Produção e manutenção

- Envio para revisão; se for recusado, recorrer citando o teste de "nenhuma ação" e o vídeo.
- Lançamento gradual (porcentagem pequena primeiro).
- Rotina: a política da Play muda; reler as páginas da fase 0 a cada atualização grande do app e quando a Google
  avisar por e-mail.

## Plano B, se a acessibilidade for recusada

O assistente digital recebe do Android, quando a pessoa o chama, o texto da tela do app de baixo (`AssistStructure`,
com "Usar texto da tela" ligado), **sem a acessibilidade**. Hoje o `onHandleAssist` o descarta. Um guia dá para fazer
um passo por vez: a pessoa chama, o painel aponta (sobre a captura, sem tocar), ela toca, chama de novo. É pior de
usar, mas não depende da política da acessibilidade. Vale um protótipo rápido na fase 1, só para saber se existe
saída.

## Riscos

- Recusa pela leitura do revisor ("planeja por IA"), mesmo sem ação nenhuma; o plano B existe por isso.
- A política muda depois da aprovação (já mudou em 2026).
- Custo do provedor sem teto se o app crescer; o servidor tem de ter limite desde o começo.
- Bancos que bloqueiam qualquer acessibilidade ligada, mesmo de app da loja: para o público, o app viraria "o que
  quebrou o banco".
- O guia ainda não está redondo (nenhum caso passou em todos os critérios na linha de base da fase 1 do tutor); a
  loja não deve vir antes da fase 2 do tutor medida.

## Ordem sugerida

A fase 0 e o protótipo do plano B podem começar já. As fases 1 a 3 dependem da fase 2 do tutor (o guia redondo) e da
fase 5 dele (o cérebro no celular, sem o PC), e andam juntas com elas: o executor "só guia" é o padrão que a fase 2 já
está construindo. As fases 4 a 7 vêm depois.

## Fontes (consultadas em 2026-11-16)

- [Use of the AccessibilityService API](https://support.google.com/googleplay/android-developer/answer/10964491?hl=en)
- [Tabela de prazos das políticas da Play](https://support.google.com/googleplay/android-developer/table/12921780)
- [Permissions and APIs that Access Sensitive Information](https://support.google.com/googleplay/android-developer/answer/16585319)
- [User Data (aviso em destaque)](https://support.google.com/googleplay/android-developer/answer/10144311)
- [AI-Generated Content](https://support.google.com/googleplay/android-developer/answer/13985936)
- [Foreground service types](https://support.google.com/googleplay/android-developer/answer/13392821) e
  [Device and Network Abuse](https://support.google.com/googleplay/android-developer/answer/13315670)
- [Testes para contas pessoais novas](https://support.google.com/googleplay/android-developer/answer/14151465)
