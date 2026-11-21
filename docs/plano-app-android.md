# Plano: o app Android do easy_phone

Proposta de 2026-10-19. Ao concluir uma etapa, marque aqui e leve as decisões para o `CLAUDE.md`; medições longas vão
para o `historico.md`.

## Objetivo

Um app no próprio Galaxy S23+ que faz o que hoje o PC faz pelo adb e pelo Portal, sem PC: lê a tela, decide, age,
mascara e fala com o provedor. Em cima dele, as funções que só um app permite: comandos por voz, uma faixa na tela
dizendo o que o agente está fazendo (como o Bixby), confirmação de ações sensíveis, correção pelo usuário quando o
agente erra, registro do uso diário (acertos, erros e falhas) para melhorar os modelos e um modo ao vivo, em que as
instruções são executadas enquanto são ditas.

Decisões do Pedro (2026-10-19): tudo no celular desde a primeira versão, **com a opção de usar o PC como cérebro**;
ferramentas Android só pela linha de comando (JDK 17, Android command-line tools, Gradle), sem Android Studio.

A regra do projeto não muda: **dado pessoal não sai do aparelho sem máscara**. No app ela fica mais fácil de cumprir
(a tela não passa mais pelo USB) e mais séria (o app tem a chave do provedor e o acesso à tela o tempo todo).

## Arquitetura

```
app easy_phone (Kotlin)
├── aparelho: serviço de acessibilidade próprio (ler a árvore, tocar, rolar, digitar, abrir app),
│             ligado só durante a tarefa; API local para o cérebro do PC (no lugar do Portal)
├── cérebro:  "celular" (Kotlin: modelos ONNX, cofre e máscara, provedor, executor, cache e mapa)
│             ou "PC" (o serviço Python de hoje, pela API acima)
└── interface: pedido por texto e voz (reconhecimento no aparelho), faixa do andamento, confirmações,
               correções, registro do uso
```

- **O formato da tela é o mesmo de hoje** (`device.render`: a árvore em texto, com índices). Assim o executor, os
  prompts, o cache e o mapa não mudam ao trocar de cérebro, e o cérebro em Kotlin é conferido contra o Python com as
  mesmas entradas.
- **Portar, não reescrever.** O cérebro em Kotlin é uma tradução do Python que está na pv1 (uns 2.500 linhas:
  `executor.py`, `proxy.py`, `masking.py`, `local_ai.py`, `modelo.py`, `cache.py`, `sources.py`, `access.py`). O Python
  continua sendo a referência e o lugar de experimentar; o que muda nele é portado depois.
- **Igualdade conferida.** O app tem um modo de depuração que responde às mesmas chamadas do `modelo_server`
  (`/entities`, `/judge`, `/pick`) e às do mascaramento: o `tests.eval_base --novo` roda o conjunto congelado contra o
  celular (pelo `adb forward`) e tem de dar os mesmos números do PC.

## Etapas

### 0. Ferramentas e esqueleto

- JDK 17 (winget), Android command-line tools com SDK, platform-tools e build-tools da API 36 (Android 16), Gradle pelo
  wrapper. Projeto em `android/` no mesmo repositório: Kotlin, Jetpack Compose, `minSdk` 34, pacote
  `dev.pedro.lmphone`, assinatura de depuração.
- `android/build.cmd` (e `.sh`) compila e instala pelo adb.

Pronto quando: um app vazio compila nesta máquina, instala no celular e abre.

**Concluída em 2026-10-19.** Sem administrador: JDK 17 portátil da Microsoft em `%LOCALAPPDATA%\Programs` (o winget
parou esperando a permissão de administrador), Android command-line tools, SDK 36 e build-tools 36.0.0 em
`%LOCALAPPDATA%\Android\Sdk` (sem o platform-tools do SDK: o adb continua o do winget, para não haver dois servidores
de adb de versões diferentes), Gradle 8.14.3 só para gerar o wrapper. `JAVA_HOME` e `ANDROID_HOME` no ambiente do
usuário. AGP 8.11.1, Kotlin 2.2.0, Compose BOM 2025.06.01. APK de depuração com 23 MB; compila em menos de 1 min.

### 1. A camada do aparelho

- `AccessibilityService` próprio: lê a árvore das janelas (sem as do próprio app) e a escreve no formato do
  `device.render`; age por nó (`performAction`: clicar, rolar, `ACTION_SET_TEXT` para digitar, sem teclado próprio) ou
  por gesto (`dispatchGesture`) quando o nó não aceita; abre apps pela intent de launcher; volta, home.
