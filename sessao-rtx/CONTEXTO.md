# Contexto para a sessão de treino (máquina com RTX 5060)

Escrito em 2026-10-16 no notebook, por quem acompanhou o projeto até a pv1 e a etapa 0 do plano. Complementa o
`CLAUDE.md` (o estado e as decisões em vigor) e o `docs/plano-modelos-pequenos.md` (o plano); não os substitui.
Onde este arquivo e esses dois discordarem, valem eles, e corrija este.

## O projeto em uma página

O easy_phone é um assistente que opera o celular Android do Pedro (Galaxy S23+) como um usuário: abre apps, lê a
tela, toca, rola e digita, a partir de um pedido em linguagem natural ("Turn on dark mode").

A regra que manda em tudo: **dado pessoal não sai do aparelho sem máscara.** Quem planeja os passos é um modelo de
provedor na nuvem (Claude Haiku 5.5 pelo OpenRouter), e ele só vê dados falsos. Antes de qualquer texto sair, o
projeto acha o que é pessoal (nomes, `@usuários`, e-mails, telefones, documentos) e troca por valores falsos
coerentes, que são destrocados na volta. "Aparelho", hoje, é o notebook ligado ao celular por USB: o serviço roda
no notebook e controla o celular pelo `adb` e pelo app Mobilerun Portal, que entrega a árvore de acessibilidade.

O caminho de uma tarefa:

1. O pedido chega ao serviço (`lmphone/service.py`). A Gemma (IA local) julga o pedido: intenção (`pesquisa`,
   `acao`, `mista`) e entidades com tipo e se precisam ser pesquisadas (`local_ai.judge_request`).
2. O pedido mascarado vai ao provedor, que devolve um plano em JSON (passos `open_app`, `tap`, `turn_on`, `type`...
   e um objetivo conferível na tela).
3. O executor (`lmphone/executor.py`) cumpre cada passo. Para tocar no controle que o plano nomeia, tenta: o rótulo
   exato na tela (código); senão o mesmo controle com outro nome, perguntando ao **Laya** (`/pick`); senão pede
   ajuda ao provedor, mandando a tela reduzida e mascarada.
4. Cada tela nova que vai ao provedor passa antes pelo mascaramento: regras fixas e cofre (`lmphone/masking.py`),
   depois o **filtro do Laya** (`/private`, descarta trechos que são claramente rótulo de interface, p < 0,15) e a
   **Gemma** nos trechos restantes (`local_ai.find_private`), que lista pessoas e usuários.

Os dois modelos locais, portanto, fazem três trabalhos, e nenhum deles precisa gerar texto:

| Trabalho | Hoje | Entrada → saída |
|---|---|---|
| Achar pessoas e usuários em trechos de tela | Gemma 4 E2B no Ollama (`find_private`), depois do filtro do Laya (`/private`) | trechos de tela → lista `{"texto", "tipo": pessoa\|usuario}` |
| Julgar o pedido | Gemma (`judge_request`) | pedido → `{"intencao", "entidades": [{"texto", "tipo", "precisa_pesquisa"}]}` |
| Achar o controle pelo nome | Laya 421M (`/pick`) | nomes que o plano dá + rótulos da tela → um rótulo ou "nenhum" |

Por isso o plano é trocar os dois por um encoder pequeno ajustado (marcação por token e classificação), de 300 a
500 MB no total, em ONNX, que também é o formato que o futuro app Android vai precisar.

## O que esta máquina faz, e o que não faz

**Decisão de 2026-10-16, que vale acima desta seção:** a máquina da RTX faz tudo o que o notebook faz, sem exceção:
tem o cofre e os dados reais, liga o celular, roda o serviço, a suíte, a linha de base e qualquer etapa do plano
(inclusive o professor local da etapa 3). Ela roda em Windows nativo, sem WSL (ver "Como rodar" no `CLAUDE.md`). A
tabela abaixo ficou como registro da divisão que se pensava antes.

Esta máquina não tem o celular, o cofre nem dados reais, e não deve passar a ter sem o Pedro decidir isso
explicitamente. O plano diz que os dados reais (fonte B) não saem do notebook; outra máquina do Pedro ainda é "fora
do notebook". Se a questão aparecer (por exemplo, rodar o professor local da etapa 3 aqui na GPU), pergunte.

| Etapa do plano | Onde | Observação |
|---|---|---|
| 0. Terminar o conjunto congelado | notebook | precisa do celular (`tests.captura`) para conferir telas |
| 1. Coleta no serviço | código em qualquer lugar; coleta no notebook | o código de gravação pode ser escrito e testado com telas fictícias aqui |
| 2. Dados sintéticos pelo provedor | **aqui** | precisa de uma chave do OpenRouter (`.env`); o provedor só vê dado fictício |
| 3. Professor local nas telas reais | notebook | os dados são reais; aqui, só se o Pedro autorizar |
| 4. Treino | **aqui**, com os sintéticos | o retreino com dados reais roda no notebook: os scripts têm de funcionar também em CPU |
| 5. Exportar para ONNX e quantizar | **aqui** | a medição final de tempo e memória é no notebook |
| 6. Integração e troca | notebook | precisa do celular e da suíte |

