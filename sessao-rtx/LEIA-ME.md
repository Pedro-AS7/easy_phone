# Sessão na máquina com RTX 5060

Esta pasta serve para continuar o `docs/plano-modelos-pequenos.md` numa máquina com GPU NVIDIA. No notebook
(Intel, sem CUDA) o treino dos encoders levaria horas por rodada; na RTX 5060, minutos.

- `LEIA-ME.md` (este arquivo): o que levar para a outra máquina, como prepará-la e o texto para abrir a sessão.
- `CONTEXTO.md`: o projeto inteiro do ponto de vista de quem vai treinar os modelos, para o agente da outra máquina
  ler antes de tudo.

## 1. No notebook, antes de sair

1. Faça commit do que está pendente (o conjunto congelado `tests/base/`, `tests/eval_base.py`, `tests/captura.py`,
   o plano e esta pasta). O repositório não tem remoto: leve-o por `git bundle`, por `git clone` via ssh ou por um
   repositório privado.

   ```sh
   git bundle create ~/easy_phone.bundle --all     # no notebook
   git clone easy_phone.bundle easy_phone            # na outra máquina
   ```

2. Leve à parte, se quiser comparar com a linha de base sem rodar a Gemma e o Laya lá: as pastas
   `reports/base-2026-10-16-123737` e `reports/base-2026-10-16-132359` (só dados fictícios; `reports/` fica fora
   do git).
3. **Não leve** `data/` (cofre, cache, mapa e as capturas em `data/capturas/`, todos com dados reais), `logs/`,
   `arquivo/`, `.venv*`. O `.env` só se a etapa 2 (dados sintéticos pelo provedor) for rodar lá, e por um canal
   seguro; dá para usar outra chave do OpenRouter, com um limite de gasto baixo.

## 2. Na máquina da RTX

- Driver NVIDIA 570 ou mais novo (a RTX 5060 é Blackwell, `sm_120`). Confira com `nvidia-smi`.
- Python 3.12 e o Claude Code instalados. Linux de preferência; no Windows, use o WSL2, porque os scripts do projeto
  são `sh`.
- O ambiente de treino o agente cria na sessão (`.venv-treino`, ver `CONTEXTO.md`). O PyTorch precisa vir das rodas
  CUDA 12.8 ou mais novas: as de CUDA 12.4 e anteriores não têm `sm_120` e falham na primeira operação na GPU.

## 3. Abrir a sessão

Na raiz do repositório (para o `CLAUDE.md` do projeto ser carregado), rode `claude` e cole:

```
Esta é a máquina de treino do easy_phone, com uma RTX 5060. Antes de qualquer coisa, leia inteiros
sessao-rtx/CONTEXTO.md, CLAUDE.md e docs/plano-modelos-pequenos.md, e depois tests/base/__init__.py,
lmphone/local_ai.py, lmphone/laya_server.py e o começo de tests/eval_base.py.

Objetivo da sessão: avançar o plano de modelos pequenos no que esta máquina faz melhor que o notebook (dados
sintéticos, treino na GPU, exportação para ONNX), sem celular e sem dados reais aqui.

Comece conferindo o ambiente (nvidia-smi, Python, espaço em disco) e me diga o que achou. Depois proponha a ordem
de trabalho desta sessão, com o que fica para o notebook, e espere meu ok antes de baixar modelos grandes ou
gastar com o provedor.
```

## 4. Na volta

O que precisa voltar ao notebook: o código (por git; `tools/treino/` e o que mudar em `lmphone/` e `tests/`), os
modelos exportados e os dados sintéticos (fora do git, ver `CONTEXTO.md`, "Onde as coisas ficam"). As medições de
tempo e memória que valem para as metas são as do notebook: refaça-as lá antes de dar uma etapa por concluída.
