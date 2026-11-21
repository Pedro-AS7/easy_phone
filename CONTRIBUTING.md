# Contribuindo com o easy_phone

Obrigado pelo interesse! Issues e pull requests são bem-vindos, em português ou em inglês.

## Antes de começar

- **Bug:** abra uma issue com o que aconteceu, o que esperava, o celular (modelo, versão do Android e da interface do
  fabricante) e se foi pelo PC (`run.sh`) ou pelo app.
- **Mudança grande** (função nova, troca de modelo ou de dependência, mudança no que vai ao provedor): abra uma issue
  antes para conversar sobre ela. Isso evita trabalho perdido.
- **Correção pequena** (texto, bug óbvio): pode mandar o PR direto.

## Estrutura

```
lmphone/            o protótipo no PC (Python 3.12, só a biblioteca padrão)
android/            o app Android (Kotlin + Compose)
  app/              o app; src/completo (o agente age) e src/loja (só ensina)
  modelos/          os modelos pequenos em Kotlin (tokenizador e ONNX)
  cerebro/          o cérebro traduzido do Python, conferido contra ele
servidor/           o servidor do provedor da variante da loja
tools/              treino dos modelos, exportação, envio ao celular
tests/              testes de unidade, suíte no celular, simulador, conjunto congelado
docs/               planos e o histórico das decisões
```

O `CLAUDE.md` da raiz explica o estado, como rodar cada parte e as decisões em vigor, com os motivos em
`docs/historico.md`. Ele também é a instrução para agentes de IA (Claude Code, Codex) que trabalhem no projeto.

## Ambiente

```sh
python3.12 -m venv .venv
.venv/bin/python -m unittest discover -s tests     # testes de unidade, sem celular
.venv/bin/python -m tests.simulador -v             # guias da loja no simulador, sem celular
```

Android: JDK 17 e o Android SDK 36.

```sh
cd android
./gradlew :cerebro:test :modelos:test :app:testLojaDebugUnitTest :app:testCompletoDebugUnitTest :app:assembleLojaDebug
```

Para rodar no celular, veja "Como rodar" no `CLAUDE.md`.

## Regras do projeto

- **Dado pessoal não sai do aparelho sem máscara.** Tudo o que vai ao provedor passa por `proxy.ask_provider`, depois
  da IA local e das regras fixas; se o mascaramento falhar, nada é enviado. Um PR que mande ao provedor algo novo (um
  texto da tela, um print, um registro) precisa explicar como isso é mascarado.
- **A variante da loja só ensina.** Nada de gestos, digitação ou outras ações do agente em `src/main` ou `src/loja`;
  o `:app:conferirLoja` falha se aparecerem.
- **O Python é a referência do cérebro.** Mudou o executor, o proxy ou a máscara: rode `tools.app.cerebro exportar` e
  `trilhas` e traga o Kotlin até `:cerebro:conferir` dar igual.
- **Idioma:** interface, comentários, documentação e mensagens de commit em português do Brasil; nomes no código em
  inglês. Comentários curtos que explicam o porquê.
- **Sem dados reais** no código, nos testes, nas capturas ou nas issues: contatos, mensagens, nomes de redes, contas.
  Use os dados fictícios de `tests/ia_cases.py` e `tests/base/`. As gravações e as telas do celular de desenvolvimento
  (`tests/gravacoes/`, `tests/telas/`) não são publicadas; sem elas, os testes que as usam são pulados.
- Ao mudar uma decisão ou concluir uma etapa, atualize o `CLAUDE.md`; medições longas vão para `docs/historico.md`.
