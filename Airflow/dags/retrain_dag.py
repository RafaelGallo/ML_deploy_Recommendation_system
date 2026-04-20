"""
DAG: Amazon Product Recommender — Retreinamento Semanal
Agenda: toda segunda-feira às 16:00 BRT
Pipeline: BigQuery → Pré-processamento → KNN → MLflow → Alertas
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow/project")

DEFAULT_ARGS = {
    "owner": "rafael",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": [os.getenv("EMAIL_RECIPIENTS", "").split(",")[0]],
}


@dag(
    dag_id="amazon_recommender_retrain",
    description="Retreinamento semanal do modelo KNN de recomendação de produtos",
    schedule_interval="0 16 * * 1",  # segunda-feira 16:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ml", "recommendation", "knn", "bigquery"],
    doc_md=__doc__,
)
def retrain_pipeline():

    @task(task_id="extract_bigquery")
    def extract_from_bigquery() -> dict:
        """Carrega dados de reviews da Amazon do BigQuery."""
        sys.path.insert(0, f"{PROJECT_ROOT}/retrain")
        from bigquery_pipeline import BigQueryPipeline

        pipeline = BigQueryPipeline()
        df = pipeline.load(source="bigquery")

        output_path = f"{PROJECT_ROOT}/output/df_products_retrain.csv"
        df.to_csv(output_path, index=False)

        logger.info(f"Extraídos {len(df)} produtos do BigQuery")
        return {
            "n_products": len(df),
            "output_path": output_path,
            "columns": list(df.columns),
        }

    @task(task_id="validate_data")
    def validate_data(extract_result: dict) -> dict:
        """Valida qualidade dos dados antes do retreinamento."""
        import pandas as pd

        df = pd.read_csv(extract_result["output_path"])
        issues = []

        if len(df) < 10:
            issues.append(f"Poucos produtos: {len(df)} (mínimo: 10)")
        if df["avg_rating"].isna().sum() / len(df) > 0.5:
            issues.append("Mais de 50% de avg_rating nulo")
        if df["all_reviews"].isna().sum() / len(df) > 0.5:
            issues.append("Mais de 50% de reviews nulas")

        if issues:
            raise ValueError(f"Validação falhou: {'; '.join(issues)}")

        logger.info(f"Dados válidos: {len(df)} produtos, {df['review_count'].sum():.0f} reviews totais")
        return {**extract_result, "valid": True, "n_products": len(df)}

    @task(task_id="retrain_knn")
    def retrain_knn(validate_result: dict) -> dict:
        """Retreina o modelo KNN com os novos dados."""
        import pandas as pd
        sys.path.insert(0, f"{PROJECT_ROOT}/retrain")
        from retrain_pipeline import RetrainPipeline

        pipeline = RetrainPipeline()
        df = pd.read_csv(validate_result["output_path"])
        df = pipeline.preprocess(df)

        feature_matrix, tfidf, scaler = pipeline.build_features(df)
        knn_model = pipeline.train_knn(feature_matrix, n_neighbors=20)
        metrics = pipeline.evaluate_knn(knn_model, feature_matrix, df)

        import mlflow
        import mlflow.sklearn
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        mlflow.set_experiment("amazon-product-recommender")

        with mlflow.start_run(run_name=f"airflow-retrain-{datetime.now().strftime('%Y%m%d')}") as run:
            mlflow.log_param("n_neighbors", 20)
            mlflow.log_param("tfidf_max_features", 500)
            mlflow.log_param("metric", "cosine")
            mlflow.log_param("n_products", len(df))
            mlflow.log_param("triggered_by", "airflow")
            mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(knn_model, "knn_model")
            run_id = run.info.run_id

        pipeline.save_artifacts(knn_model, feature_matrix, tfidf, scaler, df)

        logger.info(f"Retreinamento concluído. Run ID MLflow: {run_id}")
        return {**metrics, "run_id": run_id, "n_products": len(df)}

    @task(task_id="evaluate_model")
    def evaluate_model(retrain_result: dict) -> dict:
        """Valida se as métricas do novo modelo são aceitáveis."""
        min_precision = float(os.getenv("MIN_PRECISION_AT_5", "0.50"))
        min_hit_rate = float(os.getenv("MIN_HIT_RATE_AT_5", "0.80"))

        precision = retrain_result.get("precision_at_5", 0)
        hit_rate = retrain_result.get("hit_rate_at_5", 0)

        logger.info(f"Métricas — Precision@5: {precision:.4f}, Hit Rate@5: {hit_rate:.4f}")

        if precision < min_precision:
            raise ValueError(
                f"Precision@5 {precision:.4f} abaixo do mínimo {min_precision}"
            )
        if hit_rate < min_hit_rate:
            raise ValueError(
                f"Hit Rate@5 {hit_rate:.4f} abaixo do mínimo {min_hit_rate}"
            )

        logger.info("Modelo aprovado na avaliação!")
        return {**retrain_result, "approved": True}

    @task(task_id="send_success_alert")
    def send_success_alert(eval_result: dict):
        """Envia alerta de sucesso via Email e Telegram."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        alert = AlertManager()
        alert.notify_retrain_complete(
            run_id=eval_result["run_id"],
            metrics={
                "precision_at_5": eval_result.get("precision_at_5"),
                "f1_at_5": eval_result.get("f1_at_5"),
                "hit_rate_at_5": eval_result.get("hit_rate_at_5"),
            },
        )
        logger.info("Alerta de sucesso enviado.")

    # ── Pipeline ──────────────────────────────────────────────────────────────
    extract = extract_from_bigquery()
    validated = validate_data(extract)
    retrained = retrain_knn(validated)
    evaluated = evaluate_model(retrained)
    send_success_alert(evaluated)


retrain_dag = retrain_pipeline()
