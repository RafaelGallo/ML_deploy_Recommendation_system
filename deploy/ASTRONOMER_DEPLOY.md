# Deploy Airflow On Astronomer

Use the `astro/` folder as the Astronomer project.

## Recommended Deploy Method

Use the Astronomer GitHub integration.

In Astronomer:

1. Open your Workspace.
2. Open **Workspace Settings**.
3. Open **Git Deploys**.
4. Authorize GitHub.
5. Connect this repository:

```text
RafaelGallo/ML_deploy_Recommendation_system
```

6. Set **Astro Project Path** to:

```text
astro
```

7. Map branch `main` to your Airflow deployment.
8. Trigger the first deploy.

## Required Environment Variables

In the Astronomer deployment, configure:

```text
HF_TOKEN
GOOGLE_APPLICATION_CREDENTIALS_JSON
HF_SPACE_REPO
GCP_PROJECT_ID
BQ_DATASET
BQ_TABLE
```

Recommended values:

```text
HF_SPACE_REPO=gallorafael22/Model_ml_mlops_Recommendation_system
GCP_PROJECT_ID=samara-a2d79
BQ_DATASET=amazon_reviews
BQ_TABLE=product_reviews
```

Use the full Google service account JSON as the value for
`GOOGLE_APPLICATION_CREDENTIALS_JSON`. If the UI does not accept multiline
values, paste the JSON as one minified line.

## Access Airflow

After the deploy is healthy:

1. Open the deployment in Astronomer.
2. Click **Open Airflow**.
3. Find this DAG:

```text
huggingface_recommender_retrain
```

4. Enable the DAG.
5. Click **Trigger DAG** to test manually.

## What The DAG Does

```text
validate_project_root
run_retraining
upload_to_huggingface
```

The DAG retrains the KNN recommender, uploads updated artifacts to the
Hugging Face Space, and requests a Space restart.

## Files Used By Astronomer

```text
astro/Dockerfile
astro/requirements.txt
astro/packages.txt
astro/dags/huggingface_retrain_dag.py
astro/retrain/retrain_pipeline.py
astro/retrain/bigquery_pipeline.py
astro/scripts/upload_hf_artifacts.py
```