- Ligar e desligar o serviço: o app escreve em `Settings.Secure` com `WRITE_SECURE_SETTINGS`, dada uma vez pelo adb
  (`pm grant`). Mesma regra da pv1: ligado só durante a tarefa, nunca com app de banco em primeiro plano, desliga na
  hora se um aparecer (`access.BANKS`).
- API local (HTTP em 127.0.0.1, como o Portal): `state` (a tela em texto), `tap`, `swipe`, `type`, `back`, `open`.
  O `lmphone/device.py` ganha a opção de usá-la no lugar do Portal: é o "PC como cérebro".

Pronto quando: a suíte do PC passa usando o app no lugar do Portal (`LMPHONE_DEVICE=app`), no mesmo nível de hoje.
Ganho esperado: a leitura de tela deixa de custar 1,1 s pelo content provider.

**Concluída em 2026-10-19**, com o cérebro do PC (`LMPHONE_DEVICE=app`):

- `AgentService` (acessibilidade própria) devolve a tela no JSON do `state_full` do Portal: o texto que chega ao
  executor saiu idêntico ao do Portal, linha a linha, em Configurações e no YouTube Music (143 elementos), depois de
  tirar os elementos "não importantes" (o Portal não os pede) e de declarar `QUERY_ALL_PACKAGES` (sem ela, o nome do
  app em primeiro plano saía como pacote). `/apps` lista os apps da tela inicial, como o `packages` do Portal.
- Ações pelo serviço: toque e rolagem por gesto, Voltar e Home pelo sistema, Enter pela ação do campo, digitação por
  `ACTION_SET_TEXT` no campo de foco (ou no editável focado, no único editável, no último onde se escreveu) e, sem
  campo nenhum, pela conexão de texto do próprio serviço (`flagInputMethodEditor`). Sem teclado próprio.
- Servidor local com senha (o app a gera; o PC a lê por `run-as`). **Não pelo `adb forward`**: com ele o adb inteiro
  travou duas vezes por até 5 min nos casos que digitam, como com o servidor do Portal na pv1, então a causa é o
  túnel; o pedido vai por `adb exec-out` ao `nc` do aparelho (40 leituras seguidas de uma tela grande sem travar).
- **O congelador da Samsung** (Freecess) congela o app em segundo plano mesmo com a acessibilidade ligada, e o servidor
  para de responder; o `build.cmd` põe o app fora da economia de bateria (`deviceidle whitelist`, `RUN_ANY_IN_BACKGROUND`).
- A leitura leva uns 0,1 s em vez de 1,1 s; por isso a tela só vale parada depois de 0,6 s sem mudar (com 0,15 s, uma
  pausa no carregamento de uma página passava por tela parada).

Suíte pelo app (`reports/suite-2026-10-19-160044` e `-161300`): 23 de 26 nas duas rodadas, em 6,0 e 7,4 min (pelo
Portal, 25 de 26 em 10,9 min). As falhas variam: `ig-privada` (a conta de teste, já instável na pv1), `web-injecao`
(planos do provedor que leem "Closed on weekends" como horário; 3 de 3 nas repetições) e `notion-pagina` (2 de 4:
depois do título o Notion recria a tela e não sobra campo nem conexão de texto para o corpo; pelo Portal também falha
às vezes). Falta: a digitação do Notion, talvez com um teclado próprio como o do Portal, se o resto não bastar.

Depois, com os casos do dia a dia (`--nivel dia_a_dia`, pedidos do Pedro em português informal):

- O Freecess congelava o app mesmo fora da economia de bateria: durante a tarefa o app fica em primeiro plano
  (`TaskService`, notificação "O agente está usando o celular"); 30 de 30 leituras em 1 min, sem congelar.
- Teclado próprio (`Keyboard`, sem teclas, só uma faixa): o PC o põe como teclado ativo na tarefa e devolve o de antes,
  como o do Portal. A digitação prefere `ACTION_SET_TEXT` no campo (procurado em todas as janelas menos a do teclado,
  e esperando até 2 s ele aparecer depois do toque) e usa o teclado quando o campo não está na árvore.
- Painel rápido pela ação global do sistema (`quick_settings`).

### 2. Modelos no aparelho

