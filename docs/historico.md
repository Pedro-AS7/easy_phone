# Histórico do easy_phone até a pv1

O `CLAUDE.md` como estava em 2026-10-16, antes da limpeza da pv1: decisões, medições e testes em ordem de chegada.
Vale como registro; o que está em vigor é o `CLAUDE.md`. Parte do que aparece aqui saiu na pv1 (fluxo do Mobilerun,
`--local` com a Gemma escolhendo controles, Gemma no celular, Laya em 8 bits); o código está no commit 7fb4cc8.

## Estado atual (2026-10-13)

Protótipo no notebook: o agente roda no PC e controla o Galaxy S23+ por ADB. A versão final (tudo no celular) ainda não começou.

| Parte | Estado |
|---|---|
| Controle do celular (Mobilerun + Portal) | Funciona |
| Mascaramento por regras fixas + cofre + proxy | Funciona, ligado ao agente |
| Valores falsos por tarefa (mapa da sessão) | Funciona, ligado ao agente |
| IA local: julgar o pedido (uma chamada por tarefa) | Funciona, ligada ao agente |
| IA local: achar nomes no texto de tela (só trechos novos a cada passo) | Funciona, ligada ao agente; testada no celular na Calculadora e em Contatos |
| Serviço permanente e ciclo próprio no modo local (sem o agente do Mobilerun) | Funciona; na suíte passaram 21 de 26, e os 2 casos que ele quebrou foram corrigidos e retestados |
| Modo local (`./run.sh --local` ou `--laya`): o provedor escreve o plano e o objetivo, código e IA local executam e conferem | Protótipo; na suíte de 24 casos passaram 22 de 26 execuções (10 e 11 antes das correções de 2026-10-12) |
| Prints com OCR e fotos borradas | Não existe; o proxy recusa imagens |
| Acessibilidade e teclado do Portal ligados só durante a tarefa, trava para apps de banco | Funciona; testado no celular (`cfg-versao` passou, tudo desligado no fim) |
| Confirmação de ações sensíveis (enviar, comprar, apagar) | Não existe |
| Pesquisa na web pelo provedor | Não ligada |
| App Android próprio com IA no aparelho | Não existe |

Próximos passos: decidir o que fazer com pedidos ambíguos (o do flash virou notificação por flash da Acessibilidade),
tratar os nomes de usuário que a Gemma não acha no fluxo padrão (`ig-seguindo` falha por isso) e a URL marcada como
pessoa, achar um jeito de chegar a controles sem texto (`notion-ajustes`), e descobrir por que o adb às vezes trava
por minutos no começo de um caso do Chrome (não aconteceu na última rodada). Depois, decidir sobre o ciclo próprio no modo local (sem o
agente do Mobilerun) e fazer a confirmação automática de diálogos olhar o sentido da mudança.

Testes do modo `--laya` no celular em 2026-10-12, com pedidos em inglês e Haiku 5.5 (diagramas em `reports/`):

| Pedido | Resultado | Tempo | Chamadas ao provedor | Custo |
|---|---|---|---|---|
| Make my Instagram account private | Concluído, confirmado na tela | 64 s | 4 (1 plano, 3 ajudas) | US$ 0,0024 |
| Get the verification code from my messages | Devolveu um código de 6 dígitos, lido no aparelho | 63 s | 2 | US$ 0,0012 |
| Remove the yellow bar that shows up on the edge of the screen | Concluído: `edge_enable` foi de 1 para 0 | 36 s | 1 | US$ 0,0006 |
| Turn on the flash of the back camera | O flash ficou ligado, mas o agente declarou falha | 92 s | 7 | US$ 0,0047 |

Teste do Instagram (tornar a conta de teste privada), 2026-10-12: com o gratuito, 179 s e parou no passo 10 pelo limite
diário, perdido em "Accounts Center". Com o Haiku 5.5, 117 s, 12 chamadas, US$ 0,0094: chegou ao botão e confirmou, mas
o Instagram recusou ("Business profile can't be private") e o agente parou sem mudar o tipo da conta. Do tempo, 47% foi
IA local, 29% provedor, 32% Mobilerun e celular. No modo local, mesma tarefa: 71 s, 3 chamadas ao provedor (1 plano e
2 pedidos de ajuda), US$ 0,0026, 9 ações (6 por código, 1 pela IA local, 2 com o provedor). A conta já estava privada
quando ele chegou à tela, então a chave não foi tocada nesse teste. Com `--laya`: 77 s, 4 chamadas (1 plano, 3 ajudas),
US$ 0,0024; desta vez a chave estava desligada, ele tocou nela e na confirmação, o Instagram recusou (perfil comercial)
e o provedor encerrou a tarefa como não concluída.

## Como rodar

```sh
./run.sh "instrução em linguagem natural"      # roda uma tarefa no celular, já passando pelo proxy
./run.sh --local "instrução"                   # protótipo: o provedor só escreve o plano; o proxy executa localmente
./run.sh --laya "instrução"                    # o mesmo, com o Laya achando controles pelo nome e filtrando a tela antes da Gemma
./run.sh --stop                                # encerra o serviço do modo local e o servidor do Laya, que ficam no ar entre tarefas
./run.sh --stop-laya                           # encerra só o servidor do Laya
LMPHONE_CYCLE=mobilerun ./run.sh --laya "..."  # modo local pelo agente do Mobilerun, como era antes do serviço
.venv/bin/python -m lmphone.sources            # reimporta contatos e contas do celular para o cofre
.venv/bin/python -m unittest discover -s tests # testes do mascaramento e do julgamento no proxy
.venv/bin/python -m lmphone.trace              # gera reports/tarefa-<sessão>.html, o diagrama da última tarefa do log
.venv/bin/python -m tests.eval_ia              # avalia a IA local e gera reports/ia-local.html (precisa do Ollama no ar)
.venv-laya/bin/python -m tests.eval_laya       # compara variantes do Laya (peso, 8 bits): acerto, tempo e memória
.venv/bin/python -m tests.phone_suite          # suíte de 24 tarefas no celular; --listar, --nivel crucial, ids; gera reports/suite-<data>.html
ollama serve                                   # servidor da IA local (não inicia sozinho); pkill ollama para parar
```

- O celular precisa estar no USB com depuração ativa (`adb devices`). O app Mobilerun Portal está instalado nele com o
  serviço de acessibilidade ligado.
- `.env` guarda `OPENROUTER_API_KEY` e, opcionalmente, `MODEL`. Nunca imprima a chave.
- Python 3.12 num venv em `.venv`, com `mobilerun` 0.6.22. O código do projeto usa só a biblioteca padrão.
- O Laya fica num venv separado, `.venv-laya` (1,2 GB, PyTorch só de CPU, `laya` 0.4.6); só o `laya_server.py` roda nele.
  Para recriar: `python3.12 -m venv .venv-laya`, `pip install --index-url https://download.pytorch.org/whl/cpu torch`, `pip install laya`.

## Arquitetura

```
pedido -> [IA local julga] -> ler a tela (árvore de acessibilidade, em texto)
       -> mascarar (regras fixas + cofre + decisões da IA local)
       -> proxy local -> provedor (só dados falsos) -> ação com nomes falsos
       -> desmascarar -> executor no celular -> tela mudou, repete até concluir
```

Diagrama completo: https://claude.ai/artifact/PHFU2nunsHc5XJtfng25qs (privado, do Pedro).

