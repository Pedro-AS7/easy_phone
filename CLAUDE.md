# easy_phone

Assistente de IA que opera o celular Android como um usuário (abre apps, lê a tela, toca, rola, digita).

**Intuito (decisão do Pedro, 2026-11-16, `docs/plano-tutor.md`):** um **assistente técnico para quem tem dificuldade
com o celular**, como idosos. O foco é ensinar, explicar e consertar ("como eu faço...", "a letra tá pequena", "sumiu o
ícone"), e esse fluxo (o guia) tem de estar redondo: por padrão a pessoa toca e o agente aponta, explica e espera; uma
opção do app troca para o agente fazer explicando. Fazer tarefas do dia a dia pela pessoa (mensagem, ligação, rota no
Waze) é o foco secundário. Na dúvida entre duas soluções, vale a que serve melhor a quem tem dificuldade: a interface
padrão é o modo simples (letra grande, poucos botões, nenhum gesto obrigatório).

A regra central do projeto: **dado pessoal não sai do aparelho sem máscara**. Uma IA local entende o pedido e mascara
os dados; uma IA de provedor (nuvem) planeja os passos vendo só dados falsos.

Este arquivo descreve a versão em vigor (**pv1**, 2026-10-16) e as decisões que valem para ela. O registro completo de
como se chegou aqui, com todas as medições, está em `docs/historico.md`. Ao mudar uma decisão ou concluir uma etapa,
atualize aqui; medições longas vão para o histórico.

## Estado (pv1)

Protótipo no notebook: o serviço roda no PC e controla o Galaxy S23+ por ADB, pelo app Mobilerun Portal.

| Parte | Estado |
|---|---|
| Ciclo próprio (ler a tela pelo Portal, decidir, agir pelo adb) num serviço que fica no ar | Funciona |
| Plano escrito pelo provedor, executado por código e pelo modelo de escolha, com objetivo conferido no aparelho | Funciona; suíte de 24 casos |
| Mascaramento: regras fixas, cofre, valores falsos por tarefa, modelo de marcação julgando pedido e telas | Funciona |
| IA local: modelos pequenos (ONNX na CPU) no lugar da Gemma e do Laya, desde 2026-10-19 | Funciona; a Gemma e o Laya ficam como opção |
| Cache de caminhos e mapa dos apps | Funciona |
| Acessibilidade e teclado do Portal ligados só durante a tarefa; trava para apps de banco | Funciona; o Inter abre normalmente com o Portal instalado e desligado |
| Prints com OCR e fotos borradas | Não existe (a tela vai só como texto) |
| Confirmação de ações sensíveis: antes de enviar, comprar, pagar, apagar, publicar ou ligar, o agente pergunta na faixa (voz ou toque); sem a faixa, a pergunta é a resposta e um "sim" no pedido seguinte libera | No código desde 2026-10-24, com testes; falta conferir no celular |
| Celular sem cabo (depuração sem fio do Android), com o cabo preferido quando há os dois | No código desde 2026-10-24; falta parear e conferir |
| Pesquisa: quando o provedor não sabe com certeza, o Google do próprio celular pesquisa e ele responde vendo os resultados | Desde 2026-10-24; conferida no celular ("o que é o esporte hirox": 19,6 s) |
| App Android próprio com IA no aparelho | Etapa 2 de `docs/plano-app-android.md` (2026-10-26): os modelos pequenos rodam no app, com as mesmas respostas do PC no conjunto congelado. Etapa 3 em andamento: o cérebro traduzido para Kotlin (`android/cerebro`) confere com o Python (trilhas do executor, máscara, IA local) e já fez um pedido no celular sem o PC, escolhido na tela do app; falta a suíte com ele |
| Live mode: faixa flutuante no app (andamento, pausar, instruções faladas ou escritas, minimizar para um círculo, abrir sozinha numa pergunta respondida por voz, X que fecha e encerra), registro em `logs/live/` | Etapas 1 e 2 de `docs/plano-live-mode.md` e a interface de 2026-10-22, com `LMPHONE_DEVICE=app`; desde 2026-10-24 a faixa começa como o círculo |
| Live mode contínuo: microfone aberto, cada fala é um pedido da mesma conversa (uma fala no meio de um pedido vira o seguinte), até "finalizar" ou o X; ligado pelo botão ∞ da faixa ou do painel | No código desde 2026-10-24; falta conferir no celular |
| Estado do aparelho no plano (`facts.py`), objetivo por fato, detector de repetição | Funciona |
| Assistente: turno com responder, ver a tela, perguntar, agir ou guiar; conferência final sempre; resposta em português; conversa com memória (`run --conversa`) | Etapas 1 e 2 de `docs/plano-assistente.md`; suíte de 40 casos (5 de conversa) pelo app, linha de base em `docs/plano-orquestrador.md` |
| Chamar o assistente pelo celular: o app como assistente digital (tecla lateral), painel próprio, pedido ao PC por `adb reverse` com senha (`run --celular`) | Etapa 3 de `docs/plano-assistente.md`, conferida no celular |
| Voz no painel e na faixa: fala reconhecida só no aparelho, resposta lida com voz local, microfone e alto-falante | Etapa 4 de `docs/plano-assistente.md`; na faixa, uma resposta falada já foi reconhecida (2026-10-22) |
| Chamar pela voz: dizer "Alexa" abre o painel já ouvindo (detector do openWakeWord no app; o som fica no celular); os botões da faixa e do painel também falados ("Alexa, pausa", "Alexa, para", "Alexa, live mode") | No app desde 2026-10-26; o Kotlin dá as mesmas notas da biblioteca do Python; "Alexa" abriu o painel com a voz do dono; os comandos conferidos pelo reconhecedor com frases sintéticas; falta a ponta a ponta numa tarefa e a bateria |
| Narração e guia na faixa (passo dito e destacado), vez do dono (botão da mão ou "deixa que eu faço": o agente mostra e acompanha) | Etapa 5 de `docs/plano-assistente.md`, conferida no celular; no guia o agente ainda toca depois de 5 s (a fase 2 de `docs/plano-tutor.md` muda o padrão para a pessoa tocar) |
| Prompts de ajudante técnico paciente (ensinar e consertar primeiro, linguagem simples, sintoma vira causa, caminho resumido no fim do guia) | Fase 0 de `docs/plano-tutor.md` (2026-11-16); testes e `:cerebro:conferir` passam, falta medir no celular |
| App da Play Store (variante `loja`: só ensina, o agente nunca age) | Fases 0 a 4 de `docs/plano-play-store.md` no código (2026-11-16): variante `loja`, executor só guia (`acts`), servidor do provedor (`servidor/`, 150 pedidos por mês), modelos num pacote de recursos, tela inicial com o aviso, denúncia; um guia inteiro no S23+ sem nenhuma ação do agente. Falta publicar o servidor, a Play Integrity no app e tudo o que pede a conta do Pedro |
| Orquestrador no provedor com ferramentas (protótipo separado) | Descartado em 2026-10-21 depois da etapa 1 (32 de 45 rodadas, 3 vezes as chamadas); medição em `docs/plano-orquestrador.md`, código em `arquivo/orquestrador-etapa1/` |

Suíte inteira na One UI 9.0 (Android 17), pelo app, com o cache e o mapa zerados (`reports/suite-2026-10-22-105505`,
2026-10-22): 38 de 45 rodadas passaram, 18,7 min, US$ 0,050 (metade da entrada lida do cache de prompt), 115 chamadas.
Das 7 que não passaram, 6 vinham da One UI 9 e do mapa zerado (modo escuro sem o nome "Dark mode", modo avião fora das
Conexões e do painel rápido) e passaram depois das correções de `open_settings` e da escolha dividida; fica
`cam-flash` (pedido ambíguo, conhecido; trocado por um pedido claro em 2026-10-24, ainda não rodado).

Suíte inteira com o assistente na One UI 8.5, pelo app (`reports/suite-2026-10-21-105756`, 2026-10-21): 39 de 45 rodadas
passaram, 17,7 min, US$ 0,067, 101 chamadas, 305 mil caracteres de tela enviados; as 6 que não passaram foram
corrigidas e passaram em seguida (detalhes na linha de base de `docs/plano-orquestrador.md`).

Suíte inteira na pv1 (`reports/suite-2026-10-16-115733`, Haiku 5.5, cache e mapa de antes): 21 de 26 execuções
passaram, 4 falharam, `cam-flash` ficou para conferência manual; 8,1 min, US$ 0,021. Falharam `ig-seguindo` e
`notion-ajustes` (conhecidos), `notion-pagina` (o Laya abriu uma página existente no lugar de "New page" e a primeira
digitação caiu fora de um campo) e `ig-privada` (o agente confirmou a chave, a conferência da suíte não a achou; a
leitura da conferência passou a esperar a tela estabilizar depois de ligar a acessibilidade). Os dois últimos ainda
não foram repetidos. Os 4 casos que antes rodavam pelo agente do Mobilerun passaram pelo plano.

**Foco desde 2026-11-17 (pedido do Pedro): o app da Play Store, a variante `loja`.** Todo pedido e todo teste dele
vale para ela, salvo quando ele disser o contrário; os testes no celular rodam na `loja` (`docs/plano-play-store.md`,
"Como rodar a loja"), e a `completo` fica como ferramenta de desenvolvimento. Conta, Cloud Run e Play Console ficam para
depois de o app estar pronto.

**Próximos passos (desde 2026-11-16): as fases de `docs/plano-tutor.md`.** A fase 0 (intuito, prompts de ajudante
técnico, pendências conferíveis sem o Pedro) foi feita; a seguinte é a suíte em português do guia e dos sintomas.
Defeito achado na fase 0: depois do `set` que religa o Wi-Fi, o celular não voltou sozinho a nenhuma rede salva.
Na fase 1 (em andamento): a suíte ganhou os níveis `guia` e `sintoma`, os pedidos em português e a pessoa simulada
(`tests/pessoa.py`); o toque da pessoa no destaque do guia pausava a tarefa desde 2026-11-10 (corrigido no app).
Fase 1 concluída em 2026-11-16: nenhum guia passa em todos os critérios (objetivo em 3 de 8), sintomas 4 de 6,
casos antigos em português 38 de 41 depois das correções; cache e mapa das telas em inglês zerados. A seguinte é a
fase 2 (o guia redondo), com a lista do que a linha de base pede em `docs/plano-tutor.md`.
Proposta de 2026-11-16: publicar na Play Store uma variante que só guia (o agente nunca age), em
`docs/plano-play-store.md`; depende das fases 2 e 5 do tutor, e as decisões do início do plano são do Pedro.

Próximos passos anteriores: pedidos ambíguos (o do flash), nomes de usuário que a Gemma não acha (`ig-seguindo`), URL marcada
como pessoa, controles sem texto (`notion-ajustes`), confirmação automática de diálogos olhando o sentido da mudança.
Em andamento: trocar a Gemma e o Laya por modelos pequenos treinados nos casos do celular
(`docs/plano-modelos-pequenos.md`); a etapa 0 (conjunto congelado e linha de base) foi concluída em 2026-10-17, e a
coleta da etapa 1 (`LMPHONE_COLETA=1`) existe desde o mesmo dia e juntou, numa noite, 561 tarefas, 37 mil trechos e
1.549 escolhas (números no plano). Etapas 2 a 4 (dados sintéticos, professor local, treino) concluídas em
2026-10-19: no conjunto congelado o modelo novo mascara 185 de 187 pessoas e 38 de 38 usuários (a Gemma, 182 e 36) e
acha 110 de 217 controles com 11 toques errados (o Laya, 102 e 14). Etapa 5 (ONNX na CPU) concluída no mesmo dia:
mesmo acerto, 346 MB no disco, uns 660 MB de memória (o Ollama e o Laya somam 5,4 GB), 5 a 30 ms por chamada.
Etapa 6 concluída no mesmo dia: os modelos pequenos são o padrão. Suíte (`reports/suite-2026-10-19-133549`): 25 de 26
execuções passaram, nenhuma falhou (`cam-flash` pede conferência manual), 10,9 min, US$ 0,012, 0,8 GB; com a Gemma e o
Laya na mesma hora, 23, 14,3 min e 4,3 GB.

**Interface de 2026-11-10** (`pedro/novo-desing`, `docs/plano-live-mode.md`): os estados compacto e expandido
seguem o print do Pedro, com controles de 22 dp no cabeçalho e de 36 dp na base, alça superior e destaque **#305cde**.
A posição é guardada e compartilhada pelo painel e pela faixa; o arraste usa limites fixos da tela (nunca os insets
recortados pela janela), sem salto ao tocar na alça. Um toque externo pausa e passa a vez ao dono; Continuar limpa os
dois estados. Gestos do agente e a guarda de 1,5 s depois deles são ignorados, assim como toques no teclado durante a
escrita. Arrastar bloqueia ações no app e aparece como `typing` para os dois cérebros.
O S23+ não oferece o desfoque padrão (`wm disable-blur`: suportado=false). O vidro da faixa usa a captura da janela
abaixo dela (API de acessibilidade), reduzida e desfocada só na RAM; não inclui a própria faixa, não é gravada e nunca
entra no cérebro nem no provedor. O painel inicial usa a captura entregue pelo Android ao assistente. O Android exige “Usar captura de tela” e
“Usar texto da tela” ligados: o Pedro autorizou ambos em 2026-11-10; `onHandleAssist` descarta o contexto extra sem
ler nem encaminhar a estrutura. Se a captura é bloqueada ou a janela protegida, o fundo fica fechado. A acessibilidade
continua desligada fora de tarefas: não é ligada só para obter esse fundo. Conferido no celular: vidro da faixa,
arraste de 1.766 px sem recuos nem oscilação parado, texto expandido, teclado e pausa/continuação por toque externo;
vidro do painel inicial também confirmado no aparelho com os flags de contexto 3 e a fonte local recebida.

**Ajustes do arraste, da entrada e do vidro (2026-11-10).** O `FloatingPanel` recebe o gesto pelo `Window.Callback`
antes do recorte de `VoiceInteractionWindow` (que prejudicava a subida), fixa as dimensões durante o arraste e aplica
só x/y uma vez por quadro pelo `Choreographer`, sem medir textos no caminho do gesto. Capturas/trocas de textura do
vidro aguardam o fim do arraste. O microfone nunca vira botão de teclado: tocar no campo cancela a escuta e abre o
teclado; o microfone fica visível e volta à voz, fechando o teclado e preservando o rascunho (`VoiceDraft`). O modo
texto impede a reabertura automática do microfone no contínuo. `Listener.stop` cancela/destroi o reconhecedor e ignora
callbacks antigos, evitando um resultado final atrasado sobre a edição. O vidro calcula os filtros em ponto flutuante,
usa fonte de até 720 px e bitmap RGBA_F16, com camada neutra uniforme (sem degradê adicional). Onze testes JVM passam;
subida/descida e texto→voz→texto foram conferidos nos dois painéis do S23+, com rascunho preservado e microfone visível.
A versão foi instalada; a inspeção visual final do vidro ficou pendente porque o celular saiu do ADB após a instalação.

**Blur simples (2026-11-10).** A pedido do Pedro, substituído o acabamento de vidro por desfoque de 12 dp,
sem borda brilhante nem tonalização. Sobre a imagem há somente preto uniforme a 25% para leitura dos controles.
Vale para a faixa e o painel inicial; mantém o processamento local em F16 e o fundo fechado se não houver captura.
APK atualizado instalado no S23+ por `adb install -r`; compilação e os onze testes JVM passaram.

**Alinhamento dos controles (2026-11-10).** `Ui.headerActions` distribui os três botões superiores
na largura exata de microfone + margem + live mode, calculada em pixels para evitar diferenças de arredondamento
de dp. Assim, as bordas esquerda e direita dos dois grupos coincidem na faixa e no painel inicial.

**Abertura sem flash cinza (2026-11-10).** `FrostedGlass.beginOpening` mantém a janela transparente até o
primeiro blur ficar pronto, revelando conteúdo e fundo juntos na faixa e no painel inicial. Captura bloqueada
ou espera acima de 1,2 s revela o fundo sólido; nesse caso não troca para blur tardiamente nessa abertura.
Fechar cancela a espera e invalida o processamento pendente. Instalado no S23+: três aberturas do painel inicial
conferidas por metadados, sempre alpha=0 sem imagem e alpha=1 só com blur pronto; onze testes JVM passam.

**Menu na alça e minimizar do assistente (2026-11-10).** A tela principal tem Interface > Reunir ações na
barra superior, desligado por padrão. Quando ligado, os três botões somem e tocar na alça abre Mudar de lado,
Minimizar e Fechar; arrastar continua movendo. A preferência vale no painel inicial e na faixa, na próxima
abertura. `FloatingPanel` distingue toque de arraste e aciona o clique só sem movimento. O minimizar do painel
inicial deixa de chamar `hide`: agora troca o conteúdo por um círculo de 56 dp na mesma janela, sem ligar
acessibilidade. O círculo é arrastável, ignora toques externos e reabre pedindo nova captura local para o blur.
Pausa a escuta ao minimizar, cancela o fechamento automático e preserva o rascunho ao retornar. Instalado no S23+:
botão e menu conferidos nos dois painéis; círculo, arraste e rascunho preservado conferidos no painel inicial.

**Gestos na alça com menu (2026-11-10).** Com Reunir ações na barra superior ligado, soltar um arraste
lateral definido (72 dp, predominância horizontal) minimiza. Puxar para baixo 56 dp além do limite inferior
fecha o painel inicial ou encerra a tarefa na faixa, sem exigir o segundo toque do X. Movimentos diagonais,
curtos, cancelados, no círculo ou com a preferência desligada não disparam essas ações. Arraste vertical
normal continua reposicionando. `PanelGesture` classifica a intenção usando o movimento bruto, antes do
clamp da janela. Reabrir pelo círculo agora aguarda onHide antes de pedir nova captura: sessão já visível
podia não receber screenshot novo. Captura entregue antes de onShow fica só na RAM até a abertura.
Quinze testes JVM passaram; ambos os gestos foram conferidos nos dois painéis do S23+, com APK instalado.

**Blur opcional (2026-11-10).** Interface > Desfocar o fundo (blur), ligado por padrão, salva a preferência
para o painel inicial e a faixa. Desligado, a próxima abertura usa fundo #B3202024 (70% opaco), sem blur
nativo, imagem de fundo nem espera por captura. A faixa também para as capturas periódicas. O painel mantém
a integração de contexto do Android, mas descarta qualquer screenshot recebido enquanto o efeito está
desligado; o contexto de texto continua descartado. Reativar restaura o comportamento anterior. Quinze
testes JVM passam; desligar e religar foram conferidos nos dois painéis do S23+, com APK instalado.

## Como rodar

O projeto roda em duas máquinas que valem igual: o notebook (Linux) e a máquina da RTX 5060 (Windows 11, sem WSL).
Os comandos abaixo são os do Linux. No Windows: `run "..."` (o `run.cmd`) no lugar de `./run.sh "..."`, e
`.venv\Scripts\python.exe` no lugar de `.venv/bin/python` (o mesmo para `.venv-laya`). O que muda entre os dois fica
em `lmphone/host.py`.

```sh
./run.sh "Turn on dark mode"                    # uma tarefa (pedidos em inglês; o Laya só é bom em inglês)
./run.sh --conversa                             # conversa com o assistente pelo terminal: cada linha é um pedido, e ele lembra os anteriores
./run.sh --celular                              # o assistente atende pelo celular (tecla lateral): sobe tudo no modo do app e liga o adb reverse
./run.sh --stop                                 # encerra o serviço e a IA local e desliga a acessibilidade do Portal
./run.sh --stop-laya                            # encerra só o servidor da IA local (porta 8788: modelos pequenos ou Laya)
MODEL=outro/modelo ./run.sh "..."               # outro provedor nesta tarefa (padrão: anthropic/claude-haiku-5.5)
LMPHONE_CACHE=0 ./run.sh "..."                  # ignora o cache de caminhos e o mapa
LMPHONE_DEVICE=app ./run.sh "..."              # o aparelho pelo app do easy_phone (android/) no lugar do Portal
LMPHONE_LOCAL_AI=gemma ./run.sh "..."          # a Gemma (Ollama) e o Laya no lugar dos modelos pequenos, como antes
LMPHONE_COLETA=1 ./run.sh "..."                 # grava dados de treino da tarefa em data/treino/real/ (vale também na suíte)
.venv/bin/python -m lmphone.treino status       # contagens da coleta por app e por fonte, sem conteúdo
.venv/bin/python -m tools.treino.sintetico --chamadas 5   # dados sintéticos pelo provedor (fictícios); --orcamento US$, --amostra N
.venv/bin/python -m tools.treino.professor rotular --modelo gemma4:12b   # rótulos da coleta pelo professor local; avaliar: no conjunto congelado; parafrasear: nomes de rótulos reais
.venv/bin/python -m tools.treino.dados          # conjuntos de treino da etapa 4 (data/treino/conjunto/), só contagens
.venv-treino/bin/python -m tools.treino.treinar marcacao   # ou escolha; modelos em data/treino/modelos/
.venv-treino/bin/python -m tools.treino.servidor --marcacao DIR --escolha DIR   # porta 8790; depois tests.eval_base --novo http://127.0.0.1:8790
.venv-treino/bin/python -m tools.treino.exportar DIR_MARCACAO DIR_ESCOLHA        # ONNX em DIR/onnx/ (modelo-tabela.onnx é o que vale)
.venv-modelo/bin/python -m lmphone.modelo_server --marcacao DIR/onnx --escolha DIR/onnx   # o servidor ONNX, porta 8788 (--porta)
.venv/bin/python -m tests.coleta --rodadas 3    # coleta noturna: 183 tarefas que só navegam, buscam e leem; --orcamento US$
.venv/bin/python -m lmphone.access status       # acessibilidade, teclado e depuração do Portal no celular
.venv/bin/python -m lmphone.sources             # reimporta contatos e contas do celular para o cofre
.venv/bin/python -m unittest discover -s tests  # testes unitários
.venv/bin/python -m tests.phone_suite           # suíte de 24 tarefas no celular; --listar, --nivel crucial, ids
.venv/bin/python -m lmphone.trace               # reports/tarefa-<sessão>.html, o diagrama da última tarefa do log
.venv/bin/python -m lmphone.painel              # painel local em http://127.0.0.1:8770: suítes, rodadas, IA local, provedor, log bruto
.venv/bin/python -m tests.eval_ia               # avalia a Gemma no mascaramento (reports/ia-local.html)
.venv-laya/bin/python -m tests.eval_laya        # compara pesos do Laya: acerto, tempo e memória
.venv/bin/python -m tests.eval_base             # linha de base (Gemma e Laya) no conjunto congelado, com a causa de cada erro; --caso id, --falhas
.venv/bin/python -m tests.captura nome          # print e texto da tela atual em data/capturas/ (dados reais, só no notebook)
android/build.sh                                # o app Android (android/), variante completo: compila, instala pelo adb e abre; no Windows, android\build.cmd
android/build.sh loja                           # a variante da Play Store (só guia; pacote dev.pedro.lmphone.guia), com as conferências de "nenhuma ação"
LMPHONE_AGIR=0 ./run.sh "..."                   # o executor só guia (o da loja) pelo PC: todo passo é da pessoa, e o que abrir vai num botão da faixa
PORT=8792 .venv/bin/python -m servidor.servidor   # o servidor do provedor da loja no PC (adb reverse tcp:8792 tcp:8792); publicar: docs/loja/publicar-servidor.md
.venv/bin/python -m tests.pessoa_loja "..."     # um guia no app da loja (build de depuração), com a pessoa simulada tocando
.venv/bin/python -m tests.loja_suite [ids] [--vezes 3]   # os casos de guia e de sintoma da suíte no app da loja, com a pessoa simulada: preparo e conferências da suíte, gravação de cada rodada; espera o celular ficar parado e refaz a rodada que alguém interromper
.venv/bin/python -m tests.simulador [cenário] -v   # o app da loja sem o celular: guias inteiros num celular, faixa e pessoa de mentira (relógio de mentira, provedor por roteiro, < 1 s); -v mostra a linha do tempo
.venv/bin/python -m tests.simulador --provedor real --vezes 5 [--escolha]   # com o Haiku de verdade (uns US$ 0,003 por guia) e, com --escolha, o modelo de escolha (servidor dos modelos pequenos na 8788)
.venv/bin/python -m tests.casos [ids] [--processos 8]   # os 50 casos da loja (tests/casos_loja.py) no simulador, todos de uma vez, com o Haiku e o modelo de escolha de verdade; os mesmos rodam no celular por tests.loja_suite <ids>
.venv/bin/python -m tests.gravacao puxar [nome]    # a gravação do último guia no celular (build de depuração da loja) em tests/gravacoes/; repetir, medir, linha ARQUIVO [OUTRO]
.venv/bin/python -m tests.gravacao comparar ARQUIVO...   # a rodada do celular repetida no simulador (mesmo pedido, estado, respostas do provedor e telas): o que o guia fez, o fim, o estado e o tempo, lado a lado
.venv/bin/python -m tests.varredura [--continuar]  # as Configurações do celular como o app as lê, em tests/telas/ (--direto, --estados, --fundo 1)
.venv-modelo/bin/python -m tools.app.modelos enviar   # os modelos pequenos para o app no celular; preparar, referencia, ponte, medir: ver o arquivo
android/gradlew :modelos:conferir              # o tokenizador e os modelos em Kotlin contra o Python (depois de tools.app.modelos referencia)
.venv/bin/python -m tools.app.cerebro exportar   # os prompts, listas e expressões regulares do Python para o Kotlin (rode a cada mudança neles)
.venv/bin/python -m tools.app.cerebro trilhas    # as trilhas dos testes do executor; depois android/gradlew :cerebro:conferir
.venv/bin/python -m tools.app.cerebro enviar     # prepara o celular para o cérebro no app (permissões, data/, chave, modelos)
.venv/bin/python -m tests.phone_suite --cerebro celular   # a suíte com o cérebro no app (o PC só dispara e confere)
.venv-modelo/bin/python -m tools.app.escuta enviar      # os modelos da palavra de ativação ("Alexa") para o app; baixar, referencia: ver o arquivo
.venv-modelo/bin/python -m tools.app.escuta testar      # "Alexa, <comando>" sintéticos tocados no app no lugar do microfone (abre o painel; celular sem uso)
android/gradlew :modelos:conferirEscuta         # a palavra de ativação em Kotlin contra o openWakeWord do Python (depois de tools.app.escuta referencia)
LMPHONE_TRILHA=1 ./run.sh "..."                 # o serviço grava as trilhas do executor em logs/trilhas/ (telas reais), para a conferência
ollama serve                                    # a Gemma, só com LMPHONE_LOCAL_AI=gemma (não inicia sozinho); pkill ollama para parar
```

- Sem cabo, pela depuração sem fio do Android: Opções do desenvolvedor > Depuração sem fio > Parear o dispositivo
  com código; no PC, uma vez, `adb pair IP:PORTA CÓDIGO` (a porta do pareamento). Depois o adb se liga sozinho ao
  celular na mesma rede (`bridge.reconnect` tenta de novo pelo mDNS). Com o cabo e a rede ao mesmo tempo, o serviço, o
  `run`, a suíte, a coleta e os scripts de adb escolhem o cabo (`bridge.choose` põe `ANDROID_SERIAL`).
- O celular precisa estar no USB (ou na depuração sem fio) com depuração ativa (`adb devices`) e com o Portal instalado (`.venv/bin/mobilerun
  setup` instala e liga a acessibilidade; rode `python -m lmphone.access off` logo depois). Não precisa ligar a
  acessibilidade à mão: o serviço liga e desliga a cada tarefa.
- `.env` guarda `OPENROUTER_API_KEY`. Nunca imprima a chave.
- Python 3.12 em `.venv`. O código do projeto usa só a biblioteca padrão; o pacote `mobilerun` fica no venv para
  instalar o Portal e para um teste que compara o texto da tela com o dele. No notebook (Omarchy, desde 2026-11-16),
  os venvs são criados pelo `uv` (`uv venv --python 3.12 .venv`, `uv pip install --python .venv-modelo/bin/python
  onnxruntime==1.31.0 tokenizers numpy`); `.venv-laya` e `.venv-treino` não foram recriados. O Gradle usa o JDK 17 do
  mise: `ANDROID_HOME=~/Android/Sdk ANDROID_USER_HOME=~/.android JAVA_HOME=$(mise where java@temurin-17) bash
  android/gradlew ...`. Sem o `ANDROID_USER_HOME`, o Gradle assina com uma chave nova de `~/.config/.android` e o
  celular recusa a atualização (assinatura diferente); a chave do app instalado é a de `~/.android/debug.keystore`.
- O Laya fica em `.venv-laya` (`laya` 0.4.6); só o `laya_server.py` e o `eval_laya` rodam nele. No notebook, PyTorch
  só de CPU (1,2 GB): `python3.12 -m venv .venv-laya`, `pip install --index-url https://download.pytorch.org/whl/cpu torch`,
  `pip install laya`. Na máquina da RTX, PyTorch das rodas `cu128` (`.../whl/cu128`), e o Laya usa a GPU sozinho
  (0,01 a 0,03 s por escolha, contra 0,42 s na CPU do notebook): tempos medidos lá não valem para as metas de tempo.
- No Windows: Python 3.12, Git, adb (`Google.PlatformTools`) e Ollama instalados pelo winget; `PYTHONUTF8=1` no
  ambiente do usuário (sem ele, arquivos e a saída do adb saem na página de código do sistema); o repositório com
  `core.autocrlf false` e `core.filemode false`. O `python.exe` de um venv no Windows é um lançador: o pid gravado em
  `logs/*.pid` é o dele, e encerrar ou medir um processo pega a árvore (`host.tree`, `host.stop`).
- `.venv-treino` (só na máquina da RTX): PyTorch `cu128`, transformers, datasets, accelerate, onnx, onnxruntime, para
  o plano de modelos pequenos.
- App Android (`android/`, `docs/plano-app-android.md`): JDK 17 e Android SDK 36 (command-line tools, build-tools
  36.0.0) em `JAVA_HOME` e `ANDROID_HOME`; Gradle pelo wrapper. Na máquina da RTX, o JDK é o portátil da Microsoft em
  `%LOCALAPPDATA%\Programs` e o SDK fica em `%LOCALAPPDATA%\Android\Sdk`, sem o platform-tools dele (o adb é o do winget).
- `.venv-modelo`: só onnxruntime, tokenizers e numpy (146 MB), para `lmphone/modelo_server.py`
  (`python3.12 -m venv .venv-modelo`, `pip install onnxruntime tokenizers numpy`). Os modelos ficam em
  `data/modelos/{marcacao,escolha}/` (fora do git): `modelo-tabela.onnx`, `tokenizer.json` e `modelo.json` da pasta
  `onnx/` que `tools.treino.exportar` grava; no notebook, copiar da máquina da RTX. Tem também o `openwakeword` 0.6.0
  instalado sem as dependências (`pip install --no-deps`), só para a referência da palavra de ativação.

## Arquitetura

```
pedido -> serviço: begin (sessão nova)
       -> IA local julga o pedido ┐
       -> liga a acessibilidade ├ em paralelo
       -> provedor escreve o plano e o objetivo (pedido mascarado) ┘
       -> ciclo: ler a tela -> executor decide (rótulo exato | modelo de escolha | ajuda do provedor com tela reduzida e mascarada)
                 -> agir pelo adb -> conferir o efeito -> ... -> objetivo conferido na tela
       -> resultado ao usuário -> desliga a acessibilidade
```

| Arquivo | Papel |
|---|---|
| `lmphone/run.py` | Sobe a IA local (os modelos pequenos, ou o Laya e a Gemma com `LMPHONE_LOCAL_AI=gemma`) e o serviço quando faltam (e reinicia o serviço se o código ou o `.env` mudaram), cria a Gemma de texto no Ollama e manda a tarefa; `run.sh` (Linux) e `run.cmd` (Windows) só o chamam |
| `lmphone/host.py` | O que muda entre Linux e Windows: Python de um venv, processo que fica no ar, encerrar e medir memória de processos |
| `lmphone/service.py` | O serviço (porta 8789): uma tarefa por vez, o ciclo ler-decidir-agir, liga e desliga a acessibilidade |
| `lmphone/client.py` | Manda a tarefa ao serviço e mostra o andamento; fechar o cliente interrompe a tarefa |
| `lmphone/proxy.py` | O caminho até o provedor e o estado da tarefa: `begin`, julgamento do pedido e das telas, mascarar, enviar, registrar em `logs/proxy.jsonl`, abrir apps, cache |
| `lmphone/executor.py` | Pede o plano, decide cada ação, confere o efeito e o objetivo, pede ajuda |
| `lmphone/device.py` | O celular: tela lida do Portal pelo content provider, no formato de texto que o executor lê; toques e teclas pelo adb; digitação pelo teclado do Portal (HTTP) |
| `lmphone/access.py` | Liga e desliga a acessibilidade e o teclado do Portal; lista de apps de banco |
| `lmphone/masking.py` | `Vault` (o que proteger), `Session` (pares real ↔ falso da tarefa), `Masker` (troca e desfaz) |
| `lmphone/local_ai.py` | A IA local do pedido e das telas: `judge_request`, `find_private` (no servidor dos modelos pequenos, ou na Gemma pelo Ollama), `screen_fragments` |
| `lmphone/modelo_server.py`, `lmphone/modelo.py` | Os modelos pequenos em ONNX (porta 8788, `.venv-modelo`): API do Laya mais `/entities` e `/judge`; `modelo.py` é o texto comum ao treino e ao servidor |
| `lmphone/laya_server.py` | Servidor do Laya (porta 8788, só com `LMPHONE_LOCAL_AI=gemma`): `/pick` escolhe o controle pelo nome, `/private` filtra trechos antes da Gemma |
| `lmphone/cache.py` | Cache de caminhos por pedido (`data/paths.json`) e mapa dos apps em árvore (`data/maps.json`) |
| `lmphone/sources.py` | Lê contatos, contas, perfil e apps do celular; grava o cofre (`data/vault.json`, modo 600) |
| `lmphone/trace.py` | Diagrama de uma tarefa a partir do log |
| `lmphone/live.py` | O live mode do lado do PC: antes de cada ação pede ao app o que o usuário fez (pausa, interrupção, instrução, toques), espera ou repassa; grava `logs/live/<sessão>.jsonl` (valores reais, modo 600) |
| `lmphone/facts.py` | Estado do aparelho que não depende da tela (Wi-Fi e rede, modo avião, Bluetooth etc.), numa chamada ao adb |
| `lmphone/bridge.py` | A ponte do celular ao serviço: `adb reverse` da porta 8789, a senha de `/task` (`logs/service.token`) gravada no app por `run-as`, refeitos quando o celular volta; e a escolha do aparelho dos comandos adb (cabo ou depuração sem fio) |
| `lmphone/painel.py` | Painel web local (só 127.0.0.1): navega pelas suítes (`reports/suite-*.json`) e tarefas; por rodada, as conferências, a saída do agente, a tela final, o que a IA local gerou (`logs/detalhe/`), o diagrama do trace e o log bruto do proxy |
| `lmphone/treino.py` | Coleta para o treino dos modelos pequenos: pedido, trechos de tela, julgamentos do Laya e da Gemma, escolhas de controle com o efeito (`data/treino/real/`, modo 600); `status` só com contagens |
| `tools/treino/` | Scripts do treino dos modelos pequenos; `sintetico.py` pede ao provedor exemplos fictícios já rotulados e os confere com uma segunda chamada (`data/treino/sintetico/`); `professor.py` rotula a coleta com um modelo grande no Ollama (`data/treino/real/rotulos-*.jsonl`); `dados.py` monta os conjuntos, `treinar.py` treina a marcação e a escolha (encoder pequeno), `servidor.py` os serve com a API do Laya para a avaliação |
| `tests/` | Testes unitários (`test_*.py`), suíte no celular (`phone_cases.py`, `phone_suite.py`, `site/`), avaliações da Gemma (`ia_cases.py`, `eval_ia.py`) e do Laya (`laya_cases.py`, `eval_laya.py`), conjunto congelado da linha de base (`base/`, `eval_base.py`), captura de tela (`captura.py`; a suíte grava uma quando uma rodada falha) |
| `android/` | O app Android (Kotlin, Compose), por etapas (`docs/plano-app-android.md`): o serviço de acessibilidade `AgentService` lê a tela no formato do Portal e age; com `LMPHONE_DEVICE=app`, o cérebro do PC o usa (`device.AppDevice`). `android/modelos/` é o módulo Kotlin puro dos modelos pequenos (`Tokenizer`, `Modelo`, `Models`), que o app usa com o onnxruntime do Android e a conferência (`:modelos:conferir`) com o da JVM; `ModelService` é o modo de depuração dele no aparelho |
| `tools/app/` | `modelos.py`: o tokenizador no formato do app (`preparar`), as respostas do Python para a conferência (`referencia`), a cópia dos modelos para o celular (`enviar`), a ponte para `tests.eval_base --novo` contra o app (`ponte`) e o tempo no aparelho (`medir`). `cerebro.py`: o `cerebro.json` (`exportar`), as trilhas dos testes (`trilhas`), a referência da máscara (`mascara`), preparar o celular (`enviar`), um pedido ao cérebro no app (`tarefa`, que a suíte usa) e o registro dele (`puxar`). `escuta.py`: os modelos da palavra de ativação (`baixar`, `enviar`) e a referência da biblioteca do openWakeWord (`referencia`) |
| `android/cerebro/` | O cérebro em Kotlin (etapa 3 de `docs/plano-app-android.md`): a tradução de `masking`, `local_ai`, `facts`, `cache`, `executor`, `device` (o texto da tela), `live` e `proxy`/`service` (`Agent.kt`), com o aparelho, a faixa e o provedor por interfaces; `cerebro.json` (gerado) traz do Python os prompts, as listas e as expressões regulares; `:cerebro:conferir` o compara com o Python |
| `lmphone/trilha.py` | O gravador das trilhas do executor: o estado antes e depois de cada chamada e o que ele pediu de fora, para a conferência do Kotlin |
| `arquivo/` | Fora do git: logs, relatórios e cópias de cache e mapa de antes da pv1 |

## Decisões em vigor

Os motivos e as medições de cada uma estão em `docs/historico.md`.

**O provedor só é alcançado por `proxy.ask_provider`.** A chave existe só no processo do serviço. Tudo o que sai é
mascarado antes; se o mascaramento falhar, nada é enviado. Nada vai ao provedor antes de a IA local julgar o pedido.
A exceção é o gerador de dados sintéticos (`tools/treino/sintetico.py`), que lê a chave do `.env` e manda só texto
escrito no próprio script (nome do app e nomes fictícios), nunca nada do celular, do cofre ou de `data/treino/real/`.

**O provedor é o assistente do dono; o aparelho executa** (2026-10-20, `docs/plano-assistente.md`). Cada pedido é
um turno: o provedor recebe a conversa (os últimos 6 turnos, mascarados com os mesmos valores falsos), o estado do
aparelho e, se pedir (`look`), a tela reduzida, e responde (`reply`), pergunta (`ask`), age (plano com `say`) ou guia
(plano com `explain` por passo). Em toda tarefa que um fato do sistema não decide, ele confere a tela final, e a
mensagem dessa conferência é a resposta ao dono, em português; um "feito" dele sem o objetivo na tela vale como
`conferido`. As instruções fixas vão antes de `executor.SPLIT` e saem como mensagem de sistema com marca de cache
(`proxy.ask_provider`). Se a conferência dá passos, ela roda de novo depois deles (até 2). Ela não conta como ajuda, e recebe, conferido no aparelho, se os textos longos que a tarefa
digitou estão na tela final. A conversa dura até 10 min parada; dentro dela o cache não vale. Nome de rede Wi-Fi no
objetivo vale aproximado (`facts.same_network`: sem sufixo de faixa, uma letra errada; 2026-10-21): o provedor punha
a grafia do dono no objetivo mesmo com o aparelho já na rede.

**O celular chama o assistente** (2026-10-21, etapa 3 de `docs/plano-assistente.md`). O app é o assistente
digital do Android; o painel (`AssistSession`) sai da frente ao enviar (o agente leria o painel no lugar do app de
baixo) e volta com a resposta. O pedido vai ao serviço por `adb reverse`; como qualquer app do celular alcança a
porta, `/task` só aceita a senha que o serviço gera a cada subida e grava no app por `run-as`. A voz do painel é só
do aparelho: reconhecimento `createOnDeviceSpeechRecognizer` e leitura com voz pt-BR local; sem elas, só texto. O
painel com a resposta fecha sozinho 7 s depois de lida (2026-10-24), a menos que o dono toque nele.

**Páginas das Configurações abertas direto** (2026-10-22, depois da One UI 9). A ação `open_settings` abre pelo atalho
do Android uma das páginas de `executor.SETTINGS_PAGES` (Wi-Fi, Bluetooth, modo avião, tela, som etc.; `proxy.SETTINGS`
tem os atalhos, conferidos no S23+), e o plano a prefere aos menus, que mudam a cada versão do sistema. Quando o modelo
de escolha fica dividido entre dois rótulos (os dois primeiros somam 0,8 ou mais, nenhum sozinho), o executor pede ajuda
nesta tela em vez de rolar para longe do controle. A pergunta ao dono antes de agir só é oferecida quando alguém pode
responder (`LMPHONE_PERGUNTAR`); na suíte, não. Modo escuro, modo avião, Wi-Fi, Bluetooth, Não perturbe e
localização ligam e desligam direto pelo sistema (ação `set`, `proxy.DIRECT`: `cmd uimode night`, `cmd connectivity
airplane-mode`, `cmd wifi set-wifi-enabled`, `cmd bluetooth_manager`, `cmd notification set_dnd`, `cmd location
set-location-enabled`; os quatro últimos desde 2026-10-24, ainda não conferidos no celular), sem abrir tela,
conferidos pelo estado; só no guia o caminho é pelas telas. Escolher uma rede ou parear um aparelho continua pelas
telas. Com o celular ligado ao PC pela rede, desligar o Wi-Fi ou ligar o modo avião é recusado com uma mensagem ao
dono (`proxy.NO_CUT`): cortaria a ligação no meio da tarefa. Ligar o modo escuro: 11 s e 1 chamada (pelas telas, 16 a
19 s e 2).

**Ações que não se desfazem esperam o dono** (2026-10-24, etapa 5 de `docs/plano-app-android.md`). Antes de tocar num
controle cujo texto começa por enviar, comprar, pagar, apagar, remover, publicar, compartilhar, transferir ou ligar
para alguém (`executor.SENSITIVE`, em inglês e português, até 4 palavras), ou num passo que o plano marca com
`confirm` (a pergunta, escrita pelo provedor: "Envio a mensagem para Ana?"), o executor não toca: pergunta ao dono na
faixa (`confirm_user`: Sim e Não, falada e ouvida como as outras perguntas) com o botão destacado. Sim libera esse
toque; não encerra a tarefa (`cancelada`); outra resposta ("manda pro outro contato") vai ao provedor como a
resposta a uma pergunta. Sem a faixa (suíte, terminal com o Portal), a pergunta é a resposta do pedido (`a
confirmar`), e um "sim" no pedido seguinte da conversa libera os toques desse pedido. Na vez do dono, quem toca é
ele, e não há pergunta.

**Pesquisa no Google do celular** (2026-10-24, pedido do Pedro). Para o que o provedor não sabe com certeza (o que
muda: notícias, horários, placares, preços; um nome que ele não conhece ou que pode ter sido ouvido errado), ele responde
`{"search": "..."}`: o celular abre a pesquisa do Google no Chrome (`proxy.web_search`, com os valores reais no lugar
dos falsos), e o provedor responde vendo a página de resultados. Só nessa página os textos de até 500 caracteres e os
números vão inteiros (o horário e o placar são a resposta); tudo passa pela IA local e pelas regras fixas da máscara,
como qualquer tela. Antes ele respondia de memória: "o esporte hirox" virou a Hirox, uma marca de microscópios.

**O guia** (o tutorial). "Como eu ligo...", "me ensina..." (`executor.HOW_TO`) é guia mesmo quando o provedor não marca
`guide` (2026-10-24: "como ligar os painéis Edge" foi feito sem mostrar nada). No guia, um ajuste do sistema vai pelas
telas (`SET_SCREENS`), e um ajuste que já estava como pedido tem o caminho mostrado do mesmo jeito. Com a faixa, cada
toque é destacado em amarelo, explicado em voz alta, e o dono tem 5 s depois da explicação para tocar ele mesmo
(`GUIDE_LIMIT`, pedido do Pedro); sem o toque dele, o agente toca.

**O app da loja só ensina** (2026-11-16, `docs/plano-play-store.md`). A política da Play proíbe a acessibilidade para
um app que planeja e executa ações sozinho; a variante `loja` (`android/app/src/loja`, `productFlavors`) não tem como
agir: o código de gestos, digitação, teclas, teclado do agente, captura, servidor local e depuração fica em
`src/completo`, e `:app:conferirLoja` faz o build da loja falhar se uma API de ação ou uma permissão proibida aparecer
no código, nos recursos ou no APK pronto. O executor tem o modo só guia (`acts` False; `proxy.ACTS`, `LMPHONE_AGIR=0`;
`Agent.acts` no Kotlin): todo pedido vira guia, todo passo é da pessoa, rolar vira instrução com o gesto animado, um
app ou uma página das Configurações abre por um botão da faixa que ela toca, `set` vai pelas telas e não há pesquisa.
Na loja a acessibilidade fica ligada só durante o guia (2026-11-21: com ela ligada o tempo todo, o Inter bloqueou o
S23+ num pagamento). O app não pode se ligar sozinho; a pessoa liga pelo atalho do Android (segurar os dois botões de
volume por 3 s, configurado uma vez na tela inicial do app: Acessibilidade > Atalhos de acessibilidade > Teclas
Aumentar/Diminuir volume). Um guia que precisa da tela com o serviço desligado pede o atalho no painel (`Flavor.SWITCH_ON`)
e espera 60 s; uma resposta direta não pede (`Phone.personSwitches`: o plano vem antes). Ligado sem pedido, o painel
abre já ouvindo em 3 s. O serviço se desliga sozinho (`disableSelf`) no fim do guia, com um app de banco na frente e
depois de 3 min sem guia. Conferido no S23+ com o gesto simulado (`input keycombination`); falta com os botões de verdade
e com o Inter. A página da acessibilidade do próprio serviço não abre por Intent (pede uma permissão de sistema). A faixa
aparece só durante um guia. O provedor vem pelo servidor do easy_phone (`servidor/`: a chave só lá, 150 pedidos por mês
por instalação, teto de gasto, sem guardar conteúdo), os modelos pelo pacote de recursos `modelos` da Play, sem
contatos no cofre e sem palavra de ativação. Pacote e nome provisórios: `dev.pedro.lmphone.guia`, "Guia do Celular".
Desde 2026-11-18 os guias da loja rodam também no PC, sem o celular (`tests/simulador.py`, nos testes por
`tests/test_simulado.py` e nas trilhas do Kotlin): as páginas das Configurações montadas à mão, a faixa com os atrasos do
aviso do toque e da leitura da tela, uma pessoa que lê, toca e erra, e o provedor por roteiro. Um defeito visto numa
rodada no aparelho vira um cenário ali antes da correção; o Android, a faixa de verdade e o provedor de verdade
continuam só no aparelho. Para o simulador ficar perto do celular (proposta do Pedro, 2026-11-18): o build de depuração
da loja grava cada guia (`Gravacao.kt`: telas, fatos, toques, respostas do provedor e do modelo de escolha, o relógio
do executor), e `tests/gravacao.py` repete a gravação no executor do Python e confere que ele decide igual, mede os
tempos de verdade e compara a linha do tempo do celular com a do simulador, que grava no mesmo formato; a varredura
(`tests/varredura.py`) grava as páginas das Configurações pela leitura do próprio app, só tocando em linhas de menu e
parando se alguém mexer no celular ou um fato mudar; o simulador pode usar o Haiku e o modelo de escolha de verdade.
As telas e as gravações vão sem máscara, com os valores reais (decisão do Pedro, 2026-11-18: os dados do celular não
importam nesses testes). A varredura gravou 121 páginas (`tests/telas/`, 640 KB) e as de som e Não perturbar em cada
estado; os cenários `real-*` do simulador rodam nelas (`tests/celular_real.py`). Elas acharam, no mesmo dia, o que as
páginas montadas à mão escondiam: o título «Toque» da página de Volume é separado da barra (o guia destacava o título e
esperava para sempre), a busca que flutua no pé da página inicial cobre «Notificações», uma opção já escolhida
(«Som») deixava o guia esperando, e um passo de rolar no fim da página nunca contava; com o Haiku de verdade, 0 de 5
guias terminavam antes das correções e 4 de 5 deixaram o aparelho certo depois (42 a 65 s, 2 ou 3 ajudas: a primeira é
sempre «Não perturbe» do plano contra «Não perturbar» da tela, 0,765 no modelo de escolha). Rodadas no S23+ no mesmo dia
(a pessoa simulada pelo adb, `tests/pessoa_loja.py`; gravações em `tests/gravacoes/`): cada gravação repetida no
Python deu 0 diferenças; elas acharam e as correções resolveram o nome com outra terminação, o objetivo de som
incompleto, o `set` de volume sem caminho pelas telas, a barra só na explicação (o executor põe o passo da barra no fim),
o «sound» no lugar de «som», a fala que trocava o verbo «Toque», o caminho final só com a última parte, a resposta que
promete olhar sem passos, a faixa por cima do destaque (o toque caiu no X e encerrou o guia: agora ela vira o círculo) e
o leitor com linhas velhas depois de rolar (16 de 30 telas; com `clearCache()` antes de cada leitura, 0 de 36). As três
últimas rodadas, já com tudo: confirmado, 54 a 77 s, 0 a 2 ajudas, o aparelho certo no fim. Paridade com o
simulador (`tests.gravacao comparar`, nos testes por `tests/test_gravacao.py`): repetidas nele, as três terminam
iguais, com o mesmo estado, tudo o que o guia fez na mesma ordem (15 de 15, 17 de 17, 15 de 15) e o tempo a até 7%
(77/72, 54/50, 54/56 s), depois de pôr o painel de atalhos gravado (o gesto de puxar) e os tempos medidos nelas. O que
continua só no aparelho: a faixa, o leitor de acessibilidade do Android, o que um toque muda nas telas (modelado à
mão), as telas e gestos não gravados, outros aparelhos e versões da One UI.
Os 13 outros casos de guia e de sintoma no celular (2026-11-19, `tests.loja_suite`, 33 rodadas depois das correções):
todas com o aparelho no estado pedido, nenhuma ação do agente, as gravações repetidas no Python sem diferença; o que
faltava eram critérios de fala. As rodadas acharam e corrigiram: os painéis separados da One UI 7+ (os atalhos descem
pelo lado direito do alto: a fala e o gesto da faixa dizem isso, e quem cai nos avisos é mandado de novo), o painel de
atalhos compacto que fecha ao rolar (o «Expandir» vem antes), o «Expandir» por cima da borda de um bloco, o título
curto de uma barra («Brilho»), a rotação e o tempo para a tela apagar sem estado medido (agora `auto_rotate` e
`screen_timeout` nos fatos), o toque num destaque que não reage (8 s sem mudança vão à ajuda) e o brilho automático
que fazia um toque sem efeito parecer o passo, a fala longa pelo que o executor junta, o caminho final com o desvio.
Na pessoa simulada: o gesto perdido, o toque repetido em cima da pausa da faixa, o puxar e o voltar sem destaque.
Os 50 casos da loja (2026-11-19, pedido do Pedro; `tests/casos_loja.py`, os mesmos no celular por `tests.loja_suite`
e no simulador por `tests.casos`): letra, brilho, modo escuro, rotação, tempo da tela, Não perturbar, modo de som,
volumes, lanterna e localização, como quem tem dificuldade pede; Wi-Fi, Bluetooth e modo avião ficam de fora (cortam o
adb ou o fone). No simulador, com o Haiku e o modelo de escolha de verdade: a primeira passada deu 41 de 50 sem falha;
depois das correções, 96 de 100 rodadas sem falha e o aparelho certo em 100 (US$ 0,12, mediana de 33 s). Elas
acharam e corrigiram: a barra de diminuir com a fala e o destaque de aumentar (o brilho subia, 12 ajudas; agora a
direção sai do objetivo, e o destaque fica perto de um terço da barra), o `set` de volume depois da barra que mandava
refazer o caminho, um `read` do nível que encerrava o guia antes de a pessoa mexer (e tirava o objetivo), o objetivo
posto dentro de um passo, a pergunta do começo que deixava o resto fora do guia, a tecla de voltar que não chega como
toque (o guia dizia que a pessoa se perdeu), a lanterna respondida com "quer que eu te mostre?", a ajuda que desistia
com os passos no texto, as falas longas da explicação, as aspas de "'A' pequeno e 'A' grande" lidas como um nome, e a
resposta genérica quando só parte do objetivo mudou. No simulador, também: a lanterna numa segunda tela do painel
aberto (feita à mão: a varredura não chegou lá), o bloco do modo de som, as barras de mídia e brilho do painel, o
modo escuro, a localização e o «Expandir» (abria as Configurações). No celular, a suíte da loja passou a aceitar
«lido» (a agenda «Dormir» do Não perturbar já existia) e a pôr o nível da barra da fonte (`font_size`), que a One UI
guarda à parte da escala: uma rodada deixou a barra no máximo, e «Aumentar» não mudava nada.

**Live mode contínuo** (2026-10-24, pedido do Pedro; `docs/plano-live-mode.md`). Ligado pelo botão ∞ da faixa ou do
painel do assistente (`POST /live` no serviço), o microfone do app fica aberto e cada fala é um pedido novo da mesma
conversa (`Brain.send` com "continuo"), até o dono dizer "finalizar" ou tocar no X; não desliga sozinho. Uma fala no
meio de um pedido vira o seguinte: o app manda "novo_pedido" e o serviço encerra o que estava em curso. "Pausa",
"continua", "para" (encerra o pedido em curso; até 2026-10-26, pausava) e os outros botões falados (`Commands.kt`)
valem como os botões. Entre os pedidos a acessibilidade fica ligada (só o teclado volta a ser o do dono), e
o app se desliga sozinho se um app de banco vier para a frente (`disableSelf`, com a lista que o serviço manda). O
microfone fecha enquanto o agente fala; a resposta aparece na faixa e, 7 s depois de lida, ela volta a ser o círculo.

**O plano.** O plano (JSON, em inglês) tem passos (`open_app`, `open_settings`, `set`, `tap`,
`turn_on`, `turn_off`, `type`, `enter`, `back`, `read`) e um objetivo (`goal`: chave em um estado, ou texto que passa a
aparecer; com `gone`, o botão que começa o pedido, como o "Ir agora" do Waze, também tem de sair da tela). Cada ação tenta: rótulo exato na tela (código), o mesmo controle com outro nome (modelo de escolha: os rótulos da tela e a opção "nenhum" num softmax, abaixo de 0,8 é
"nenhum"; com o Laya, abaixo de 0,5), ajuda do provedor. O plano é pedido sem raciocínio (2 a 3 s); as ajudas, com. Limites:
6 ajudas por tarefa, 2 para o mesmo passo. Um objetivo por fato do sistema encerra a tarefa assim que vale só quando o
resto do plano é ajuste (sem abrir outro app nem ler um valor): "desliga o Bluetooth e volta pro Waze" parava antes do
Waze. Num plano que vai a outro app sem mudar aquele ajuste, o fato é descartado e quem confere é a conferência final
(2026-10-24: "coloca uma música e volta pro Waze" veio com o objetivo "Wi-Fi na rede X", que já valia, e acabou em "já
estava" sem fazer nada). A ação `keep_scrolling` ("fica rolando a tela") rola a cada poucos segundos até o dono pedir
outra coisa ou passar 10 min. Uma resposta do provedor que não é JSON é pedida de novo uma vez; duas encerram a tarefa
com uma mensagem. O resultado é `confirmado` (a tela mostra o objetivo), `já estava`,
`sem confirmação`, `lido` ou `falhou`; só `confirmado` e `já estava` alimentam o cache e o mapa.

**Um passo vale pelo efeito, não pelo que o provedor esperava.** A tela mudou (textos, estados, app, teclado, foco)
ou a chave está no estado pedido. Chaves: o toque vai no controle marcável, não no título; diálogo novo de confirmação
aberto pela chave é confirmado por código. O executor espera a tela carregar (até 4 vezes por passo) antes de rolar,
pular ou pedir ajuda, e a tela só vale quando duas leituras seguidas saem iguais.

**O pedido é informal e o agente o lê pelo sentido** (2026-10-19, depois dos casos do dia a dia). O plano é pedido
sabendo que nomes podem vir aproximados ou errados e que o fim esperado é o natural (rota começada, lugar aberto,
música tocando); para o que só a tela diz (uma rede, um resultado de busca) o passo pede ajuda em vez de rolar. A
ajuda manda não insistir nas palavras literais. Quando o plano acaba, o provedor confere a tela final contra o pedido,
uma vez (não no caminho do cache nem com objetivo de chave). Rolagem por passo: até 4 (eram 8). Os apps preferidos do
dono (`data/preferencias.txt`, "música: YouTube Music") vão no pedido do plano. Ação `quick_settings` abre o painel
rápido. O pedido costuma vir da voz (2026-10-24): o plano sabe que o reconhecedor erra nomes ("hirox" é o Hyrox), e o
reconhecedor do app prefere os nomes dos apps do aparelho (`Vocabulary`). Um pedido com várias partes ("toca uma música
e volta pro Waze") faz todas, e o objetivo é o fim da última. O app é achado pelo nome também por apelido
(`proxy.APP_ALIASES`: o YouTube Music aparece como "YT Music"), sem espaços e com uma letra trocada.

**Senha dita no pedido é mascarada por regra fixa** (`masking.passwords`: o que vem depois de "senha é", "senha:",
"password"; depois de "pra" ou logo depois de "senha", só o que tem cara de senha), e só volta ao real na digitação no
aparelho.

**Regras que valem sem a IA local, trazidas do maskai** (2026-11-12, `docs/mascaramento.md`). `Masker.learn` aprende,
antes de cada troca, os nomes que a forma do texto denuncia (prenome frequente em qualquer caixa e o que continua o
nome, nome do cofre sem acento ou em minúsculas, nome de logradouro), com as listas de `lmphone/nomes.py`; CNPJ, CEP,
placa, RG, CNH, conta e CPF e cartão sem pontuação têm regra; os falsos de nome não têm acento e nunca são uma palavra
já vista num texto; um literal só de números curto não é aprendido. Só com as regras e o cofre, o conjunto congelado
foi de 83 para 169 de 187 pessoas; com o modelo, ficou igual (186 de 187, 38 de 38 usuários). Tudo isso está igual no
Kotlin (`:cerebro:conferir`).

**O que a IA local gera fica num registro à parte, com valores reais** (2026-10-19): `proxy.detail` grava em
`logs/detalhe/<sessão>.jsonl` (modo 600) o julgamento do pedido, cada tela julgada, cada escolha do modelo de escolha com
o ranking, e no fim as trocas real → falso e os controles escolhidos. É só para o painel; nunca vai ao provedor nem
ao `proxy.jsonl`. `LMPHONE_DETALHE=0` desliga.

**Nos pedidos de ajuda, a tela vai reduzida** (`redact`): texto com mais de 60 caracteres vira `[hidden text]` e
números de 3 ou mais dígitos viram `#`; depois vem o mascaramento. O valor de um `read` (um código) é lido no aparelho
e entregue ao usuário sem passar pelo provedor; desde 2026-10-24 ele também não fica no `proxy.jsonl` nem na conversa
que vai ao provedor no pedido seguinte (antes ficava: um código de verificação estava no registro).

**Árvore de acessibilidade, não print.** Texto é fácil de mascarar; pixels não.

**O cofre guarda só valores reais; os falsos nascem e morrem com a tarefa.** Uma tarefa é um `begin`: valores falsos
novos, cofre relido, executor novo. O que vem de fonte estável do aparelho (contatos, contas, perfil) vai para o cofre;
o que só apareceu na tela vive só na sessão.

**A IA local decide por entidade e só pode liberar o que é ambíguo.** Pessoas (famosas também, desde 2026-10-18:
um modelo pequeno não sabe quem é famoso; nome de pessoa dentro de título também), e-mails, telefones, CPF, cartões e `@usuários` são mascarados sempre (um "usuário" que o modelo acha no pedido sem a forma de um, sem @, ponto, _
ou número, e sem rede social no pedido, não é: em 2026-10-24 o Hyrox, ouvido como "rayrox", virou um usuário falso). A
IA local pode pedir mais máscara (nomes fora do cofre, em minúsculas; nomes de usuário, e-mails e telefones que as
regras fixas não pegam) e liberar negócios, instituições e lugares só quando a tarefa exige pesquisá-los. Na dúvida ou
com a IA local fora do ar, valem só as regras fixas. Palavras de categoria, parentescos, marcas e nomes de apps não são mascarados (`STOPLIST`, mais
`data/stoplist.txt`). Na tela, só trechos novos são julgados; os modelos pequenos julgam todos (5 a 30 ms
por bloco), e com a Gemma o Laya descarta antes os que são claramente rótulos de interface (abaixo de 0,15).

**Modelos.** Provedor: Claude Haiku 5.5 pelo OpenRouter (o gratuito do OpenRouter para em 50 pedidos por dia). Local:
dois modelos pequenos sobre o `intfloat/multilingual-e5-small`, treinados nos casos do celular
(`docs/plano-modelos-pequenos.md`): marcação (entidades por token e intenção do pedido) e escolha de controle; ONNX
com só a tabela de tokens em int8, 173 MB cada, uns 660 MB de memória com o tokenizador compartilhado. Com
`LMPHONE_LOCAL_AI=gemma`, como antes: Gemma 4 E2B sem o projetor de imagem (`gemma4-e2b-texto`, que o `run.sh` cria no Ollama), com `think` desligado,
saída por esquema JSON, arquivo mapeado, e uma chamada de preparo que deixa o prompt fixo no cache do Ollama. Laya
(421M) com o peso em inglês fixo (2,1 GB). Os três ficam carregados entre tarefas.

**Os modelos pequenos no app** (2026-10-26, etapa 2 de `docs/plano-app-android.md`). O tokenizador é próprio, em
Kotlin, e copia a biblioteca `tokenizers` do Python até nas esquisitices dela (a referência é o Python; a conferência
`:modelos:conferir` compara token a token e resposta a resposta, e deu 100% igual). O onnxruntime é o mesmo 1.31.0
do PC, com a telemetria desligada (no Android ele tenta mandar eventos de uso à Microsoft). No S23+, com a
acessibilidade do app ligada: 20 ms para julgar um pedido, 40 ms uma tela, 104 ms uma escolha; 470 a 520 MB com os
dois modelos. Sem a acessibilidade, a One UI só dá ao app os 3 núcleos lentos, e tudo fica 3 a 7 vezes mais lento:
o cérebro no celular tem de rodar com ela ligada. Os modelos não vão no APK (que passou a 58 MB): ficam em
`files/modelos/` do app, copiados pelo adb.

**O cérebro em Kotlin segue o Python** (2026-10-26, etapa 3 de `docs/plano-app-android.md`). O Python é a referência
e o lugar de experimentar. Os textos e as tabelas não são copiados à mão: `tools.app.cerebro exportar` os grava no
`cerebro.json` que o Kotlin lê, e `tests/test_cerebro.py` falha se ele ficou velho. A lógica traduzida é conferida por
trilhas: depois de mudar o executor, o proxy ou a máscara, rode `tools.app.cerebro trilhas` (e `mascara`) e
`android/gradlew :cerebro:conferir`, e traga o Kotlin até dar igual. No celular não há o adb: `set` vai pelas telas
(`executor.SCREENS`); ligar a acessibilidade e o teclado do agente usa `WRITE_SECURE_SETTINGS`, dada pelo adb.

**Chamar pela voz** (2026-10-26, pedido do Pedro; `docs/plano-app-android.md`). Dizer "Alexa" abre o painel do
assistente já ouvindo (`Wake.kt`). O nome é o de um detector pronto do openWakeWord; "Rudy", o preferido se desse no
mesmo, pede treinar um. O detector de palavra do Android é só para apps da fábrica, então o microfone fica aberto num
serviço em primeiro plano (notificação e ponto verde sempre ligados), e o som vira números a cada 80 ms no próprio
aparelho, sem ser gravado. Ligado pela tela do app. Os botões também valem falados (`Commands.kt`, a fala inteira, sem
o provedor): "Alexa, live mode", "Alexa, pausa", "Alexa, para" (encerra a tarefa, como o X), "deixa que eu faço",
"minimiza", "silêncio" etc. Numa tarefa, "Alexa" abre a faixa e ela ouve; sem a faixa na tela a escuta fica fechada
durante a tarefa (o painel cobriria o app que o agente lê). Sem tarefa, "pausa" e "para" são pedidos ao assistente.
O que vem logo depois da palavra vai ao reconhecedor do aparelho por um cano (`EXTRA_AUDIO_SOURCE`), para dizer tudo
de uma vez; o resultado final dele chega vazio por esse caminho, e vale a última parcial.

**Acessibilidade só durante a tarefa.** Apps de banco bloqueiam o aparelho quando veem um serviço de acessibilidade de
fora da loja ligado (o Inter bloqueou em 2026-10-13). Conferido: com o Portal instalado, a acessibilidade e o teclado
dele desligados e a depuração USB ligada, o Inter abre normalmente. O serviço liga em paralelo com o pedido do plano
(1,5 s até a primeira tela) e desliga depois de mandar o resultado. Não liga com app de banco em primeiro plano; se um
aparece no meio da tarefa, desliga na hora e encerra; o proxy não abre app de banco. Lista em `access.BANKS`, extras
em `data/banks.txt`.

**Cache e mapa.** O mesmo pedido (sem contar maiúsculas, acentos e pontuação) repete o caminho gravado sem chamar o
provedor; duas falhas seguidas apagam a entrada. O mapa guarda, por app, a árvore dos toques de tarefas concluídas: o
executor o usa para chegar a um alvo que não está na tela, e ele vai no pedido do plano só para os apps de que o
pedido fala. Não entram tarefas que digitam ou leem um valor, nem rótulos que o mascaramento trocaria.
Desde 2026-11-17 (o guia mandou procurar "Tela" num aparelho em que o item é "Visor"): o mapa aprende também com os
guias e vale no só guia (o caminho gravado não), guarda os nomes curtos das telas por onde o caminho passou ("seen",
só os que a máscara não trocaria) e põe a página aberta direto no lugar dela no menu (`SETTINGS_WAY`). Os nomes vistos
enquanto se rola atrás de um passo vão à ajuda, a fala troca o nome imaginado pelo do controle destacado, e um nome
entre aspas que não está na tela fica no registro do live mode (a conferência "nomes" da suíte).

## Limites conhecidos

- A IA local julga cada trecho de tela uma vez; um erro dela vale até o fim da tarefa (a Gemma já marcou o título
  "Switch to private account?" e uma URL como pessoa, e as palavras passaram a sair trocadas).
- Nomes de usuário fora do cofre que a IA local não acha saem sem máscara (com a Gemma, `ig-seguindo`; os modelos
  pequenos acham 38 de 38 no conjunto congelado). O modelo de escolha ainda escolhe às vezes um controle parecido
  quando o pedido não está na parte visível da tela (45 de 49 "nenhum" certos no conjunto congelado). Seus próprios nomes de
  usuário não estão no cofre. Endereços em texto livre não são detectados. O DDD dos telefones é preservado.
- "Confirmado" quer dizer que a tela mostra o objetivo que o provedor definiu, não que ele entendeu o pedido; num
  pedido ambíguo o cache repete a interpretação da primeira vez. Um objetivo `shows` confere só o texto escolhido.
- O que a árvore não mostra não se confirma (o estado do flash da Câmera).
- O plano varia entre rodadas iguais; um plano errado pode ficar em laço até o limite de ajudas.
- A confirmação automática aceita botões novos que começam por "Switch to", "Turn on" etc., sem olhar o sentido.
- Um toque num ícone de banco (tela inicial) abre o app com a acessibilidade ainda ligada, até a leitura seguinte.
  Outros bancos podem olhar sinais que o Inter não olha (app instalado, depuração USB).
- O `adb forward` trava o adb inteiro por minutos com tráfego grande (o servidor do Portal na pv1, o do app em
  2026-10-19, nos casos que digitam): o app é alcançado por `adb exec-out` e `nc`, sem túnel.
- O adb às vezes trava por minutos (todo `adb shell` para, até um `echo`; volta sozinho em 1 s a 4 min). Na máquina
  da RTX (2026-10-17) o gatilho foi a leitura da tela pelo servidor HTTP do Portal atrás do `adb forward`: em telas
  grandes (YouTube Music, 67 KB), a segunda leitura seguida travou 2 de 2 vezes, com o adb 37.0.1 e com o 35.0.2;
  pelo content provider (`adb shell content query --uri content://com.mobilerun.portal/state_full`), 25 de 25 sem
  travar, a 1,1 s cada contra 0,2 s pelo túnel. Desde então o serviço lê a tela pelo content provider; o túnel
  ficou só para a digitação. No notebook travava no começo de casos do Chrome, o que combina com a mesma causa.
- Máscara não protege contra reconhecimento pelo conteúdo, e texto na tela pode tentar dar ordens ao agente
  (injeção de prompt); não há defesa além de o plano vir antes da tela.
- A avaliação da Gemma tem 40 casos escritos por nós; a taxa real deve ser menor.
- Conta de teste do Instagram: a chave "Private account" já voltou a desligada sozinha entre rodadas.
- A confirmação de ações sensíveis olha as palavras do controle: um botão só com ícone e sem descrição só pede
  confirmação se o plano marcar o passo (`confirm`).
- Pela rede (depuração sem fio), um caminho pelas telas que desligue o Wi-Fi (no guia) corta a ligação no meio da
  tarefa; só o `set` é recusado.
- Live mode contínuo: o microfone aberto ouve também a TV e outras pessoas (uma frase delas vira pedido) e gasta
  bateria; a acessibilidade fica ligada entre os pedidos, e um app de banco pode olhar antes de o app se desligar.
- A página de resultados de uma pesquisa vai ao provedor com textos longos (mascarados): um resultado sobre alguém
  conhecido do dono passa pela IA local como qualquer tela, sem a proteção extra de esconder textos longos.
- Cérebro no celular: os ajustes vão pelas telas, e "desliga o modo escuro" falhou na One UI 9 (opções "Light" e
  "Dark", com agendamento); não sabe qual app toca nem o nome da rede sem a localização; as contas do aparelho só
  entram pelo cofre do PC.
- Um passo `read` sem `target` lê o primeiro texto da tela (visto em 2026-10-26, num plano de ajuda).
- Uma gravação do celular (`tests/gravacoes/`) só repete igual no executor da mesma versão: depois de uma mudança nele,
  as diferenças da repetição são a mudança, não um defeito do Kotlin.
- Chamar pela voz: o detector de "Alexa" foi treinado em inglês; com a voz sintética em português ele falha na fala
  lenta e em "Ei Alexa" e dispara com "Alex, abre". Qualquer pessoa (ou a TV, ou um Echo da Amazon por perto) chama o
  assistente, e o microfone aberto gasta bateria (12 a 27 ms de CPU a cada 80 ms no S23+). Os comandos falados são a
  fala inteira: "Alexa, para" de outra pessoa encerra a tarefa.

## Cuidados ao trabalhar aqui

- **Não imprima valores reais do cofre nem da tela do celular** (contatos, contas, mensagens): a saída dos comandos vai
  para o provedor do próprio assistente de código. Confira contagens e formatos, e use os dados fictícios de
  `tests/ia_cases.py`. O `logs/proxy.jsonl` contém só texto já mascarado.
- Teste o agente em telas neutras (Configurações, Calculadora, Contatos já mascarados).
- Não rode `uiautomator dump` durante uma tarefa: ele suspende os outros serviços de acessibilidade, e o agente perde a tela.
- Não abra app de banco no celular enquanto uma tarefa roda.
- Depois de editar `lmphone/laya_server.py`, rode `./run.sh --stop-laya`; o serviço o `run.sh` reinicia sozinho.
- Cuidado com `pkill -f` em comandos que citam o próprio padrão: ele mata o shell que o executa.
- O cofre desatualiza: depois de mudar contatos, rode `lmphone.sources`.
- O assistente digital do celular é o easy_phone desde 2026-10-21 (antes, o Google). Para voltar: `adb shell cmd role
  add-role-holder android.app.role.ASSISTANT com.google.android.googlequicksearchbox`.
- Celular no USB-C pode virar fonte de energia e travar a CPU do notebook em 400 MHz (ver `~/.claude/sistema.md`).
- Aparelho: Galaxy S23+ (SM-S916B), Android 17, One UI 9.0 (desde 2026-10-22; antes Android 16 e One UI 8.5: as
  medições até 2026-10-21 e o cache, o mapa e os modelos pequenos são da 8.5), sem root, Portal 0.7.25. Interface
  em **português** desde 2026-11-16 (antes, inglês): a suíte, as conferências, o cache, o mapa e os modelos pequenos
  foram feitos com telas em inglês e precisam ser medidos de novo. A descrição do
  aparelho que vai ao provedor é lida dele (`proxy.device_name`). Ollama em `~/.local/opt/ollama`, modelos em
  `~/.ollama` (no Windows, `%LOCALAPPDATA%\Programs\Ollama`, e o app do Ollama já deixa o servidor no ar).
- Com a Proteção Avançada do Android 17 ligada, o sistema bloqueia a acessibilidade de apps que não se declaram
  ferramenta de acessibilidade (o do easy_phone e o Portal): ela fica desligada no aparelho.