- onnxruntime-android e os dois modelos de `data/modelos/` no armazenamento do app (copiados pelo adb na primeira
  vez; 2 × 173 MB não cabem bem dentro do APK). Tokenizador: o mesmo `tokenizer.json`, por uma biblioteca que leia o
  formato do Hugging Face no Android ou por uma implementação própria do Unigram, conferida token a token contra o
  Python nos textos da coleta.
- Porta de `lmphone/modelo.py` (blocos, BIO, palavra inteira, a opção nenhum) e do servidor (`/entities`, `/judge`,
  `/pick`), no modo de depuração.

Pronto quando: `tests.eval_base --novo` contra o celular dá os mesmos números do PC; tempo e memória medidos no S23+.

**Concluída em 2026-10-26.**

- **Tokenizador próprio** (`android/modelos/.../Tokenizer.kt`), sem biblioteca: a normalização `Precompiled` (a árvore
  Darts do `tokenizer.json`), as palavras com o "▁", o Unigram e os cortes. Copia de propósito duas esquisitices da
  biblioteca `tokenizers`: num grafema curto vale a regra do começo mais curto, e o resto some ("Ａ" mais um acento vira
  "A"); um controle apagado no começo do texto desloca as posições dos caracteres seguintes. Lê o `tokenizador.bin`
  (5,3 MB) que `tools/app/modelos.py preparar` grava do `tokenizer.json`, conferindo antes que ele é do tipo que o
  Kotlin sabe ler. O texto de `lmphone/modelo.py` (blocos, rótulos, palavra inteira) foi traduzido em `Modelo.kt`,
  contando em code points como o Python.
- **Igualdade no PC** (`android\gradlew.bat :modelos:conferir`, com o onnxruntime da JVM, contra as respostas que
  `tools/app/modelos.py referencia` grava do Python): 227 mil tokenizações iguais em ids e posições (os 37 mil trechos
  e os pedidos da coleta, as telas, 46 mil pares da escolha com cortes de 64, 20 e 5 tokens, 3 mil textos aleatórios e
  casos escritos à mão), 1.471 de 1.471 marcações e 2.245 de 2.245 escolhas iguais (probabilidades a 1e-15).
- **No celular**: onnxruntime-android 1.31.0, a mesma versão do `.venv-modelo`. O `ModelService` (modo de depuração,
  ligado pelo adb com `am start-foreground-service`) atende com a API do `modelo_server`, e `tools/app/modelos.py ponte`
  o leva a 127.0.0.1:8791. `tests.eval_base --novo` contra ele deu os mesmos números do PC, caso a caso (427 de 427):
  185 de 187 pessoas, 38 de 38 usuários, 113 de 217 controles com 10 toques errados.
- **Tempo no S23+**, o medido no app, sem o adb (`tools/app/modelos.py medir`), com a acessibilidade do app ligada,
  como numa tarefa: julgar um pedido, 19 a 23 ms (mediana); uma tela, 39 a 45 ms; uma escolha, 104 ms (p90 de 140 ms).
  No PC, menos de 20 ms e 31 ms. Com 1, 2, 4, 6 ou todos os núcleos, quase igual.
- **Sem a acessibilidade ligada**, só com o serviço em primeiro plano, a One UI põe o processo no grupo "moderate"
  (`/dev/cpuset/moderate`: os núcleos 0 a 2, de 2,0 GHz) e na fatia "background" da CPU, e tudo fica 3 a 7 vezes mais
  lento (a escolha, 0,5 a 0,9 s). Com a acessibilidade ligada o processo vai para o grupo "foreground" (núcleos 0 a 6).
  O cérebro no celular tem de rodar enquanto ela está ligada.
- **Memória**: 470 a 520 MB (PSS do app; 385 MB nativos) com os dois modelos; no PC, uns 660 MB. Carregar os dois leva
  de 1,1 a 5,5 s; dá para fazer em paralelo com o pedido do plano.
- **Tamanho**: o APK passou de 23 para 58 MB (o `libonnxruntime.so`, só de arm64, tem 34 MB). Os modelos ficam fora
  dele, em `files/modelos/` do app (2 × 182 MB e o tokenizador), copiados por `tools/app/modelos.py enviar` (13 s pelo
  cabo).
- O onnxruntime 1.31 do Android tenta mandar telemetria à Microsoft (o log diz que não manda porque falta o cliente
  HTTP dele); o `Models` a desliga (`setTelemetry(false)`).