A ordem razoável nesta máquina: preparar o ambiente; escrever o avaliador do modelo novo no conjunto congelado
(ver "Como medir"); gerar uma primeira leva sintética pequena e mostrar uma amostra ao Pedro; treinar um primeiro
modelo de cada tarefa; só então gerar em volume e comparar encoders base. Começar pelo `pick` é uma boa aposta: é o
ponto mais fraco da linha de base e o mais fácil de gerar sinteticamente.

## Metas e números a bater

Do plano, em ordem de prioridade, medidos no conjunto congelado `tests/base/`:

1. **Não vazar mais que hoje.** Linha de base: pessoas mascaradas 150 de 154; nomes de usuário 32 de 36; e-mails,
   telefones e documentos 20 de 20 (regras fixas, que continuam valendo por cima de qualquer modelo); textos que
   deviam ficar 361 de 368; liberados para pesquisa 14 de 14; intenção 67 de 67. Recall de pessoa e usuário pesa
   mais que precisão: deixar passar um nome é pior que mascarar um rótulo.
2. **Escolher controles pelo menos tão bem quanto o Laya.** Segunda rodada (`reports/base-2026-10-16-132359`, a que
   vale): 80 de 155 presentes achados, 33 de 36 ausentes respondidos como "nenhum", 11 toques errados; nas 63
   escolhas de telas conferidas no aparelho, 31 certas. Critério: **achar mais controles sem passar de 11 toques
   errados.** O Laya falha em sinônimos óbvios ("Reload" e "Refresh", "Chronometer" e "Stopwatch") e prefere
   "nenhum"; afrouxar a pergunta a ele aumenta os toques errados (detalhes no plano).
3. **Tamanho:** até 1 GB somando tudo, no disco e na memória; alvo de 300 a 500 MB.
4. **Tempo:** não ficar mais lento que hoje, **na CPU do notebook** (Intel Core Ultra 7 355, 8 núcleos, 16 GB):
   Gemma 2,0 s por chamada (pior 10,5 s), Laya 0,42 s por escolha. O modelo roda em CPU no uso real (e depois no
   celular, ARM). Tempo medido na RTX não serve como argumento; escolha arquiteturas pensando na CPU.

O conjunto congelado hoje: 149 casos de mascaramento (pedidos e telas, 780 trechos) e 191 escolhas de controle, em
cerca de 20 apps. A etapa 0 ainda não fechou: faltam casos de apps muito usados (YouTube Music, Prime Video, Netflix,
OLX, Mercado Livre, X, Samsung Notes, app do Google), refazer o Waze em português e conferir Instagram e Chrome. Isso
é no notebook; o conjunto vai crescer, e os números acima mudam junto.

## Regras para os dados de treino

- **O conjunto congelado nunca entra no treino**, nem parecido. Os nomes fictícios de `tests/base/mascaramento.py`
  (`CONTATOS`, `EMAILS`, `TELEFONES` e os nomes dentro dos casos) e os rótulos de tela de `tests/base/controles.py`
  não podem ser usados como semente da geração sintética, e o prompt de geração não pode citar os casos. Gere as
  listas de nomes fictícios do zero (o `tests/ia_cases.py` divide 14 nomes com o conjunto congelado, então não serve
  de fonte sem filtrar) e confira por código que a interseção com `tests/base` é vazia, em nomes e em pares (passo,
  rótulo certo). Rótulos de interface
  reais iguais (por exemplo "Settings", "Wi-Fi") vão se repetir e tudo bem; o que não pode é o mesmo exemplo.
- O provedor nunca vê dado real. Aqui não há dado real, então a regra se cumpre sozinha; mantenha assim.
- Idiomas: a interface do aparelho é em inglês (rótulos de tela em inglês), mas as conversas, os nomes e parte dos
  apps são em português (o Waze está em português). Pedidos chegam nas duas línguas. Gere os dois.
- Ruído que importa: nomes em minúsculas ("manda pro caio..."), apelidos ("Juninho"), nomes que são palavras comuns
  ("Rosa"), usuários com pontos e números (`ana_souza12`, `joao.lima`), rótulos de interface parecidos com nomes,
  pessoas públicas (não se mascaram), parentescos ("Tia", "Vó": ficam, o nome depois sai trocado), negócios do cofre
  numa ação (mascarar) e numa pesquisa (liberar).
