# Plano: modelos locais pequenos treinados nos casos do celular

Proposta de 2026-10-16; etapas 0 a 6 concluídas até 2026-10-19 (os modelos pequenos são o padrão). Ao concluir uma etapa, marque aqui e leve as decisões para o `CLAUDE.md`;
medições longas vão para o `historico.md`.

## Objetivo

Trocar a Gemma (3,3 GB no disco, cerca de 1,5 GB em uso de fato) e o Laya (2,1 GB) por modelos pequenos, treinados só
para o que o projeto pede e só com casos dos apps que o Pedro usa, rotulados por modelos mais fortes.

Metas, nesta ordem:

1. **Não vazar mais que hoje.** No mascaramento, achar pelo menos as mesmas pessoas e `@usuários` que a Gemma com as
   regras fixas (recall), no conjunto de teste congelado da etapa 0.
2. **Escolher controles pelo menos tão bem quanto o Laya** (na primeira rodada da etapa 0: 76 de 149 presentes,
   27 de 29 ausentes, 14 toques errados).
3. **Tamanho:** até 1 GB somando tudo, no disco e na memória; o alvo é de 300 a 500 MB.
4. **Tempo:** não ficar mais lento que hoje em nenhuma chamada (medir na etapa 0).

Ganhos de quebra: o Ollama e o PyTorch saem do caminho da tarefa, e os modelos ficam no formato que o app Android vai
precisar (ONNX).

## O que os modelos fazem hoje

Nenhum dos dois precisa gerar texto: são tarefas de classificação e de marcar trechos, que um encoder pequeno
ajustado faz bem.

| Chamada hoje | Tarefa | Substituto |
|---|---|---|
| `local_ai.find_private`, `screen_fragments` (Gemma) | marcar trechos com pessoa, usuário, negócio, instituição, lugar | encoder com classificação por token (BIO) |
| `local_ai.judge_request` (Gemma) | intenção do pedido; para cada entidade, tipo e se precisa de pesquisa | mesmo encoder: marcação por token + cabeças de classificação |
| `laya_server.pick` (`/pick`) | qual rótulo da tela é o controle que o passo pede, ou nenhum | cross-encoder (passo, rótulo) → nota, com limiar para "nenhum" |
| `laya_server.private` (`/private`) | o trecho cita pessoa ou é rótulo de interface | provavelmente desnecessário: o encoder de marcação já roda em milissegundos em todos os trechos |

A ideia é um encoder base só, com várias cabeças, num servidor que mantém a API atual (`/pick`, `/private`) e ganha
`/entities` e `/judge`, para mexer pouco no `executor.py` e no `proxy.py`.

## Regra para os dados de treino

A regra do projeto vale também aqui: **o modelo de provedor nunca vê dado real**. Por isso, três fontes:

| Fonte | O que é | Quem rotula | Onde fica |
|---|---|---|---|
| A. Sintética | telas, pedidos e passos fictícios imitando os apps do celular | o provedor gera já rotulado | `data/treino/sintetico/` |
| B. Real coletada | trechos de tela, pedidos e escolhas de controle das tarefas | professor local, numa das duas máquinas | `data/treino/real/` (modo 600, fora do git) |
| C. Rótulo de graça | escolhas de controle cujo efeito foi conferido na tela | o próprio executor | junto com B |

- A lista de apps para a fonte A sai de `lmphone.sources` (apps instalados), ordenada pelo uso nas tarefas.
- Na fonte B, quem confere uma amostra dos rótulos é o Pedro, olhando o arquivo; o assistente de código só vê
  contagens e formatos (ver "Cuidados ao trabalhar aqui" no `CLAUDE.md`).
- O `logs/proxy.jsonl` não serve como rótulo de pessoa: ele só marca o que a Gemma e as regras já acharam, e o
  modelo novo herdaria os erros dela.

## Etapas

### 0. Linha de base e conjunto de teste congelado

**Concluída em 2026-10-17**, na máquina da RTX (ver "Conclusão" no fim desta etapa). O que segue até lá é o
registro de 2026-10-16. Feito: o conjunto em `tests/base/` (149 casos de mascaramento, com 780 trechos de
tela, e 178 escolhas de controle, em 20 apps), o avaliador `tests/eval_base.py` e a captura `tests/captura.py`.
Conferência no aparelho (2026-10-16, com `tests/captura.py`; dos apps pessoais só se imprimiu se um rótulo
candidato existe ou não na tela):

- Apps mais usados no último ano, por tempo de tela, sem jogos, banco e tela inicial: YouTube (312 h), Chrome (202 h),
  YouTube Music (79 h), Instagram (74 h), Prime Video, WhatsApp, Netflix, app do Google, Waze, Play Livros, Claude,
  OLX, Câmera, Samsung Notes, Galeria, Calculadora, Configurações, SofaScore, Mercado Livre, Android Auto, Gmail, X, 99.
- Telas conferidas e corrigidas nos casos de escolha (campo `conferido`): Configurações em três telas de rolagem,
  Câmera, Calculadora, WhatsApp, YouTube, Galeria, Gmail, Contatos. Achados: a Calculadora não expõe as teclas na
  árvore; a Câmera expõe proporção e foto em movimento por nomes internos (`BACK_CAMERA_PICTURE_SIZE_NORMAL`); a busca
  do Gmail é "Ask Gmail"; o WhatsApp não tem filtro de não lidas nesta conta.