### 3. O cérebro no aparelho

- Cofre a partir dos contatos e contas do próprio aparelho (`READ_CONTACTS`; a porta de `sources.py`), máscara
  (`masking.py`), julgamento do pedido e das telas, cliente do provedor (chave no Keystore, posta pelo adb ou pela
  tela de ajustes, nunca no APK), executor, cache e mapa.
- Escolha do cérebro nos ajustes do app: celular ou PC.

Pronto quando: a suíte roda com o cérebro no celular (o PC só dispara os casos e confere) e passa no mesmo nível do
Python.

**Decisão do Pedro (2026-10-26): o caminho A, o cérebro traduzido para Kotlin.** Como fica:

- **O Python continua a referência, e os textos e as tabelas não são copiados à mão.** `tools/app/cerebro.py exportar`
  lê do Python os prompts (o do plano, o da ajuda, o da conferência e os pedaços deles), os limites, as listas
  (apelidos de apps, páginas das Configurações, palavras de confirmação, bancos, stoplist) e as expressões regulares, e
  grava `android/cerebro/src/main/resources/cerebro.json`, que o Kotlin lê. Também vão nele as tabelas do Unicode do
  Python que o Kotlin não tem igual (o `casefold` e as marcas combinantes do `plain`). Um teste do Python falha se o
  JSON ficou velho. Mudar um prompt no Python é rodar a exportação de novo, sem tocar no Kotlin.
- **Módulo `android/cerebro`** (Kotlin puro, como `android/modelos`): a máscara (`masking.py`), a IA local
  (`local_ai.py`, chamando os modelos direto), os fatos (`facts.py`), o cache e o mapa (`cache.py`), o executor
  (`executor.py`) e o caminho até o provedor (`proxy.py` e o ciclo de `service.py`). O aparelho, o provedor e a faixa
  entram por interfaces; o app as implementa.
- **Conferência do executor por trilhas**: com `LMPHONE_TRILHA=1` (e nos testes do executor), o Python grava, a cada
  chamada de fora (`step`, `prepare`, `use`, `confirm_answer`), o estado inteiro do executor antes e depois, o que ele
  pediu ao provedor, ao modelo de escolha e ao aparelho, e o que recebeu. A conferência em Kotlin parte de cada estado,
  responde com o que foi gravado e confere que pediu os mesmos textos (o prompt inteiro, letra a letra), deu a mesma
  ação e chegou ao mesmo estado. Os 101 testes do executor viram trilhas, e cada rodada da suíte no PC, mais.
- **A máscara e a IA local** são conferidas como os modelos na etapa 2: os mesmos textos, o mesmo cofre (fictício) e
  valores falsos determinísticos dos dois lados, a mesma saída.
- **No app**: o aparelho direto pelo `AgentService` (sem HTTP), a faixa direto pelo `Overlay`, os fatos pelas APIs do
  Android, o cofre pelos contatos (`READ_CONTACTS`) mais o que o PC já tem, a chave do provedor cifrada pelo Keystore
  (posta pelo adb sem passar pelo terminal, ou digitada nos ajustes), a escolha do cérebro nos ajustes, os registros
  (`proxy.jsonl`, `detalhe/`, `live/`) no armazenamento do app, puxados pelo PC para o painel.
- **O que o app não pode fazer como o adb**: `set` (os comandos `cmd` do sistema) não existe para um app comum; no
  celular o ajuste vai pelas telas (o mesmo caminho do guia, sem chamar o provedor). Ligar e desligar a própria
  acessibilidade e o teclado pede `WRITE_SECURE_SETTINGS`, dada uma vez pelo adb.

**Como está (2026-10-26).** O cérebro inteiro está em Kotlin e confere com o Python:

- `android/cerebro/`: `Py.kt` (o que imita o Python: as expressões regulares com o `\w`, o `\d`, o `\s` e o `\b`
  dele, o `casefold`, o `plain`, o `str.format`, o JSON escrito como o `json.dumps`), `Masking.kt`, `LocalAi.kt`,
  `Facts.kt`, `Cache.kt`, `Difflib.kt` (o `get_close_matches`), `ExecutorText.kt` e `Executor.kt`, `DeviceText.kt` (o
  texto da tela de `device.py`), `LiveMode.kt` (`live.py`) e `Agent.kt` (`proxy.py` e o ciclo de `service.py`). O
  aparelho (`Phone`), a faixa (`Strip`) e o provedor (`Upstream`) entram por interfaces.
