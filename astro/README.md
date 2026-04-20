# Astro Airflow Deployment

This folder is the Astronomer project for the recommender retraining flow.

Use this folder as the **Astro Project Path** when connecting GitHub to
Astronomer:

```text
astro
```

## Required Environment Variables

Configure these in the Astronomer deployment:

- `HF_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `HF_SPACE_REPO`
- `GCP_PROJECT_ID`
- `BQ_DATASET`
- `BQ_TABLE`

Recommended values:

```text
HF_SPACE_REPO=gallorafael22/Model_ml_mlops_Recommendation_system
GCP_PROJECT_ID=samara-a2d79
BQ_DATASET=amazon_reviews
BQ_TABLE=product_reviews
```

## DAG

- `huggingface_recommender_retrain`

The DAG retrains the recommender from BigQuery or CSV, uploads the updated
artifacts to the Hugging Face Space, and requests a Space restart.
