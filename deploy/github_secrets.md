# GitHub Secrets — Como Configurar

Vá em: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

## Secrets Necessários

| Secret | Valor | Onde obter |
|--------|-------|-----------|
| `GCP_PROJECT_ID` | `samara-a2d79` | Google Cloud Console |
| `GCP_SA_KEY` | JSON da service account | Ver passo abaixo |
| `MLFLOW_TRACKING_URI` | URL do MLflow no Railway | railway.app → seu projeto |
| `API_URL` | URL do Cloud Run após primeiro deploy | console.cloud.google.com/run |
| `EMAIL_SENDER` | `rafaelhenriquegallo@gmail.com` | seu Gmail |
| `EMAIL_PASSWORD` | Senha de app Gmail | myaccount.google.com/apppasswords |
| `EMAIL_RECIPIENTS` | `rafaelhenriquegallo@gmail.com` | seu email |
| `GOOGLE_CHAT_WEBHOOK_URL` | URL do webhook do espaço | Ver passo abaixo |
| `HF_TOKEN` | token do Hugging Face | huggingface.co/settings/tokens |
| `HF_USERNAME` | seu username HF | huggingface.co/settings/profile |

---

## Criar Service Account GCP (GCP_SA_KEY)

```bash
PROJECT_ID=samara-a2d79

# 1. Criar service account
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer" \
  --project=$PROJECT_ID

# 2. Dar permissões necessárias
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

# 3. Gerar chave JSON e copiar o conteúdo para o secret GCP_SA_KEY
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account="github-deployer@$PROJECT_ID.iam.gserviceaccount.com"
cat gcp-key.json
```

> **ATENÇÃO**: Não commite o arquivo `gcp-key.json` no git!

---

## Criar Webhook no Google Chat (GOOGLE_CHAT_WEBHOOK_URL)

O espaço já existe: `https://mail.google.com/mail/u/0/#chat/space/AAQA7lnxSaU`

**Passos:**
1. Abra o Google Chat e vá até o espaço **AAQA7lnxSaU**
2. Clique no **nome do espaço** no topo
3. Selecione **"Gerenciar webhooks"** (ou "Manage webhooks")
4. Clique em **"Adicionar webhook"**
5. Nome: `ML System Alerts`
6. Clique em **Salvar**
7. Copie a URL gerada — formato:
   ```
   https://chat.googleapis.com/v1/spaces/AAQA7lnxSaU/messages?key=...&token=...
   ```
8. Cole essa URL no secret `GOOGLE_CHAT_WEBHOOK_URL` no GitHub e no `.env`

---

## Criar Senha de App Gmail (EMAIL_PASSWORD)

1. Acesse: https://myaccount.google.com/security
2. Ative verificação em 2 etapas (obrigatório)
3. Acesse: https://myaccount.google.com/apppasswords
4. Selecione "Mail" e "Windows Computer"
5. Copie a senha de 16 caracteres → salve como `EMAIL_PASSWORD`

> A senha de app é diferente da sua senha normal do Gmail.