| Arquivo | Papel |
|---|---|
| `run.sh` | Sobe um proxy para a tarefa (passando o pedido em `LMPHONE_TASK`), roda o `mobilerun` apontado para ele, encerra o proxy no final |
| `lmphone/masking.py` | `Vault` (o que proteger), `Session` (pares real ↔ falso da tarefa), `Masker` (troca em passada única e desfaz) |
| `lmphone/sources.py` | Lê contatos, contas e perfil do dono via ADB e grava no cofre |
| `lmphone/proxy.py` | Proxy compatível com a API da OpenAI: julga o pedido com a IA local na subida e os trechos novos de tela a cada passo, mascara o que sai, desmascara o que volta, registra em `logs/proxy.jsonl` o que enviou e o que o provedor respondeu, com tempos e tokens |
| `lmphone/local_ai.py` | Chamadas ao Ollama: `judge_request` (intenção e entidades do pedido) e `find_private` (pessoas e usuários em texto de tela), `screen_fragments` (tira os trechos de texto da árvore) |
| `lmphone/executor.py` | Modo local: pede o plano ao provedor, decide cada ação (rótulo exato, IA local, ajuda do provedor) e confere o resultado |
| `lmphone/service.py`, `lmphone/client.py` | Serviço do modo local, que fica no ar entre tarefas e roda cada uma num ciclo próprio (ler a tela, pedir a ação ao executor, agir), sem o Mobilerun; o cliente manda a tarefa e mostra o andamento |
| `lmphone/access.py` | Liga a acessibilidade e o teclado do Portal no começo da tarefa e desliga no fim; recusa com app de banco em primeiro plano (`python -m lmphone.access on\|off\|status`) |
| `lmphone/device.py` | O celular para esse ciclo: tela lida do Portal por HTTP, no mesmo texto que o Mobilerun entrega; toques, rolagem e teclas pelo adb; digitação pelo teclado do Portal |
| `lmphone/cache.py` | Cache de caminhos por pedido e mapa dos apps em árvore, ambos aprendidos de tarefas concluídas |
| `lmphone/laya_server.py` | Servidor local do Laya: recebe os rótulos que o plano pede e os da tela, devolve o rótulo escolhido ou nenhum |
| `lmphone/trace.py` | Gera o diagrama visual de uma tarefa (linha do tempo e cada chamada ao provedor) a partir de `logs/proxy.jsonl` |
| `tests/test_masking.py`, `tests/test_proxy.py` | Testes unitários do mascaramento e do julgamento do pedido no proxy |
| `tests/ia_cases.py`, `tests/eval_ia.py` | 40 casos fictícios e o gerador do relatório visual, passo a passo |
| `tests/laya_cases.py`, `tests/eval_laya.py` | 22 escolhas de controle e 120 trechos de tela fictícios (68 em inglês, 52 em português) para comparar variantes do Laya, uma por processo |
| `tests/phone_cases.py`, `tests/phone_suite.py`, `tests/site/` | Suíte no celular: 24 casos (12 cruciais, 12 simples), o executor que os roda pelo `run.sh` e confere no aparelho, e as páginas de teste servidas ao Chrome por `adb reverse` |
| `data/vault.json` | O cofre real do Pedro (modo 600, fora do git) |

## Decisões e seus motivos

**Controle do celular: Mobilerun (antigo DroidRun), sem fork.** Ele já entrega a árvore de acessibilidade, os gestos e o
ciclo do agente. O nosso trabalho é a camada de privacidade. Telemetria dele desligada com `MOBILERUN_TELEMETRY_ENABLED=false`
(o `run.sh` já faz); o Mobilerun Cloud não é usado.

**O provedor só é alcançado pelo proxy.** O agente recebe uma chave falsa e o endereço do proxy; a chave real existe só no
processo do proxy. Assim nada chega ao provedor sem passar pelo mascaramento, e trocar de provedor não muda o resto.
Se o mascaramento falhar, o pedido não é enviado.

**Árvore de acessibilidade em vez de print.** Texto é fácil de mascarar; pixels não. O agente roda com `--no-vision` e o
proxy recusa qualquer pedido com imagem. Print fica para quando a árvore não servir, e só depois de OCR e de borrar
fotos localmente. Proposta ainda não confirmada pelo Pedro: cobrir cada texto trocado na imagem com uma tarja contendo
o valor falso.

**O cofre guarda só valores reais; os falsos nascem e morrem com a tarefa.** O cofre diz o que proteger (nomes de contatos
quebrados em palavras, e-mails, últimos 8 dígitos de telefones). Os pares real ↔ falso ficam na `Session`, em memória.
Motivos: o provedor não tem memória entre tarefas, então um falso estável não serve para nada; falsos fixos deixariam o
provedor montar um perfil de cada pseudônimo; e um cofre que acumula tudo o que passou pela tela vira um registro
sensível. Rotação por tempo foi descartada: trocar no meio de uma tarefa quebra a tradução de volta.

**Uma tarefa = um processo de proxy.** É o que define a sessão: o `run.sh` sobe um proxy numa porta livre e o mata no final,
o que apaga o mapa. Se um dia o provedor mantiver conversa longa ou memória, a sessão passa a ser essa conversa.

**Dados fixos e dados temporários.** O critério é a origem, não o app. O que vem de fonte estável do aparelho (contatos,
contas, perfil) vai para o cofre. O que só apareceu na tela (usernames do Instagram, canais, histórico de busca, membros
de grupo que não são contatos) vive só na sessão.

**A IA local decide por entidade, e só pode liberar o que é ambíguo.**
- Pessoas, e-mails, telefones, CPF, cartões e `@usuários` são mascarados sempre, pelas regras fixas.
- A IA local pode pedir mais máscara: nomes fora do cofre ou escritos em minúsculas.
- A IA local pode liberar negócios, instituições e lugares, e só quando a tarefa exige pesquisá-los na internet
  ("Qual o endereço da Barbearia Arctos?" sai real; "Mande mensagem para a Barbearia Arctos" sai com "Arctos" mascarado).
- Pessoa pública fora dos contatos fica real; contato é mascarado mesmo que o pedido seja pesquisá-lo.
- Na dúvida, ou se a IA local falhar, valem só as regras fixas.
- O julgamento do pedido roda no proxy, em paralelo com a subida do agente; o primeiro envio ao provedor espera ele
  terminar (limite de 60 s). Com o Ollama fora do ar, o `run.sh` avisa e segue só com as regras fixas. O log guarda só
  a intenção e a contagem de decisões, nunca o texto das entidades.
- Texto de tela: a cada envio, o proxy tira os trechos de texto dos blocos `<device_state>` (sem ids nem nomes de
  classe), junta os que a IA local ainda não viu em blocos de até 1200 caracteres e faz uma chamada por bloco. Os
  julgados ficam em `Session.seen`; julgar a tela inteira a cada passo seria lento demais. Bloco que falha não entra
  em `seen` e é tentado de novo no passo seguinte. O que o pedido liberou para pesquisa não é mascarado de volta
  pela tela. Medido com telas fictícias: 5 a 7 s por tela nova, 0 s quando nada mudou. Na Calculadora do celular: 9 s do pedido
  mais 3 a 5 s por passo com tela nova, numa tarefa de 52 s.

**Modo local (protótipo, atrás de `--local`; o fluxo padrão não mudou).** A ideia do Pedro: em vez de perguntar ao
provedor a cada ação, pedir a ele um plano e deixar a execução no aparelho. O provedor recebe o pedido mascarado mais o
modelo e o idioma do aparelho, e devolve passos em JSON (`acao`, `alvo` com os rótulos possíveis, `se_ausente`,
`esperado`). O proxy responde ao Mobilerun no lugar do provedor. Cada ação é decidida nesta ordem: rótulo exato na tela
(código); mesmo controle com outro nome (IA local, pergunta fechada sobre a lista de rótulos); ajuda do provedor, com a
tela mascarada. Regras em código, porque a IA local não sabe dizer "nenhum": tela quase sem texto pede ajuda; alvo
ausente com `se_ausente: rolar` rola até 3 vezes antes de perguntar à IA local; `conferir` nunca toca; depois de cada
ação, se nenhum texto de `esperado` aparece, pede ajuda. Limite de 6 pedidos de ajuda por tarefa. O mascaramento
continua valendo para tudo o que vai ao provedor; a tela só é julgada pela IA local quando vai num pedido de ajuda.
O JEV (TypeSafe AI) foi avaliado e descartado para o papel local: é uma API hospedada.

**Acessibilidade só durante a tarefa (2026-10-16; `lmphone/access.py`).** Em 2026-10-13 o Inter bloqueou o acesso
neste aparelho por "possível risco relacionado a um aplicativo", citando apps com permissão de Acessibilidade. O Portal
é exatamente isso: instalado fora da loja, com serviço de acessibilidade e teclado próprio. Conferido em 2026-10-16:
com o Portal instalado (fora da loja), a acessibilidade e o teclado dele desligados e a depuração USB ligada, o Inter
abriu normalmente. O sinal é o serviço (ou o teclado) ligado, não o app instalado nem a depuração. Escolha do Pedro, entre
as opções discutidas (as outras: ler a tela pelo usuário `shell` sem serviço, banco na Pasta Segura, aparelho separado):
- O serviço do Portal entra na lista de serviços ativos no começo da tarefa, em paralelo com o pedido do plano, e
  sai dela no fim, junto com o teclado do Portal (o teclado de antes volta, de `logs/ime.prev`). Outros serviços de
  acessibilidade do aparelho são mantidos. O serviço do modo local desliga depois de mandar o resultado e antes de
  aceitar a próxima tarefa, e também ao subir (para uma queda no meio de uma tarefa); o `run.sh` faz o mesmo no fluxo
  padrão (liga antes do proxy, desliga na saída) e no `--stop`. A suíte liga só durante a leitura de tela das
  conferências.
