# Mascaramento

Como o easy_phone impede que dado pessoal saia do aparelho sem máscara. A regra do projeto: o provedor (a IA na nuvem)
planeja vendo só valores falsos; a IA local e o código trocam os reais pelos falsos na ida e os falsos pelos reais na
volta. Os motivos e as medições de cada decisão estão em `docs/historico.md`; este arquivo descreve o funcionamento.

O código é `lmphone/masking.py` (as trocas), `lmphone/local_ai.py` (o julgamento da IA local), `lmphone/proxy.py` (onde
tudo é aplicado) e `executor.redact` (a tela reduzida). No celular, a tradução em Kotlin fica em
`android/cerebro/.../Masking.kt` e `LocalAi.kt`, conferida contra o Python por `tools.app.cerebro mascara` e
`android/gradlew :cerebro:conferir`.

## Visão geral

```
pedido ──► regra fixa de senha ──► IA local julga o pedido ──► (judged) ──┐
                                                                          ▼
tela ──► redact (textos longos e números somem) ──► IA local julga os trechos novos
                                                                          │
                       Masker.mask: cofre + sessão + regras fixas, uma passada
                                                                          │
                                                        provedor (só valores falsos)
                                                                          │
                       Masker.unmask: falsos voltam a reais ◄─────────────┘
                                                                          │
                              plano executado no aparelho com os valores reais
```

Tudo o que vai ao provedor passa por `proxy.ask_provider`, o único lugar que tem a chave. Ele espera o julgamento do
pedido (`judged`), julga os trechos de tela ainda não vistos, mascara cada parte da mensagem e só então envia. Se o
mascaramento levanta erro, nada é enviado. A resposta volta por `masker.unmask` antes de chegar ao executor, então o
plano já tem os nomes, telefones e textos reais para tocar e digitar.

## As três peças de `masking.py`

### `Vault`: o que proteger

O cofre (`data/vault.json`, modo 600, fora do git) guarda **só valores reais**, por tipo:

| Tipo | O que é | Como entra |
|---|---|---|
| `name` | cada palavra de um nome (3 letras ou mais, em minúsculas, fora da `STOPLIST`) | contatos, perfil do dono, contas com espaço no nome |
| `email` | e-mails, em minúsculas | contas do aparelho, e-mails dos contatos |
| `literal` | valores inteiros, como nomes de usuário (4 caracteres ou mais) | contas sem espaço que não são o nome do app |
| `phone` | os últimos 8 dígitos de cada número | telefones dos contatos, contas que são números |

Quem preenche é `lmphone/sources.py` (`python -m lmphone.sources`), que lê pelo adb as contas (`dumpsys account`), o
perfil e os contatos. As palavras dos nomes dos apps instalados entram como stoplist nessa importação, para um contato
chamado como um app não mascarar o app. O cofre desatualiza: depois de mudar contatos, rode `lmphone.sources` de novo.

### `Session`: os pares real ↔ falso

Cada tarefa (ou conversa, enquanto viva: até 10 min parada) tem uma `Session` em memória. Ela guarda:

- `forward` e `reverse`: real → falso e falso → real, por tipo (os quatro do cofre mais `digits`, para CPF, CNPJ, CEP
  e cartão, `handle`, para `@usuários`, e `code`, para placa, RG, CNH e conta);
- `extra_names`: nomes fora do cofre que a IA local ou as regras de nome mandaram mascarar (valem em qualquer caixa);
- `cap_names`: nomes que só valem capitalizados, porque também são palavra comum ("Rosa", "Costa");
- `words`: as palavras dos textos já mascarados, para um falso novo nunca ser igual a uma delas;
- `extra_literals`: nomes de usuário e senhas vistos no pedido ou na tela;
- `released`: palavras do cofre que esta tarefa precisa mandar reais (pesquisa sobre um negócio);
- `seen`: trechos de tela que a IA local já julgou.

Os falsos são sorteados na primeira vez que um real aparece (`Session.get`) e nunca saem da memória:

| Tipo | Falso |
|---|---|
| nome | prefixo + sufixo de `_PREFIXES`/`_SUFFIXES` ("Marino", "Helilda"), na caixa do original; sem acento, e nunca um nome das listas de `nomes.py` nem uma palavra já vista num texto |
| e-mail | `contato123456@exemplo.com` |
| literal | `usuario123456` |
| `@usuário` | `@usuario123456` |
| telefone, CPF, CNPJ, CEP, cartão | mesma quantidade de dígitos, sorteados; a pontuação e o DDD ficam |
| placa, RG, CNH, conta | a mesma forma: letra por letra, dígito por dígito |

