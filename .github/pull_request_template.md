## O que muda

<!-- O que este PR faz e por quê. Se resolve uma issue: "Resolve #123". -->

## Como testei

<!-- Testes de unidade, simulador, e o que foi testado no celular (modelo e versão do Android). Diga também o que NÃO foi testado. -->

## Conferido

- [ ] `python -m unittest discover -s tests` passa (e os testes do Android, se mexi em `android/`)
- [ ] Nada novo vai ao provedor sem passar pela máscara, ou expliquei acima como vai
- [ ] Mudei o executor, o proxy ou a máscara e rodei `tools.app.cerebro exportar`/`trilhas` e `:cerebro:conferir`, ou não mexi neles
- [ ] Nada de dados reais (contatos, mensagens, redes, contas, chaves) no código, nos testes, nos textos ou nas capturas
