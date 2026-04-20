# GitHub Secrets — Como Configurar

Vá em: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

## Secrets Necessários

| Secret | Valor | Onde obter |
|--------|-------|-----------|
| `GCP_PROJECT_ID` | ID do projeto GCP | console.cloud.google.com |
| `GCP_SA_KEY` | JSON da service account | Ver passo abaixo |
| `MLFLOW_TRACKING_URI` | URL do MLflow no Railway | railway.app → seu projeto |
| `API_URL` | URL do Cloud Run após primeiro deploy | console.cloud.google.com/run |
| `EMAIL_SENDER` | seu_email@gmail.com | seu Gmail |
| `EMAIL_PASSWORD` | Senha de app Gmail | myaccount.google.com/apppasswords |
| `EMAIL_RECIPIENTS` | email1@gmail.com,email2@gmail.com | seus emails |
| `TELEGRAM_BOT_TOKEN` | token do bot | @BotFather no Telegram |
| `TELEGRAM_CHAT_ID` | id do grupo/chat | @userinfobot ou getUpdates API |
| `HF_TOKEN` | token do Hugging Face | huggingface.co/settings/tokens |
| `HF_USERNAME` | seu username HF | huggingface.co/settings/profile |

---

## Criar Service Account GCP (GCP_SA_KEY)

```bash
# 1. Criar service account
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer"

# 2. Dar permissões necessárias
PROJECT_ID=$(gcloud config get-value project)

for ROLE in \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/storage.admin \
  roles/bigquery.admin \
  roles/cloudbuild.builds.editor \
  roles/cloudscheduler.admin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="$ROLE" --quiet
done

# 3. Gerar chave JSON
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account="github-deployer@$PROJECT_ID.iam.gserviceaccount.com"

# 4. Copiar o conteúdo do JSON para o secret GCP_SA_KEY
cat gcp-key.json
```

> **ATENÇÃO**: Não commite o arquivo `gcp-key.json` no git!

---

## Criar Bot no Telegram

1. Abra o Telegram → procure **@BotFather**
2. Digite `/newbot`
3. Escolha nome: `Amazon Recommender Bot`
4. Escolha username: `amazon_recommender_bot` (único)
5. Copie o token → salve como `TELEGRAM_BOT_TOKEN`
6. Adicione o bot ao seu grupo
7. Envie uma mensagem no grupo
8. Execute para obter o Chat ID:
   ```bash
   curl "https://api.telegram.org/botSEU_TOKEN/getUpdates"
   ```
   Pegue o valor de `message.chat.id` (número negativo para grupos)

---

## Criar Senha de App Gmail

1. Acesse: https://myaccount.google.com/security
2. Ative verificação em 2 etapas (se não tiver)
3. Vá em: https://myaccount.google.com/apppasswords
4. Selecione "Mail" e "Windows Computer"
5. Copie a senha gerada (16 caracteres) → salve como `EMAIL_PASSWORD`