O falso nunca coincide com outro falso da sessão nem com um real do cofre. Os falsos de nome não têm acento (o provedor
devolvia "Rosalia" ou `Ros\u00e1lia` e o falso não voltava ao real) e não podem ser uma palavra que já apareceu num
texto: um "Alberto" de verdade na tela, com "Alberto" sendo o falso de outra pessoa, voltava como essa pessoa. Se a
palavra aparece depois de o falso já existir, ela ganha um falso próprio (`Masker.learn`). Um literal escrito com
maiúsculas (uma senha "Kz81!x") tem o par pelo texto exato, para voltar igual. Como a sessão dura a conversa, "ela" no
pedido seguinte é o mesmo nome falso de antes, e o provedor consegue seguir o assunto.

### `Masker`: trocar e desfazer

`Masker.mask` monta uma única expressão regular com todas as alternativas e aplica as trocas **numa só passada**, para
nunca mascarar de novo um trecho já trocado. A ordem das alternativas é a prioridade:

1. e-mail (`EMAIL`)
2. `@usuário` (`HANDLE`)
3. cartão (4 grupos de 4 dígitos, ou 16 dígitos seguidos com o dígito de Luhn certo)
4. CNPJ e CPF pontuados, CEP (`00000-000`)
5. placa Mercosul, e placa antiga, RG, CNH, conta e CEP sem hífen depois do rótulo (`LABELED`, com 5 dígitos ou mais)
6. literais do cofre e da sessão (sem diferença de caixa; os só de números não casam dentro das coordenadas de um
   elemento da tela)
7. telefone (com DDD, com ou sem +55, ou `99999-9999`)
8. CPF e CNPJ sem pontuação, só com os dígitos verificadores certos
9. nomes do cofre e da sessão, menos os liberados (a borda é a letra: `livia_bastos` tem o nome dentro)

Antes da troca, `Masker.learn` lê o texto e aprende os nomes que a forma dele denuncia (ver as regras fixas abaixo).
As instruções fixas do executor passam sem isso (`mask(..., learn=False)`), para não mudarem a cada sessão e o
provedor continuar lendo essa parte do cache.

Os nomes do cofre só casam capitalizados ou em maiúsculas ("Casa" e "CASA", não "casa"): um contato chamado "Casa" não
pode trocar a palavra comum. Os nomes que a IA local apontou nesta tarefa casam em qualquer caixa. Nomes e literais
mais longos vêm primeiro na alternância.

`Masker.unmask` monta a expressão inversa a partir de `reverse` e devolve os reais. As duas expressões são refeitas só
quando a versão do cofre ou da sessão muda. `Masker.walk` aplica uma função a todas as strings de uma estrutura JSON.

## Regras fixas (valem sem a IA local)

- E-mails, `@usuários`, cartões, CPF, CNPJ, CEP, placas e telefones, pelas expressões acima, em qualquer texto.
- Tudo o que está no cofre.
- **Nomes pela forma do texto** (`Masker.learn`, 2026-11-12, com as listas de `lmphone/nomes.py`, vindas do maskai):
  um prenome frequente é pessoa em qualquer caixa ("pergunta pra gisele"), e o que vem colado depois dele continua o
  nome (sobrenome das listas, nome do cofre ou, com tudo capitalizado, até duas palavras quaisquer); um nome do cofre
  escrito sem acento ("Livia") ou em minúsculas, se a palavra só é nome ("souza" sim, "casa" e "livre" não); o nome de
  um logradouro ("Rua das Acácias", ou "rua das acácias 482" em minúsculas, só com o número). Um prenome que também é
  palavra comum (`nomes.AMBIGUOUS`: "Rosa", "Clara", "Vitória", "Salvador") só vale com um sobrenome depois. Só com
  estas regras e o cofre, sem modelo, o conjunto congelado foi de 83 para 169 de 187 pessoas e de 9 para 23 de 38
  usuários (`tests/test_regras.py` não deixa piorar).