- O Waze está em português no aparelho: os casos dele, em inglês, estão errados. A barra de cima do Instagram e a
  tela inicial do Chrome não foram conferidas.
- Achado fora da etapa: `local_ai.screen_fragments` manda à IA as linhas de cabeçalho (`**App:** …`) e linhas de id
  interno sem classe (`3. "com.android.settings:id/app_bar_viewpager", …`) como se fossem texto de tela.

Falta: casos dos apps mais usados que não têm nenhum (YouTube Music, Prime Video, Netflix, OLX, Mercado Livre, X,
Samsung Notes, app do Google), refazer o Waze em português, conferir Instagram e Chrome. Os casos de Spotify, iFood,
Uber, Telegram e LinkedIn ficam, mas pesam pouco no uso real.

Primeira rodada (`reports/base-2026-10-16-123737`, Gemma `gemma4-e2b-texto`, Laya `english`, MIN_P 0,5, GATE 0,15):

| Medida | Resultado |
|---|---|
| Casos de mascaramento sem erro | 135 de 149 |
| Pessoas mascaradas | 150 de 154 (perdidas: `ig-feed`, `ig-busca-recentes`, `pt-wa-conversa`, `pt-notif-varias`; a Gemma não listou) |
| Nomes de usuário mascarados | 32 de 36 (3 a Gemma não listou, 1 copiou pela metade) |
| E-mails, telefones, documentos | 20 de 20 (regras fixas) |
| Textos que deviam ficar | 361 de 368 (pessoas públicas marcadas como pessoa; "Nome" de um formulário) |
| Liberados para pesquisa; intenção | 14 de 14; 67 de 67 |
| Trechos descartados pelo filtro do Laya | 234 de 736, nenhum com pessoa |
| Controles presentes achados | 76 de 149 (56 "nenhum", 5 abaixo do limiar, 12 toques errados) |
| Ausentes respondidos como nenhum | 27 de 29 (2 toques errados) |
| Tempo | Gemma 2,0 s por chamada (pior 10,5 s); Laya 0,42 s por escolha |
| Memória no fim (PSS) | Ollama 3,4 GB (com o arquivo mapeado), Laya 2,0 GB |

Segunda rodada das escolhas, com as telas conferidas (`reports/base-2026-10-16-132359`): 80 de 155 presentes,
33 de 36 ausentes, 11 toques errados; **nas 63 escolhas de telas conferidas no aparelho, 31 certas**. Os tempos dessa
rodada não valem (outro processo do Laya disputava a CPU).

Ajustar a pergunta ao Laya não resolve (teste de 2026-10-16, script fora do projeto): baixar MIN_P para 0,35 ou
reescrever a opção "nenhum" muda 1 a 3 casos; aceitar sinônimos na pergunta acha 85 em vez de 80, com 17 toques
errados em vez de 11; tirar a opção "nenhum" acha 102, com 39 toques errados. O Laya não separa "o mesmo controle com
outro nome" de "um controle parecido". Critério para o modelo novo: achar mais controles **sem passar de 11 toques
errados** no conjunto congelado.

O ponto fraco é a escolha de controle: em metade dos casos o Laya prefere "nenhum" a um sinônimo óbvio ("Reload" e
"Refresh", "Chronometer" e "Stopwatch"), o que vira pedido de ajuda ao provedor, e 14 vezes ele tocaria o controle
errado. No mascaramento, o que vaza são nomes e usuários que a Gemma não lista.

Como um erro é investigado:

1. O relatório (`reports/base-<data>/relatorio.html`) abre nas falhas. Cada uma mostra o caminho inteiro (regras
   fixas, filtro do Laya com o p de cada trecho, entrada e resposta bruta da Gemma, decisões, texto enviado; ou o
   ranking completo do Laya numa escolha) e, para cada conferência que falhou, a causa e onde mexer. A tabela
   "Causas dos erros" agrupa os casos por causa.
2. `python -m tests.eval_base --caso <id>` repete só aquele caso e imprime o caminho no terminal: é o ciclo de
   corrigir e conferir. `--falhas` repete tudo o que falhou na última rodada completa. Cada rodada é comparada com
   a anterior ("Mudanças desde a rodada anterior").
3. Quando o erro pode ser do caso, e não do modelo (a tela real é diferente da imitada), abra no celular a tela de
   `onde` e rode `python -m tests.captura <id>`: o print e o texto da tela ficam em `data/capturas/`, só no
   notebook. Têm dados reais: só mostre o print a um assistente se a tela não tiver dados pessoais. A suíte no
   celular grava uma captura dessas sozinha quando uma rodada falha.
4. Um caso errado é corrigido no próprio arquivo, com o motivo no commit; o conjunto continua fora do treino.

Plano original da etapa:

- Ampliar `tests/ia_cases.py` (hoje 40 casos) e `tests/laya_cases.py` (22 escolhas, 120 trechos) para algumas
  centenas de casos, escritos à mão ou revisados um a um, cobrindo os apps mais usados, em português e inglês.
  Incluir os erros conhecidos: `ig-seguindo` (usuário sem máscara), "Switch to private account?" e URL marcados como
  pessoa, `notion-pagina` (página existente no lugar de "New page").
- Congelar esse conjunto: nada dele entra no treino.
- Medir a Gemma e o Laya atuais nele: recall e precisão por tipo de entidade, acerto do `pick`, tempo por chamada,
  memória. Esse é o número a bater.

Pronto quando: `tests.eval_ia` e `tests.eval_laya` rodam no conjunto novo e o relatório da linha de base está em
`reports/`.

