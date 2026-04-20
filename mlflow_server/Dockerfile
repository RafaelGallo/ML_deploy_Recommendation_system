FROM python:3.11-slim

WORKDIR /mlflow

RUN pip install --no-cache-dir mlflow==2.18.0 google-cloud-storage==2.19.0 psycopg2-binary==2.9.10

ENV MLFLOW_BACKEND_STORE_URI=sqlite:///mlflow.db
ENV MLFLOW_ARTIFACT_ROOT=./mlartifacts
ENV PORT=5000

EXPOSE 5000

CMD mlflow server \
    --backend-store-uri ${MLFLOW_BACKEND_STORE_URI} \
    --default-artifact-root ${MLFLOW_ARTIFACT_ROOT} \
    --host 0.0.0.0 \
    --port ${PORT}