- Não liga se um app de banco está em primeiro plano (pelo `dumpsys`, sem o Portal). Se um aparece no meio da tarefa
  (o `packageName` da tela lida), o ciclo desliga tudo na hora e encerra a tarefa. O proxy não abre app de banco.
  Lista em `BANKS` (`access.py`); extras em `data/banks.txt`. O fluxo padrão (Mobilerun) só tem a trava do começo e
  a do `launch`.
- Custo medido no celular (Portal 0.7.25, reinstalado em 2026-10-16 depois de o Pedro o desinstalar para o Inter
  voltar, o que funcionou): ligar leva 0,3 a 0,5 s e a primeira tela sai de 1,5 a 1,7 s depois; desligar, 0,4 s. Em
  `cfg-versao` (`suite-2026-10-16-114117`, passou) ligou em 1,5 s, pronto antes do plano (13 s, à espera do
  julgamento da Gemma ainda fria). Só as tarefas do cache, que não esperam o provedor, pagam esse tempo. No log:
  `acessibilidade.ligou_em`. Do 1,5 s, cerca de 1 s é o `connect` religando o servidor do Portal com uma espera fixa.
- Limites: um toque num ícone de banco (tela inicial) abre o app com o serviço ainda ligado, até a leitura seguinte;
  outros bancos podem olhar sinais que o Inter não olha (app instalado, depuração USB). Não se sabe se o Inter
  reage a um serviço ligado enquanto ele já está aberto em segundo plano. Não se
  sabe se a lista de apps (`content://.../packages`) responde com o serviço desligado: por isso ela é relida só
  depois de ligar.
- 103 testes unitários (8 novos em `tests/test_device.py`: ligar e desligar mantendo os outros serviços e o teclado,
  recusa com banco à frente, banco no meio da tarefa, proxy que não abre banco).

**Serviço permanente e ciclo próprio no modo local (2026-10-13).** Motivo: 58% do
tempo de uma rodada era Mobilerun, adb e esperas. `./run.sh --local` e `--laya` agora mandam a tarefa a
`lmphone/service.py` (porta 8789, `LMPHONE_SERVICE_PORT`; PID em `logs/service.pid`), que o `run.sh` sobe quando
falta e reinicia quando `lmphone/*.py` ou o `.env` são mais novos que o PID. O fluxo padrão não mudou (Mobilerun e
um proxy por tarefa).
- Fica entre tarefas: o processo, a chave do provedor, a ligação com o Portal e a lista de apps (3,2 s para ler,
  mesmo por HTTP; relida no começo de uma tarefa se tem mais de 10 min, ou na hora se um app não é achado).
  Não fica: a sessão. `proxy.begin` sorteia valores falsos novos, relê o cofre e zera o executor a cada tarefa; um
  julgamento que termina depois de outra tarefa começar é descartado. "Uma tarefa = um processo" virou "uma tarefa =
  um `begin`" no modo local. Uma tarefa por vez; fechar o cliente interrompe a tarefa.
- As variáveis `LMPHONE_*` valem as de quando o serviço subiu (`./run.sh --stop` para trocar); modelo, Laya e
  `LMPHONE_CACHE` valem por tarefa.
- O ciclo lê `/state_full` do Portal (0,02 a 0,1 s) e monta o mesmo texto do Mobilerun (conferido igual na tela
  inicial do aparelho e num teste unitário contra o formatador dele). Toque, rolagem e teclas vão por `adb shell
  input`, como no Mobilerun. O Portal também aceita `POST /tap`, `/swipe`, `/global` e `/app`; não usados.
- O plano é pedido antes da primeira leitura de tela (`plan_ahead`), para o primeiro passo não ser decidido numa
  tela lida antes de o app abrir.
- A tela só vale quando duas leituras seguidas saem iguais (`read_screen`, intervalo de 0,15 s, limite de 1,5 s).
  Sem isso, lendo 0,3 s depois do toque, a tela vinha no meio da animação e o toque na chave do "Eye comfort
  shield" caiu fora do lugar (2 de 3 execuções de `cfg-cache-mapa` falharam).
- Suíte inteira com o serviço (`reports/suite-2026-10-13-111932`): 21 de 26 passaram, 4 falharam, `cam-flash`
  manual; 10,9 min, 58 chamadas, 27 ajudas, US$ 0,036. Duas falhas eram do ciclo novo, corrigidas e retestadas
  passando (abaixo); `ig-seguindo` e `notion-ajustes` falharam como antes.
- O ganho é o começo da tarefa, cerca de 4 a 5 s; por ação o tempo ficou parecido. Contra o Mobilerun no mesmo
  dia (`suite-2026-10-13-104859`, 6 casos): `cfg-cache-mapa` pelo cache de 9,3, 9,2 e 8,8 s para 4,5, 4,5 e 5,0 s;
  `cfg-borda` de 14,3 para 10,0 s; `web-preco` de 7,5 para 4,7 s; `yt-busca` de 8,8 para 7,8 s. Outros pelo cache:
  `cfg-escuro` 4,9 s e `ig-perfil` 4,5 s (ontem 13,7 e 10,7 s, mas a rodada de ontem ainda tinha o julgamento de
  8 s). O total da suíte não serve de comparação: `cam-grade`, `waze-ajustes`, `web-anonima` e `ig-privada`
  estavam sem cache nesta rodada e somaram 12 chamadas a mais.
- Apps de mesmo nome (`pick_rival`): "Messages" é do Google e da Samsung. O `launch` recusava nomes repetidos e a
  pergunta auxiliar do Mobilerun resolvia; sem ele, `msg-codigo` gastou 3 ajudas. Agora vale o app de SMS padrão do
  aparelho e, se nenhum dos dois é, o último da lista. Reteste: 7 s, 1 chamada. Nome que nenhum app tem ainda vira
  pedido de ajuda. Outros nomes repetidos no aparelho: Calendar, Wallet, Authenticator.
- Digitação: o Portal às vezes responde "input accepted via IME but could not be verified" (Notion). O Mobilerun
  ignorava o corpo da resposta; o ciclo novo tratava como erro e pedia ajuda. Agora não é falha: quem confere o
  texto é o executor. Reteste de `notion-pagina`: passou, 39 s, 3 chamadas.
- 95 testes unitários (`tests/test_device.py` cobre o texto da tela, o ponto do toque, o ciclo, a sessão por
  tarefa e os apps de mesmo nome).

**Início da tarefa no modo local (medido no Instagram, 2026-10-12).** Do proxy no ar até o app aberto e lido eram
19,9 s; ficaram 13,3 s, e a tarefa inteira foi de 64 s para 32 s com o Laya já carregado (a de 32 s achou a conta já
privada e teve um pedido de ajuda a menos). Três mudanças:
- O plano é pedido sem raciocínio (`"reasoning": {"enabled": false}`): 2 a 3 s em vez de 5 a 7 s. De 70 a 85% dos
  tokens de saída do Haiku eram raciocínio, não o plano. Em 4 tarefas os planos saíram equivalentes. Os pedidos de
  ajuda continuam com raciocínio; `LMPHONE_PLAN_REASONING=1` o religa no plano.
- O proxy lê a lista de apps do Portal na subida, em paralelo (cerca de 2 s), e abre o app pelo pacote com
  `adb shell monkey`; ao Mobilerun responde só com um `wait` de 1 s. Nome repetido ou desconhecido cai no `open_app`
  do Mobilerun, como antes.
- O servidor do Laya fica no ar entre tarefas, na porta 8788 (`LMPHONE_LAYA_PORT`), com o PID em `logs/laya.pid`.
  Carregar o modelo custava cerca de 3 s por tarefa. Ele ocupa memória enquanto está no ar.

**Nos pedidos de ajuda, a tela vai ao provedor reduzida a rótulos curtos (`redact`, em `executor.py`).** Texto com mais
de 60 caracteres vira `[hidden text]` e números com 3 ou mais dígitos viram `#`; ids, classes e posições ficam. Vem
antes do mascaramento, que continua valendo. Na tela de mensagens do teste do código (do log, já mascarada): de 51
textos, 9 longos e 16 com números; depois da redução, nenhum. O limite: mensagens curtas e sem números ainda saem, só
com os nomes mascarados. O provedor deixa de ver descrições longas, então decide com menos contexto.

