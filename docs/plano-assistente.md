# De executor de tarefas a assistente

Pedido do Pedro (2026-10-20): "o agente está muito mais para um robô executor de tarefas do que um assistente que
também executa tarefas. A ideia do live mode é conseguir utilizar o celular por voz, usar como usaria com as mãos, mas
esse agente parece não ter contexto e noção do que ele é ou tem que fazer, só recebe uma tarefa e tenta executar sem
nem mesmo saber se acertou."

## Diagnóstico: por que ele é um robô

Cada ponto abaixo está no código de hoje.

1. **O provedor é um planejador cego.** O `PLAN_PROMPT` começa com "You write step-by-step plans that a small
   on-device model will execute". Ele escreve o plano inteiro a partir da tela inicial, sem ver nada. Depois disso
   só vê a tela em dois casos: quando o executor trava (`help`) e uma vez no fim (`REVIEW`), e esse fim é pulado no
   caminho do cache e quando o objetivo é uma chave. No meio, quem decide são o rótulo exato e o modelo de escolha,
   que casam palavras e não entendem nada.
2. **"Confirmado" quer dizer que um texto apareceu.** O objetivo é um rótulo que o provedor chutou antes de ver a
   tela. Se o rótulo aparece por outro motivo, o agente diz que acertou; se o fim certo tem outro rótulo, ele diz que
   falhou (Wi-Fi e modo avião na suíte de 2026-10-19).
3. **Ele não sabe o que é.** Nenhum prompt diz que ele é o assistente do Pedro, que está numa conversa, que pode
   responder, explicar, perguntar ou dizer o que viu. O papel que o prompt dá a ele é de gerador de JSON.
4. **Cada pedido é uma tarefa isolada.** `proxy.begin` apaga tudo: os valores falsos, o executor e o que já foi dito.
   Um pedido como "manda pra ela também" ou "não, o outro" não tem a que se referir.
5. **Todo pedido vira plano.** O desenho do Pedro (`pedro/exemlo_arquiterura_live_mode`) separa ação simples, pedido
   a enriquecer, dúvida ou tutorial, ação complexa e "retornar informação ao usuário". Hoje só existe o primeiro
   caminho: "como eu mudo o tema do Instagram?" vira uma tentativa de mudar o tema.
6. **A saída é um status, não uma resposta.** "Pronto: Done, and confirmed on screen.", em inglês. Ele não diz o que
   fez nem o que viu ("a rota começou, chegada às 14h32"), salvo num `read`.
7. **O celular não chama o assistente.** A tarefa sai do terminal do PC. A faixa só existe durante uma tarefa, porque
   ela é janela do serviço de acessibilidade, que desliga no fim por causa dos bancos. E não há voz.

O que não é defeito e fica como está: os modelos locais não conversam (só marcam e escolhem), e o mascaramento vem
antes de tudo. Logo, a conversa precisa estar no provedor, sempre com dados falsos.

## Arquitetura proposta

```
dono (texto ou voz, na faixa)
  -> IA local julga e mascara (como hoje)
  -> CONVERSA: um turno do assistente no provedor, com:
       quem ele é e o que sabe fazer | preferências do dono | histórico da conversa (mascarado)
       | estado do aparelho | a tela atual (reduzida e mascarada), quando o pedido fala dela
  -> o provedor escolhe UMA saída:
       responder  (dúvida, informação, conversa)          -> texto na faixa (e fala)
       perguntar  (pedido ambíguo, falta um dado)          -> pergunta com opções na faixa
       agir       (plano + objetivo, como hoje)            -> executor
       guiar      (tutorial: agir explicando cada passo)   -> executor, com narração
  -> agir/guiar: executor como hoje (rótulo, modelo de escolha, cache, ajuda)
       + CONFERÊNCIA SEMPRE: no fim, o provedor vê a tela final e o estado e decide se o pedido está feito
         (o mesmo pedido já escreve a resposta ao dono, em português)
  -> resposta desmascarada no aparelho e mostrada na faixa; o turno entra no histórico
```

### O que muda em cada parte

