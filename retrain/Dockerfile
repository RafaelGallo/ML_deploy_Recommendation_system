FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY retrain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY retrain/ /app/
COPY alerts/ /app/alerts/
COPY models/ /app/models/
COPY output/ /app/output/

ENV MODELS_DIR=/app/models
ENV DATA_PATH=/app/output/df_products.csv

CMD ["python", "retrain_pipeline.py"]
