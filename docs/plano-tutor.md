# O easy_phone como assistente técnico

Decisão do Pedro (2026-11-16): o easy_phone é um **assistente técnico para quem tem dificuldade com o celular**, como
idosos. O foco é o tutorial, a explicação e o conserto ("como eu faço", "a letra tá pequena", "sumiu o ícone"), e esse
fluxo tem de estar redondo. Fazer tarefas do dia a dia pela pessoa (mandar mensagem, ligar, rota no Waze) continua
existindo, como foco secundário. A regra de privacidade não muda: nada pessoal vai ao provedor sem máscara.

## Diagnóstico (2026-11-16)

O sistema foi construído e medido como executor de tarefas para um usuário experiente. O guia existe, mas é uma
variação da execução ("faço explicando"), não o centro.

1. **O guia não é medido.** Nenhum dos 40 casos da suíte é de guia.
2. **No guia, o agente faz.** A pessoa tem 5 s (`executor.GUIDE_LIMIT`) e ouve "ou eu toco daqui a pouco". A contagem
   apressa, e quem aprende fazendo é a pessoa.
3. **Errar não tem caminho próprio.** Um toque fora do destacado cai na ajuda genérica; falta o "esse não, vamos
   voltar".
4. **A explicação diz o rótulo, não onde ele está.** O aparelho tem os limites de cada controle e pode dizer "no alto,
   à direita" sem nada sair dele.
5. **Gestos não são ensinados.** Rolar, puxar o painel do alto, toque longo e o teclado: o destaque é só uma moldura.
6. **Falta ritmo e revisão:** repetir, mais devagar, voltar um passo, resumo do caminho no fim, rever um tutorial já
   feito (o cache de caminhos guarda só rótulos de interface).
7. **Assistência técnica quase não existe.** O `facts.py` lê Wi-Fi, modo avião, Bluetooth, Não perturbe, localização,
   modo escuro e o que toca. Faltam volumes, tamanho da fonte, TalkBack, economia de bateria, armazenamento, modo
   silencioso: o que explica "sem som", "letra pequena", "falando sozinho", "não tira foto".
8. **A interface é de usuário avançado:** controles de 22 dp, gestos escondidos na alça, desfoque que tira contraste,
   painel que fecha 7 s depois da resposta, chamada pela tecla lateral ou por "Alexa" (que disputa com um Echo).
9. **O celular de teste estava em inglês**, a suíte é em inglês e os modelos pequenos foram treinados com telas em
   inglês da One UI 8.5.
10. **Depende do PC.** Para entregar a alguém, o cérebro tem de rodar no celular.
11. **Golpes.** Esse público é o alvo principal; instalar app de acesso remoto, dar permissões, ligar a acessibilidade
    de outro app e ler um código de verificação durante uma ligação não pedem confirmação hoje.

## Decisões

- **Quem toca no guia:** a pessoa, por padrão; o agente aponta, explica e espera, sem contagem. Uma opção nas
  configurações do app troca o padrão para o agente fazer explicando (o comportamento de hoje). Na hora, "faz pra mim"
  e "deixa que eu faço" continuam valendo.
- **Modo simples como padrão da interface:** letra grande, fundo sólido, poucos botões grandes com texto, nenhum gesto
  obrigatório, resposta na tela até a pessoa fechar. A interface atual vira opção avançada.
- **O celular de teste fica em português** (já está em pt-BR desde 2026-11-16). As medições antigas, o cache, o mapa e
  os modelos pequenos são de telas em inglês: espera-se queda até medir e treinar de novo.

## Fases

### 0. Intuito e pendências (2026-11-16, feita)

- O intuito no `CLAUDE.md` e neste plano.
- Os prompts do provedor (`PLAN_PROMPT`, `HELP_PROMPT`, `GUIDE_HELP`): ele é o assistente e ajudante técnico paciente
  de quem acha o celular difícil; ensinar e consertar vêm primeiro, fazer pela pessoa depois; frases curtas, sem termos
  técnicos, apontando ícones pela forma; sintoma descrito vira causa achada pelo estado e pela tela, consertada e
  explicada; no guia, nenhum passo é pulado e a mensagem final termina com o caminho em poucas palavras. O
  `cerebro.json` foi exportado e a conferência do Kotlin deu igual (245 de 245 chamadas, 167 de 167 funções).
