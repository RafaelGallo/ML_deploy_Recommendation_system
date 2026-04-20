FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ /app/
COPY alerts/ /app/alerts/
COPY retrain/ /app/retrain/
COPY models/ /app/models/
COPY output/df_products.csv /app/output/df_products.csv

ENV MODELS_DIR=/app/models
ENV DATA_PATH=/app/output/df_products.csv
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
