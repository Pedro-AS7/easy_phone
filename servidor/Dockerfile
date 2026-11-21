# O servidor do provedor do app da loja no Cloud Run (docs/plano-play-store.md, fase 2). Só a biblioteca padrão.
FROM python:3.12-slim
WORKDIR /app
COPY servidor.py /app/servidor.py
ENV PYTHONUNBUFFERED=1
# A chave vem de um segredo do Secret Manager (OPENROUTER_API_KEY); ARMAZEM, INTEGRIDADE e os limites, das variáveis do serviço.
CMD ["python", "/app/servidor.py"]
