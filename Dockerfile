FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODELS_DIR=/home/user/app/models \
    DATA_PATH=/home/user/app/output/df_products.csv \
    API_URL=http://127.0.0.1:8000 \
    MLFLOW_TRACKING_URI=file:/tmp/mlruns \
    MLFLOW_FALLBACK_TRACKING_URI=file:/tmp/mlruns \
    PORT=7860

RUN useradd -m -u 1000 user

WORKDIR /home/user/app
RUN chown -R user:user /home/user/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements-huggingface.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY --chown=user api/ ./api/
COPY --chown=user alerts/ ./alerts/
COPY --chown=user retrain/ ./retrain/
COPY --chown=user streamlit_app/ ./streamlit_app/
COPY --chown=user models/ ./models/
COPY --chown=user output/df_products.csv ./output/df_products.csv
COPY --chown=user docker/start_huggingface.py ./docker/start_huggingface.py

USER user

EXPOSE 7860

CMD ["python", "docker/start_huggingface.py"]
