"""
DAG: Ciclo de Vida Completo do Modelo
Agenda: toda sexta-feira às 18:00 BRT
Fluxo: validar dados → verificar necessidade de retrain → treinar →
       avaliar → registrar no MLflow → promover para produção → notificar
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow/project")

DEFAULT_ARGS = {
    "owner": "rafael",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": [os.getenv("EMAIL_RECIPIENTS", "").split(",")[0]],
}


@dag(
    dag_id="model_lifecycle",
    description="Ciclo de vida completo: dados → treino → avaliação → registro → produção",
    schedule_interval="0 18 * * 5",  # sexta-feira 18:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["lifecycle", "mlops", "knn", "ncf"],
)
def model_lifecycle():

    @task(task_id="check_data_freshness")
    def check_data_freshness() -> dict:
        """Verifica se há dados novos suficientes para justificar retreinamento."""
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")
        table = os.getenv("BQ_TABLE", "product_reviews")

        query = f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT asins) AS unique_products,
                COUNT(DISTINCT reviews_username) AS unique_users
            FROM `{dataset}.{table}`
        """
        row = list(client.query(query).result())[0]
        return {
            "total_rows": row["total_rows"],
            "unique_products": row["unique_products"],
            "unique_users": row["unique_users"],
            "has_enough_data": row["total_rows"] >= 500 and row["unique_products"] >= 10,
        }

    @task(task_id="check_current_model_metrics")
    def check_current_model_metrics() -> dict:
        """Busca as métricas do modelo atualmente em produção no MLflow."""
        import mlflow

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        client = mlflow.tracking.MlflowClient()

        runs = client.search_runs(
            experiment_ids=["1"],
            filter_string="",
            order_by=["start_time DESC"],
            max_results=1,
        )

        if not runs:
            return {
                "has_production_model": False,
                "precision_at_5": 0.0,
                "hit_rate_at_5": 0.0,
                "run_id": None,
            }

        last_run = runs[0]
        metrics = last_run.data.metrics
        return {
            "has_production_model": True,
            "precision_at_5": metrics.get("precision_at_5", 0.0),
            "hit_rate_at_5": metrics.get("hit_rate_at_5", 0.0),
            "run_id": last_run.info.run_id,
            "model_age_days": (
                datetime.now() - datetime.fromtimestamp(last_run.info.start_time / 1000)
            ).days,
        }

    @task(task_id="decide_retrain")
    def decide_retrain(data_check: dict, model_check: dict) -> dict:
        """Decide se o modelo precisa ser retreinado."""
        reasons = []

        if not model_check["has_production_model"]:
            reasons.append("Nenhum modelo em produção")
        if not data_check["has_enough_data"]:
            reasons.append("Dados insuficientes para retreinamento")
            return {"should_retrain": False, "reasons": reasons}

        age = model_check.get("model_age_days", 0)
        precision = model_check.get("precision_at_5", 1.0)
        hit_rate = model_check.get("hit_rate_at_5", 1.0)

        if age > 30:
            reasons.append(f"Modelo com {age} dias (limite: 30 dias)")
        if precision < 0.60:
            reasons.append(f"Precision@5 baixo: {precision:.4f} (limite: 0.60)")
        if hit_rate < 0.85:
            reasons.append(f"Hit Rate@5 baixo: {hit_rate:.4f} (limite: 0.85)")

        should_retrain = len(reasons) > 0

        return {
            "should_retrain": should_retrain,
            "reasons": reasons,
            "data": data_check,
            "model": model_check,
        }

    @task(task_id="retrain_model", trigger_rule="all_success")
    def retrain_model(decision: dict) -> dict:
        """Executa o retreinamento se necessário."""
        if not decision["should_retrain"]:
            return {"skipped": True, "message": "Retreinamento não necessário."}

        sys.path.insert(0, f"{PROJECT_ROOT}/retrain")
        from retrain_pipeline import RetrainPipeline

        pipeline = RetrainPipeline()
        run_id = pipeline.run(source="bigquery")
        return {"skipped": False, "run_id": run_id}

    @task(task_id="register_model")
    def register_model(retrain_result: dict) -> dict:
        """Registra o novo modelo no MLflow Model Registry."""
        if retrain_result.get("skipped"):
            return {"skipped": True}

        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        client = MlflowClient()
        run_id = retrain_result["run_id"]

        model_uri = f"runs:/{run_id}/knn_model"
        model_name = "knn-recommender"

        try:
            client.create_registered_model(model_name)
        except Exception:
            pass

        mv = client.create_model_version(
            name=model_name,
            source=model_uri,
            run_id=run_id,
            description=f"Treinado em {datetime.now().strftime('%Y-%m-%d')} via Airflow",
        )

        return {
            "skipped": False,
            "model_name": model_name,
            "version": mv.version,
            "run_id": run_id,
        }

    @task(task_id="promote_to_production")
    def promote_to_production(register_result: dict) -> dict:
        """Promove o modelo para o estágio 'Production' no MLflow."""
        if register_result.get("skipped"):
            return {"skipped": True}

        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        client = MlflowClient()

        client.transition_model_version_stage(
            name=register_result["model_name"],
            version=register_result["version"],
            stage="Production",
            archive_existing_versions=True,
        )

        return {
            "skipped": False,
            "model_name": register_result["model_name"],
            "version": register_result["version"],
            "stage": "Production",
        }

    @task(task_id="send_lifecycle_report")
    def send_lifecycle_report(decision: dict, promote_result: dict):
        """Envia relatório completo do ciclo de vida."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        if not decision["should_retrain"]:
            subject = "[ML] Ciclo de Vida — Modelo OK (sem mudanças)"
            msg = (
                f"Verificação semanal concluída.\n\n"
                f"Status: Modelo em produção sem necessidade de atualização.\n"
                f"Precision@5 atual: {decision['model'].get('precision_at_5', 'N/A')}\n"
                f"Hit Rate@5 atual: {decision['model'].get('hit_rate_at_5', 'N/A')}\n"
                f"Idade do modelo: {decision['model'].get('model_age_days', '?')} dias\n"
            )
        else:
            subject = "[ML] Ciclo de Vida — Novo Modelo em Produção"
            msg = (
                f"Ciclo de vida executado com sucesso!\n\n"
                f"Motivos do retreinamento:\n"
                + "\n".join(f"  - {r}" for r in decision["reasons"])
                + f"\n\nNovo modelo:\n"
                f"  Nome: {promote_result.get('model_name', 'N/A')}\n"
                f"  Versão: {promote_result.get('version', 'N/A')}\n"
                f"  Stage: {promote_result.get('stage', 'N/A')}\n"
                f"  Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            )

        AlertManager().send_all(subject, msg)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    data = check_data_freshness()
    model = check_current_model_metrics()
    decision = decide_retrain(data, model)
    retrained = retrain_model(decision)
    registered = register_model(retrained)
    promoted = promote_to_production(registered)
    send_lifecycle_report(decision, promoted)


lifecycle_dag = model_lifecycle()