**Conclusão (2026-10-17).** Feito na máquina da RTX, com o celular nela:

- Conferidas no aparelho: Instagram › Início (a barra de baixo tem "Message", não "Messenger"; criar e notificações
  não têm rótulo), Chrome › aba nova ("Search Google or type URL", "See N tabs", "Open the home page"), Waze em
  português (início, menu e configurações; os controles sem texto aparecem pelas etiquetas do Compose, como
  `HAMBURGER_BUTTON`) e os oito apps que faltavam: YouTube Music, Netflix (em português), Prime Video, OLX (em
  português), Mercado Livre (busca em espanhol), X, app do Google e Samsung Notes.
- Como, sem imprimir dado real: `arquivo/tela.py` (fora do git) mostra da tela só ✓/✗ de rótulos candidatos, os
  ids internos, a forma do texto (letras viram "a") e os textos que estão entre os embutidos no próprio APK do app
  (`arquivo/apk_textos.py`, que puxa o APK e extrai os textos com o androguard). Chrome, Instagram e o português do
  Waze não estão no APK; esses foram por ids, forma e palpite conferido.
- Conjunto: 161 casos de mascaramento (eram 149) e 266 escolhas (eram 191), das quais 153 em telas conferidas (eram
  63). Os casos do Waze passaram para o português; `wz-alerta` e `wz-velocidade` saíram (os rótulos não existem na
  tela). Uma escolha pode ter mais de um rótulo certo (`certo` em tupla) quando o mesmo controle aparece como dois
  elementos, como a etiqueta da linha e o texto dela.
- Corrigido o achado de `local_ai.screen_fragments`: o cabeçalho (app e teclado) e o id de elemento sem classe não
  vão mais à IA, e o estado da chave não gruda no texto.

Linha de base no conjunto novo (`reports/base-2026-10-17-160734`, Gemma e Laya na GPU da RTX; nas 191 escolhas antigas
o Laya na GPU deu a mesma escolha que na CPU em 189):

| Medida | Resultado |
|---|---|
| Casos de mascaramento sem erro | 147 de 161 |
| Pessoas; nomes de usuário; e-mails, telefones, documentos | 170 de 173; 35 de 38; 20 de 20 |
| Textos que deviam ficar; liberados; intenção | 403 de 412; 14 de 14; 72 de 72 |
| Controles presentes achados | 102 de 217 |
| Ausentes respondidos como nenhum | 46 de 49 |
| Toques errados | 14 |
| Certos nas telas conferidas no aparelho | 78 de 153 |

Nos apps novos o Laya erra mais que na média: 7 de 16 no Waze (rótulo em português ou etiqueta interna, como
"Menu" → `HAMBURGER_BUTTON`), 4 de 9 no Netflix ("Search" → "Buscar"), 1 de 6 nos casos novos do Chrome. A Gemma só
errou um caso novo (`ytm-inicio`, mascarou o que devia ficar). Critério novo para o modelo de escolha: **achar mais
que 102 dos 217 presentes sem passar de 14 toques errados**; para o mascaramento, não perder nenhuma das 170 pessoas
e 35 nomes de usuário que hoje saem mascarados. Os tempos desta rodada não valem para as metas (GPU).

Mudança no conjunto (2026-10-18): famosos passaram a ser pessoas a mascarar, como qualquer pessoa (decisão do Pedro;
ver a etapa 2). Mudaram `ped-pub-noticia`, `ped-pub-musica`, `ped-pub-video`, `ped-en-pub`, `ped-pub-e-amigo`,
`ch-noticia`, `sp-inicio`, `sp-playlist`, `ytm-inicio` e `x-timeline`, e dois casos de `tests/ia_cases.py`. A Gemma
mudou junto (no pedido não há mais o tipo "pessoa_publica"; na tela, ela lista também os famosos). Linha de base nova
(`reports/base-2026-10-18-155702`, só mascaramento): **151 de 161 casos**, 182 de 187 pessoas, 36 de 38 nomes de
usuário, 20 de 20 e-mails e telefones, 400 de 403 textos que deviam ficar, intenção 72 de 72. Ganharam os casos de
famosos e `pt-notif-varias`; perdeu `sp-playlist` (a Gemma deixou de achar "Larissa Prado"), e em `x-timeline` ela não
acha "Marisa Monte" dentro da frase.

### 1. Coleta no serviço

- Gravar, atrás de uma variável (`LMPHONE_COLETA=1`), em `data/treino/real/`:
  - trechos novos de cada tela, com o app em primeiro plano;
  - o pedido do usuário;
  - cada escolha de controle: o passo, os rótulos da tela, quem decidiu (rótulo exato, Laya, ajuda do provedor) e se
    o efeito foi conferido. Escolha conferida é um exemplo positivo; um toque do Laya desfeito por uma ajuda é um
    negativo.
- Rodar a suíte e tarefas do dia a dia nos apps mais usados até ter, como ordem de grandeza, 2 a 5 mil trechos e
  1 a 3 mil escolhas de controle.

Pronto quando: as contagens por app e por fonte aparecem num `python -m lmphone.treino status`, sem mostrar
conteúdo.

**Em andamento (2026-10-17).** A coleta existe: `LMPHONE_COLETA=1` no ambiente de quem pede a tarefa (o cliente a
manda ao serviço com o pedido, sem reiniciá-lo). Um arquivo por dia em `data/treino/real/`, um registro por linha:

