"""Conjunto de teste congelado da etapa 0 (docs/plano-modelos-pequenos.md).

Nada daqui entra em treino. Mudar um caso muda a linha de base: só corrija um caso quando ele estiver errado (o
esperado não é o que deveria ser), e registre o motivo no commit. Para cobrir algo novo, acrescente um caso com id novo.

- `mascaramento.py`: pedidos e telas, com o que não pode sair e o que precisa ficar.
- `controles.py`: escolhas de controle pelo nome (o `/pick` do Laya).

Todos os dados são fictícios. Cada caso diz onde está a tela que ele imita (`onde`), para conferir no aparelho com
`python -m tests.captura` quando o erro puder ser do caso e não do modelo.
"""
