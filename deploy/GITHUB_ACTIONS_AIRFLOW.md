# GitHub Actions With Optional Airflow

This project can use GitHub Actions as the free scheduler for retraining.
Airflow is kept as an optional DAG for environments where a persistent
Airflow server exists.

## Recommended Setup

- Hugging Face Space runs Streamlit and FastAPI.
- GitHub Actions runs `retrain/retrain_pipeline.py` on a schedule.
- The workflow uploads refreshed artifacts back to the Hugging Face Space.
- MLflow logs are stored as GitHub Actions artifacts for each run.

## Why Airflow Is Optional

GitHub Actions does not host a persistent Airflow webserver, scheduler, or
metadata database. It can validate a DAG file and run the same Python pipeline,
but a real Airflow UI needs another always-on platform.

## Required GitHub Secrets

Create these secrets in the GitHub repository:

- `HF_TOKEN`: Hugging Face token with write permission to the Space.
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`: Google service account JSON for
  BigQuery access.

If you train from CSV instead of BigQuery, `GOOGLE_APPLICATION_CREDENTIALS_JSON`
is not required.

## Workflow

File:

- `.github/workflows/retrain-huggingface.yml`

It runs every Monday at 08:00 UTC and can also be started manually from the
GitHub Actions tab.

Manual inputs:

- `source`: `bigquery` or `csv`.
- `table_id`: optional full BigQuery table id.
- `allow_csv_fallback`: optional fallback to local CSV.

## Optional Airflow DAG

File:

- `Airflow/dags/huggingface_retrain_dag.py`

This DAG runs the same retraining command and the same Hugging Face upload
script. Use it only if you later deploy Airflow on another platform.

## Shared Upload Script

File:

- `scripts/upload_hf_artifacts.py`

Uploaded artifacts:

- `models/knn_model.pkl`
- `models/feature_matrix.pkl`
- `models/tfidf_vectorizer.pkl`
- `models/scaler.pkl`
- `output/df_products.csv`