| Tipo | Campos |
|---|---|
| `pedido` | o texto e o julgamento da Gemma (intenção e entidades), ou nada se ela falhou |
| `trecho` | o app e o texto; cada trecho uma vez por tarefa |
| `julgamento` | nos pedidos de ajuda: os trechos novos, a nota do Laya (`/private`) de cada um e o que a Gemma achou por bloco |
| `escolha` | o app, o passo (ação e alvo), os rótulos da tela, o escolhido, quem escolheu (`rótulo exato`, `mapa`, `cache`, `IA local`, `provedor`) e o efeito: `conferido`, `desfeito` (veio um pedido de ajuda), `já estava`, `nenhum` (o Laya não achou), `incerto`, `erro` (o aparelho não fez a ação) ou vazio (descartada antes do toque) |
| `fim` | o resultado da tarefa e as ajudas |

Primeira rodada (3 casos da suíte): 118 trechos, 7 escolhas, 2 julgamentos. Falta juntar o volume.

O volume vem de uma coleta noturna em vez do uso do dia a dia: `tests/coleta.py` roda as tarefas de
`tests/coleta_cases.py` (183, em 71 apps instalados) sem cache, para o provedor planejar toda vez e as escolhas
variarem. As tarefas só navegam, buscam e leem; apps de banco, pagamento, governo, autenticação, VPN e acesso remoto
ficam de fora. O script mantém a tela do celular e o computador acordados, para se o adb sumir por 5 min ou o
celular aparecer bloqueado, e para no orçamento. Teste com 9 tarefas (Relógio e Spotify): 3 min, US$ 0,005, 568
trechos e 19 escolhas (11 do Laya, 8 delas "nenhum"). Pela conta, as 183 tarefas levam cerca de 1 h e US$ 0,10.

Coleta de 2026-10-17 (3 rodadas das 183 tarefas, em três partes: parou uma vez com a cortina de notificações aberta
e o celular bloqueado, o que levou à recuperação antes de cada tarefa e ao `--de`, e uma vez o celular caiu do USB e
voltou dentro dos 5 min): 549 tarefas em cerca de 6 h, US$ 0,65 de provedor. Com a primeira rodada e o teste, o
`status` mostra:

| | |
|---|---|
| Tarefas e pedidos | 561 |
| Trechos | 37.477 (9.774 distintos; os que mais aparecem são da tela inicial, do Chrome e das Configurações) |
| Julgamentos de tela | 560 |
| Escolhas de controle | 1.549 |
| Rótulo exato | 807: conferido 759, incerto 34, desfeito 11, sem efeito 3 |
| IA local (Laya) | 649: nenhum 531, desfeito 63, conferido 52, sem efeito 3 |
| Provedor | 93: conferido 81, desfeito 8, incerto 4 |

O volume da etapa passou da meta. O Laya ficou abaixo de 0,5 em 82% das vezes em que foi chamado, e das escolhas que
fez, mais foram desfeitas do que conferidas: é o caso que o modelo pequeno precisa resolver. Só 106 dos 531 "nenhum"
têm depois, no mesmo passo e na mesma tarefa, uma escolha conferida (89 do rótulo exato, 10 do provedor, 7 do Laya)
que serve de resposta certa; os outros 425 ficam sem rótulo, e a resposta deles terá de vir da etapa 2 ou de uma
conferência à parte.

### 2. Dados sintéticos pelo provedor

- Um script pede ao provedor, app por app, telas fictícias no formato de texto do `device.py`, já com os trechos
  rotulados (BIO), pedidos com entidades e `precisa_pesquisa`, e pares (passo, rótulos da tela, resposta) com
  sinônimos e casos de "não está aqui".
- Nomes, usuários e números saem de listas fictícias, nunca do cofre, e sem interseção com `tests/base` (o
  `tests/ia_cases.py` divide 14 nomes com ele e não serve de fonte sem filtrar).
- Variar idioma (português e inglês), comprimento e ruído (rótulos de interface parecidos com nomes, nomes em
  minúsculas, usuários com pontos e números).

Pronto quando: alguns milhares de exemplos por tarefa, com uma amostra lida e aprovada.

**Em andamento (2026-10-17).** O gerador é `tools/treino/sintetico.py` (no `.venv`; grava em
`data/treino/sintetico/<tipo>.jsonl`, e o descartado em `descartes.jsonl`). Cada chamada pede ao provedor, para um app
sorteado e uma parte dele sorteada, 6 telas, 15 pedidos ou 12 escolhas. Ele não passa pelo `proxy`: o que vai é só o
nome do app e nomes das listas fictícias do próprio script, das quais saem as palavras dos nomes do conjunto congelado.

Cada lote passa por uma conferência: outra chamada, com raciocínio e sem ver a resposta do gerador, refaz o rótulo
(qual controle, ou nenhum; quem é pessoa ou usuário na tela; intenção, pessoas e o que precisa de pesquisa no pedido),
e o exemplo só fica se as duas concordam. Também caem: entidade que não está no texto, certo fora da tela, pedido
igual a um rótulo, nome do conjunto congelado e pessoa pública com nome das listas de pessoas privadas.

O que os testes (8 rodadas pequenas, US$ 0,14 no total) mostraram e o que mudou por causa disso:

- O provedor copia os exemplos do prompt: "Mark as read" e "Grace period" saíram em 6 e 5 de 18 telas. O prompt passou
  a descrever as armadilhas em vez de dar exemplos.