- Formato das telas: o que o modelo vê são **trechos**, o resultado de `local_ai.screen_fragments` sobre o texto que
  `device.render` produz (uma linha por elemento: `12. TextView: "id", "texto" - (l,t,r,b)`). Gere trechos como o
  Portal os entrega (ordem da tela, um texto por elemento), não telas em prosa. Achado da etapa 0 ainda não corrigido:
  `screen_fragments` deixa passar linhas de cabeçalho (`• **App:** ...`) e de id interno sem classe; não treine o
  modelo para tratar isso, corrija a função (é um bug pequeno e separado).
- No `pick`, o executor manda todos os nomes que o plano dá ao controle de uma vez (`wanted`, uma lista) e só os
  rótulos de até 60 caracteres (`executor.MAX_LABEL`). Os casos "o controle não está nesta tela" são metade do valor:
  é o que evita toque errado.

## Como medir

`tests/eval_base.py` hoje roda o caminho real do serviço com a Gemma e o Laya (`proxy.judge_screen` e
`judge_task`) e confere cada caso com as funções `check_masking` e as das escolhas, apontando a causa de cada erro.
Para o modelo novo, o melhor é o mesmo avaliador com outro modelo atrás, para os números serem comparáveis um a um:

- O jeito que o plano prevê (etapa 6) é o servidor novo manter a API do Laya (`/pick`, `/private`, porta 8788) e
  ganhar `/entities` e `/judge` que devolvem **o mesmo JSON que a Gemma devolve** (`{"itens": [...]}` e
  `{"intencao", "entidades"}`). Assim `local_ai.apply_screen` e `apply_request`, que transformam o achado em máscara,
  continuam iguais, e a troca é uma variável (`LMPHONE_LOCAL_AI=gemma|novo`) em `local_ai.py`.
- Antes disso, para iterar rápido no treino, vale um avaliador direto em `tools/treino/` que importa os casos de
  `tests/base` e reaproveita as conferências do `eval_base` (sem copiar a lógica). Os números de referência estão nos
  `resultados.json` das pastas `reports/base-*` trazidas do notebook.
- Rodar a Gemma e o Laya aqui não é necessário (os números da linha de base já existem). Se precisar: Ollama com
  `gemma4:e2b-it-qat` e o `run.sh` cria o `gemma4-e2b-texto`; o Laya num `.venv-laya` (ver `CLAUDE.md`). Na GPU os
  tempos não se comparam com os do notebook.

## Decisões técnicas já tomadas e o que está em aberto

- Ambiente de treino separado: `.venv-treino` (transformers, datasets, onnx, accelerate), scripts em `tools/treino/`.
  O `.venv` do projeto continua **só com a biblioteca padrão**: nada de `import torch` em `lmphone/`.
- O servidor final roda com onnxruntime e tokenizers, sem PyTorch (`.venv-modelo`).
- Candidatos a encoder base: multilingual-e5-small, mDeBERTa-v3-small/xsmall, DistilBERT multilíngue. O que pesa
  neles é o vocabulário multilíngue (até 250 mil tokens); cortá-lo para os tokens de português e inglês dos dados
  reduz muito o tamanho. Medir antes e depois do corte.
- Quantização em 8 bits **calibrada**, no ONNX. A quantização dinâmica do PyTorch no Laya não serviu (memória igual,
  acerto pior; `docs/historico.md`, "Memória dos modelos"). Os limiares (o 0,5 do `pick`, o 0,15 do filtro) mudam
  com o modelo: recalibre no conjunto congelado e diga quanto.
- Pesos de perda a favor do recall de pessoa e usuário.
- Em aberto, decidir pelo resultado: um encoder com várias cabeças ou dois modelos (mascaramento e `pick`); se a
  cabeça de `judge_request` não bater a Gemma (a decisão "liberar este negócio porque o pedido manda pesquisá-lo"
  pode exigir raciocínio), a Gemma fica só para essa chamada, uma por tarefa, e sai do caminho das telas.
- O `/private` (filtro) provavelmente some: o encoder de marcação roda em todos os trechos em milissegundos.
- Nada disso está no ar: a etapa 0 está em andamento e as etapas 1 a 6 não começaram. Não há `tools/treino/`,
  `.venv-treino` nem `data/treino/` ainda.

### Sobre a RTX 5060

- 8 GB de VRAM. Ajuste fino de encoders de 100 a 300M com bf16 ou fp16 e lotes de 32 a 64 cabe com folga.
- PyTorch 2.7 ou mais novo, das rodas `cu128` (`pip install --index-url https://download.pytorch.org/whl/cu128
  torch`); confira com `torch.cuda.get_device_capability()` → `(12, 0)` e uma operação de teste na GPU.
- Um professor de 12 a 14B em Q4 (cerca de 9 GB) não cabe inteiro na VRAM; com descarga parcial roda, mais devagar.
  De todo modo, a etapa 3 é sobre dados reais (ver acima).
