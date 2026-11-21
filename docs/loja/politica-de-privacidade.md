# Política de privacidade do Guia do Celular (rascunho)

Rascunho para a fase 5 de `docs/plano-play-store.md`; precisa de uma página pública e da revisão do Pedro. Nome e
contato são provisórios.

**Última atualização:** [data da publicação]

O Guia do Celular ensina a usar o celular: você pergunta como se faz algo, e ele mostra na tela onde tocar, explica e
espera você fazer. O Guia nunca toca, digita, compra nem muda nada no seu celular.

## O que o Guia lê

- **O texto da tela**, pelo serviço de acessibilidade do Android, que você liga nas Configurações depois de ler o
  aviso do app. Serve para saber onde estão os botões e mostrar onde tocar.
- **Onde você toca** durante um guia, para saber que você fez o passo.
- **O que você pede**, falado ou escrito. A fala é transformada em texto no próprio celular.
- **Alguns ajustes do celular** (tamanho da letra, volume, brilho, Wi-Fi ligado ou não), para conferir se o que você
  pediu mudou.

O Guia não lê seus contatos, suas fotos, sua localização nem o que você digita em outros apps. Ele não lê a tela quando
você não pediu um guia.

## O que sai do celular, e como

Durante um guia que você pediu, o Guia manda ao **servidor do Guia do Celular** e a um **provedor de inteligência
artificial** (hoje, o Claude, da Anthropic, pelo OpenRouter) o seu pedido e o texto da tela, **com os dados pessoais
trocados por dados falsos antes de sair do celular**: nomes de pessoas, telefones, e-mails, documentos, números de
cartão e conta. A troca é feita no próprio aparelho, por regras e por um modelo de IA pequeno que roda nele. A resposta
volta com os falsos, e o celular os troca de volta pelos verdadeiros para você ler.

Textos muito longos da tela não são enviados.

## O que o servidor guarda

- Um número sorteado que identifica a instalação do app (não identifica você), e quantos pedidos ela fez no mês, para
  o limite gratuito de 150 pedidos por mês.
- Quanto custaram os pedidos do mês, no total.
- Se você **denunciar uma resposta**, o texto dessa resposta, como você o leu, para a nossa análise.

O servidor **não guarda** o seu pedido, o texto da tela nem as respostas. O provedor de IA recebe os pedidos já com os
dados falsos, sob os termos dele: [links do OpenRouter e da Anthropic].

## No seu celular

O Guia guarda no próprio celular um registro dos guias (o que foi dito e onde você tocou), para funcionar e para você
poder ver o que aconteceu. Ele fica só no app e é apagado quando você desinstala o app ou apaga os dados dele.

## Seus direitos

Você pode desligar o Guia a qualquer momento nas Configurações (Acessibilidade). Para apagar os dados do servidor
ligados à sua instalação, ou para qualquer dúvida: [e-mail de contato].

O Guia não é para crianças.