- Sem pedir, não vieram telas sem pessoa (0 de 18), e só 14% das escolhas eram "nenhum". O prompt passou a fixar
  quantas de cada por chamada.
- Sem conferência, 2 de 8 escolhas "nenhum" tinham o controle na tela com outro nome ("log out" com "Sign out" na
  tela), justamente o erro do Laya que o treino quer corrigir. Com a conferência, de cada lote caem de 0 a 10 de 12
  escolhas, e nas discordâncias olhadas a conferência estava certa quase sempre.
- Nos pedidos, o gerador chamava de "mista" pedidos que só agem no aparelho. A pesquisa é comparada por sobreposição
  ("iguatemi" e "shopping iguatemi"), porque a conferência corta os nomes de outro jeito e lista produtos.
- Telas em português em apps que no aparelho são em inglês, e nomes fictícios como pessoa pública (jogadores no
  Sofascore): o prompt passou a pedir rótulos em inglês e pessoas públicas reais.
- Revisão da amostra pelo Pedro: o resto certo, mas e-mails e telefones vinham no tipo genérico "outro". Passaram
  a ter tipos próprios (`email`, `telefone`, `documento`), conferidos por código: o tipo tem de ter a forma, e uma
  tela com e-mail ou telefone visível sem marcação é descartada. As telas já geradas foram convertidas.
- Sem o tipo "pessoa pública" (decisão do Pedro, 2026-10-18): todo nome de gente é "pessoa" e é mascarado, famoso
  ou não. Um modelo pequeno não sabe quem é famoso e decide pelo contexto; se aprender a soltar alguns nomes, solta
  nomes de pessoas privadas também. Mascarar um famoso custa pouco: o provedor planeja com o nome falso e o aparelho
  digita o real. O gerador pede famosos como pessoa, as conferências os listam como pessoa, e o que vier com o tipo
  antigo vira pessoa. Nos dados já gerados, 94 viraram pessoa nas telas e 63 nos pedidos. (Antes disso valeu por
  algumas horas uma regra intermediária, pessoa pública só em apps de conteúdo público.)

Último teste (`--chamadas 5`): 28 telas, 63 pedidos e 34 escolhas guardados, 51 descartados, US$ 0,030. Por exemplo
guardado: tela US$ 0,0005, pedido US$ 0,0002, escolha US$ 0,0003. Para 1.500 telas, 3.000 pedidos e 3.000 escolhas,
cerca de US$ 2 e pouco mais de 1 h com 4 chamadas em paralelo. O Pedro leu a amostra (`--amostra 15 >
data/treino/sintetico/amostra.txt`) e aprovou com a correção dos tipos de e-mail e telefone.

Geração completa (2026-10-17 e 18, 6 chamadas em paralelo), somada aos testes que ficaram:

| Tipo | Guardados | Descartados (principais motivos) | Custo |
|---|---|---|---|
| Telas | 1.306 (18.344 trechos; 321 sem entidade) | 355: conferência 236, entidade fora dos trechos 42, nome do conjunto congelado 39 | US$ 0,46 |
| Pedidos | 3.057 (ação 2.219, pesquisa 717, mista 121) | 997: conferência 805, entidade fora do texto 112 | US$ 0,57 |
| Escolhas | 3.135 em 73 apps (651 "nenhum") | 1.053: conferência 729, pedido igual a rótulo 245, certo fora da tela 79 | US$ 0,69 |

Entidades nas telas: pessoa 2.700, usuário 724, lugar 511, negócio 279, e-mail 256, telefone 171, instituição 110,
documento 94. Total US$ 1,72; 42 chamadas falharam (JSON quebrado duas vezes ou conexão) e foram puladas. Os pedidos
saíram com pouca "mista" (4%); se a cabeça de intenção errar nela, gerar mais desse tipo. **Volume da etapa 2
atingido**; falta só, se quisermos, medir a taxa de erro dos rótulos numa amostra maior lida à mão.

### 3. Rótulos das telas reais por um professor local

- Rodar um modelo grande no notebook, fora do caminho da tarefa, de madrugada: um Qwen ou Gemma de 12 a 14B em Q4
  (cerca de 9 GB; cabe nos 16 GB com o resto fechado). Ele rotula a fonte B com o mesmo esquema da fonte A.
- Onde o professor e a Gemma atual discordam, o caso vai para revisão do Pedro.

Pronto quando: a fonte B está rotulada e a taxa de concordância com a amostra revisada é conhecida.

**Em andamento (2026-10-18/19), na máquina da RTX** (8 GB de VRAM, 15,6 GB de RAM), com `tools/treino/professor.py`
(Ollama, saída por esquema JSON, temperatura 0, sem raciocínio, contexto de 8192):

- Escolha do professor no conjunto congelado (`professor avaliar`): **gemma4:12b**. Mascaramento: 181 de 187 pessoas,
  38 de 38 usuários, 146 de 161 casos. Controles: 206 de 217 presentes, 44 de 49 ausentes, 11 toques errados, contra
  102/217, 46/49 e 14 do Laya. O qwen3:14b não coube (10 GB, 42% na CPU) e a avaliação dele foi interrompida por falta
  de memória; na parte que rodou ficou atrás (137 de 161 casos, 17 toques errados em 129).
- O "nenhum" no esquema precisa ser um valor da lista (`"(none)"`): com `null` num `anyOf`, nenhum modelo respondia
  nenhum (0 de 49).
