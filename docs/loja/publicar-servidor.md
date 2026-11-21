# Publicar o servidor do provedor no Cloud Run

Fase 2 de `docs/plano-play-store.md`. O servidor (`servidor/servidor.py`) guarda a chave do OpenRouter, conta os 150
pedidos por mês de cada instalação e o gasto do mês, e não guarda o conteúdo dos pedidos. Estes passos precisam da
conta Google do Pedro; nada aqui foi feito ainda.

## Uma vez

```sh
gcloud auth login
gcloud projects create guia-do-celular --name="Guia do Celular"     # ou um projeto que já exista
gcloud config set project guia-do-celular
gcloud services enable run.googleapis.com firestore.googleapis.com secretmanager.googleapis.com \
    playintegrity.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud firestore databases create --location=southamerica-east1    # as contagens (coleção "contagens")
printf %s "$OPENROUTER_API_KEY" | gcloud secrets create openrouter --data-file=-   # a chave, sem aparecer no terminal
```

A conta de serviço do Cloud Run precisa ler o segredo e escrever no Firestore:

```sh
SA=$(gcloud projects describe guia-do-celular --format='value(projectNumber)')-compute@developer.gserviceaccount.com
gcloud secrets add-iam-policy-binding openrouter --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
gcloud projects add-iam-policy-binding guia-do-celular --member=serviceAccount:$SA --role=roles/datastore.user
```

## Publicar (e a cada mudança em `servidor/`)

```sh
gcloud run deploy guia-servidor --source servidor --region southamerica-east1 --allow-unauthenticated \
    --set-secrets OPENROUTER_API_KEY=openrouter:latest \
    --set-env-vars ARMAZEM=firestore:guia-do-celular,LIMITE_MES=150,TETO_MES_USD=30,INTEGRIDADE=0 \
    --max-instances 3 --memory 256Mi --timeout 300
```

O endereço que o comando mostra (`https://guia-servidor-....run.app`) vai no build de publicação:
`bash android/gradlew :app:bundleLojaRelease -PservidorLoja=https://guia-servidor-....run.app/v1`.

`--allow-unauthenticated` é porque quem chama é o app no celular de qualquer pessoa; quem barra abuso é o limite por
instalação, o teto do mês e, ligada, a Play Integrity.

## Ligar a Play Integrity (antes do teste fechado)

1. No Play Console: Integridade do app > Play Integrity API > vincular o projeto `guia-do-celular` do Google Cloud.
2. No app (falta fazer): a biblioteca `com.google.android.play:integrity`, um token por pedido com o `requestHash` =
   sha256 do id do pedido (base64url), no cabeçalho `X-Lmphone-Integridade`. Precisa do número do projeto
   (`gcloud projects describe guia-do-celular --format='value(projectNumber)'`).
3. No servidor: `INTEGRIDADE=1` e `PACOTE=` o pacote definitivo do app.

## Acompanhar

- Gasto do mês: o documento `contagens/AAAA-MM_gasto` no Firestore (campo `dados`, JSON com `usd`).
- Denúncias: `contagens/AAAA-MM_denuncias` (o texto que a pessoa enviou).
- Registro: `gcloud run services logs read guia-servidor` (hora, instalação resumida, status, custo; nunca conteúdo).
- Um alerta de orçamento no Google Cloud (Faturamento > Orçamentos) além do teto do próprio servidor.