- Os scripts de treino precisam rodar também em CPU (`device` escolhido sozinho), para o retreino com dados reais
  no notebook.

## Onde as coisas ficam

| O quê | Onde | No git? |
|---|---|---|
| Plano e estado das etapas | `docs/plano-modelos-pequenos.md` | sim |
| Conjunto congelado | `tests/base/` | sim |
| Scripts de treino, geração, exportação | `tools/treino/` | sim |
| Dados sintéticos | `data/treino/sintetico/` | não (`data/` está no `.gitignore`); copie de volta ao notebook à mão |
| Modelos treinados e exportados | proponha um lugar fora do git (por exemplo `modelos/`, acrescentado ao `.gitignore`) | não |
| Relatórios | `reports/` | não |

Os dados sintéticos são fictícios e podem ser mostrados, impressos e conferidos à vontade. Mesmo assim ficam fora
do git pelo volume; se o Pedro preferir versionar uma amostra, ótimo.

## Jeito de trabalhar neste projeto

- Tudo em português do Brasil: documentação, comentários, mensagens de commit, relatórios. Os textos que vão a um
  modelo (prompts, planos, perguntas ao Laya) são em inglês.
- Escrita direta, com números medidos e o motivo de cada decisão. Ao concluir algo: marque a etapa no plano, leve as
  decisões que passam a valer ao `CLAUDE.md` e as medições longas ao `docs/historico.md`. Um resultado negativo também
  se registra (o que foi tentado, quanto deu, por que não serviu).
- O código segue o estilo do que existe: Python simples, funções curtas, poucos comentários e só para o porquê,
  nomes em inglês no código e em português nos dados e na interface. Testes unitários em `tests/test_*.py`
  (`.venv/bin/python -m unittest discover -s tests`); rode-os depois de mexer em `lmphone/` ou `tests/`.
- Commits pequenos, com o motivo na mensagem. Um caso do conjunto congelado só muda quando está errado, com o
  motivo no commit.
- Antes de gastar com o provedor ou baixar algo grande, diga quanto e espere o ok. O provedor padrão custa pouco
  (a suíte inteira de 26 execuções saiu US$ 0,021), mas gerar milhares de exemplos não é a mesma ordem; estime pelo
  tamanho das respostas e mostre a conta.
- Ao gerar dados sintéticos, mostre uma amostra ao Pedro antes de gerar em volume. Ao treinar, o número que importa
  é o do conjunto congelado; acerto no próprio sintético não diz nada.

## Armadilhas conhecidas

- **Treinar e testar no mesmo tipo de dado.** Se o sintético imitar demais o conjunto congelado, o número engana.
  Daí a regra da interseção vazia e as telas conferidas no aparelho (campo `conferido` em `controles.py`): reporte o
  acerto nelas separado.
- **O `logs/proxy.jsonl` não serve de rótulo.** Ele só marca o que a Gemma e as regras já acharam; o modelo novo
  herdaria os erros dela. (E ele não está nesta máquina.)
- **Erros conhecidos da Gemma**, que o modelo novo deve corrigir e que valem como casos difíceis no sintético (com
  outros nomes): marcou o título "Switch to private account?" e uma URL como pessoa; não acha nomes de usuário fora
  do cofre (`ig-seguindo`); copia um usuário pela metade; marca pessoas públicas.
- **Casos do conjunto que podem estar errados**, não o modelo: os do Waze (em inglês, o aparelho está em português).
  Telas do Instagram e do Chrome não foram conferidas no aparelho.
- A Calculadora não expõe as teclas na árvore de acessibilidade; a Câmera expõe alguns controles por nomes internos
  (`BACK_CAMERA_PICTURE_SIZE_NORMAL`). Isso é o que o modelo vai ver de verdade, não ruído a limpar.

## Glossário rápido

- **Portal**: o app Mobilerun Portal no celular; entrega a árvore de acessibilidade por HTTP e digita pelo teclado
  dele. Acessibilidade ligada só durante a tarefa, por causa dos apps de banco.
- **Cofre** (`data/vault.json`): valores reais a proteger (contatos, contas, perfil). Só no notebook.
- **Sessão**: os pares real ↔ falso de uma tarefa; nascem e morrem com ela.
- **STOPLIST**: palavras que nunca se mascaram (categorias, parentescos, marcas, apps).
- **Liberar**: deixar um negócio, instituição ou lugar sair real porque o pedido manda pesquisá-lo.
- **Suíte**: `tests/phone_suite.py`, 24 tarefas reais no celular. **Linha de base**: `tests/eval_base.py` no conjunto
  congelado, sem celular.
- **Pedro**: o dono do projeto e do celular. Fala português; decide o que sai do notebook.
