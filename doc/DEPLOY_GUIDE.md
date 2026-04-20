# Deploy Guide — Free Cloud

## Arquitetura de Deploy (100% Gratuito)

```
┌─────────────────────────────────────────────────────────┐
│                     NUVEM GRATUITA                      │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  FastAPI     │    │  Streamlit   │                   │
│  │ Google Cloud │    │  Hugging     │                   │
│  │    Run       │◄───│  Face Spaces │                   │
│  │  (Free Tier) │    │   (Free)     │                   │
│  └──────┬───────┘    └──────────────┘                   │
│         │                                               │
│  ┌──────▼───────┐    ┌──────────────┐                   │
│  │   MLflow     │    │  BigQuery    │                   │
│  │   Railway    │    │  (Free Tier) │                   │
│  │  (Free $5)   │    │  10GB grátis │                   │
│  └──────────────┘    └──────────────┘                   │
│                                                         │
│  Alertas: Gmail SMTP (grátis) + Telegram Bot (grátis)  │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Google Cloud Run — FastAPI (GRATUITO)

**Limite gratuito**: 2 milhões de requests/mês + 360K GB-s/mês

```bash
# Instalar Google Cloud CLI
# https://cloud.google.com/sdk/docs/install

# Login
gcloud auth login
gcloud config set project SEU_PROJETO_ID

# Build e push da imagem
gcloud builds submit --tag gcr.io/SEU_PROJETO_ID/recommender-api .

# Deploy
gcloud run deploy recommender-api \
  --image gcr.io/SEU_PROJETO_ID/recommender-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --set-env-vars="MLFLOW_TRACKING_URI=https://sua-url-mlflow.railway.app" \
  --set-env-vars="EMAIL_SENDER=seu@gmail.com" \
  --set-env-vars="EMAIL_PASSWORD=sua_senha_app" \
  --set-env-vars="TELEGRAM_BOT_TOKEN=seu_token" \
  --set-env-vars="TELEGRAM_CHAT_ID=seu_chat_id"
```

---

## 2. Hugging Face Spaces — Streamlit (100% GRATUITO)

**Sem limites de request, 16GB RAM disponível**

1. Crie conta em https://huggingface.co
2. Crie novo Space → SDK: Streamlit
3. Clone o repositório do Space:
```bash
git clone https://huggingface.co/spaces/SEU_USERNAME/amazon-recommender
```
4. Copie `streamlit_app/app.py` e `streamlit_app/requirements.txt`
5. Adicione `API_URL` nas configurações do Space (Settings → Variables):
   ```
   API_URL = https://recommender-api-xxxxx-uc.a.run.app
   ```
6. Push:
```bash
git add . && git commit -m "deploy" && git push
```

---

## 3. Railway — MLflow (GRATUITO até $5/mês)

1. Acesse https://railway.app e conecte o GitHub
2. New Project → Deploy from Dockerfile
3. Selecione `mlflow_server/Dockerfile`
4. Configure variáveis:
   - `PORT=5000`
   - `MLFLOW_BACKEND_STORE_URI=sqlite:///mlflow/mlflow.db`
5. Exponha a porta 5000 e copie a URL gerada

**Alternativa grátis total**: Render.com (Free tier, 512MB RAM)
```
https://render.com → New Web Service → Docker → mlflow_server/Dockerfile
```

---

## 4. BigQuery — Dados e Retreinamento (GRATUITO)

**Free tier**: 10GB storage + 1TB queries/mês

```bash
# Criar dataset
bq mk --location=US amazon_reviews

# Upload do CSV inicial
bq load \
  --autodetect \
  --source_format=CSV \
  amazon_reviews.product_reviews \
  input/7817_1.csv

# Criar tabela de produtos processados
bq load \
  --autodetect \
  --source_format=CSV \
  amazon_reviews.df_products \
  output/df_products.csv
```

---

## 5. Gmail SMTP — Alertas de Email (GRATUITO)

1. Acesse sua conta Google: https://myaccount.google.com/apppasswords
2. Crie uma "Senha de App" para "Mail"
3. Use essa senha no `.env` como `EMAIL_PASSWORD`

---

## 6. Telegram Bot — Alertas no Grupo (GRATUITO)

1. Abra o Telegram e vá em @BotFather
2. Digite `/newbot` e siga as instruções
3. Copie o token gerado → `TELEGRAM_BOT_TOKEN`
4. Adicione o bot ao seu grupo
5. Obtenha o Chat ID:
   - Adicione @userinfobot ao grupo
   - Ou acesse: `https://api.telegram.org/botSEU_TOKEN/getUpdates`
6. Use o `id` negativo do grupo → `TELEGRAM_CHAT_ID`

---

## 7. Execução Local com Docker Compose

```bash
# Copiar e configurar variáveis
cp .env.example .env
# Edite o .env com seus dados

# Build e start
docker-compose up --build

# Serviços disponíveis:
# FastAPI:   http://localhost:8000
# Docs API:  http://localhost:8000/docs
# Streamlit: http://localhost:8501
# MLflow:    http://localhost:5000
```

---

## 8. Retreinamento Automático com Cloud Scheduler (GRATUITO)

```bash
# Criar job semanal no Cloud Scheduler
gcloud scheduler jobs create http retrain-weekly \
  --schedule="0 2 * * 1" \
  --uri="https://SUA_API_URL/retrain" \
  --message-body='{"source":"bigquery","notify":true}' \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --time-zone="America/Sao_Paulo"
```

---

## Resumo dos Custos

| Serviço | Plataforma | Custo |
|---------|-----------|-------|
| FastAPI | Google Cloud Run | **$0** (free tier) |
| Streamlit UI | Hugging Face Spaces | **$0** (sempre grátis) |
| MLflow | Railway | **$0** (até $5 crédito) |
| BigQuery | Google Cloud | **$0** (10GB free) |
| Cloud Scheduler | Google Cloud | **$0** (3 jobs free) |
| Email | Gmail SMTP | **$0** |
| Telegram | Bot API | **$0** |
| **TOTAL** | | **$0/mês** |