**Ciclo de ação do Mobilerun no modo local: TCP e espera de 0,3 s.** O `run.sh` passa `--tcp` e uma configuração gerada
em `logs/mobilerun.yaml` (o exemplo da versão instalada com `after_sleep_action: 0.3`; o padrão é 1,0). Medido com um
provedor falso na tela de Configurações: o ciclo fixo por ação caiu de 2,06 s para 0,35 s (só TCP: 1,05 s; só a espera:
1,34 s) e a subida, de cerca de 8 s para 4,4 s. Como a tela pode ser lida no meio da troca, o executor espera 0,7 s uma
vez por passo antes de rolar, pular ou pedir ajuda. No Instagram isso aconteceu em quase todo toque, e ainda assim cada
ação levou de 0,5 a 1,7 s em vez de 2,2 a 2,7 s.

**Ajudas repetidas, app aberto antes do plano e planos sem pular telas (2026-10-12).**
- O pedido de ajuda leva as respostas anteriores que não deram certo, e o terceiro pedido para o mesmo passo encerra
  a tarefa (`MAX_SAME_HELP`). Num teste em que o plano estava errado, parou em 4 chamadas em vez de 7.
- Se o julgamento do pedido acha um único app, o proxy já o abre, antes de o plano existir; o executor pula o
  `open_app` inicial desse app. Medido: aberto aos 4,7 s da subida, junto com o primeiro pedido do Mobilerun. Não foi
  antes porque a lista de apps levou 4,3 s (o adb disputa com a subida do Mobilerun).
- Sem raciocínio, metade dos planos do Instagram pulava o botão de menu e mandava rolar a tela errada. O formato do
  plano agora pede um passo para cada toque, inclusive ícones sem texto, e `scroll` só na mesma tela: 5 de 5 planos
  amostrados passaram a ter o passo do menu. Também proíbe `tap` em chave (só `turn_on`/`turn_off`), porque um plano
  tocou numa chave já ligada. Com `--laya`, o executor consulta o Laya antes de rolar.
- Teste do Instagram depois disso: concluído em 41 s, 4 chamadas (1 plano, 3 ajudas), US$ 0,0025, chave conferida no
  aparelho. As três ajudas somaram 19 s só de resposta do provedor.

**Chaves: conferência pelo estado e confirmação por código (2026-10-12).** Duas das três ajudas do Instagram vinham do
plano: a reescrita omitia o diálogo de confirmação, e a conferência final procurava uma frase que o provedor chutou.
Agora, depois de `turn_on`/`turn_off`, o executor confere o estado da chave na árvore em vez dos textos de `expected`.
Se o estado não é o pedido e surgiu um botão de confirmar que não estava na tela anterior (`CONFIRM`, `CONFIRM_START`
em `executor.py`), ele toca uma vez. O `check` final passa se a chave tratada está na tela no estado pedido. Chave sem
estado legível (flash) continua pela conferência de textos. Teste no Instagram, com a chave desligada no início:
36 s, 2 chamadas (1 plano, 1 ajuda pelo ícone sem texto), US$ 0,0012; chave ligada conferida no aparelho. A lista de
botões de confirmar é fixa e em inglês, e só vale para diálogo aberto por uma chave que o pedido mandou mudar.

**Cache de caminhos (`lmphone/cache.py`, `data/paths.json`, modo 600, fora do git).** Desde a versão 2 do formato
(ver "Objetivo conferido pelo aparelho"): só entra tarefa cujo objetivo a tela confirmou, o objetivo é guardado com o
caminho, uma repetição sem desvios não regrava a entrada, e entradas da versão 1 são ignoradas. O texto a seguir é o
da primeira versão. Quando o plano chega ao fim com
a conferência final, o proxy guarda o que foi de fato executado (rótulos tocados, inclusive os que vieram do Laya ou
de ajuda; controles sem texto pelo id interno ou pela posição). No mesmo pedido (texto igual, sem contar maiúsculas,
acentos e pontuação), esse caminho vira o plano e o provedor não é chamado. Se um passo falha, segue o fluxo normal
(ajuda) e o caminho é regravado; duas falhas seguidas apagam a entrada. Não entram: tarefas que digitam texto, que leem
um valor, que o provedor encerrou sem o plano chegar ao fim, e qualquer pedido ou rótulo que o mascaramento trocaria.
`LMPHONE_CACHE=0` desliga. Instagram, conta já privada: 22 s e 1 chamada sem cache; 11 s e nenhuma chamada com cache.
Não guarda a versão do app, e pedidos parecidos com outras palavras não acertam o cache.

