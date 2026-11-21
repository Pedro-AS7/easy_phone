# Plano: o live mode

Proposta de 2026-10-19, a partir do diagrama do Pedro (`pedro/exemlo_arquiterura_live_mode/`). Ao concluir uma etapa,
marque aqui e leve as decisões para o `CLAUDE.md`.

## O que o Pedro pediu

- Uma interface flutuante, como o Bixby e a Siri, **em toda tarefa**: mostra o que o agente está fazendo e aceita
  instruções a qualquer momento, por **texto**, com botões de **pausar** e **interromper**.
- O agente pergunta ao usuário quando nem o provedor sabe o que fazer (a pergunta é escrita pelo provedor: os modelos
  locais não geram texto).
- O usuário pode mudar o plano, avisar que o agente travou ou que está errado, enquanto ele trabalha.
- **Tudo é registrado** para analisar os erros e treinar os modelos: passos e ações do agente, toques do usuário durante
  a tarefa, perguntas e respostas, instruções no meio da tarefa.

O diagrama: entrada → julgamento (ação simples | dúvida/tutorial | complexa) → enriquecimento ("coloca o park shopping
no waze" = iniciar a rota) → executa → erro? → ajuda do usuário (live) → nova entrada → julgamento...

## Antes: o agente saber que a tarefa já está feita (feito em 2026-10-19)

O caso do Wi-Fi: o celular já estava na ALAMEDA, e o agente, nas duas rodadas, tocou de novo na rede, digitou a senha,
tentou "Adicionar rede" e terminou como falha. Causas: o plano era escrito sem saber o estado do aparelho, o objetivo
só era conferido no fim e como texto na tela, e nada impedia repetir a mesma ação na mesma tela.

- `lmphone/facts.py`: Wi-Fi e rede, modo avião, Bluetooth, não perturbe, localização, modo escuro e mídia tocando, numa
  chamada ao adb (0,5 s). Vai no pedido do plano e nas ajudas.
- O provedor pode responder "já está feito" sem passos; objetivo `{"fact": {"wifi": "ALAMEDA"}}`, conferido antes do
  primeiro passo e depois de cada um (encerra assim que vale; sem nenhuma ação, o resultado é "já estava").
- A mesma ação (toque ou digitação) na mesma tela não é repetida: o provedor olha antes; se ele mandar repetir, vale.

## Arquitetura

```
celular (app easy_phone)                                PC (cérebro, por enquanto)
┌──────────────────────────────┐                     ┌───────────────────────────────────┐
│ AgentService (acessibilidade)│  /state /tap ...    │ service.py: ciclo ler-decidir-agir │
│ + janela flutuante           │ ◄────────────────── │                                   │
│   (TYPE_ACCESSIBILITY_OVERLAY)│  /live: o que mostrar│ live.py: eventos, perguntas,      │
│   faixa: passo atual         │ ◄────────────────── │   instruções, registro            │
│   ⏸ pausar  ⏹ interromper    │                     │                                   │
│   campo de texto             │  /events: o que o   │ executor: instrução do usuário =  │
│   cartão de pergunta         │ ──────────────────► │   ajuda com a frase dele          │
│ fila de eventos do usuário   │  usuário fez/disse  │                                   │
└──────────────────────────────┘                     └───────────────────────────────────┘
```

- A janela é do próprio serviço de acessibilidade: não precisa da permissão de sobreposição, e as janelas do app já
  ficam fora da leitura da tela.
- **Pausar e interromper valem no celular na hora**, sem esperar o PC: o app recusa gestos e digitação enquanto está
  pausado ou interrompido. O PC vê o estado no próximo pedido e para de decidir.
- O PC pede `/events` a cada leitura de tela (junto, sem custo de tempo no aparelho) e, enquanto espera uma resposta,
  a cada 0,5 s.
- Registro: `logs/live/<sessão>.jsonl` (modo 600, valores reais, só na máquina), no painel ao lado do resto da tarefa.

## Pontos de falha e contrapontos

1. **Classificar "simples ou complexa" antes de começar não funciona bem.** A complexidade aparece no meio (um pedido
   de senha, duas redes parecidas, um diálogo inesperado), e o modelo local só tem as intenções acao, pesquisa e mista.
   Por isso a interface fica em toda tarefa, e o que liga a conversa são gatilhos durante a execução: o provedor não
   resolveu, campo de senha, ação sensível, repetição. O julgamento antes de começar continua só para mascarar.
2. **"Erro acontece?" supõe que o agente sabe que errou.** Quase sempre ele não sabe: o problema do Wi-Fi era
   justamente esse, e um "confirmado" só quer dizer que a tela mostra o objetivo que o provedor chutou. Por isso a
   intervenção do usuário a qualquer momento, o objetivo por fato e o "estava certo?" no fim importam mais que o ramo
   de erro do diagrama.
3. **Enriquecer o pedido pode mudar o que o usuário quis.** "Coloca o park shopping no waze" pode ser iniciar a rota
   ou só salvar o lugar. O enriquecimento é do provedor (o modelo local não gera texto), e a faixa mostra a
   interpretação antes do primeiro passo ("Vou iniciar a rota até Park Shopping no Waze"), para o usuário corrigir
   cedo.
4. **Transformar dúvida em ação é perigoso.** "Como crio um post no Instagram?" pede uma explicação, não um post
   publicado. O modo tutorial deve navegar até o lugar e parar antes de qualquer ação que publique, envie ou apague,
   explicando o passo na faixa; nunca concluir a ação sozinho.
5. **Usuário e agente agindo ao mesmo tempo.** Se o usuário toca enquanto o agente decide, a ação seguinte é decidida
   numa tela velha e pode cair no lugar errado. Regra: um toque do usuário pausa o agente sozinho até a tela parar, e a
   decisão seguinte usa a tela nova.
6. **Separar toque do usuário e toque do agente.** Os dois geram os mesmos eventos de acessibilidade. O app marca a
   janela de tempo dos próprios gestos; o que cair fora dela é do usuário. Um toque que chega logo depois de um gesto
   do agente pode ser atribuído errado: registrar com a distância no tempo para o treino poder descartar os duvidosos.
7. **Perguntas escritas pelo provedor citam valores falsos.** Ele vê "Ana Lima" no lugar do nome real: a pergunta
   precisa ser desmascarada antes de aparecer na faixa, e a resposta do usuário mascarada antes de voltar ao provedor
   (ela passa pelo julgamento, como o diagrama já diz).
8. **Resposta com senha.** A regra fixa de senha só pega "a senha é X". A resposta a "qual a senha da rede?" é só a
   senha: o tipo da pergunta (o provedor marca `secret`) é o que faz a resposta ser mascarada sempre e digitada só no
   aparelho, sem passar pelo registro em texto claro.
9. **Teclado.** Durante a tarefa o teclado ativo é o do agente, que não tem teclas. Para o usuário escrever na faixa, o
   app devolve o teclado dele enquanto o campo da faixa está em foco e volta ao do agente depois. Se o agente precisar
   digitar nesse meio-tempo, espera.
10. **A janela flutuante cobre parte da tela.** Os toques do agente podem cair nela: ela fica pequena, arrastável, e o
    agente a tira da frente (ou toca por nó, sem gesto) quando o alvo está embaixo dela.
11. **Cérebro no PC.** Com o USB e o PC no meio, a faixa depende do PC para mostrar o passo. Pausar e interromper
    precisam valer no celular sozinhos (item da arquitetura); o resto aceita o atraso de uma leitura.
12. **Dados de treino com ruído.** O usuário toca por outros motivos (fechar uma notificação), e uma instrução pode ser
    uma mudança de ideia, não uma correção. Cada evento leva o tipo que o usuário escolheu ou o que a interface sabe
    (resposta a pergunta, instrução, correção, toque), e o treino usa só os tipos certos para cada coisa.
13. **Privacidade do registro.** Toques e respostas do usuário são dados reais (o que ele tocou num app pessoal). O
    registro fica no aparelho e no PC, modo 600, fora do git e nunca vai ao provedor; com app de banco em primeiro
    plano, a faixa some e nada é registrado (a regra da acessibilidade vale para a faixa também).
14. **Custo.** Cada instrução e cada pergunta é uma chamada ao provedor a mais (uns US$ 0,002 cada, com o Haiku).

## Etapas

1. **Faixa e controles.** Janela flutuante no `AgentService` com o passo atual, pausar, interromper; `/live` (o PC
   manda o que mostrar) e `/events` (o app devolve pausas, interrupções e toques do usuário). Registro em
   `logs/live/`. Pronto quando: a suíte roda com a faixa na tela sem mudar o resultado, e pausar/interromper funcionam
   no meio de uma tarefa.
   **Feita em 2026-10-19** (`android/.../Live.kt`, `Overlay.kt`, `lmphone/live.py`). Conferido no celular, com toques e
   digitação pelo adb: a faixa mostra cada ação ("Tocando em “Display”", "Pensando…", "Pronto: …"); pausar segura o
   agente e o app recusa as ações enquanto isso; interromper encerrou a tarefa em 0,4 s. O clique do próprio toque do
   agente chega uns 300 ms depois do gesto: é descartado quando cai no ponto em que o agente tocou. Durante um gesto do
   agente a faixa não recebe toques (o toque que cairia nela vai ao app de baixo).

2. **Instruções do usuário.** Campo de texto na faixa (com o teclado do usuário); a instrução passa pelo julgamento e
   vira um pedido de ajuda ao provedor com a frase do usuário e a tela atual. Toque do usuário pausa o agente até a
   tela parar.
   **Feita em 2026-10-19.** Ao tocar no campo, a faixa sobe e o teclado do usuário volta (pelo `softKeyboardController`
   do serviço de acessibilidade); ao enviar, volta o do agente. A instrução vai ao provedor como um pedido de ajuda com
   prioridade sobre o plano, sem contar no limite de ajudas, e a tarefa não ensina o cache. Conferido: no meio de
   "abre as configurações de bateria", a instrução "na verdade abre as configurações de som" levou o agente ao som.
   Falta: as mensagens do fim vêm em inglês do executor e do provedor ("Pronto: Done, and confirmed on screen.").

3. **Perguntas do agente.** Quando o provedor não resolve (limite de ajudas, mesmo passo), em vez de falhar, ele
   escreve uma pergunta (com opções, se couber); a faixa mostra, o usuário responde, a resposta volta como na etapa 2.
   Senhas pela marcação `secret`.
4. **Interpretação e "estava certo?".** A faixa mostra a interpretação antes do primeiro passo e, no fim, o resultado
   com "estava certo?"; a correção vai para o registro.
5. **Painel e treino.** O painel mostra a linha do tempo do live mode; o treino passa a ler `logs/live/`.

Voz e o modo tutorial ficam para depois da etapa 5.

## Modo contínuo (2026-10-24)

O que o Pedro pediu: "o microfone fica aberto sempre e não tem finalização de tarefa": pedir algo, depois mais coisas,
sem encerrar ("abre o YouTube" → "fica rolando a tela" → "clica no vídeo x" → "abre o Instagram" → "vai nas mensagens"
→ "finalizar"), ligado pela interface ou pelo app. Decisões dele: uma fala no meio de um pedido vira o próximo pedido;
só "finalizar" ou o X encerram (sem desligar sozinho por tempo).

Como ficou:

- **Ligar.** O botão ∞ na faixa (durante um pedido: o app avisa o PC por um evento e chama `POST /live` "iniciar") ou
  no painel do assistente (só `POST /live`). O serviço liga a acessibilidade e a deixa ligada (`service.CONTINUOUS`);
  a faixa aparece como o círculo, com o microfone no lugar do ícone e o anel vermelho enquanto ouve.
- **Cada fala.** O app reconhece no aparelho, como antes, e manda o texto como um pedido (`/task` com "continuo"),
  dentro da mesma conversa (o assistente lembra os pedidos anteriores). Texto escrito na faixa vale igual. Se há um
  pedido em curso, o app manda "novo_pedido": `live.gate` encerra o pedido em curso (`Stopped(NEW_REQUEST)`, sem
  "Interrompido."), e o novo espera a vez. Um "novo_pedido" que sobrou na fila é descartado no começo do pedido seguinte.
- **Comandos.** "Finalizar", "encerrar", "tchau" encerram tudo (como o X); "pausa"/"espera" e "continua" valem como os
  botões; com uma pergunta do agente em aberto, a fala é a resposta.
- **A resposta.** Aparece na faixa, é lida e, 7 s depois, a faixa volta a ser o círculo. O microfone fecha enquanto o
  agente fala e reabre depois.
- **"Fica rolando a tela".** Ação `keep_scrolling`: uma rolagem a cada poucos segundos, sem fim, até o pedido seguinte
  (ou 10 min). Não conta nos passos da tarefa.
- **Entre os pedidos** o teclado volta a ser o do dono, e a lista dos apps de banco fica no app: se um deles vier para a
  frente, o serviço de acessibilidade se desliga sozinho, sem esperar o PC.

Pontos de falha e contrapontos:

1. **O microfone aberto ouve tudo.** A TV, outra pessoa ou o próprio dono falando com alguém viram pedidos. O
   reconhecimento é só do aparelho (nada de áudio sai), mas um pedido ouvido errado age no celular. As ações que não se
   desfazem continuam pedindo confirmação; o resto (abrir um app, rolar) é barato de desfazer.
2. **Sem fim por tempo, a acessibilidade pode ficar ligada horas.** É o risco dos apps de banco: o app se desliga ao ver
   um deles na frente, mas um banco que olhe os serviços ligados antes do evento de janela ainda pode bloquear. Por
   isso o anel e o ícone do círculo mostram que o modo está ligado.
3. **Bateria.** O reconhecedor reinicia a cada silêncio; é o custo de não ter palavra de ativação.
4. **O agente ouvir a si mesmo.** O microfone fecha durante cada fala do agente; uma fala cortada por outra (sem aviso
   de fim) é coberta por uma nova tentativa a cada meio segundo.
5. **Fala no meio do pedido.** O pedido em curso só para na volta seguinte do ciclo (depois da chamada ao provedor
   em curso): pode haver mais uma ação dele antes de parar.


## Interface flutuante (2026-11-10)

Proposta do Pedro em `pedro/novo-desing`: vidro fosco, altura que acompanha o texto e toque fora para pausar e assumir
os controles. Acrescentada a alça superior que arrasta o container como um picture-in-picture.

Implementado:

- `Ui.glass`: desfoque nativo da janela, borda e fundo translúcido; acompanha a disponibilidade do desfoque e usa um
  fundo mais fechado quando ele está desligado. Sem captura da tela.
- `FloatingPanel` e `PanelPosition`: arraste pela alça, posição proporcional salva e compartilhada pelo painel do
  assistente e pela faixa, limites pelas barras do sistema/corte da tela e pelo teclado. Os textos têm altura limitada
  e rolagem; o container cresce conforme o conteúdo. Ativar a alça sem arrastar alterna entre alto e baixo, inclusive
  pelo leitor de tela. O agente pode afastar a faixa durante um gesto e depois devolver à posição anterior.
- O arraste bloqueia novas ações localmente (`Live.dragging`) e aparece como `typing` no protocolo já usado pelo PC e
  pelo cérebro Kotlin. Soltar a alça libera o bloqueio de arraste, preservando os outros bloqueios.
- O botão da mão foi removido. A faixa e o círculo observam `ACTION_OUTSIDE` com `FLAG_WATCH_OUTSIDE_TOUCH`: numa
  tarefa, um toque externo pausa e passa a vez ao dono. Continuar remove pausa e vez do dono; o ciclo existente lê a
  tela antes de decidir a próxima ação. Os gestos do agente e a guarda de 1,5 s depois deles são ignorados. Enquanto
  se escreve na faixa, toques externos são do teclado e não disparam essa troca; no modo contínuo ocioso, não pausam.
- O painel do assistente conserva fechar ao tocar fora; ele sai antes de a tarefa começar, como antes.

Validação: APK de depuração compilado; seis testes JVM cobrem limites, teclado/crescimento do texto, rotação,
restauração da posição e bloqueio durante arraste. Os 237 testes Python passaram. O lint completo aponta o erro
preexistente `CoarseFineLocation` no manifesto (há FINE sem COARSE), além de avisos.

**Pendente no S23+** (nenhum aparelho conectado nesta sessão): aparência do vidro nas duas janelas, crescimento e
arraste com teclado, alternância painel/faixa/círculo, eventos de toque externo em áreas vazias e rolagens, distinção
dos gestos do agente e continuação depois de o dono mudar a tela. A implementação de observar toques externos precisa
dessa conferência: os testes JVM não exercitam o WindowManager nem o input da One UI.


## Correção do visual e do arraste (2026-11-10)

A primeira implementação manteve controles grandes e dependia só do blur nativo. No S23+ o Android informa que
cross-window blur não é suportado, então não havia vidro fosco. A posição também dependia dos insets da própria
janela, que variam enquanto ela se move, realimentando o cálculo.

Correções:

- A disposição segue os estados compacto e expandido do print: título de 13 sp, corpo separado que só aparece com
  texto maior, três controles de 22 dp no cabeçalho (mudar de lado, minimizar com traço, fechar), botões de 36 dp na
  base e entrada de 34 dp. A cor de destaque pedida pelo Pedro é **#305cde**, também nos ajustes do app. O botão de
  envio substitui o infinito quando há texto; o controle de voz da resposta fica no toque longo no microfone.
- A alça não alterna mais entre alto e baixo ao receber um toque simples; só arrasta. Os limites vêm dos insets da
  tela inteira e são congelados durante o gesto. Alterar só a posição não refaz o layout; o vidro é redesenhado na
  nova posição. Crescimento do texto e teclado preservam a âncora sem usar a janela como referência de seus limites.
- `FrostedGlass` usa o blur nativo onde existe. Sem ele, `GlassBlur` desfoca uma imagem reduzida com três filtros de
  caixa. A faixa captura só a janela de baixo (`takeScreenshotOfWindow`, `canTakeScreenshot`), a cada 600 ms enquanto
  expandida, sem capturar a própria sobreposição. Só pixels pequenos e já desfocados ficam no drawable; os buffers
  originais são liberados. Imagens não vão para logs, arquivos, modelos locais ou provedor. Minimizar/fechar limpa o
  fundo e para as capturas. Janela protegida ou falha de captura deixa o fundo fechado.
- O painel inicial pede `SHOW_WITH_SCREENSHOT | SHOW_WITH_ASSIST` e usa `onHandleScreenshot`. O Android só entrega
  a imagem se ambos os flags e as opções “Usar captura de tela” e “Usar texto da tela” estiverem ligados. O Pedro
  autorizou as duas opções em 2026-11-10. `onHandleAssist` é um descarte explícito: não lê nem encaminha a estrutura
  extra que o sistema exige entregar. Não liga acessibilidade só por causa do vidro. Para reverter, desative essas
  duas opções do assistente (secure settings `assist_screenshot_enabled` e `assist_structure_enabled` = 0).
- A conferência visual tem uma Activity e um receiver só no APK debug, protegidos pela permissão DUMP, para mostrar
  um fundo fictício e consultar apenas geometria/estado do vidro, sem expor textos nem pixels do celular.

Conferido no S23+: vidro real na faixa com `native=false` e fonte local presente; arraste vertical de 1.766 px, sem
recuos nas amostras e sem oscilação nos 12 registros depois de soltar; toque fora pausa e Continuar libera; texto
expandido; teclado com 8 posições idênticas e retorno ao fechar. O painel inicial também foi conferido quanto ao
arraste. Depois da autorização das duas opções e dos flags de contexto 3, o vidro dele foi confirmado no aparelho
(`glass=true`, `native=false`, captura recebida), consultando só metadados e sem exportar a imagem. O APK compila e os oito testes JVM passam,
incluindo duas verificações de desfoque real (cor uniforme e borda suavizada).


## Subida do arraste, microfone e contornos de cor (2026-11-10)

Retorno do Pedro: a subida ainda prendia de vez em quando, o microfone virava um botão de teclado desnecessário e o
vidro apresentava ondas/faixas de cor.

- A janela `VoiceInteractionWindow` recorta o MotionEvent às suas bordas; o dedo sai logo da borda superior ao subir.
  O `FloatingPanel` envolve o callback da janela e trata o gesto em coordenadas raw antes desse recorte. Os eventos
  são agrupados por quadro com `Choreographer`; o caminho do MOVE só altera x/y em pixels. As dimensões ficam fixas
  até soltar, sem percorrer textos/insets a cada movimento. A faixa não captura novas imagens durante o arraste, e
  o vidro só aplica uma textura que terminou de processar quando o gesto acabar.
- Retirado o botão de esconder teclado e a troca do ícone de microfone por teclado. Tocar no input cancela a voz e
  abre a escrita; o microfone permanece visível, fecha o teclado e liga a voz de novo. O texto corrigido é preservado
  e a nova fala é acrescentada (`VoiceDraft`); parciais substituem só a parte nova. No contínuo, escolher texto impede
  o loop de religar o microfone por trás da edição. O reconhecedor é cancelado ao trocar para texto, com callbacks
  de instâncias anteriores descartados; `stopListening` podia entregar um resultado final atrasado.
- O filtro inteiro usa ponto flutuante, sem truncar RGB a cada passada. A fonte foi aumentada de 360 para 720 px na
  maior dimensão e o resultado é RGBA_F16, preservando gradientes sutis até a renderização. A camada sobre o fundo é
  uniforme: removido o degradê artificial. A regra de imagens só locais permanece.
- O receiver de prévia bloqueia envio/execução, para testar a alternância com o reconhecedor real sem gerar tarefas.
  A exportação opcional desenha só o próprio painel com texto e fundo fictícios; não é um screenshot de outros apps.

Validação no S23+: faixa em RGBA_F16; subida de aproximadamente 1.770 px com 169 quadros aplicados em 1,5 s, sem recuos
(intervalo máximo de 17,1 ms na amostra), descida com 171 quadros e intervalo máximo de 16,0 ms. No painel inicial,
170 quadros na subida e 173 na descida, sem recuos (máximos de 25,0 e 18,3 ms). Nos dois, tocar no input deixou a voz
desligada e o teclado ativo; tocar no microfone voltou à voz, com teclado fechado, botão visível e o rascunho fictício
de cinco caracteres intacto. Voltar ao texto também passou. Onze testes JVM passaram, incluindo o gradiente escuro
com valores sub-byte e a preservação do rascunho. APK instalado com sucesso.

A conferência visual final das faixas de cor não foi concluída: o telefone desconectou do ADB depois da instalação
(sem aparelho no USB nem reconexão sem fio disponível). O formato F16 foi confirmado no aparelho antes disso; a
aparência final ainda precisa ser julgada na tela. Os números acima são amostras do teste, não garantia de todos os
quadros em qualquer carga do aparelho.


## Blur simples (2026-11-10)

O Pedro preferiu abandonar o acabamento de vidro. O fundo compartilhado agora usa desfoque de 12 dp
(nativo quando disponível, ou filtro local existente), sem borda brilhante e sem tonalização cinza.
Só uma camada preta uniforme de 25% ajuda a ler os controles; não há degradê nem efeitos de brilho.
O processamento F16 e as regras de privacidade continuam. Compilação e onze testes JVM passaram;
APK instalado no S23+ preservando os dados. A preferência visual fica para avaliação do Pedro no aparelho.


## Abertura sem flash cinza (2026-11-10)

A janela aparecia com o fundo sólido enquanto a captura e o filtro rodavam em segundo plano.
Agora `beginOpening` oculta a janela com alpha=0 e só a revela quando o primeiro resultado é aplicado.
Se não houver captura ou ela demorar mais de 1,2 s, abre sólido e ignora resultados tardios até a próxima
abertura, evitando outra troca de fundo. O modo nativo abre diretamente. Ocultar cancela a espera.
A mesma implementação atende a faixa e o painel inicial. A prévia debug também passou a consultar o
InsetsController depois de criar o decor, corrigindo uma falha que impedia o teste com fundo fictício.

Compilação e onze testes JVM passaram. APK instalado no S23+. Três aberturas do painel inicial sobre a
Activity fictícia passaram: todas as amostras sem imagem tinham alpha=0, seguidas de alpha=1 com blur
pronto. Conferência por metadados; não foram exportados screenshots nem textos do aparelho.


## Menu na barra e minimizar do painel inicial (2026-11-10)

Nova preferência na tela principal: Interface > Reunir ações na barra superior. Padrão desligado, preservando
os três botões. Ligada, oculta os botões e usa um PopupMenu na alça com Mudar de lado, Minimizar e Fechar.
O toque abre o menu e o arraste só move a janela; release após arraste ou cancelamento não abre menu.
A configuração é aplicada na próxima abertura do painel inicial ou expansão da faixa.

O minimizar do AssistSession chamava hide(), sem oferecer círculo para voltar. Agora troca o conteúdo da
própria janela por um círculo de 56 dp, com fundo próprio, sem blur nem captura atrás dele. Não depende de
acessibilidade ou nova permissão. Para a escuta e a fala, fecha o teclado, cancela o fechamento automático
e mantém o rascunho. Tocar fora não fecha o círculo; ele pode ser arrastado. Tocá-lo pede nova captura ao
Android, restaura o painel e retoma a escuta com o texto existente. A faixa mantém seu círculo existente.

Validação: compilação e onze testes JVM passaram; APK instalado no S23+. Sobre fundo fictício, o botão e
o menu minimizaram nos dois painéis. No painel inicial, toque externo preservou o círculo; tocar nele
reabriu com blur; o menu Fechar respondeu. Arraste do círculo e preservação de rascunho fictício de cinco
caracteres também passaram. As preferências e a acessibilidade usadas no teste foram restauradas.


## Gestos da alça no modo menu (2026-11-10)

Pedido do Pedro: com as ações reunidas na barra, arrastar para o lado minimiza; puxar para baixo quando
já se chegou ao limite inferior encerra como Fechar. Implementação compartilhada no FloatingPanel, só
para a alça original e com a preferência ligada. A ação ocorre ao soltar: lateral de pelo menos 72 dp
e 1,5 vez o movimento vertical minimiza; puxada predominantemente vertical ultrapassando o limite
inferior em 56 dp fecha. O movimento é medido antes do clamp da posição, permitindo detectar a puxada
mesmo com a janela parada na borda. Cancelamento, toque curto, diagonal e arraste do círculo não disparam
essas ações. A faixa usa a mesma rotina de encerramento do X, mas a puxada deliberada não precisa de
confirmação por outro gesto; a proteção de gestos do agente permanece.

O teste revelou retorno intermitente do círculo com fundo sólido: ao pedir show em uma sessão ainda
visível, o Android podia não entregar nova captura. O círculo agora solicita hide e, depois de onHide,
pede show com os flags de captura. Screenshots adiantados são mantidos só na RAM até onShow; ocultar
ou destruir limpa os pendentes. O conteúdo continua sendo revelado somente após o blur ficar pronto.

Validação: quinze testes JVM passaram (quatro novos casos de direção, limiar inferior, movimentos
pequenos/diagonais e subida). No S23+, sobre fundo fictício: modo tradicional não minimizou ao arrastar
para o lado; modo menu minimizou nos dois painéis; puxar além da borda fechou o assistente e encerrou
a faixa. Subida normal continuou movendo o painel e o círculo reabriu com blur. APK instalado; as
preferências de menu e a acessibilidade foram restauradas ao estado anterior aos testes.


## Preferência para desligar o blur (2026-11-10)

Nova chave persistida em interface/blur, padrão true, com o controle Desfocar o fundo (blur) na seção
Interface da tela principal. A alteração vale na próxima abertura/expansão. Sem blur, o fundo é somente
#B3202024, com transparência real, preservando o arredondamento e os controles. FrostedGlass desliga
o blur nativo, invalida imagens pendentes e abre imediatamente com alpha=1. A faixa não captura nem
agenda atualizações de imagem nesse modo. O painel inicial preserva os flags de integração com o
Android; o framework ainda pode entregar uma captura, descartada pelo callback sem processamento.
O contexto extra de texto segue ignorado. Nenhuma opção de privacidade do Android foi alterada.

Reativar restaura o blur e a espera pelo primeiro resultado, com o fallback existente se o Android
não entregar a captura. A habilitação nativa também respeita a ausência de fundo no círculo minimizado.
Compilação e quinze testes JVM passaram. APK instalado no S23+; sobre fundo fictício, os dois painéis
abriram sem fonte de imagem e com alpha=1 quando desligados. Ao reativar, ambos voltaram a ter fonte
de blur; no painel inicial foram conferidos flags=3. Preferências e acessibilidade restauradas após o teste.