| Parte | Hoje | Proposta |
|---|---|---|
| Sessão (`proxy.begin`) | uma por tarefa | uma por **conversa**: os mesmos valores falsos e o histórico valem entre os pedidos; acaba após 10 min parada ou quando a faixa fecha |
| Prompt do provedor | planejador de JSON | **assistente** do dono, com identidade, capacidades e limites; o plano passa a ser uma das ferramentas dele |
| Saídas | plano ou `finish` | `reply`, `ask`, `act` (plano), `guide` (plano com explicação por passo) |
| Fim da tarefa | objetivo por rótulo; `REVIEW` só às vezes | objetivo por rótulo ou fato (rápido) **e** conferência do provedor sempre que o fato não decide, junto com a resposta ao dono |
| Resposta | status fixo, em inglês | frase do assistente, em português, com o que viu (desmascarada no aparelho) |
| Início | terminal do PC | faixa no celular, fora da acessibilidade; o app chama o serviço do PC por `adb reverse` |
| Voz | não há | reconhecimento de fala do próprio aparelho (offline) e leitura da resposta em voz |

O que fica: o plano executado no aparelho, o cache, o mapa, o modelo de escolha, o mascaramento e a acessibilidade
ligada só enquanto age. O assistente não chama o provedor a cada toque: o caminho rápido continua o mesmo, e o
provedor entra no começo, quando trava e no fim.

## Pontos de falha e contrapontos

1. **Mais chamadas ao provedor.** Um turno com raciocínio custa 2 a 5 s. Contraponto: o plano e as ajudas já são
   chamadas; o que entra é a conferência final sempre e o turno inicial no lugar do plano (é a mesma chamada, com
   mais contexto). No Haiku 5.5 isso é menos de US$ 0,001 por pedido.