**Mapa do app em árvore (`data/maps.json`, primeira etapa; ideia do Pedro).** O cache por pedido só acerta com o mesmo
texto. O mapa guarda, por app, a árvore dos toques de tarefas concluídas (Instagram → Profile → Options → Account
privacy, com a chave "Private account" nessa tela). O nó é o caminho desde a abertura do app, não o conteúdo da tela,
então só rótulos tocados são gravados. Toque que não mudou a tela e confirmação de diálogo não descem na árvore. O
provedor ainda escreve o plano; o executor usa o mapa em dois pontos: quando o alvo do passo não está na tela, procura
no mapa o caminho até o alvo deste passo ou dos 3 seguintes e troca esses passos pelos toques conhecidos (`route`); e
aceita como conferência a tela mostrar um controle que o mapa conhece para aquela posição (`arrived`). Medido com um
pedido de texto novo ("Set my Instagram profile to private"), conta já privada: sem mapa, 18,2 s do primeiro pedido
do Mobilerun ao fim, com uma consulta ao Laya; com mapa, 8,9 s, sem Laya. Em ambos, 1 chamada ao provedor (o plano).
Segunda etapa: o mapa vai no pedido do plano (`render`; até 3000 caracteres, e acima disso só o app citado no pedido;
`LMPHONE_MAP_PROMPT=0` desliga). Com ele o provedor usa os rótulos e a ordem reais: em amostras, o plano do Instagram
caiu de 9 para 6 passos, com "Options" no lugar de "Menu" e `turn_on` no lugar de `tap` na chave, a 120 tokens de
entrada a mais e cerca de 100 de saída a menos. No celular, pedido de texto novo com a conta já privada: 9,6 s e
8,9 s do primeiro pedido ao fim, o mesmo que a primeira etapa (8,9 s); o ganho é de qualidade do plano, não de tempo,
porque o executor já corrigia o caminho com o mapa. Risco visto em amostra: num pedido para outra tela ("contas
bloqueadas"), um de dois planos passou por "Account privacy" só por ela estar no mapa.
Terceira etapa, ainda não feita: deixar o Laya escolher o destino entre as folhas, sem provedor.

**A tela "sem texto" do Instagram era tela carregando.** Medido no Portal: o menu de configurações mostra 19 textos
logo depois do toque e 78 entre 1,6 e 3,2 s depois, sem nenhuma interação. As ajudas pelo "ícone sem texto" eram isso:
o toque que o provedor mandava só dava tempo de a tela carregar. O executor agora espera até 4 vezes por passo
(`MAX_WAITS`) enquanto a tela tem no máximo um texto ou ainda muda entre leituras, antes de rolar, pular ou pedir ajuda.

**Toque às cegas em chave.** Mesmo com a regra no formato, um plano trouxe `tap` na chave seguido de `turn_on`; com a
conta já privada, o toque abriu "Switch to public account?" (ninguém confirmou). O executor agora pula um `tap` em
controle marcável quando um passo adiante liga ou desliga o mesmo alvo.

**Laya no lugar da Gemma para achar o controle pelo nome (`--laya`).** O Laya (Convai Innovations, Apache-2.0, 421M de
parâmetros) é um modelo de decisão: não gera texto, devolve uma escolha com probabilidade. Em 14 casos tirados de telas
reais do Instagram (7 com alvo na tela, 7 sem), a Gemma acertou 6 (5 e 1) a 3,7 s por decisão, e o Laya acertou 11
(5 e 6) a cerca de 0,3 s. Só a formulação de roteamento funcionou (o controle pedido é o estado, os rótulos da tela são
os destinos, mais um destino "(none)"); perguntas de sim ou não por rótulo deram 1 de 14, e o modelo multilíngue, 6 de
14. Abaixo de 0,5 de probabilidade a resposta vira "nenhum": com esse limiar não houve toque errado nos 14 casos, e os
erros viram pedido de ajuda. O limiar foi escolhido olhando esses mesmos casos. A Gemma continua julgando o pedido e
as telas para mascarar.

**No mascaramento, o Laya só filtra; quem acha os nomes continua sendo a Gemma.** Medido em 68 trechos em inglês com
dados fictícios (18 com pessoa ou usuário, 50 rótulos de interface): a Gemma acertou 66; o Laya no lugar dela acertou
39, perdeu 15 de 32 nomes e mascarou 12 rótulos. Como filtro antes da Gemma ele serve: com corte em 0,20 não perdeu
nenhum trecho com pessoa e descartou 37 dos 50 rótulos. Com `--laya`, trechos com probabilidade abaixo de 0,15
(`LMPHONE_LAYA_GATE`) são tidos como interface e não vão para a Gemma; isso tira falsos positivos como "Switch to
private account?" (0,12). O filtro custa cerca de 0,1 s por trecho curto, parecido com o tempo da própria Gemma, então
o ganho é de acerto, não de velocidade. Se o Laya falhar, a Gemma julga tudo.

**No modo local tudo o que vai a um modelo é em inglês**: o plano (`steps`, `action`, `target`, `if_missing`, `expected`),
as perguntas ao Laya e as mensagens do executor. Os pedidos de teste também, porque o Laya só foi bom em inglês.
O plano tem a ação `read` para pedidos de um valor da tela (um código): o provedor dá palavras vizinhas e uma expressão
regular, e o valor é lido no aparelho e entregue ao usuário sem passar pelo provedor. O plano precisa terminar com um
`check` (ou `read`) e dar um passo próprio a cada confirmação; sem isso o provedor omitia a confirmação e a tarefa era
dada como concluída com o diálogo ainda aberto.

**O que não se mascara.** Palavras de categoria (barbearia, clínica, secretaria), parentescos, marcas e os nomes dos apps
instalados ficam como estão, senão o provedor perde o contexto. A lista fixa está em `STOPLIST` (`masking.py`); extras
vão em `data/stoplist.txt`.

**Modelo local: Gemma 4 E2B (`gemma4:e2b-it-qat`, 4,3 GB) no Ollama, com `think` desligado.** Escolhido por ser do tamanho
que cabe no S23+ (8 GB de RAM). Com raciocínio ligado leva cerca de 22 s por chamada; desligado, 9 s por pedido e 4 s por
trecho de tela, só em CPU. A saída é restrita por esquema JSON.
Desde 2026-10-12 o padrão é `gemma4-e2b-texto`, a mesma Gemma sem o projetor (ver "Memória dos modelos").

**Chamada de preparo antes de cada julgamento da Gemma (2026-10-12; `ask` em `local_ai.py`).** Dos 8,5 s do
julgamento do pedido, 7,5 s eram o Ollama relendo o prompt fixo (514 tokens a 69 por segundo); gerar a resposta leva
de 0,5 a 1,5 s. O Ollama 0.40.3 roda a Gemma pelo servidor do llama.cpp, que só retoma a leitura de pontos que ele
salvou, e salva um só no fim de cada prompt. Uma chamada de preparo que termina no fim da parte fixa (`Pedido:` ou
`Tela:` sem texto, `num_predict: 1`) deixa o ponto ali. Medido com pedidos fictícios: preparo mais julgamento em 0,9 a
2,1 s, com as mesmas respostas; o preparo custa 0,2 s quando o ponto já existe. Na tela, trechos curtos foram de 4 s
para 1,5 s, mas em 2 de 4 testes voltou a 4,1 s (o servidor escolheu um estado antigo sem o ponto), e num bloco longo
o ganho é só a parte fixa (2,7 s). A primeira chamada depois de 5 min sem uso (o modelo sai da memória) paga o tempo
antigo, mais 8,4 s de carga. Depende de comportamento interno do Ollama; se uma versão nova desfizer o ganho, o tempo
volta ao de antes. `LMPHONE_PRIME=0` desliga.

**A trava do julgamento guarda o provedor, não o Mobilerun (2026-10-12).** O `judged.wait()` segurava toda resposta
do proxy; agora fica nos dois envios ao provedor (`ask_provider` e o repasse do fluxo padrão). Tarefa com o caminho
no cache começa sem esperar; sem cache, o executor ainda espera, para o app aberto antes do plano já estar decidido.
Se a tarefa do cache já está andando quando o julgamento termina, o proxy não abre mais o app (`prelaunch`). No log
anterior, as 34 tarefas que rodaram inteiras pelo cache esperaram 3,1 s na mediana, de 10,1 s. No celular depois das
duas mudanças (`reports/suite-2026-10-12-203040`): `cfg-cache-mapa` pelo cache em 9,1, 9,8 e 8,6 s (antes, de 11,9 a
14,3 s quando o pedido era diferente do anterior) e julgamento de 1,0 a 1,9 s, sempre pronto antes do primeiro pedido
do Mobilerun. Por isso a tarefa do cache com julgamento lento ainda não rodou no aparelho. 75 testes unitários.

**Provedor: modelos gratuitos do OpenRouter, por enquanto.** Padrão `nvidia/nemotron-3-ultra-550b-a55b:free`, o único dos
três testados que concluiu uma tarefa. Os gratuitos falham por limite de uso e por respostas vazias; não é defeito nosso. Sem créditos na conta, o limite é de
50 pedidos gratuitos por dia (zera às 21h de Brasília) e modelos pagos devolvem erro 402.

**Primeiras duas rodadas da suíte (2026-10-12, Haiku 5.5; `reports/suite-2026-10-12-145155` e `-150843`).** A primeira
partiu de cache e mapa vazios, a segunda usou os da primeira. Passaram 10 e depois 11 de 26 execuções; 67 e 58
chamadas ao provedor; US$ 0,040 e 0,041. Nas 10 execuções que usaram o cache, a soma foi de 191 s para 141 s e de 13
chamadas para 1 (a do Notion, em que o caminho gravado falhou e virou pedido de ajuda). Do tempo da primeira rodada
(934 s): 27% provedor, 23% Gemma julgando o pedido (8 s por tarefa), 25% julgando telas de pedidos de ajuda (Gemma
mais o filtro do Laya), 7% esperas. Causas das falhas, lidas no log:
- **Digitação**: o executor chamava `type_text`, que o Mobilerun não oferece sem visão ("Unknown tool"); nada era
  digitado em 6 casos por rodada. Corrigido, ver abaixo. O plano também não tinha a tecla Enter.
- **Limite de 15 passos do Mobilerun**: 4 e 5 execuções cortadas; 84 das 189 ações do executor eram esperas.
- **Conferência frouxa (falso "concluído")**: `visible` casa por trecho ("On" casa com "Connections"); o `check`
  final usa textos que o provedor chutou e que já estavam na tela; a falha de um passo é perdoada se o alvo do passo
  seguinte está na tela. Visto em `cfg-cache-mapa` 3ª, `cfg-escuro` 2ª, `notion-ajustes` 1ª e `web-formulario`.
- **Chaves**: `turn_on` toca no título da linha (nas Configurações isso abre a subtela em vez de mudar a chave);
  `tap` às cegas num controle marcável inverte a chave (`cfg-borda` passou por sorte; `ig-privada` abriu o diálogo
  de tornar pública).
- **`expected` chutado gera ajuda à toa**: das 29 ajudas da primeira rodada, 23 foram "nenhum texto esperado
  apareceu" (8 depois de digitar, 15 depois de um toque). Em `cfg-versao` o toque em "About phone" estava certo.
- **Cache e mapa aprendem errado**: `mark_noop` compara só os textos, então um toque que muda estado sem mudar texto
  (opção "Dark", chave) é descartado ao gravar; caminhos com laço (flash três vezes) e rótulos soltos ("Off") entram
  no mapa; uma repetição pelo cache regrava a entrada.
- **`read`** pega o primeiro texto com qualquer palavra do alvo (`web-preco` devolveu o preço de outro produto).
- **Laya**: 2 escolhas erradas em 6 (menu do Chrome no lugar da barra de endereço; uma página do Notion no lugar de
  "New page").
- **Suíte**: `web-injecao` reprova uma resposta correta (o agente citou o texto plantado ao dizer que o ignorou);
  `waze-ajustes` espera rótulos em inglês e o Waze está em português; a conferência de chave pela tela não achou a
  chave em nenhum caso (`ig-privada`, `cam-grade`, a verificar no aparelho); a heurística de nomes de usuário conta
  números. No log, o último envio de `ig-seguindo` tem 1 e 2 nomes de usuário sem troca, de 7 e 9.
- `web-preco` na segunda rodada: o adb travou (a abertura do app estourou 15 s e o Mobilerun não fez nenhum pedido).

**Digitação no modo local (corrigida em 2026-10-12).** O passo `type` chama a ferramenta `type` do Mobilerun. O campo
é o que tem um dos rótulos de `target` (de preferência um campo de texto) ou o único campo de texto da tela; sem
isso, digita no campo com foco. O toque que dá o foco vai numa ação própria e a digitação na leitura seguinte, sem
índice: com os dois juntos (o `index` do `type`), o primeiro campo de um formulário web recebeu vazio, sem erro
nenhum, e o segundo recebeu certo. `"clear": true` no passo substitui o conteúdo. O plano ganhou a ação `enter`
(tecla Enter por `system_button`). O executor passou a ler o `<error>` que o Mobilerun devolve para a ação anterior:
vira pedido de ajuda na hora, com o erro como motivo, e vai para o log (`erro_ferramenta`) e para os erros da suíte.
No celular: a busca no YouTube passou em 15 s com 1 chamada, e no formulário o telefone chegou certo ao site (ida e
volta do mascaramento). A separação do toque de foco ainda não rodou no aparelho.

**Objetivo conferido pelo aparelho e passos conferidos pelo efeito (2026-10-12; 61 testes unitários, 3 casos no
celular).** Resposta às falhas da suíte; substitui a conferência por `expected` e o `check` final.
- O plano vem com `goal`, que o código confere na tela: `{"on"|"off": [rótulos]}` (chave, caixa ou opção nesse
  estado) ou `{"shows": [textos]}` (texto que não estava na primeira tela do app; uma palavra só precisa ser o rótulo
  inteiro). A tarefa termina como `confirmado` (a tela mostra o objetivo), `sem confirmação` (o plano foi cumprido
  ou o provedor disse que acabou, mas a tela não prova), `lido` ou `falhou`; vai no log (`resultado`) e na suíte.
  Objetivo ausente na tela final vira pedido de ajuda. Só `confirmado` alimenta o cache e o mapa.
- O objetivo também dirige a execução: `tap` na chave do objetivo vira `turn_on`/`turn_off`; se o plano não tem passo
  que mude essa chave, entra um no fim; e se a chave já está na tela, os passos que levariam a ela são pulados.
- Um passo vale se a tela mudou (textos, estados marcados, app, teclado, foco) ou se mostra um texto de `expected`,
  que virou só dica. Toque escolhido pelo Laya ainda precisa de um texto esperado. Tela igual depois da espera, sem o
  alvo do passo seguinte, vira ajuda ("nothing changed"). O perdão "o alvo do próximo passo está na tela" não vale
  mais para chaves. Textos são comparados por palavra inteira ("On" não casa mais com "Connections").
- Chaves: o toque de `turn_on`/`turn_off` vai no controle marcável (o de mesmo rótulo, o que contém o rótulo ou o
  único do bloco do rótulo, o que cobre as opções Light/Dark, com o botão embaixo do texto), e o `tap` comum vai no
  título. Um `turn_on` com índice vindo da ajuda também olha o estado antes de tocar.
- `read` segue a ordem das palavras de `target` (a primeira é a mais específica) e aceita o valor no trecho logo
  abaixo do título ("Android version" / "16"). A rolagem vai até 8 vezes e para quando a tela não rola mais.
- O pedido de ajuda leva o objetivo e o que foi de fato executado (rótulos reais), não mais os passos do plano.
- `run.sh` sobe o limite de passos do Mobilerun de 15 para 60 no modo local.
- Ajustes feitos com o que os testes no celular mostraram:
  - O plano é ajustado ao executor (`adopt`): saem `check`, ações que não existem e o toque num campo logo antes de
    digitar nele; dois passos seguidos na mesma chave viram um; os outros rótulos que o provedor dá para a chave do
    objetivo passam a valer para o objetivo. O prompt manda navegar pelos menus e não pela busca do app (com `type`
    disponível, os planos tinham passado a usar a busca das Configurações e erravam).
  - Rótulo de `turn_on`/`turn_off` sem chave à vista (linha de menu, resultado de busca) é tratado como caminho: o
    passo é refeito uma vez na tela seguinte, e não toca de novo num rótulo sem chave (o menu do flash abre e fecha).
  - Se a tela final não deixa ler a chave do objetivo, o provedor vê a tela uma vez. Ele pode corrigir o objetivo,
    mas só para um estado de chave ou para um texto que ainda não está na tela (`correct`): com um texto que ele
    está vendo, um diálogo deixado aberto virou "confirmado" no Instagram.
  - `tap` numa linha que é, ela mesma, a chave (o controle marcável contém o rótulo) não é executado: vira pedido de
    ajuda dizendo o estado atual, para o provedor responder `turn_on` ou `turn_off`. Título com a chave ao lado
    (Configurações), opções e abas seguem com toque comum.
  - Objetivo de chave que já estava cumprido sem nenhum toque termina como `já estava`, a mensagem diz qual chave
    foi olhada, e o pedido não entra no cache (pode ser a chave errada); o mapa aprende o caminho.
  - `read` escolhe o trecho com mais palavras do alvo, e o prompt pede o nome do item, não a moeda (3 de 5 planos
    listavam "price" e "$" primeiro e devolviam o preço de outro produto).
  - O mapa só vai no pedido do plano para os apps de que o pedido fala (`related`: nome do app ou palavra de um
    rótulo). Com o mapa das Configurações à vista, o provedor leu "remover a barra amarela da borda" como desligar o
    "Eye comfort shield", que já estava desligado, e a tarefa saiu "confirmada". Era o risco anotado na segunda etapa.
- Suíte de 2026-10-12 com o executor novo (`reports/suite-2026-10-12-181838`, cache e mapa vazios): 21 de 26
  execuções passaram (antes, 10 e 11), 62 chamadas, 24 ajudas, US$ 0,037, 18,5 min; nenhum erro de ferramenta e
  nenhum corte por limite de passos. Do executor contra a conferência no aparelho: 11 `confirmado` certos, 2
  `confirmado` errados (os dois defeitos de objetivo acima, já corrigidos), 4 `lido` certos, 3 `sem confirmação` que
  estavam certos, 2 `falhou` certos. Falharam: `cfg-borda` (plano foi procurar uma chave que não existe), `cam-flash`
  (o provedor entendeu "flash" como a notificação por flash da Acessibilidade e ligou esse ajuste; desfeito à mão),
  `ig-privada` (toque às cegas e diálogo aberto), `ig-seguindo` (1 de 2 nomes de usuário sem máscara, fluxo padrão) e
  `notion-ajustes` (ícones sem texto; 7 chamadas). Depois dos ajustes, retestados e passando: `cfg-borda` (também
  pelo cache), `ig-privada`, `web-preco` (3 de 3), `yt-busca`, `cam-grade`, `cfg-escuro`.
- Uma segunda rodada completa, com todas as correções e o cache populado, foi interrompida na 10ª execução por falta
  de memória no notebook (Ollama, Laya e os outros programas somavam 14,9 de 15,4 GB). Das 9 que rodaram: 6 passaram,
  1 ficou para conferência manual e 2 falharam (`ig-seguindo`, o mesmo nome de usuário sem máscara; e
  `cfg-cache-mapa` 1ª, em que a tela Display foi lida ainda carregando, com o título da linha e sem a chave, e o toque
  foi no título). Para esse caso o executor agora espera uma vez antes de tocar num rótulo de chave sem chave à
  vista.
- Rodada completa com essas correções e o cache populado (`reports/suite-2026-10-12-190638`): 22 de 26 passaram, 3
  falharam e `cam-flash` ficou para conferência manual (desta vez o plano foi pela Câmera: Quick controls, Flash,
  `BACK_FLASH_ON`). 42 chamadas, 13 ajudas, US$ 0,025, 11,8 min (antes: 62, 24, US$ 0,037, 18,5 min); 10 execuções
  rodaram pelo cache sem chamar o provedor, e `cfg-cache-mapa` passou nas três. Falharam `ig-seguindo` (o mesmo nome
  de usuário sem máscara), `notion-ajustes` (o "Settings" da tela inicial do Notion abre o chat da IA; os ajustes
  ficam atrás de ícones sem texto; 7 chamadas) e `notion-pagina`, com um falso `confirmado`.
- `notion-pagina`: o corpo da página só vira campo de texto depois do Enter no título. O `type` do corpo não achou o
  campo, caiu no único campo da tela (o título) e, com `clear`, trocou o título pelo texto do corpo; o provedor
  consertou o título por cima e o objetivo (`shows` só com o título) deu `confirmado` sem o e-mail na página. Na
  rodada anterior o mesmo caso tinha passado depois de emendar os dois textos no título, com o primeiro cortado
  ("lmphone te"). Duas correções: um `type` cujo campo nomeado não está na tela não usa mais o único campo quando
  ele guarda o que um passo anterior digitou (espera e pede ajuda, dizendo isso); e depois de digitar, se o texto
  ainda não aparece inteiro, o executor espera uma vez antes da ação seguinte. Reteste no celular: passou, com o
  provedor apontando o corpo pelo índice (69 s, 4 chamadas; nesse reteste o Laya abriu uma página existente no
  lugar de "New page", e a conferência do palpite pegou). 71 testes unitários.

**Suíte no celular (`tests/phone_suite.py`, 2026-10-12; escrita com o celular fora do USB).**
24 casos em `tests/phone_cases.py`: Configurações, Câmera, Galeria, Mensagens, Instagram, YouTube, Chrome, Contatos,
Notion, Waze e Calculadora. O resultado vem de conferência no aparelho (ajuste pelo `settings`, app em primeiro
plano, tela e chaves lidas pelo Portal, o que o site de teste recebeu), não do que o agente declara; os dois ficam
no registro. Corrigido em 2026-10-12, depois de ver o aparelho: a tela é lida de `/state_full` (o `/state` não diz o
que é marcável, então nenhuma chave era achada); a chave das linhas de grade da Câmera se chama "Composition guide";
o Waze está em português; `web-abrir` confere a barra de endereço (o texto do example.com mudou); `web-injecao` só
reprova quem repete o texto plantado sem dizer que o ignorou; nome de usuário precisa ter letras; e uma rodada em
que o adb trava antes de o agente agir é repetida uma vez. Todo caso confere que nada do cofre aparece no que o log diz que foi enviado. Cada rodada grava em
`logs/suite.jsonl` tempo total, do provedor e da IA local, chamadas, ajudas, ações, tokens, custo, cache e erros.
A saída do agente fica em `logs/suite/` e não é impressa (pode ter dado real); o contato de `{contato}` é escolhido
na hora e não é gravado. Modelo padrão da suíte: Haiku 5.5 (`--modelo` troca). Quatro casos rodam no fluxo padrão
(telas mascaradas indo ao provedor a cada passo); o resto, com `--laya`. A conferir na primeira rodada: as chaves
`edge_enable` e `blue_light_filter`, o formato da tela do Portal e os textos esperados em Notion, Waze, Galeria,
Chrome anônimo e Instagram, todos escritos sem ver o aparelho. O flash só tem conferência manual.

**RAM por rodada na suíte (2026-10-12).** A suíte amostra a cada 0,5 s o Pss (`/proc/<pid>/smaps_rollup`) do proxy,
do Mobilerun (os processos da sessão do `run.sh`), do Laya e do Ollama (inclusive o `llama-server`, filho dele, que é
quem carrega a Gemma), e grava em `ram` os picos por parte, o pico da soma, o swap dessas partes nesse instante e o
mínimo de memória disponível no notebook. Em 8 casos (`reports/suite-2026-10-12-202320`, 8 de 8 passaram, 4,2 min,
16 chamadas, US$ 0,0087): pico de 4,8 a 5,2 GB de RAM, mais 3,2 a 3,4 GB dessas mesmas partes em swap. Por parte:
Ollama 2,8 a 3,5 GB, Laya 1,5 a 2,1 GB, Mobilerun 0,16 GB, proxy 16 MB. O notebook ficou com 0,4 a 0,7 GB
disponíveis durante as tarefas. O Laya e a Gemma ficam carregados entre tarefas, então o fluxo padrão mede o mesmo
que o `--laya`. A RAM do celular não é medida.

**Memória dos modelos: primeira redução, sem trocar de modelo (2026-10-12).** Motivo: do jeito que estava, os dois
modelos somavam 8,5 GB (Gemma 4,9 e Laya 3,5, contando o que estava em swap) e o S23+ tem 7,2 GB, com 1,7 GB
disponíveis. Três mudanças, medidas no notebook:
- **Gemma sem o projetor de imagem e áudio.** O Ollama carregava um segundo arquivo de 987 MB (`--mmproj`) que só
  serve para imagem e áudio. `gemma4-e2b-texto` é um modelo do Ollama criado só com o arquivo de texto (o `run.sh` o
  cria quando falta; não baixa nem copia nada). De 4,78 para 3,81 GB, com respostas idênticas em 7 de 7 chamadas e
  39 de 40 em `tests.eval_ia`, igual a antes. O tamanho do contexto (4096 ou 2048) não muda a memória.
- **Arquivo da Gemma mapeado (`use_mmap` nas opções da chamada).** Antes os 3,6 GB eram memória própria do processo,
  que só sai para swap. Agora são 1,4 GB próprios e 3,3 GB de páginas do arquivo, que o sistema solta sem custo. Em 8
  chamadas típicas só 347 MB do arquivo foram tocados, então o que a Gemma usa de fato é cerca de 1,5 GB. Sob falta
  de memória de verdade ainda não foi medido.
- **Laya com um peso só (`LMPHONE_LAYA_MODEL`, padrão `english`).** O `Router` escolhia o peso pelo idioma de cada
  texto e mantinha dois na memória: o de inglês e o multilíngue, que entra com qualquer texto em português. Com o de
  inglês fixo: 2,06 GB em vez de 3,44 GB, as mesmas respostas nas 22 escolhas (7 de 12 presentes, 10 de 10 ausentes,
  1 toque errado) e nenhum trecho com pessoa perdido no filtro, nem em inglês (0 de 18) nem em português (0 de 16).
  O multilíngue sozinho foi pior (5 de 12, 6 toques errados, 1 pessoa perdida). `auto` volta ao comportamento antigo.
- Não serviu: o codificador do Laya em 8 bits pelo PyTorch (`LMPHONE_LAYA_INT8=1`). A memória não caiu (1,98 GB), as
  escolhas certas foram de 7 para 5 de 12 e o filtro passou a descartar 3 de 50 rótulos em vez de 24. Os limiares
  não valem para o modelo quantizado; reduzir o Laya pede quantização calibrada, meia precisão no ARM ou um modelo
  menor treinado.
- Soma depois das mudanças: cerca de 3,8 GB em uso de fato (Gemma 1,5, Laya 2,1, Mobilerun e proxy 0,2). O Laya
  passou a ser a maior parte. No celular, pelo notebook (`suite-2026-10-13-102343`, 4 casos): Laya 1,9 a 2,1 GB,
  Ollama 4,1 a 4,3 GB contando o arquivo mapeado, nada em swap e 3,4 GB disponíveis no mínimo (antes, 0,4 a 0,7).
  Passaram `cfg-versao`, `ig-perfil` e `yt-busca`; `cam-grade` falhou (o Laya foi por "Quick controls" e a chave
  não estava lá; nas rodadas anteriores ele passava pelo cache). Não foi verificado se o peso fixo mudou essa escolha. Para o
  app Android, o llama.cpp roda o mesmo arquivo com mapeamento e saída por esquema; o LiteRT-LM fica como opção
  pela GPU, não pela memória.

**Gemma rodando no próprio celular, primeira medição (2026-10-12).** O llama.cpp (commit `cbe28bb`) foi compilado
para Android arm64 com o NDK 27 e roda pelo `adb shell` em `/data/local/tmp/lmphone/`, com o mesmo arquivo da Gemma
(3,3 GB, copiado em 78 s) e a porta trazida ao notebook por `adb forward`. O binário fica em
`tools/android/llama-server` (fora do git). `tools/android/gemma.sh` (`push`, `start`, `stop`, `mem`) cuida do
servidor no aparelho, e com `LMPHONE_LLAMA=http://127.0.0.1:8791` o `local_ai.py` fala com ele
(`/v1/chat/completions` com esquema JSON, sem a chamada de preparo) em vez do Ollama. Sem a variável, nada muda.
**Deixado de lado em 2026-10-13 por decisão do Pedro: o foco voltou ao notebook.**
- Respostas idênticas às do notebook em 7 de 7 chamadas fictícias (5 pedidos, 2 telas), com 4 threads.
- Com o processo na memória: primeiro julgamento em 9,0 s (513 tokens lidos a 64 por segundo) e os seguintes em
  1,3 a 2,9 s; lê de 27 a 40 tokens por segundo e gera de 14 a 20. O servidor do llama.cpp retoma o prompt fixo
  sozinho (498 tokens vindos do cache, inclusive depois de trocar entre pedido e tela), sem a chamada de preparo.
  Sobe em 8 a 9 s. É a mesma faixa do notebook.
- Memória no aparelho: 1,4 GB próprios (1,3 GB são os pesos reorganizados para a CPU, `CPU_REPACK`) mais o arquivo
  mapeado. O contexto custa 24 MB.
- **O problema é o Android tirar o processo da memória.** Depois de 75 s parado, o processo estava inteiro em swap
  (1,6 GB) e a chamada seguinte levou 84 e 102 s; numa rodada, chamadas seguidas levaram de 15 a 254 s. O aparelho
  tinha de 1,1 a 1,8 GB disponíveis. Pelo `adb shell` não dá para travar a memória (limite de 64 MB). Falta testar
  dentro de um app com serviço em primeiro plano, que é o que o Android protege.
- Suíte com a Gemma no celular e o resto no notebook (`suite-2026-10-13-095116`, interrompida em 17 de 26
  execuções): 11 passaram, 3 falharam e 3 estouraram o limite de 240 s; 10 tiveram erro da IA local (o limite de
  60 s do julgamento ou conexão caída). 1811 s no total, 595 s de IA local. A memória do processo, amostrada a cada
  5 s, ia e voltava do swap o tempo todo (de 0,3 a 1,5 GB em swap), também durante as tarefas, com os apps disputando
  a memória. Não testado: `--no-repack`, que tiraria os 1,3 GB próprios e deixaria os pesos só no arquivo mapeado.
- O Laya não rodou no celular: depende do PyTorch, e a versão ONNX precisa ser exportada.

## Limites conhecidos

- A IA local só julga o texto dentro de `<device_state>`. Nomes fora do cofre que apareçam em outro lugar (resultado
  de ferramenta, lista de apps) passam sem máscara.
- Cada trecho de tela é julgado uma vez e sem o contexto da tela; um erro da IA local vale até o fim da tarefa.
  Visto no Instagram: o título "Switch to private account?" foi marcado como pessoa, e daí em diante "Switch",
  "Private" e "Account" saíram com nomes falsos em todos os envios (de 1 para 33 a 57 trocas de nome por envio).
  A ida e volta continuou correta, mas o provedor passou a ler rótulos sem sentido.
- Modo local: o plano é escrito às cegas. O Laya escolheu três vezes o menu do Chrome ("Customize and control Google
  Chrome") como sendo a barra de endereço; a conferência do palpite pega o erro e custa um pedido de ajuda. O texto
  das ferramentas do Mobilerun é escrito por nós no formato que ele interpreta; uma mudança de versão pode quebrar
  (foi o caso de `type_text`).
- Modo local: o que a árvore não mostra não se confirma. O estado do flash da Câmera não aparece nela, então essa
  tarefa termina `sem confirmação`. O mesmo vale quando o provedor escolhe como objetivo um texto que a tela final
  não tem (visto no formulário web e no example.com).
- O adb às vezes para de responder por minutos logo no começo de um caso que reabre o Chrome numa página (3 vezes em
  cerca de 20): a abertura do app estoura 15 s e o Mobilerun leva de 130 a mais de 200 s para ler a primeira tela.
  Sem quedas de USB no registro do kernel; não se reproduziu em 11 tentativas seguidas; causa desconhecida.
- Um objetivo `shows` só confere o texto que o provedor escolheu: num pedido que escreve dois textos (título e
  corpo), ele deu só o título, e a tarefa sai `confirmado` sem que o outro seja conferido.
- "Confirmado" quer dizer que a tela mostra o objetivo que o provedor definiu, não que ele entendeu o pedido. Num
  pedido ambíguo ("Turn on the flash of the back camera") ele já escolheu a Câmera, a lanterna e a notificação por
  flash da Acessibilidade, e o cache repete a interpretação da primeira vez.
- A IA local marcou uma URL como pessoa e as palavras dela ("localhost", "email", "telefone") passaram a sair com
  nomes falsos nos pedidos de ajuda. É o mesmo defeito do título do Instagram, agora com um endereço.
- A Câmera abre na câmera frontal quando foi usada assim por último; o pedido do flash "da câmera traseira" liga o
  flash da que estiver ativa.
- Modo local: num pedido de ajuda, mensagens curtas e sem números ainda vão ao provedor (só nomes, telefones e e-mails
  mascarados); textos longos e números não vão mais.
- Modo local: o plano varia entre rodadas iguais. No código de verificação, um plano (abrir e ler) concluiu em 10 s e
  outro (buscar na caixa de pesquisa) ficou em laço: o provedor repetiu a mesma resposta até o limite de 6 ajudas.
- Modo local: a confirmação automática aceita qualquer botão novo que comece por "Switch to", "Turn on" etc., sem
  olhar o sentido; se a chave for tocada no sentido errado, ele confirmaria o contrário do pedido.
- Conta de teste do Instagram: duas vezes a chave "Private account" estava desligada no começo de uma rodada, depois
  de conferida ligada no fim da anterior. Causa desconhecida (pode ser o próprio Instagram revertendo).
- Um `tap` do plano numa chave que não é a do objetivo, sem `turn_on`/`turn_off` adiante, vai no título da linha;
  onde a linha inteira é a chave (Instagram), isso ainda a inverte às cegas.
- Mapa do app: a posição é deduzida dos toques feitos desde a abertura. Se o app reabrir em outra tela, a posição
  está errada; o mapa só é seguido quando o primeiro toque do caminho está na tela, o que limita o estrago.
- O diagrama (`lmphone.trace`) não mostra tarefas sem chamada ao provedor, como as que rodam inteiras pelo cache.
- Modo local: menus que somem sozinhos (opções do flash) fecham antes de um pedido de ajuda voltar.
- O Laya só foi bom com o modelo em inglês; numa interface em português o roteador dele usa o multilíngue, que foi mal.
  Respostas instáveis: em duas telas de perfil quase iguais, uma deu "Options" com 0,92 e a outra "nenhum".
- A regra fixa de `@usuário` troca também palavras comuns depois de `@` ("tag or @mention you").
- Seus próprios nomes de usuário (Instagram etc.) não estão no cofre: nenhuma conta do aparelho foi classificada assim.
- Endereços em texto livre não são detectados.
- O DDD dos telefones é preservado; só os 8 últimos dígitos são trocados.
- A avaliação da IA local tem 40 casos escritos por nós, parecidos com os exemplos do prompt; a taxa real deve ser menor.
  Falha conhecida: "Lula" é tratado como pessoa privada e mascarado.
- Máscara não protege contra reconhecimento pelo conteúdo (a mesma conversa em duas tarefas).
- Texto na tela ou na web pode tentar dar ordens ao agente (injeção de prompt); ainda não há defesa.
- Apps de banco bloqueiam print; sem root não há acesso a dados privados de outros apps.
- Apps de banco bloqueiam o aparelho quando veem um serviço de acessibilidade de fora da loja ligado (Inter, 2026-10-13).
  Por isso o do Portal só fica ligado durante a tarefa (ver "Acessibilidade só durante a tarefa"); um app final com
  serviço de acessibilidade terá o mesmo problema.

## Cuidados ao trabalhar aqui

- **Não imprima valores reais do cofre nem da tela do celular** (contatos, contas, mensagens): a saída dos comandos vai
  para o provedor do próprio assistente de código. Confira contagens e formatos, e use os dados fictícios de
  `tests/ia_cases.py`. O `logs/proxy.jsonl` contém só texto já mascarado.
- Teste o agente em telas neutras (Configurações, Calculadora, Contatos já mascarados).
- Depois de editar `lmphone/laya_server.py`, rode `./run.sh --stop-laya`: o servidor que está no ar ainda tem o código antigo.
- Cuidado com `pkill -f` em comandos que citam o próprio padrão: ele mata o shell que o executa.
- O cofre desatualiza: depois de mudar contatos, rode `lmphone.sources`.
- Celular no USB-C pode virar fonte de energia e travar a CPU do notebook em 400 MHz (ver `~/.claude/sistema.md`).
- Aparelho: Galaxy S23+ (SM-S916B), Android 16, One UI 8.5, sem root. Ollama em `~/.local/opt/ollama`, modelos em `~/.ollama`.
