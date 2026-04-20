PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION     ?= us-central1
API_IMAGE  := gcr.io/$(PROJECT_ID)/recommender-api
API_SERVICE := recommender-api
UI_SERVICE  := recommender-streamlit

.PHONY: help build up down logs test deploy-api deploy-ui bigquery-setup

help:
	@echo ""
	@echo "Amazon Product Recommender — Deploy Commands"
	@echo "============================================"
	@echo "  make build          Build all Docker images locally"
	@echo "  make up             Start all services (local)"
	@echo "  make down           Stop all services"
	@echo "  make logs           Tail logs from all containers"
	@echo "  make test           Test API health and endpoints"
	@echo "  make deploy-api     Deploy FastAPI to Google Cloud Run"
	@echo "  make deploy-ui      Deploy Streamlit to Hugging Face Spaces"
	@echo "  make bigquery-setup Upload data to BigQuery"
	@echo "  make retrain        Trigger model retraining"
	@echo ""

build:
	docker-compose build

up:
	cp -n .env.example .env 2>/dev/null || true
	docker-compose up -d
	@echo ""
	@echo "Services running:"
	@echo "  FastAPI:   http://localhost:8000"
	@echo "  API Docs:  http://localhost:8000/docs"
	@echo "  Streamlit: http://localhost:8501"
	@echo "  MLflow:    http://localhost:5000"

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	@echo "Testing API health..."
	curl -s http://localhost:8000/health | python -m json.tool
	@echo ""
	@echo "Testing KNN recommendation..."
	curl -s -X POST http://localhost:8000/recommend/knn \
	  -H "Content-Type: application/json" \
	  -d '{"product_name": "Fire", "top_k": 3}' | python -m json.tool

deploy-api:
	@echo "Building and deploying FastAPI to Cloud Run..."
	gcloud builds submit \
	  --tag $(API_IMAGE) \
	  --project $(PROJECT_ID)
	gcloud run deploy $(API_SERVICE) \
	  --image $(API_IMAGE) \
	  --platform managed \
	  --region $(REGION) \
	  --allow-unauthenticated \
	  --memory 2Gi \
	  --cpu 1 \
	  --concurrency 80 \
	  --min-instances 0 \
	  --max-instances 3 \
	  --project $(PROJECT_ID) \
	  --set-env-vars="MLFLOW_TRACKING_URI=$(MLFLOW_URI),GCP_PROJECT_ID=$(PROJECT_ID)"
	@echo "API deployed!"
	gcloud run services describe $(API_SERVICE) --region $(REGION) --format="value(status.url)"

deploy-ui:
	@echo "Deploying Streamlit to Hugging Face Spaces..."
	@echo "Set HF_TOKEN and HF_USERNAME environment variables first."
	cd huggingface_spaces && \
	  git init && \
	  git remote add space https://$(HF_USERNAME):$(HF_TOKEN)@huggingface.co/spaces/$(HF_USERNAME)/amazon-recommender 2>/dev/null || true && \
	  cp ../streamlit_app/app.py . && \
	  cp ../streamlit_app/requirements.txt . && \
	  git add -A && \
	  git commit -m "deploy streamlit app" && \
	  git push --force space main
	@echo "Streamlit deployed to HF Spaces!"

bigquery-setup:
	@echo "Setting up BigQuery dataset and uploading data..."
	GCP_PROJECT_ID=$(PROJECT_ID) python deploy/setup_bigquery.py $(PROJECT_ID)

retrain:
	@echo "Triggering model retraining..."
	curl -s -X POST $(API_URL)/retrain \
	  -H "Content-Type: application/json" \
	  -d '{"source":"bigquery","notify":true}' | python -m json.tool