- Rótulos dos dados reais (`professor rotular`, retoma de onde parou; `data/treino/real/rotulos-*.jsonl`): os 9.774
  trechos distintos em 472 blocos de até 40 por tarefa, e as 742 escolhas que não foram por rótulo exato. Nas telas
  marcou pessoa 683, usuário 334, e-mail 151, telefone 3, documento 1. Num bloco o modelo entrou em laço e o JSON saiu
  cortado; desde então a resposta tem limite e o bloco é dividido ao meio até dar certo (o que nem sozinho responde
  vai em `falhou`; nenhum trecho ficou assim). Duas paradas por falta de memória do PC no meio, retomadas.
- Escolhas: a concordância bruta com as conferidas (49 de 125) engana. Nas que o Laya escolheu e o efeito conferiu,
  43 de 52 iguais. Das 79 do provedor, 38 são controles sem texto (escolhidos pelo índice; o professor só vê
  rótulos) e 29 não têm palavra em comum com o alvo do plano (o provedor tocou outro controle para chegar lá, e
  "nenhum" é a resposta certa para o alvo); nas 10 que têm, 10 iguais. Onde o Laya disse nenhum, o professor
  escolheu um controle em 181 de 531: são os rótulos novos que interessam, ainda sem conferência.
- Professor x Gemma nos trechos (só os que a Gemma julgou, depois do filtro do Laya): os dois marcam 112, só o
  professor 42, só a Gemma 154. Outros 652 trechos que o professor marca nunca chegaram à Gemma (o filtro do Laya os
  descartou, ou o cofre e as regras fixas já os cobriam). Amostra para revisão em
  `data/treino/real/revisao-professor-gemma.txt` (modo 600): 162 trechos e 60 escolhas, para marcar quem acertou.

- Revisão da amostra (2026-10-19; o Pedro marcou 6, o Claude o resto, e o Pedro confere): nos 162 trechos, o
  professor certo em 132, a Gemma (não havia o que marcar) em 21, nenhum em 1, sem decisão em 6. Nos 60 que só a
  Gemma marcou, ela errou todos os decididos (títulos, marcas, ids `_R_…`, "Papai"). O professor erra para o lado
  seguro: marca bandas e páginas públicas como pessoa ou usuário. Nas 60 escolhas em que o Laya disse nenhum, o
  professor acertou 24 e errou 33 (3 sem decisão): aponta um controle do caminho ou só parecido em vez de nenhum.
- Critério da revisão: pessoa se mascara sempre, famosa, artista ou nome dentro de título (decidido pelo Pedro em
  2026-10-19); banda, marca, título e página pública que não é pessoa, não.
- Consequência para a etapa 4: os rótulos de tela do professor entram no treino; as escolhas dele não. Para o
  `pick`, só escolhas por rótulo exato, as de efeito conferido e as sintéticas.

Falta: o Pedro conferir a revisão do Claude.

### 4. Treino

- Ambiente próprio, `.venv-treino` (transformers, datasets, onnx), separado do `.venv` do projeto, que segue só com
  a biblioteca padrão. Scripts em `tools/treino/`.
- Encoders base a comparar: multilingual-e5-small, mDeBERTa-v3-small/xsmall, DistilBERT multilíngue. O que pesa
  nesses modelos é o vocabulário multilíngue (até 250 mil tokens): cortá-lo para os tokens que aparecem em português
  e inglês nos dados reduz bastante o tamanho sem mexer no resto.
- Treino na RTX 5060 da máquina Windows (`.venv-treino`, PyTorch `cu128`): com um encoder de cerca de 100M e alguns
  milhares de exemplos, minutos por rodada. Os dados reais ficam nas duas máquinas do projeto, nunca em serviço de fora.
- Pesos de perda favorecendo o recall de pessoa e usuário: deixar passar um nome é pior que mascarar um rótulo.

Pronto quando: um modelo bate a linha de base nas metas 1 e 2 no conjunto congelado.

**Concluída em 2026-10-19**, na RTX, com o encoder `intfloat/multilingual-e5-small` (118M) nos dois modelos:

- Dados (`tools/treino/dados.py` → `data/treino/conjunto/`, modo 600): telas sintéticas e reais rotuladas pelo
  professor, pedidos sintéticos, escolhas sintéticas e reais; nada do conjunto congelado (4.009 trechos iguais
  saíram). Acréscimos locais, sem provedor: pedidos com uma pessoa trocada por um nome de usuário fictício (os
  sintéticos não tinham nenhum), telas com nomes encurtados ("Nome S.", só "Nome") e escolhas em telas reais com
  resposta conhecida: o professor dá outros nomes a rótulos sorteados de 527 telas da coleta (`professor
  parafrasear`, 1.571 rótulos, uns 40 min), e nomes de rótulos de outra tela do mesmo app viram casos de nenhum.
- Marcação (`tools/treino/treinar.py marcacao`): BIO por token, com "negocio+" etc. para o que o pedido manda
  pesquisar, e uma cabeça de intenção; perda com peso 3 em pessoa e usuário; a marcação é estendida até a palavra
  inteira (um usuário saía em pedaços). 10 épocas, 4 min.
- Escolha (`treinar.py escolha`): cross-encoder treinado por tela, com os rótulos e a opção "nenhum" num softmax;
  limiar tirado da validação (0,85). A versão por pares (cada rótulo com uma nota sozinho) ordenava bem (146 de 217
  em primeiro) mas não sabia dizer nenhum; sem as telas reais parafraseadas, o modelo por lista ficava em 91.
  6 épocas, 6 min (com pares de até 64 tokens; um treino que começou com o Ollama ainda soltando a GPU caiu para a
  memória compartilhada e levou 30 min por época).
