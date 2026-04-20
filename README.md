# Amazon Product Recommender

Sistema de recomendacao de produtos da Amazon com KNN e Neural Collaborative Filtering.

Este Space usa Docker para rodar dois servicos no mesmo container:

- FastAPI interna em `127.0.0.1:8000`
- Streamlit publico na porta `7860`

## Arquivos usados no deploy

- `Dockerfile`
- `docker/start_huggingface.py`
- `docker/requirements-huggingface.txt`
- `api/`
- `streamlit_app/`
- `models/`
- `output/df_products.csv`


## BigQuery no Hugging Face

Para retreinar usando BigQuery no Space, configure estas variaveis em Settings:

- `GCP_PROJECT_ID`
- `BQ_DATASET`
- `BQ_TABLE`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` ou `GOOGLE_APPLICATION_CREDENTIALS_B64`
- `MLFLOW_TRACKING_URI`, opcional

Use `GOOGLE_APPLICATION_CREDENTIALS_JSON` como Secret com o conteudo completo do JSON da service account. Nao envie o arquivo `config/*.json` para o repositorio publico.