- Conferência (`android\gradlew.bat :cerebro:conferir`): as trilhas dos testes do executor, do proxy e do `device`
  (`tools/app/cerebro.py trilhas`) deram 245 de 245 chamadas ao executor iguais (o prompt letra a letra, a ação e o
  estado inteiro depois) e 167 de 167 chamadas a funções; a máscara e a IA local de ponta a ponta
  (`tools/app/cerebro.py mascara`), 1.322 de 1.322 casos (1.121 reais da coleta) e 76 telas; e o `Agent` com um
  celular e um provedor de mentira (modo escuro pelas telas; o nome de um contato fora do envio e do registro). Uma
  mudança proposital no executor em Kotlin apareceu como diferença de prompt e de estado.
- O executor ganhou `SCREENS` (no Python e no Kotlin): o `setter` do celular o devolve, e o `set` vira a página das
  Configurações e a chave (o caminho do guia), sem chamar o provedor.
- No app: `PhoneImpl` (o aparelho direto pelo `AgentService`, os fatos pelas APIs do Android), `ProviderKey` (a chave
  cifrada pelo Keystore; o PC a manda pela entrada padrão do adb, e o app apaga o texto claro), `Contacts` (o cofre
  pelos contatos, somado ao que veio do PC), `OnDevice` (o `Agent` com tudo isso; os modelos carregam no primeiro
  pedido e saem 10 min depois do último), a escolha do cérebro na tela inicial e `BrainService`, que atende a suíte.
  `tools/app/cerebro.py enviar` prepara o celular (as permissões que só o adb dá, data/, a chave, os modelos).
- No celular: "abre a calculadora" com o cérebro no app, de ponta a ponta, em 23 s (o celular estava bloqueado; o
  agente perguntou na faixa, e seguiu com a resposta). O registro saiu igual ao do PC.

Falta:

- **A suíte com o cérebro no celular** (`tests.phone_suite --cerebro celular`), comparada com a do PC: é o "pronto
  quando" desta etapa.
- **Ajustes pelas telas.** "Desliga o modo escuro" falhou no celular: na One UI 9 a página Tela tem "Light" e "Dark"
  como opções (o caminho do guia procura uma chave "Dark"), e nem um toque do adb em "Light" mudou o modo (a página
  tem um agendamento do modo escuro; o modo seguiu ligado). O provedor terminou com um `read` sem alvo, que leu o
  primeiro texto da tela: falta recusar um `read` sem `target` (no Python e no Kotlin).
- O que o app não alcança: o app que toca (precisaria do acesso às notificações: vai só "some app" ou "nothing"), o
  nome da rede Wi-Fi sem a localização ligada, as contas do aparelho (vêm do cofre do PC). O teclado do agente
  precisa estar ativado (o `enviar` o ativa; o `access.off` do PC o desativa de novo).

### 4. Interface da tarefa

- Pedido por texto e por voz: `SpeechRecognizer.createOnDeviceSpeechRecognizer` (o áudio não sai do aparelho; se o
  reconhecimento no aparelho não existir para pt-BR, a voz fica desligada em vez de mandar áudio a um serviço).
- Faixa sobre a tela durante a tarefa (janela de sobreposição do próprio serviço de acessibilidade): o passo atual em
  palavras ("Abrindo Configurações", "Tocando em Exibição"), botão de parar. As janelas do app ficam fora da leitura
  da tela.

### 5. Confirmação de ações sensíveis

- Antes de tocar num controle que envia, compra, paga, apaga ou publica (pelo rótulo do controle e pelo passo do
  plano; uma lista fixa primeiro, um classificador depois), o agente para e pergunta na faixa, por toque ou voz. Sem
  resposta, não faz.

**Feita no cérebro do PC em 2026-10-24** (`executor.SENSITIVE`, a marca `confirm` do plano, `confirm_user` na faixa;
detalhes em `docs/plano-assistente.md`). Falta conferir no celular.

### 6. Correções e registro do uso

- Ao fim de cada tarefa, o resultado e um "estava certo?" na faixa; por voz ou texto, o usuário diz o que o agente fez
  de errado. Isso entra, junto com o caminho da tarefa (passos, escolhas e o efeito de cada uma), num registro local
  no formato da coleta (`data/treino/real/`), em armazenamento privado do app.