- Avaliação: `tools/treino/servidor.py` (API do Laya mais `/entities` e `/judge`) e `tests.eval_base --novo URL`, o
  mesmo caminho do serviço com as respostas trocadas. `local_ai.apply_request` passou a mascarar usuário, e-mail,
  telefone e documento vindos do pedido (a Gemma não dá esses tipos).

Resultado no conjunto congelado (`reports/base-2026-10-19-121248`), contra a linha de base de 2026-10-17/18:

| Medida | Gemma e Laya | Modelo novo |
|---|---|---|
| Casos de mascaramento sem erro | 151 de 161 | 156 de 161 |
| Pessoas; usuários; e-mails etc. | 182/187; 36/38; 20/20 | 185/187; 38/38; 20/20 |
| Textos que deviam ficar; liberados; intenção | 400/403; 14/14; 72/72 | 402/403; 13/13; 70/72 |
| Controles presentes achados | 102 de 217 | 110 de 217 |
| Ausentes respondidos como nenhum | 46 de 49 | 42 de 49 |
| Toques errados | 14 | 11 |
| Certos nas telas conferidas no aparelho | 78 de 153 | 84 de 153 |

Nenhuma pessoa ou usuário que a Gemma mascarava sai sem máscara (meta 1); as duas pessoas que faltam já faltavam.
A intenção erra dois pedidos de pesquisa como "mista", o que não muda a máscara (liberar vale nas duas). Tamanho: 466
MB cada modelo em fp32 (932 MB juntos); a redução é a etapa 5.

### 5. Exportar e reduzir

- Exportar para ONNX e quantizar em 8 bits com calibração nos dados de treino (a quantização dinâmica do PyTorch no
  Laya não serviu: a memória não caiu e o acerto piorou, ver `historico.md`). Comparar fp32, fp16 e int8 no conjunto
  congelado; recalibrar os limiares (o 0,5 do `pick`) para o modelo quantizado.
- Servidor novo em `.venv-modelo` com onnxruntime e tokenizers, sem PyTorch, na porta 8788 e com a API do Laya.

Pronto quando: o modelo final cabe na meta 3 e não perde nas metas 1 e 2 para o fp32.

**Concluída em 2026-10-19.** `tools/treino/exportar.py` exporta para ONNX e quantiza; `lmphone/modelo_server.py`
serve os dois modelos no `.venv-modelo` (onnxruntime, tokenizers, numpy; 146 MB, sem PyTorch), com a API do Laya mais
`/entities` e `/judge`. As funções de texto comuns ao treino e ao servidor (blocos, BIO, palavra inteira, a opção
nenhum) passaram para `lmphone/modelo.py`, só com a biblioteca padrão.

| Versão | Mascaramento | Pessoas; usuários | Controles; toques errados | Disco (os dois) | Memória do servidor |
|---|---|---|---|---|---|
| PyTorch na GPU (etapa 4) | 156/161 | 185/187; 38/38 | 110/217; 11 | 932 MB | — |
| ONNX fp32 | 156/161 | 185/187; 38/38 | 110/217; 12 | 896 MB | mais de 1 GB |
| Tudo em int8 (dinâmica, por canal) | 154/161 | 183/187; 38/38 | 110/217; 15 | 226 MB | ~540 MB |
| **Só a tabela de tokens em int8** | **156/161** | **185/187; 38/38** | **109/217; 11** | **346 MB** | **~660 MB** |
| Vocabulário cortado, int8 | 153/161 | 184/187; 36/38 | 94/217; 11 | 74 MB | — |

- Vale a tabela em int8 (`modelo-tabela.onnx`): a tabela de tokens (250 mil × 384) é quase todo o tamanho e só tem os
  pesos arredondados uma vez; as camadas em fp32 evitam o erro da quantização das ativações, que fez o int8 completo
  perder "Duda T." e "Wellington" e passar de 14 toques errados. A quantização estática com calibração do plano não
  foi preciso tentar. fp16 ficou de fora: na CPU não ganha nada.
- Cortar o vocabulário (`--cortar`: os tokens dos textos do projeto, os 20 mil mais frequentes e os caracteres soltos,
  43 mil de 250 mil) reduz a 37 MB por modelo, mas muda a tokenização de palavras fora dos textos ("Wellington" vira
  "Well", "ing", "ton") e o modelo perdeu nomes. Para a máscara, não vale o risco.
- Memória (Windows, memória privada do processo): uns 130 MB por modelo e 256 MB do tokenizador, que os dois
  compartilham (mesmo vocabulário). Dois achados: o OpenBLAS do numpy reservava 490 MB na importação (uma thread
  basta; `OPENBLAS_NUM_THREADS=1`), e cada modelo carregava o seu tokenizador. Hoje o Ollama e o Laya somam 5,4 GB.
- Tempo na CPU da máquina da RTX, com o HTTP: tela 9 ms de mediana (pior 30 ms), pedido 5 ms, escolha 31 ms (pior
  141 ms); a Gemma levava 2,0 s por chamada e o Laya 0,42 s por escolha no notebook. Falta medir no notebook.
- O limiar da escolha, recalculado na validação com o modelo exportado, continua 0,85.

