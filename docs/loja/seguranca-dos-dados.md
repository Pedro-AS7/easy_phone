# Segurança dos dados no Play Console (rascunho das respostas)

Tem de bater com `politica-de-privacidade.md`. Fase 5 de `docs/plano-play-store.md`.

**O app coleta ou compartilha algum dos tipos de dados exigidos?** Sim.

| Tipo de dado (nome no Console) | Coletado | Compartilhado | Opcional | Para quê | Observação |
|---|---|---|---|---|---|
| Atividade no app > Interações no app (toques e telas vistas) | Sim, só em trânsito | Sim, com o provedor de IA | Não (sem isso o guia não funciona) | Funcionalidade do app | O texto da tela vai com os dados pessoais trocados por falsos; nada fica no servidor |
| Mensagens no app / Outro conteúdo gerado pelo usuário (o pedido) | Sim, só em trânsito | Sim, com o provedor de IA | Não | Funcionalidade do app | Mascarado no aparelho; não é guardado |
| Áudio > Gravações de voz | Não | Não | — | — | A fala vira texto no próprio celular; o áudio não sai |
| Identificadores do dispositivo ou outros IDs | Sim (o número sorteado da instalação) | Não | Não | Funcionalidade do app, prevenção de fraude | Para o limite mensal |
| Informações pessoais (nome, e-mail, contatos) | Não | Não | — | — | Trocados por falsos antes de sair do aparelho |
| Localização | Não | Não | — | — | |

- **Os dados são criptografados em trânsito?** Sim (HTTPS até o servidor e até o provedor).
- **A pessoa pode pedir para apagar os dados?** Sim, pelo contato da política (o servidor só tem o número da
  instalação e as contagens; as denúncias, se houver).
- **Processamento efêmero:** o pedido e a tela passam pelo servidor e pelo provedor sem serem guardados pelo app.
- **Denúncias:** o texto de uma resposta denunciada é guardado, por escolha da pessoa (Outro conteúdo gerado pelo
  usuário, coletado, opcional, para segurança e conformidade).
