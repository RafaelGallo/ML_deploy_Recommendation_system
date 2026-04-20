#!/usr/bin/env bash
# deploy.sh - One-click deploy to free cloud
# Uso: bash deploy/deploy.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo "=================================="
echo "  Amazon Product Recommender"
echo "  Deploy to Free Cloud"
echo "=================================="
echo ""

# ── Load .env ─────────────────────────────────────────────────
if [ ! -f .env ]; then
    warn ".env nao encontrado. Copiando .env.example..."
    cp .env.example .env
    error "Preencha o .env com suas credenciais e rode novamente."
fi
set -a; source .env; set +a

# ── Validar variaveis obrigatorias ─────────────────────────────
for VAR in GCP_PROJECT_ID EMAIL_SENDER EMAIL_PASSWORD; do
    if [ -z "${!VAR:-}" ]; then
        error "$VAR nao esta definido no .env"
    fi
done

REGION=${REGION:-us-central1}
API_IMAGE="gcr.io/${GCP_PROJECT_ID}/recommender-api"

# ── Step 1: BigQuery ───────────────────────────────────────────
info "Step 1/5: Configurando BigQuery..."
python deploy/setup_bigquery.py "${GCP_PROJECT_ID}" && success "BigQuery pronto."

# ── Step 2: Build & Push API image ────────────────────────────
info "Step 2/5: Construindo imagem Docker da FastAPI..."
gcloud auth configure-docker --quiet
docker build -f api/Dockerfile -t "${API_IMAGE}:latest" .
docker push "${API_IMAGE}:latest"
success "Imagem enviada para o GCR."

# ── Step 3: Deploy API to Cloud Run ───────────────────────────
info "Step 3/5: Deploy da FastAPI no Cloud Run..."
gcloud run deploy recommender-api \
    --image "${API_IMAGE}:latest" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 1 \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 3 \
    --project "${GCP_PROJECT_ID}" \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},\
BQ_DATASET=${BQ_DATASET:-amazon_reviews},\
BQ_TABLE=${BQ_TABLE:-product_reviews},\
MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI:-},\
EMAIL_SENDER=${EMAIL_SENDER},\
EMAIL_PASSWORD=${EMAIL_PASSWORD},\
EMAIL_RECIPIENTS=${EMAIL_RECIPIENTS:-${EMAIL_SENDER}}" \
    --quiet

API_URL=$(gcloud run services describe recommender-api \
    --region "${REGION}" --format="value(status.url)")
success "FastAPI online: ${API_URL}"

# ── Step 4: Health check ───────────────────────────────────────
info "Step 4/5: Verificando saude da API..."
sleep 5
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/health")
if [ "$HTTP" != "200" ]; then
    error "Health check falhou (HTTP ${HTTP}). Verifique os logs do Cloud Run."
fi
success "API saudavel!"

# ── Step 5: Deploy Streamlit to Hugging Face ──────────────────
info "Step 5/5: Deploy Streamlit no Hugging Face Spaces..."
if [ -n "${HF_TOKEN:-}" ] && [ -n "${HF_USERNAME:-}" ]; then
    sed -i "s|API_URL_PLACEHOLDER|${API_URL}|g" huggingface_spaces/README.md
    mkdir -p hf_deploy
    cp streamlit_app/app.py hf_deploy/
    cp streamlit_app/requirements.txt hf_deploy/
    cp huggingface_spaces/README.md hf_deploy/
    cd hf_deploy
    git init -q
    git remote remove space 2>/dev/null || true
    git remote add space "https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${HF_USERNAME}/amazon-recommender"
    git add -A
    git -c user.email="deploy@local" -c user.name="Deploy" commit -qm "deploy"
    git push --force space main:main
    cd ..
    success "Streamlit online: https://huggingface.co/spaces/${HF_USERNAME}/amazon-recommender"
else
    warn "HF_TOKEN ou HF_USERNAME nao definidos - pulando HF Spaces."
fi

# ── Cloud Scheduler (retreinamento semanal) ───────────────────
info "Configurando retreinamento semanal..."
gcloud scheduler jobs create http retrain-weekly \
    --schedule="0 5 * * 1" \
    --uri="${API_URL}/retrain" \
    --message-body='{"source":"bigquery","notify":true}' \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --time-zone="America/Sao_Paulo" \
    --project="${GCP_PROJECT_ID}" \
    --location="${REGION}" \
    --quiet 2>/dev/null || warn "Job ja existe - ignorando."
success "Retreinamento agendado: toda segunda 02:00 BRT."

# ── Notificacao de deploy por email ───────────────────────────
python -c "
import smtplib
from email.mime.text import MIMEText
msg = MIMEText('Deploy concluido com sucesso!\n\nAPI: ${API_URL}\nProjeto: ${GCP_PROJECT_ID}')
msg['Subject'] = '[ML] Deploy Concluido'
msg['From'] = '${EMAIL_SENDER}'
msg['To'] = '${EMAIL_RECIPIENTS:-${EMAIL_SENDER}}'
with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login('${EMAIL_SENDER}', '${EMAIL_PASSWORD}')
    s.send_message(msg)
print('Email de deploy enviado.')
" && success "Email de notificacao enviado." || warn "Email nao enviado."

# ── Resumo ────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Deploy Concluido!"
echo "============================================"
echo ""
echo "  FastAPI  : ${API_URL}"
echo "  API Docs : ${API_URL}/docs"
if [ -n "${HF_USERNAME:-}" ]; then
echo "  Streamlit: https://huggingface.co/spaces/${HF_USERNAME}/amazon-recommender"
fi
echo "  MLflow   : ${MLFLOW_TRACKING_URI:-configure MLFLOW_TRACKING_URI}"
echo "  Email    : ${EMAIL_SENDER}"
echo ""