Metas: 1 e 2 mantidas; 3 dentro do limite de 1 GB, acima do alvo de 300 a 500 MB (uns 660 MB). O caminho para o alvo
é um encoder só com as duas cabeças (questão aberta da etapa 4): um modelo e um tokenizador, uns 400 MB.

### 6. Integração e troca

- Escolha por variável (`LMPHONE_LOCAL_AI=gemma|novo`), o padrão continua o atual.
- Rodar `tests.eval_ia`, `tests.eval_laya` e a suíte inteira no celular com os dois; comparar acerto, falhas,
  tempo, memória e custo do provedor (menos ajudas é sinal de `pick` melhor).
- Se o novo vencer: vira o padrão, o `run.sh` deixa de subir o Ollama e o Laya, e o `CLAUDE.md` muda (Modelos,
  Como rodar, Arquitetura). A Gemma e o Laya ficam como opção por um tempo.

Integração (2026-10-19): `LMPHONE_LOCAL_AI=novo` ligava os modelos pequenos: o `lmphone.run` sobe o
`lmphone/modelo_server.py` (no `.venv-modelo`, modelos em `data/modelos/`) na porta do Laya, não usa o Ollama, e troca
o servidor e o serviço quando o modo muda; `local_ai.judge_request` e `find_private` vão a `/judge` e `/entities`. O
padrão continua a Gemma e o Laya.

Suíte inteira no celular, as duas rodadas na mesma hora, na máquina da RTX, com o mesmo cache e mapa:

| | Modelos pequenos (`reports/suite-2026-10-19-124803`) | Gemma e Laya (`reports/suite-2026-10-19-130052`) |
|---|---|---|
| Execuções | 24 passaram, 1 falhou, 1 erro | 23 passaram, 2 falharam, 1 erro |
| Falhas | `cfg-borda` | `ig-seguindo` (nome de usuário saiu sem máscara), `notion-pagina` |
| Tempo; custo | 11,1 min; US$ 0,017 | 14,3 min; US$ 0,021 |
| Memória (serviço e IA local) | ~0,82 GB | ~4,3 GB (pico 6,3 GB) |

O erro nas duas é `cam-flash`, que pede conferência manual e rodou sem terminal. A IA local somou 0,3 s na rodada
inteira com os modelos pequenos; o resto do tempo é o celular, o provedor e a própria suíte. `ig-seguindo`, que vaza
um nome de usuário com a Gemma desde a pv1, passou. `cfg-borda` falhou por um toque errado: o passo pedia "Edge
panels", que estava abaixo, fora da tela, e a escolha deu "Eye comfort shield" com p=0,96 e desligou essa chave. É o
ponto fraco já visto no conjunto congelado (ausentes: 41 de 49, contra 46 do Laya).

Reforço do "nenhum" (decisão do Pedro antes da troca): ~3 mil escolhas novas, de telas reais da coleta, pedindo pelo
nome exato um rótulo de outra tela do mesmo app (a resposta é nenhum). Conjunto congelado
(`reports/base-2026-10-19-133443`): 113 de 217 presentes, 45 de 49 ausentes, 10 toques errados, 94 de 153 nas telas
conferidas (antes 109, 41, 11 e 82; o Laya, 102, 46, 14 e 78). Limiar novo, da validação: 0,8. "Edge panels" na tela
Display passou a dar nenhum (0,87).

Suíte de novo com os modelos pequenos (`reports/suite-2026-10-19-133549`): **25 de 26 passaram, nenhuma falhou**
(`cam-flash` pede conferência manual), 10,9 min, US$ 0,012, ~0,8 GB.

**Concluída em 2026-10-19**: os modelos pequenos viraram o padrão (`LMPHONE_LOCAL_AI=gemma` volta ao Laya e à Gemma);
`tests.eval_base` e `tests.eval_ia` continuam medindo a Gemma (o primeiro recusa os modelos pequenos na porta do Laya
sem `--novo`). Falta medir os tempos no notebook e levar `.venv-modelo` e `data/modelos/` para lá.

## Manutenção

- Apps mudam com atualizações e aparecem apps novos. A coleta (etapa 1) fica ligada, e um retreino periódico usa o
  que se acumulou. Até lá, o caminho de reserva atual (confiança baixa → ajuda do provedor com tela mascarada) segura
  os casos fora do treino.
- As regras fixas de mascaramento continuam valendo por cima de qualquer modelo.

## Riscos

- **Treinar e testar no mesmo tipo de dado.** Se o conjunto congelado for parecido demais com o sintético, o número
  engana. Ele precisa ter telas reais revisadas.
- **Herdar erros do professor.** Daí a revisão das discordâncias e o recall medido em casos escritos à mão.
- **Pedidos que exigem raciocínio** ("liberar um negócio só se a tarefa pede pesquisá-lo") podem não caber num
  classificador. Se a cabeça de `judge_request` não bater a Gemma, ela pode ficar só para essa chamada, uma por
  tarefa, e sair do caminho das telas.
- **Conjunto pequeno.** Com poucos milhares de exemplos, o modelo decora os apps vistos; é aceitável, desde que a
  reserva funcione nos outros.

## Questões abertas

- Um encoder com várias cabeças ou dois modelos (mascaramento e `pick`)? Decidir na etapa 4 pelo resultado.
- Qual professor local cabe e rotula bem em português? Testar dois na etapa 3 contra a amostra revisada.
- O mesmo ONNX roda no celular (onnxruntime mobile) quando o app Android começar; conferir antes de fechar a etapa 5.