- Conferido no celular: a acessibilidade estava desligada; `set` de Bluetooth, Não perturbe e localização muda e volta
  certo. O `set` do Wi-Fi desliga e liga, mas **ao religar o celular não voltou sozinho a nenhuma rede salva** (2 min,
  com varredura): o objetivo `{"wifi": "on"}` daria "confirmado" sem rede. A corrigir: depois de ligar, esperar a
  conexão e, sem ela, ir pelas telas.
- Ficam para quando o Pedro estiver com o celular: a confirmação pela faixa (sim e não, por voz e toque), a depuração
  sem fio, o live mode contínuo. `dia-waze-rota` e `cam-flash` ficam para a suíte em português (fase 1).

### 1. Medir o foco

- Suíte em português, com o celular em pt-BR, revisando as conferências que esperam rótulos em inglês.
- Casos de guia ("como eu aumento a letra", "como ligo a lanterna", "como mando uma foto no WhatsApp", "como bloqueio
  um número", "como apago as fotos repetidas", "como faço uma chamada de vídeo"), conferidos por critério: cada passo
  explicado, destaque presente, onde tocar dito em palavras, para antes do irreversível, se recupera de um toque errado
  (um script fazendo o papel da pessoa, como no teste da vez do dono).
- Casos de sintoma ("a letra tá pequena", "o celular tá sem som", "o celular tá falando sozinho", "sumiu o ícone do
  WhatsApp"), com o aparelho preparado no estado do defeito e desfeito depois.
- Pedidos ditos como esse público diz: vagos, longos, com hesitação.
- Coleta (`LMPHONE_COLETA=1`) nas telas em português para o treino dos modelos pequenos.

**Andamento (2026-11-16).**

- A suíte tem 54 casos: os 40 de antes, com os pedidos em português informal e os rótulos em pt-BR nas conferências
  que leem a tela, e 14 novos, nos níveis `guia` (8) e `sintoma` (6), da categoria `ajuda`. Os casos novos conferem
  pelo estado do aparelho (tamanho da fonte, brilho, rotação, tempo de tela, volumes, lanterna, Não perturbe), não por
  rótulos.
- `tests/pessoa.py` faz o papel da pessoa nos casos de guia: lê o registro do live mode e toca no destaque quando é a
  vez dela ("toca"), aperta Voltar no primeiro passo ("erra") ou não toca ("olha"). O destaque passou a dizer quando é
  para a pessoa (`"dono": true` no registro, `destaque_dono` para o app).
- Critérios do guia, lidos do registro (`phone_suite.guide_checks`): cada ação explicada, a pessoa tocou e o agente
  não, o toque dela não pausou a tarefa, as falas dizem onde fica o controle, falas curtas e sem termos em inglês, a
  resposta final resume o caminho.
- **Defeito achado e corrigido:** desde 2026-11-10 um toque fora da faixa pausa a tarefa e passa a vez ao dono,
  inclusive quando é o toque que o guia está esperando. Conferido no celular: o toque no destaque pausava ("Pausado —
  toque em continuar") e o guia parava no primeiro passo; a vez do dono também. Agora o toque não pausa com um destaque
  para o dono (`Live.ownerTarget`) nem na vez dele (`Overlay.outsideTouch`); com o destaque do agente, continua
  pausando. APK instalado e conferido.
- Linha de base do guia e dos sintomas (2026-11-16, `reports/suite-2026-11-16-100445` e `-102817`, pelo app, Haiku
  5.5, US$ 0,05 nas duas): **nenhum guia passa em todos os critérios.** O objetivo foi alcançado em 3 de 8 (letra,
  girar a tela, tempo de tela); o Não perturbe pede conferência manual. Sintomas: 4 de 6 consertados (letra, avisos,
  girar, tempo de tela).

  | Caso | Objetivo | O que falhou |
  |---|---|---|
  | guia-letra | sim | só 1 de 5 falas diz onde fica o controle; 2 falas longas |
  | guia-letra-erro | não | depois do Voltar, uma mudança de tela (animação) contou como passo da pessoa; o toque dela chegou com o destaque já tirado e pausou a tarefa (2 pausas) |
  | guia-lanterna | não | o painel rápido não mostra «Lanterna» na árvore; o agente rolou à toa e terminou perguntando |
  | guia-girar | sim | o agente também tocou; uma fala longa |
  | guia-brilho | não | "tela mais clarinha" virou desligar o modo escuro; o caminho do guia mandou tocar em «Escuro» para desligar; o brilho é uma barra e o guia não ensina arrastar |
  | guia-toque | não | volume é uma barra: terminou com "arraste a bolinha" e deu por feito |
  | guia-tela-apaga | sim | 3 de 8 ações sem explicação (as rolagens); 3 falas longas |
  | guia-nao-perturbe | manual | o agente também tocou; falas longas |
  | sint-mudo | não | explicou como subir o volume, sem subir: o agente não tem como mudar volume |
  | sint-escura | não | chegou na tela de brilho e disse que não consegue mexer na barra |

  Em comum: falas longas (muitas com mais de 35 palavras), quase nunca dizem onde fica o controle, a explicação é
  repetida depois do toque da pessoa, o agente diz "aumentei" quando quem tocou foi ela, e um destaque caiu num
  controle cortado na borda de baixo da tela. Nenhuma fala teve termo em inglês.
- Defeitos da medição achados e corrigidos na mesma manhã: a lanterna era lida ao contrário (o registro da câmera vem
  do mais novo para o mais velho); a tela apagava no meio (o cabo aparece como carregador de tomada, e o
  `svc power stayon usb` não valia: agora `true`); um caso que encontra o celular bloqueado para com aviso.

- Casos antigos em português (2026-11-16, `reports/suite-2026-11-16-103907`, sem os 4 do Instagram, a pedido do
  Pedro): 32 de 41 rodadas, 14,8 min, US$ 0,065. Repetidas depois das correções (`-105824`, `-110708`), passaram
  `cfg-cache-mapa`, `web-formulario`, `conv-ele`, `dia-x-perfil` e `dia-farmacia`. Ficam: `cfg-borda` ("tira essa
  barrinha amarela": o agente não liga a barra aos «Painéis Edge» e pergunta), `dia-wifi` (não conectou na ALAMEDA e
  deixou o celular sem rede: falta voltar à rede de antes quando falha) e `cam-flash` (erro 500 do provedor; manual).
  Correções feitas: o cache e o mapa eram das telas em inglês (guardados em `arquivo/cache-ingles-2026-11-16/` e
  zerados); a conferência de privacidade contava os nomes falsos da sessão como dado do cofre (as regras de
  2026-11-12 os reconhecem como nomes: não houve vazamento); o formulário virou conversa (o envio espera o "sim");
  a suíte repete a rodada quando o serviço ainda está na tarefa anterior.
- Rótulos da One UI 9 em pt-BR que importam: a página Tela é «Visor»; «Proteção para conforto ocular», «Tamanho e
  estilo da fonte», «Duração da luz de fundo», «Painéis Edge», «Claro» e «Escuro». Há um **«Modo Fácil»** (letras e
  ícones maiores), que interessa ao público do app.
- Coleta com telas em português nas rodadas de hoje: o total passou de 561 para 615 tarefas. Os arquivos da coleta e
  dos registros vieram do Pop com modo 666; voltaram a 600 (pastas 700).

**Fase 1 concluída em 2026-11-16.**

### 2. O guia redondo

O que a linha de base pede, além da lista abaixo: só contar um passo da pessoa quando houve toque dela (não qualquer
mudança de tela); não repetir a explicação depois do toque; não dizer "fiz" pelo que ela fez; ações diretas para o
volume e o brilho (`set` com valor, pelo sistema), e no guia ensinar o arraste da barra; "clara/escura" numa queixa
de não enxergar é brilho; o caminho do guia para o modo escuro escolhe a opção certa (Claro ou Escuro), não
"desliga" o Escuro tocando nele; o painel rápido da One UI 9 em português (onde está a Lanterna); rolar para mostrar
o controle inteiro antes de destacar.


- "Você faz, eu aponto" como padrão, sem contagem; lembrete gentil depois de uns 20 s, com "quer que eu faça?". A opção
  nas configurações do app.
- Toque errado: o provedor vê a tela nova e explica com calma o que abriu e como voltar, e o guia volta ao passo.
- Onde tocar: o aparelho transforma os limites do controle em palavras ("no alto, à direita", "embaixo, no meio") e as
  junta à explicação, sem mandar nada ao provedor.
- Gestos: animação do gesto sobre a tela (seta, mão) e explicação própria para rolar, puxar o painel, toque longo e o
  teclado.
- Comandos falados: "repete", "mais devagar", "volta um passo", "não entendi". Fala mais lenta no guia.
- Tarefa pedida pelo Pedro (2026-11-16): a faixa sabe onde ficar. Em vários casos o destaque (o sinalizador de toque)
  fica embaixo da faixa, e a pessoa não vê onde tocar (e o toque dela cairia na faixa). Antes de mostrar um destaque,
  a faixa (ou o círculo) sai de cima dele: vai para o outro lado da tela (alto ou embaixo) e volta à posição guardada
  pelo dono quando o destaque some. O mesmo vale para os controles que o agente vai tocar.
- Resumo do caminho no fim e tutoriais lembrados: "como era mesmo pra...?" refaz o guia pelo cache, sem o provedor.

**Andamento (2026-11-16, commit 7cf3ea6), falta conferir no celular** (saiu do adb antes da instalação): a pessoa
toca por padrão, sem contagem, com lembrete aos 20 s e a opção "Ensinar" no app; passo só com toque dela
(`toque_tela`); sem repetir a explicação; onde fica o controle em palavras; a tela sobe para o controle cortado; barra
destacada na parte da direita; volume e brilho por `set` com nível; "tela escura" é brilho; modo escuro desligado pelo
"Claro"; "repete", "mais devagar", "mais rápido"; as três tarefas do Pedro na faixa. Falta: instalar o APK, rodar
`--nivel guia` e `--nivel sintoma`, recuperação do toque errado pelo provedor, gestos animados, Lanterna no painel
rápido e tutoriais lembrados.

### 3. Assistência técnica e proteção

- `facts.py` com volumes, tamanho da fonte, TalkBack, economia de bateria, armazenamento livre e modo silencioso.
- Diagnóstico: o provedor levanta a causa pelo estado, confere pela tela, explica e conserta ou guia.
- Confirmação com aviso para instalar apps, conceder permissões, ligar a acessibilidade de outro app, fontes
  desconhecidas e redefinir o aparelho; nunca ler nem repassar um código de verificação durante uma ligação.
- Mais adiante: "isso é golpe?", com um classificador local ou com o envio daquela mensagem, mascarada, só com o sim da
  pessoa.

### 4. Interface do modo simples

- Letra que segue a escala de fonte do sistema, alvos de 48 dp ou mais, fundo sólido de alto contraste, no máximo três
  botões com texto ("Falar", "Repetir", "Parar"), resposta que fica até ser fechada.
- Um jeito fácil de chamar: botão "Ajuda" na tela inicial (widget) e, depois, uma palavra de ativação em português.
- Tarefa pedida pelo Pedro (2026-11-16): com a faixa minimizada (o círculo), um toque da pessoa na tela faz a faixa
  voltar à forma padrão (aberta), para ela ver o que o agente diz.
- Tarefa pedida pelo Pedro (2026-11-16): enquanto o agente roda uma tarefa (e enquanto o guia espera a pessoa), a tela
  não apaga por inatividade. Visto na suíte: os gestos do agente pela acessibilidade não contam como uso, e com o tempo
  de tela em 15 s o celular bloqueou no meio do guia. Caminho provável: `FLAG_KEEP_SCREEN_ON` na janela da faixa (ou
  do círculo) durante a tarefa, tirado no fim.

### 5. Sem o PC

- A suíte do tutor com o cérebro no celular (`--cerebro celular`); os ajustes pelas telas na One UI 9 em português.

### 6. Dia a dia

- Parentescos e apelidos no cofre local ("filha" é um contato): "liga pra minha filha" sem o nome sair do aparelho.
- Ligação, mensagem e áudio no WhatsApp, rota no Waze, com a confirmação antes de enviar ou ligar.