- Acertos, erros e falhas do uso diário vão para o mesmo registro. O PC puxa pelo adb e o treino da etapa 4 do plano
  dos modelos pequenos usa como mais uma fonte (com a correção do usuário valendo mais que o rótulo do professor).

### 7. Modo ao vivo

- Uma sessão de voz contínua: cada instrução é julgada e executada enquanto a próxima é ouvida; "para", "volta",
  "não, a outra" corrigem o passo em andamento.

### Chamar pela voz (pedido do Pedro, 2026-10-26)

Dizer "Alexa" abre o painel do assistente já ouvindo, como o toque longo na tecla lateral. O Pedro pediu um nome como
"Ok Google", Siri ou Alexa se fosse mais fácil, e "Rudy" se desse no mesmo. Ficou "Alexa": o openWakeWord
(https://github.com/dscripka/openWakeWord) tem o detector dela pronto, e "Rudy" pede treinar um detector próprio.

- Um app comum não alcança o microfone de baixo consumo do sistema que o "Ok Google" e o Bixby usam: o detector de
  palavra do Android (`AlwaysOnHotwordDetector`, `HotwordDetectionService`) exige permissões só de apps da fábrica.
  O caminho é o microfone aberto num serviço em primeiro plano (`WakeService`, tipo `microphone`), com a notificação e o
  ponto verde do Android sempre ligados.
- `WakeWord` (em `android/modelos/`) traduz o caminho em tempo real da biblioteca do Python (versão 0.6.0, modelos da
  0.5.1): espectrograma mel, o `speech_embedding` do Google e o detector, a cada 80 ms, no onnxruntime que o app já
  tem. Os três modelos (3,3 MB) ficam em `files/escuta/`, copiados por `tools.app.escuta enviar`. O som não é gravado
  nem sai do aparelho.
- Conferência (`tools.app.escuta referencia` e `android\gradlew.bat :modelos:conferirEscuta`): 49 frases fictícias
  faladas pelas vozes do Windows, com e sem a palavra; o Kotlin deu as 2.924 notas iguais às da biblioteca, com
  diferença 0. A própria biblioteca, com a voz em português: acima de 0,5 em 10 de 17 frases com "Alexa" (falha na fala
  lenta e em "Ei Alexa") e em 1 de 32 sem (sempre "Alex, abre a porta", que soa "Alexa-bre"). O detector pronto foi
  treinado em inglês.
- O microfone fecha enquanto o app usa o dele (o reconhecedor do painel e da faixa), no live mode contínuo (que já
  ouve tudo) e enquanto o app fala. Durante um pedido, ou com o agente usando o celular, ele só ouve se a faixa está na
  tela: sem ela, a chamada abriria o painel por cima do app que o agente lê.
- No S23+: 14 ms por pedaço de 80 ms com o app na frente (12 deles no embedding), 27 ms com ele atrás. Com a tela
  apagada e o celular bloqueado o microfone segue aberto, e o painel abre por cima da tela de bloqueio. Depois de
  reinstalar o app, o Android religa o serviço sozinho quando o assistente digital volta (início em segundo plano
  permitido, com o microfone).

**Os botões falados** (pedido do Pedro, 2026-10-26: "Alexa, live mode", "Alexa, pausa", "Alexa, para").
`Commands.kt` reconhece a fala inteira, sem o provedor: live mode, finalizar, para (encerra a tarefa, como o X), fecha,
pausa, continua, deixa que eu faço, faz você, minimiza, mostra a faixa, muda de lado, silêncio, liga a voz, repete,
escrever. Numa tarefa, "Alexa" abre a faixa e ela ouve o comando; o que não é comando vai ao agente como instrução,
como antes. Sem tarefa, quem ouve é o painel, e "pausa" e "para" seguem como pedido ao assistente (pausar a música, como
numa Alexa). No modo contínuo basta o comando ("para" encerra o pedido em curso e segue ouvindo; antes, "para" pausava).

- Dito de uma vez: o que vem logo depois de "Alexa" vai ao reconhecedor do aparelho por um cano (`EXTRA_AUDIO_SOURCE`
  do Android), sem esperar o painel abrir e sem trocar de microfone; o aviso é uma vibração (um bipe entraria no som).
  O reconhecedor do Google entende pelo cano (as parciais vêm certas), mas o resultado final chega vazio: vale a
  última parcial.
- Conferência (`tools.app.escuta testar`, ou só o reconhecedor com `WakeTest --es reconhecer`): frases "Alexa,
  <comando>" das vozes do Windows tocadas no app no lugar do microfone. Pelo cano, as 6 frases saíram com o texto e o
  comando certos ("Alexa silêncio", MUTE; "Alexa pausa", PAUSE). O texto ouvido vai ao logcat só quando o som veio de
  um arquivo de teste; da fala de verdade, só o tamanho.

Falta: o teste de ponta a ponta com o painel e numa tarefa com a faixa (o celular estava em uso), conferir com a voz do
Pedro (perto, longe, com música), depois de religar o celular e o gasto de bateria em um dia. Se o detector pronto errar com
o português, o passo seguinte é treinar um próprio ("Rudy", ou "Alexa" em português) com o treino do openWakeWord na
máquina da RTX: milhares de exemplos sintéticos da palavra e horas de áudio sem ela.

## Riscos

- **Apps de banco** veem o serviço de acessibilidade de um app de fora da loja. A regra da pv1 vale igual (ligado só
  na tarefa), e é preciso conferir de novo com o Inter, agora com o app instalado no lugar do Portal.
- **Android 13 em diante** restringe serviços de acessibilidade de apps instalados fora da loja ("configurações
  restritas"); o caminho pelo adb (`pm grant` e `settings put secure`) contorna, mas precisa ser conferido no One UI 8.5.
- **A chave do provedor no celular.** Fica no Keystore e só sai para o provedor; perder o aparelho é perder a chave
  (revogável no OpenRouter).
- **Memória e bateria.** Os modelos usam uns 660 MB no PC; no celular, medir na etapa 2. O app não deve ficar com os
  modelos carregados fora de uma tarefa.
- **Duas cópias do cérebro** (Python e Kotlin) podem divergir. A conferência pelo conjunto congelado e pela suíte é o
  que segura isso; o Python segue sendo a referência.

## Etapas 2 e 3: o que decidir antes (2026-10-24)

O cérebro cresceu desde a proposta: o Python que teria de ir para o celular tem hoje umas 3.900 linhas (o executor
sozinho, 1.500), não 2.500, e muda toda semana. Manter duas cópias iguais, em Python e em Kotlin, é o maior risco da
lista acima. Duas saídas:

- **A, a do plano**: traduzir o cérebro para Kotlin. Fica tudo nativo e enxuto; cada mudança no Python tem de ser
  traduzida e conferida de novo.
- **B**: levar o próprio Python ao celular, dentro do APK (o Chaquopy faz isso; aberto desde 2022, a conferir a
  licença e o Python 3.12), com só a camada do aparelho e os modelos em Kotlin. É o mesmo código do PC, sem
  tradução; o APK fica maior e o Python no celular precisa ser medido (tempo de partida, memória, bateria).

As duas precisam da etapa 2 (os modelos em Kotlin, com onnxruntime-android), concluída em 2026-10-26. Proposta: começar por ela e decidir entre
A e B depois de medir. Boa parte dela não precisa do celular: o tokenizador (Unigram do XLM-R, 250 mil peças, com a
normalização `nmt_nfkc`) e a montagem do texto de `modelo.py` em Kotlin, conferidos no PC por testes da JVM (Gradle,
com o onnxruntime da JVM) contra o Python no conjunto congelado e nos textos da coleta, token a token e resposta a
resposta. Antes disso, baixar o onnxruntime da JVM e o do Android (dezenas de MB) pede o OK do Pedro.

Depois da etapa 2 (2026-10-26): a tradução conferida contra o Python deu certo de primeira no tokenizador e nos
modelos, o que conta a favor de A; mas lá a referência estava parada, e o cérebro muda toda semana. Para as duas, o
cérebro tem de rodar com a acessibilidade ligada (sem ela, a One UI dá ao app só os núcleos lentos), e os modelos
podem carregar em paralelo com o pedido do plano (1 a 5 s).

## Questões abertas

- ~~Tokenizador no Android: biblioteca pronta ou Unigram próprio?~~ Próprio (etapa 2), igual ao Python.
- Reconhecimento de voz no aparelho em pt-BR no One UI 8.5: conferir na etapa 4.
- Juntar os dois modelos num encoder só (uns 400 MB) antes de levar para o celular? Não medido; separados, os dois
  usam 470 a 520 MB no celular, o que coube. Fica para quando a memória pesar.