- **Senhas ditas no pedido** (`masking.passwords`): o valor depois de "senha", "password", "passcode", "passwd" vira
  literal da sessão já em `proxy.begin`, antes de qualquer julgamento. Depois de "é", ":" ou "=" vale qualquer palavra
  que não seja de `_NOT_PASSWORD` ("a senha do wifi da casa é limao2024"); depois de "pra"/"para" ou logo depois de
  "senha", só o que tem cara de senha, com dígito, símbolo ou maiúscula no meio ("troca a senha do wifi pra
  abc12345"). Até 2026-11-12 a regra pegava a primeira palavra depois de "senha": "pra", "instagram" e "casa" viravam
  literais da sessão e a senha de verdade saía real.
  Vale também para instruções faladas no meio da tarefa (`proxy.instruct`) e respostas do dono (`proxy.answered`); uma
  resposta marcada como segredo vira literal inteira. A senha só volta ao real na digitação no aparelho.
- Palavras de categoria, parentescos, marcas e apps nunca são nome (`STOPLIST` em `masking.py`, mais
  `data/stoplist.txt`).

Se a IA local está fora do ar ou falha, só estas valem: o pedido segue, com menos máscara, nunca com menos regra.

O que a IA local aponta também é filtrado por código: uma "pessoa" com a forma de um endereço de site
(`local_ai.URLISH`) fica como está; uma palavra comum que também é nome, apontada capitalizada, só vale capitalizada
(`cap_names`); um literal só de números com menos de 4 dígitos não é aprendido.

## A IA local

Desde 2026-10-19 são os modelos pequenos em ONNX (`lmphone/modelo_server.py`, porta 8788: `/judge` e `/entities`); com
`LMPHONE_LOCAL_AI=gemma`, a Gemma pelo Ollama, com o Laya filtrando antes os trechos que são claramente rótulos de
interface. As respostas têm o mesmo formato nos dois casos.

**A IA local decide por entidade e só pode pedir mais máscara ou liberar o que é ambíguo.** Ela nunca libera o que as
regras fixas pegam.

### O pedido (`judge_request` → `apply_request`)

Roda uma vez por pedido, em paralelo com a subida da tarefa (`proxy.judge_task`); `ask_provider` espera por ela. A IA
classifica a intenção (`pesquisa`, `acao`, `mista`) e lista as entidades com tipo e se precisam de pesquisa. O texto
de cada uma é realinhado ao pedido (`align`: a IA às vezes devolve outros acentos ou outra caixa). Decisões:

| Tipo | Decisão |
|---|---|
| pessoa (famosa também) | mascarar; as palavras viram `extra_names` |
| usuário, e-mail, telefone, documento | mascarar inteiro como literal |
| usuário sem a forma de um (sem @, ponto, _ ou número) num pedido que não fala de rede social | manter (o Hyrox ouvido como "rayrox" virou usuário falso em 2026-10-24) |
| negócio, instituição, lugar que precisa de pesquisa (e o pedido não é só ação) | liberar: sai real, mesmo se estiver no cofre |
| negócio, instituição, lugar no cofre, sem pesquisa | mascarar (é um contato) |
| negócio, instituição, lugar fora do cofre | manter |
| app, outro | manter |

Exemplo, com o pedido fictício "Vê o preço do ingresso do Cine Drive e manda pra Paula no WhatsApp": "Cine Drive" é
liberado (precisa ser pesquisado), "Paula" é mascarada, "WhatsApp" fica.

### A tela (`screen_fragments` → `find_private` → `apply_screen`)

A cada pedido ao provedor, `proxy.judge_screen` tira da tela os trechos de texto visíveis (sem ids, classes e o
cabeçalho), descarta os que a IA já julgou nesta sessão (`seen`) e manda os novos em blocos de até 1.200 caracteres.
A IA devolve pessoas e nomes de usuário; todos são mascarados. Um nome que o pedido liberou para pesquisa continua
liberado (`keep_released`). Um bloco que falha não entra em `seen`: vale a regra fixa agora e ele é julgado de novo
no passo seguinte.

## A tela reduzida (`executor.redact`)

Antes do mascaramento, a tela que vai num pedido de ajuda ou num `look` do assistente é reduzida:

- texto com mais de 60 caracteres (`MAX_LABEL`) vira `[hidden text]`: mensagens, descrições, corpos de e-mail;
- números com 3 ou mais dígitos têm os dígitos trocados por `#`: códigos, valores, telefones que as regras não pegaram;
- ids, classes e posições ficam (o provedor precisa deles para escolher o controle).

A exceção é a página de resultados da pesquisa no Google do celular: lá vão textos até 500 caracteres
(`SEARCH_LABEL`) e os números inteiros, porque o horário e o placar são a resposta. Esses textos ainda passam pela IA
local e pelas regras fixas.

O provedor sabe que vê valores falsos e textos escondidos e é instruído a usá-los como reais e a nunca dizer isso ao
dono. Para dar ao dono um valor que só aparece escondido, o plano termina com `read`: o aparelho lê o valor real e o
entrega sem passar pelo provedor; ele também não fica no `proxy.jsonl` nem na conversa do pedido seguinte
(`proxy.READ_HIDDEN`).

## Na volta

`ask_provider` devolve a resposta já desmascarada. Assim:

- `type` digita o texto real no aparelho;
- `tap` procura na tela o rótulo real;
- `search` (`proxy.web_search`) abre no Chrome a pesquisa com os valores reais;
- as perguntas e confirmações mostradas na faixa (`service.py`) aparecem com os nomes reais.

## Onde ficam os valores reais

| Lugar | Conteúdo |
|---|---|
| `data/vault.json` (600) | só os reais do cofre |
| memória do serviço | a `Session`: pares real ↔ falso; somem com a tarefa ou conversa |
| `logs/proxy.jsonl` | só texto mascarado e contagens (o que foi enviado, quantas trocas por tipo, as decisões da IA local contadas) |
| `logs/detalhe/<sessão>.jsonl` (600) | o que a IA local gerou, com os reais e as trocas real → falso, só para o painel; `LMPHONE_DETALHE=0` desliga |
| `logs/live/<sessão>.jsonl` (600) | o registro do live mode, com reais |
| `data/treino/real/` (600) | a coleta para o treino, só com `LMPHONE_COLETA=1` |

Nada disso vai ao provedor. O cache de caminhos e o mapa dos apps também ficam limpos: `proxy.remember` só grava um
caminho se nenhum rótulo dele mudaria com o mascaramento, e só grava o pedido se ele mesmo não muda.

## Testes

- `tests/test_masking.py`: as trocas, a passada única, as caixas, as senhas, a volta.
- `tests/test_regras.py` e `tests/regras_cases.py` (fictícios): as regras que valem sem a IA local, e o conjunto
  congelado só com elas. Os mesmos casos entram em `tools.app.cerebro mascara`, para o Kotlin.
- `tests/test_cerebro.py` e `:cerebro:conferir`: o Kotlin igual ao Python.
- `tests.eval_base` (conjunto congelado): quantas pessoas e usuários a IA local acha (modelos pequenos: 185 de 187
  pessoas e 38 de 38 usuários).
- `tests.eval_ia`: a Gemma em 40 casos escritos à mão.

Use os dados fictícios de `tests/ia_cases.py`. Não imprima valores do cofre nem da tela do celular.

## Limites

- A IA local julga cada trecho uma vez; um erro dela vale até o fim da tarefa.
- Nomes de usuário fora do cofre que a IA local não acha saem sem máscara. Os próprios nomes de usuário do dono não
  estão no cofre.
- De um endereço em texto livre, só o nome do logradouro é mascarado (o número, o bairro e os endereços de Brasília
  por quadra ficam). O DDD dos telefones é preservado.
- Um nome colado a outro sem separador (`liviabastos_`) só é achado pela IA local.
- As regras de nome mascaram a mais quando um prenome das listas é outra coisa no texto (uma marca, um lugar fora de
  `AMBIGUOUS`); a troca volta na resposta, mas o provedor não vê a palavra.
- Máscara não protege contra reconhecimento pelo conteúdo (o assunto de uma conversa identifica alguém).
- A página de resultados de uma pesquisa vai sem esconder textos longos.
- Texto na tela pode tentar dar ordens ao provedor (injeção de prompt); a única defesa é o plano vir antes da tela.


## Imagem usada só no fundo da interface (2026-11-10)

O vidro fosco não muda o que o provedor recebe: o agente continua lendo e enviando só texto pelo caminho acima.
Na One UI sem suporte ao blur nativo, a faixa captura a janela abaixo dela pela API de acessibilidade, reduz e
desfoca a imagem só na RAM. O painel inicial usa a captura que o Android entrega ao assistente, com as duas opções
de contexto autorizadas pelo Pedro; `onHandleAssist` descarta a estrutura extra sem ler seu conteúdo. Essas imagens
não entram no cérebro ou nos modelos locais, não são gravadas e não são enviadas ao provedor. Ao fechar ou minimizar,
a imagem é liberada. Falhas e janelas protegidas usam um fundo fechado, sem tentar contornar a proteção do Android.