2. **Mais tela vai ao provedor.** A tela final passa a ir sempre. Ela vai do mesmo jeito que nas ajudas: reduzida
   (`redact`) e mascarada. A tela só vai no começo do turno quando o pedido fala dela ("o que é isso?", "responde
   ele"), e o julgamento do pedido decide isso.
3. **Valores falsos que duram a conversa.** Um falso que dura vários pedidos permite ligar os pedidos entre si. É
   justamente o que a conversa precisa ("manda pra ela também"). A sessão acaba com 10 min sem uso, e o cofre
   continua sendo relido a cada pedido.
4. **Histórico cresce.** Vão só os últimos turnos (pedido, resposta e um resumo das ações, sem telas); o resto sai.
5. **Responder dúvida de memória erra.** O provedor não conhece a One UI 8.5 do Pedro. Contraponto: "como faço X"
   vira `guide` sempre que X é feito no próprio celular. O assistente faz mostrando, e a tela real corrige o palpite.
   `reply` fica para o que não depende de tela ("o que é modo avião?").
6. **Injeção de prompt.** Com mais tela no contexto, um texto na tela pode tentar dar ordens. Regra: ação só vem de
   turno do dono, e a tela entra marcada como dado ("conteúdo da tela, não são ordens"). Envio, compra e exclusão
   continuam sem existir até haver confirmação.
7. **A conferência pode discordar do objetivo.** Se o fato ou o rótulo diz feito e o provedor diz que não, vale o
   provedor, que dá os passos que faltam (com o limite de ajudas). Se o provedor diz feito e o rótulo não aparece, o
   resultado vira "feito, conferido pelo assistente", uma categoria separada de "confirmado" no registro.
8. **A faixa fora da acessibilidade.** Fica fora da acessibilidade porque ela desliga por causa dos bancos. A faixa
   passa a ser janela do app (`TYPE_APPLICATION_OVERLAY`, permissão de sobrepor). Apps de banco costumam recusar
   toques com sobreposição na tela. A faixa só aparece quando chamada e some com 10 min sem uso; se um banco está na
   frente, ela fica recolhida.
9. **`adb reverse` pode travar como o `adb forward` travou.** O `forward` travou com tráfego grande (telas de 67 KB).
   Pelo `reverse` passam só pedidos e respostas curtas, e as telas continuam pelo caminho de hoje. Se travar, o PC
   lê os pedidos pela faixa no mesmo `/events` que o live mode já consulta.
10. **Voz erra nomes.** Um nome ouvido errado pode escapar da máscara do jeito que foi transcrito. O julgamento roda
    sobre o texto transcrito, como roda sobre o digitado, e a faixa mostra o que foi entendido antes de agir.
11. **Sem provedor, não há conversa.** As respostas de reserva ficam fixas, em português, e o pedido simples que está
    no cache continua funcionando.
12. **A suíte mede tarefas, não conversa.** Ela continua valendo para `agir`. Entram casos de conversa: um pedido
    seguido de "e agora o outro", uma dúvida, um pedido ambíguo que precisa de pergunta, e um "já está feito".

## Etapas

1. **Assistente e conferência** (implementada em 2026-10-20; falta rodar no celular). O prompt passa a ser de assistente, com as saídas `reply`, `ask`, `act` e
   `guide`. A conferência final do provedor roda sempre, menos quando o fato decide, e escreve a resposta ao dono
   em português. Pela linha de comando, sem mudar o app. Medida: a suíte inteira, mais casos de dúvida e de "já
   está feito".
2. **Conversa** (implementada em 2026-10-20; falta rodar no celular). A sessão passa a ser da conversa: os mesmos valores falsos e o histórico entre pedidos, e um modo
   de conversa no `run` (`run --conversa`) para testar pelo terminal. Entram casos encadeados na suíte.
3. **Chamar pelo celular** (feita em 2026-10-21; ver "Como ficou (etapa 3)"). O app como assistente padrão (toque
   longo na tecla lateral), com um painel próprio. O pedido é escrito no painel e vai ao PC por `adb reverse`. A
   acessibilidade continua ligada só enquanto age.
4. **Voz** (feita em 2026-10-21; ver "Como ficou (etapa 4)"; falta o dono testar falando). Fala reconhecida no
   aparelho, e resposta lida em voz alta, com botão para calar.
5. **Narração e guia** (feita em 2026-10-21; ver "Como ficou (etapa 5)"). No `guide`, cada passo mostra na faixa o
   que vai ser feito e por quê. O dono pode dizer "deixa que eu faço", e o agente espera e acompanha.

## Como ficou (etapas 1 e 2)

- `executor.PLAN_PROMPT` é o turno do assistente: identidade, valores falsos que duram a conversa, estado do
  aparelho, histórico e o pedido. As saídas: `reply`, `look` (o mesmo turno de novo, agora com a tela reduzida),
  `ask`, `say` com o plano, `guide` com um `explain` por passo, e `finish`. O turno continua sem raciocínio (2 a 3 s);
  o `look` e as ajudas vão com raciocínio.
- `Executor.take` decide o que fazer com a resposta. Resultados novos: `respondido` (nada foi feito no aparelho),
  `pergunta` (a pergunta foi a resposta, porque não havia faixa) e `conferido` (o provedor viu a tela e o estado e
  disse que está feito, sem que o objetivo dele aparecesse). Só `confirmado` e `já estava` ensinam o cache, como antes.
- Modo assistente (`Executor.assistant`, que o proxy liga): a conferência final roda em toda tarefa que um fato do
  sistema não decide, inclusive no caminho do cache e com objetivo de chave. A mensagem dela é a resposta ao dono.
  Desligado (os testes antigos), vale a regra anterior.
- As mensagens de fim estão em português (`finish`, `fail`, `facts.speak`). A faixa mostra a mensagem como veio,
  sem "Pronto:" na frente, e mostra o `say` e o `explain` antes da ação.
- Conversa: `proxy.begin(..., conversation=id)` mantém o `masker` e o histórico (`CONVERSATION`, só na memória do
  serviço) enquanto a conversa não fica 10 min parada. Vão ao provedor os últimos 6 turnos: o pedido, a resposta e
  um resumo das ações. No meio de uma conversa o cache não é lido nem gravado (o pedido depende do anterior); o mapa
  continua.
- `run --conversa` conversa pelo terminal (cada linha é um pedido do mesmo id); `LMPHONE_CONVERSA=id` faz o mesmo
  com `run "..."`.
- Uma resposta sem ação não precisa da acessibilidade: com um banco aberto ou o Portal fora do ar, o pedido é
  respondido do mesmo jeito (`service.answer_only`).

## Como ficou (etapa 3) e o que veio do teste do orquestrador (2026-10-21)

Chamar pelo celular:

- O app é o assistente digital do Android (`AssistService`, um `VoiceInteractionService`, com `AssistSessionService` e
  um `AssistRecognition` que só existe porque o Android exige um serviço de fala). O toque longo na tecla lateral
  (Recursos avançados > Tecla lateral > Pressionar e segurar > Assistente digital) abre o painel `AssistSession`: a
  última resposta, um campo e "Enviar". O painel não usa a acessibilidade.
- Ao enviar, o painel sai da frente antes de o pedido chegar ao PC: o agente lê a janela ativa, e leria o painel no
  lugar do app de baixo. Enquanto o agente age, o andamento aparece na faixa do live mode; no fim o painel volta com a
  resposta (`VoiceInteractionService.showSession`). Sem o serviço de assistente no ar, a resposta vai numa notificação.
- O pedido vai a `http://127.0.0.1:8789/task` do celular (`Brain.kt`), que o `adb reverse` leva ao serviço do PC. Um
  toque fora do painel o fecha. A conversa (o id) fica no app e dura 10 min parada, como no serviço.
- Segurança: qualquer app do celular alcança essa porta. O serviço gera uma senha a cada subida
  (`logs/service.token`, modo 600) e só aceita `/task` com ela no cabeçalho `X-Lmphone-Token`. O cliente do PC a lê do
  arquivo; o app, de `files/pc_token`, que só o adb grava (`run-as`, `lmphone/bridge.py`). O serviço refaz o `adb
  reverse` e a senha quando o celular volta ao USB (a cada 10 s confere).
- `run --celular` sobe a IA local e o serviço no modo do app e liga o celular. Para virar o assistente:
  `adb shell cmd role add-role-holder android.app.role.ASSISTANT dev.pedro.lmphone`; para voltar ao Google:
  `adb shell cmd role add-role-holder android.app.role.ASSISTANT com.google.android.googlequicksearchbox` (ou em
  Configurações > Apps > Apps padrão > Assistente digital).
- Conferido no celular: uma dúvida ("O que o modo avião faz?") respondida no painel sem mexer em nada, em 2,2 s de
  provedor; "Desliga o modo escuro", "Liga de novo" e "Desfaz isso" em sequência, os três confirmados na tela, com o
  painel voltando com a resposta a cada um.
- `adb shell cmd voiceinteraction show` não abre o painel (o shell não tem a permissão); `input keyevent
  KEYCODE_ASSIST` abre, como a tecla lateral.

O que veio do teste do orquestrador:

- Cache de prompt: as instruções fixas vêm antes de `executor.SPLIT`, e `proxy.ask_provider` as manda como mensagem
  de sistema com `cache_control`; a situação (pedido, estado, tela) vai depois. Em 5 rodadas de teste, 12 de 29 mil
  tokens de entrada vieram do cache; o plano e a ajuda têm instruções diferentes, cada uma com o seu cache.
- O passo `read` tem `answer`, a frase que o dono ouve com `{value}` no lugar do valor ("A mochila azul custa R$
  189,90."). O valor continua lido no aparelho, sem passar pelo provedor.
- Nomes com outra grafia (`executor.close_names`): no pedido de ajuda, o aparelho compara, com os valores reais, os
  nomes do pedido com os rótulos da tela («Alamada 2g» é «ALAMEDA-5G» ou «ALAMEDA»). A IA local às vezes marca o nome de
  uma rede como pessoa, e mascarados os dois viram falsos diferentes.

## Como ficou (etapa 4)

- A regra do projeto decide o desenho: a fala traz nomes e mensagens, e a resposta já vem com os valores reais. O
  reconhecimento é só o do próprio aparelho (`SpeechRecognizer.createOnDeviceSpeechRecognizer`, pt-BR); sem ele, o
  painel diz que não há voz e fica só o texto. O reconhecedor comum não é usado: ele pode mandar o áudio para a nuvem.
  Se o português não está baixado no reconhecedor, o app pede o download (`triggerModelDownload`).
- A resposta é lida só com uma voz pt-BR que sintetiza no aparelho (sem `isNetworkConnectionRequired`); no S23+ é a
  `pt-br-x-pte-local` do Google. Sem voz local, a resposta fica só escrita.
- O painel ouve assim que abre. O que foi entendido aparece no campo ("Entendi: «...»") e vai sozinho depois de
  1,5 s, a menos que o dono toque no campo para corrigir (um nome ouvido errado escaparia da máscara do jeito que foi
  transcrito). 🎤 ouve de novo; 🔊/🔇 liga e desliga a leitura e cala a que está em curso; fechar o painel também cala.
- O microfone é pedido ao abrir o app (o painel não pode pedir permissão).
- Conferido no celular: o reconhecedor do aparelho ouve sem erro (sem ninguém falando, termina em "Não ouvi nada"), e
  a voz local foi achada. Falta o teste com alguém falando.
- No mesmo dia: depois de passos que a conferência final pediu, ela roda de novo (até 2 por tarefa): a rota do Waze
  pedida pelo painel tinha terminado em "Ver rotas", com a resposta padrão e sem conferir se a navegação começou.

## Como ficou (etapa 5)

- Narração: o que o assistente diz durante a tarefa (o `say` do plano, a explicação de cada passo do guia, a vez do
  dono) aparece na faixa e é lido em voz alta pelo app (`/live` com `fala`, mesma voz local da etapa 4, respeitando
  🔊/🔇). O status comum ("Tocando em …") só aparece.
- Guia: antes de cada toque a faixa destaca o controle (uma moldura numa janela à parte, que não recebe toques) e o
  agente espera 2,5 s (`service.GUIDE_PAUSE`). Os passos que a ajuda dá no meio do guia também vêm explicados (a ajuda
  pede `explain` no guia), e um passo sem explicação ganha uma frase curta ("Agora toco em «About phone».").
- A vez do dono: ✋ na faixa, ou escrever "deixa que eu faço" (também "eu faço", "deixa comigo"). O agente para de
  agir: para cada passo mostra e diz "Sua vez: toque em «X»", destaca X, e espera a tela mudar
  (`executor.owner_turn`). A mudança vale como o passo feito na tela em que foi mostrado e é conferida como uma ação
  do agente (`verify`); se o dono fez outra coisa, o fluxo normal (ajuda) decide. 🤖, ou "faz você", devolve a vez; o
  agente faz o passo em aberto. Os comandos escritos ficam no PC (`live.OWNER_ON`/`OWNER_OFF`), não vão ao provedor.
- Na vez do dono: o app recusa as ações do agente (`Live.blocked`); o texto de um passo `type` não aparece nem é
  dito (pode ser senha); o app do pedido não é aberto antes do plano (`proxy.OWNER`); as esperas não gastam os passos
  da tarefa, e 5 min parado no mesmo passo encerram ("Fiquei esperando você…"); a conferência final sabe quantos passos
  o dono fez e não diz "abri" por ele; o que o dono fez não ensina o cache.
- `LMPHONE_VEZ_DO_DONO=1` (no pedido, `"dono": true`) começa a tarefa na vez do dono, como se ele tivesse apertado ✋.
- Conferido no celular: "Me ensina a ver a versão do Android" com cada passo dito e destacado antes do toque; "Abre as
  configurações de som e vibração" na vez do dono, com um script fazendo o papel do dono (abriu o app quando pedido e
  tocou nos destaques), terminando "conferido" com a resposta sem dizer que o agente fez.
- Cuidado ao testar: `uiautomator dump` suspende os outros serviços de acessibilidade (o do agente também) enquanto
  roda; durante uma tarefa, ele faz o agente perder a tela.

## Interface da faixa e do painel (2026-10-22)

Pedido do Pedro: o texto aparecia cortado e não rolava; minimizar para um círculo flutuante, que abre sozinho quando o
agente precisa do dono; a resposta a uma pergunta do agente por voz, com opção de texto; ícones de verdade no lugar dos
emojis; um jeito de tirar a faixa da tela que encerra a tarefa.

- Status, pergunta e resposta do painel ficam numa área que rola, com altura máxima (`Ui.CappedScroll`), esmaecida na
  borda e com barra de rolagem.
- O ícone de minimizar troca a faixa por um círculo (anel azul trabalhando, amarelo pausado ou esperando resposta,
  verde na vez do dono) que dá para arrastar; um toque o abre. Uma pergunta do agente abre a faixa. O círculo também
  sai do caminho dos gestos do agente.
- A pergunta do agente é lida em voz alta e, ao fim da leitura (`Speaker.speak(..., then)`), a faixa ouve
  (`Listener`, só o reconhecedor do aparelho); o que foi entendido vai sozinho em 1,5 s, a menos que o dono toque no
  campo. Ouvindo, o botão do microfone vira o do teclado, para escrever. Pergunta de senha ou código vai direto ao
  campo escondido. O microfone também manda instruções no meio da tarefa; enquanto o dono fala ou escreve, o agente
  espera.
- Ícones vetoriais (`res/drawable/ic_*.xml`, desenhos do Material Icons, Apache 2.0) na faixa e no painel.
- O X tira a faixa da tela e encerra a tarefa: `Live.stopped`, as ações do agente passam a ser recusadas na hora e o
  PC recebe o evento `fechou`. Ele substitui o botão de parar.
- Conferido no Android 17 (One UI 9.0), sobre a Calculadora, sem tarefa: o texto rola; o círculo aparece e a pergunta
  o abre; a pergunta foi lida, a faixa ouviu "casa" e mandou a resposta (o microfone funciona dentro do serviço de
  acessibilidade); o X fechou a faixa com `stopped` e `fechou` no `/events`.

## One UI 9.0 (Android 17), 2026-10-22

O celular foi atualizado. Conferido: Proteção Avançada desligada (com ela, o Android 17 bloqueia a acessibilidade de
apps que não se declaram ferramenta de acessibilidade); a acessibilidade liga e desliga pelo adb como antes; o app
continua o assistente digital; `facts.py` lê tudo igual ao sistema. A descrição do aparelho que vai ao provedor passou a
ser lida dele (`proxy.device_name`); antes dizia Android 16. O cache e o mapa da One UI 8.5 foram guardados em
`arquivo/cache-oneui85-2026-10-22/`.

Suíte inteira (`reports/suite-2026-10-22-105505`): 38 de 45, contra 39 de 45 na 8.5, US$ 0,050 contra 0,067 (cache de
prompt). Uma primeira corrida foi parada no começo por três defeitos, corrigidos antes desta:

- Um toque do agente no Instagram caiu no X da faixa e encerrou a tarefa. Os botões da faixa ignoram toques durante um
  gesto do agente e até 1,5 s depois, e o X pede dois toques.
- Sem o mapa, o provedor perguntava antes de agir até onde a tela respondia ("qual mensagem tem o código?"); na suíte
  ninguém responde. A pergunta só é oferecida quando alguém pode responder, e não para o que o aparelho mostra.

Das 7 rodadas que não passaram na corrida inteira:

- Modo escuro (`cfg-escuro`, `conv-desfaz`): na One UI 9 a tela de Tela tem "Light" e "Dark", sem estado de marcado e
  sem "Dark mode"; o modelo de escolha ficou dividido entre "Dark" (0,48) e "Dark mode schedule" (0,47), respondeu
  "nenhum", e o executor rolou para longe. Agora, dividido, ele pede ajuda nesta tela; e o plano abre a página direto.
- Modo avião (`dia-aviao`): saiu das Conexões e do painel rápido; tem uma tela própria, aberta pelo atalho
  `android.settings.AIRPLANE_MODE_SETTINGS`. Daí a ação `open_settings` (18 páginas, atalhos conferidos no S23+).
- `dia-waze-rota` e `dia-ig-seguir`: o agente disse "confirmado" e a suíte não (a rota não tinha começado; o perfil
  não estava na tela final). Passaram ao repetir.
- `cfg-cache-mapa` 3: o mapa recém-criado não bastou para o pedido com outras palavras; passou ao repetir, com 1
  chamada.
- `cam-flash`: o pedido ambíguo de sempre.

Depois das correções (`open_settings`, escolha dividida), as 6 primeiras passaram: modo escuro em 14 a 18 s com 2
chamadas (eram 64 a 70 s e falha), modo avião em 20 s com 2 (eram 86 s, 7 chamadas e falha).

Depois, a pedido do Pedro, modo escuro e modo avião passaram a mudar direto pelo sistema, sem abrir tela: a ação `set`
(`executor.DIRECT`) roda `cmd uimode night yes|no` ou `cmd connectivity airplane-mode enable|disable` (`proxy.DIRECT`,
os mesmos comandos do preparo da suíte; na One UI 9 o de modo escuro deixa "Dark" marcado na tela de Tela), e o objetivo
por fato confere. O plano usa `set` para os dois, menos no guia. Na suíte: modo escuro em 11 s com 1 chamada e nenhuma
tela enviada (eram 16 a 19 s e 2 chamadas pelas telas), modo avião em 6 s com 1 chamada, "desfaz" em 6 s. As entradas
do cache com os caminhos pelas telas desses pedidos foram tiradas para não se repetirem.

## Sem o celular, 2026-10-24

Feito com o celular desconectado, com testes unitários (208 no total), e ainda não conferido no aparelho:

- **Confirmação de ações sensíveis** (etapa 5 de `docs/plano-app-android.md`). Antes de um toque num controle cujo
  texto começa por enviar, comprar, pagar, apagar, remover, publicar, compartilhar, transferir ou ligar para alguém, ou
  num passo que o plano marca com `confirm`, o executor pergunta na faixa ("Posso tocar em «Send»?", ou a pergunta do
  provedor) e destaca o botão. Sim libera, não encerra, outra resposta vai ao provedor. Sem a faixa, a pergunta é a
  resposta do pedido, e um "sim" no pedido seguinte da conversa libera. A leitura do sim e do não é estrita ("manda pro
  outro contato" não é sim).
- **Mais ajustes diretos**: Wi-Fi, Bluetooth, Não perturbe e localização ligam e desligam pelo `set`, como o modo
  escuro e o modo avião. Objetivo `{"wifi": "on"}` vale para qualquer rede.
- **Depuração sem fio**: `bridge.choose` escolhe o aparelho dos comandos adb (o cabo primeiro), refeito a cada 10 s
  e a cada tarefa; `bridge.reconnect` religa pelo mDNS um aparelho já pareado. Pela rede, desligar o Wi-Fi ou ligar o
  modo avião é recusado.
- **Rota do Waze** (`dia-waze-rota`, falha de 2026-10-22, sessão `9c6849ed`): o objetivo era só "Park Shopping" na
  tela, que já aparece na prévia da rota; o toque em "Ir agora" não começou a navegação, e na segunda conferência o
  provedor tocou em "18 min" (o tempo até o destino) e o código deu "confirmado" pelo nome do lugar. Agora o objetivo
  pode ter `gone` (o "Ir agora" tem de sair da tela), e a conferência final sabe que um botão de começar ainda na tela
  quer dizer que não começou, e que não deve tocar só para ver detalhes.
- **`cam-flash`**: o pedido ambíguo ("Turn on the flash of the back camera") virou "Open the Camera and set the flash
  for photos to On (not Auto)". A conferência continua manual.

A conferir no celular, nesta ordem:

1. `adb shell settings get secure enabled_accessibility_services` (a acessibilidade ficou desligada depois da última
   tarefa?).
2. Os quatro comandos novos do `set`, um por vez, lendo o estado antes e depois (`facts.read`): Bluetooth, Não
   perturbe, localização; o Wi-Fi por último e só com o cabo (não mexer nas redes).
3. A confirmação pela faixa: um pedido que envia uma mensagem para o próprio dono (por exemplo, uma nota para si no
   WhatsApp), respondendo "não" uma vez e "sim" na outra, por voz e por toque.
4. Parear a depuração sem fio, tirar o cabo e rodar `run --celular` e um pedido pela tecla lateral; ver se o `adb
   reverse` funciona pela rede e se a ponte volta depois de desligar e ligar a depuração sem fio.
5. `dia-waze-rota` e `cam-flash` na suíte (`tests.phone_suite dia-waze-rota cam-flash`).
