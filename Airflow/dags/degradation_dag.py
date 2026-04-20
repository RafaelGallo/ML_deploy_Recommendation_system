"""
DAG: Detecção de Degradação do Modelo
Agenda: diariamente às 16:00 BRT
Compara métricas atuais com a baseline de produção.
Se detectar degradação significativa, alerta e aciona retreinamento automático.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.dates import days_ago

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow/project")

# Thresholds de degradação configuráveis
DEGRADATION_THRESHOLD = float(os.getenv("DEGRADATION_THRESHOLD", "0.10"))  # 10% de queda
MIN_PRECISION_HARD = float(os.getenv("MIN_PRECISION_HARD", "0.45"))         # limite absoluto
MIN_HIT_RATE_HARD = float(os.getenv("MIN_HIT_RATE_HARD", "0.75"))

DEFAULT_ARGS = {
    "owner": "rafael",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": True,
    "email": [os.getenv("EMAIL_RECIPIENTS", "").split(",")[0]],
}


@dag(
    dag_id="model_degradation_detection",
    description="Detecta degradação do modelo e aciona retreinamento automático",
    schedule_interval="0 16 * * *",  # 16:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["monitoring", "degradation", "drift", "mlops"],
)
def degradation_detection():

    @task(task_id="get_production_baseline")
    def get_production_baseline() -> dict:
        """Recupera as métricas da versão de produção atual no MLflow."""
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        client = MlflowClient()

        # Tenta buscar o modelo em produção
        try:
            versions = client.get_latest_versions("knn-recommender", stages=["Production"])
            if versions:
                run = client.get_run(versions[0].run_id)
                metrics = run.data.metrics
                return {
                    "source": "mlflow_production",
                    "precision_at_5": metrics.get("precision_at_5", 0.763),
                    "hit_rate_at_5": metrics.get("hit_rate_at_5", 1.0),
                    "f1_at_5": metrics.get("f1_at_5", 0.212),
                    "ndcg_at_5": metrics.get("knn_ndcg_at_5", 0.80),
                    "model_version": versions[0].version,
                }
        except Exception:
            pass

        # Fallback: métricas conhecidas do treinamento original
        return {
            "source": "hardcoded_baseline",
            "precision_at_5": 0.7630,
            "hit_rate_at_5": 1.0000,
            "f1_at_5": 0.2119,
            "ndcg_at_5": 0.80,
            "model_version": "baseline",
        }

    @task(task_id="compute_current_metrics")
    def compute_current_metrics() -> dict:
        """Calcula métricas do modelo atualmente carregado em memória."""
        import joblib
        import numpy as np
        import pandas as pd
        from pathlib import Path

        models_dir = Path(PROJECT_ROOT) / "models"
        data_path = Path(PROJECT_ROOT) / "output" / "df_products.csv"

        knn = joblib.load(models_dir / "knn_model.pkl")
        feature_matrix = joblib.load(models_dir / "feature_matrix.pkl")
        df = pd.read_csv(data_path)

        relevant_threshold = df["avg_rating"].quantile(0.6)
        k = 5
        precisions, hits, f1s, ndcg_scores = [], [], [], []

        for i in range(min(len(df), 30)):
            n_neighbors = min(k + 1, feature_matrix.shape[0])
            distances, indices = knn.kneighbors(feature_matrix[i], n_neighbors=n_neighbors)
            rec_idx = indices[0][1:]
            relevant = (df.iloc[rec_idx]["avg_rating"] >= relevant_threshold).values

            tp = relevant.sum()
            prec = tp / max(len(rec_idx), 1)
            rec_val = tp / max((df["avg_rating"] >= relevant_threshold).sum(), 1)
            f1 = 2 * prec * rec_val / max(prec + rec_val, 1e-8)
            hit = 1.0 if tp > 0 else 0.0

            dcg = sum(r / np.log2(i + 2) for i, r in enumerate(relevant))
            ideal = sum(1 / np.log2(i + 2) for i in range(min(int(tp), k)))
            ndcg = dcg / max(ideal, 1e-8)

            precisions.append(prec)
            hits.append(hit)
            f1s.append(f1)
            ndcg_scores.append(ndcg)

        return {
            "precision_at_5": round(float(np.mean(precisions)), 4),
            "hit_rate_at_5": round(float(np.mean(hits)), 4),
            "f1_at_5": round(float(np.mean(f1s)), 4),
            "ndcg_at_5": round(float(np.mean(ndcg_scores)), 4),
            "computed_at": datetime.now().isoformat(),
        }

    @task(task_id="detect_degradation")
    def detect_degradation(baseline: dict, current: dict) -> dict:
        """Compara métricas atuais com baseline e detecta degradação."""
        degradations = []
        alerts = []

        metrics_to_check = [
            ("precision_at_5", "Precision@5"),
            ("hit_rate_at_5", "Hit Rate@5"),
            ("ndcg_at_5", "NDCG@5"),
        ]

        for metric_key, metric_name in metrics_to_check:
            base_val = baseline.get(metric_key, 0)
            curr_val = current.get(metric_key, 0)

            if base_val > 0:
                drop_pct = (base_val - curr_val) / base_val
                if drop_pct > DEGRADATION_THRESHOLD:
                    degradations.append({
                        "metric": metric_name,
                        "baseline": base_val,
                        "current": curr_val,
                        "drop_pct": round(drop_pct * 100, 2),
                    })

        # Limites absolutos (mais críticos)
        if current["precision_at_5"] < MIN_PRECISION_HARD:
            alerts.append(f"CRÍTICO: Precision@5={current['precision_at_5']} abaixo do limite={MIN_PRECISION_HARD}")
        if current["hit_rate_at_5"] < MIN_HIT_RATE_HARD:
            alerts.append(f"CRÍTICO: Hit Rate@5={current['hit_rate_at_5']} abaixo do limite={MIN_HIT_RATE_HARD}")

        degraded = len(degradations) > 0 or len(alerts) > 0
        critical = len(alerts) > 0

        return {
            "degraded": degraded,
            "critical": critical,
            "degradations": degradations,
            "critical_alerts": alerts,
            "baseline": baseline,
            "current": current,
            "check_time": datetime.now().isoformat(),
        }

    @task(task_id="log_degradation_bigquery")
    def log_degradation_bigquery(result: dict):
        """Registra o resultado da verificação de degradação no BigQuery."""
        import pandas as pd
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")

        row = {
            "check_time": result["check_time"],
            "degraded": result["degraded"],
            "critical": result["critical"],
            "current_precision_at_5": result["current"].get("precision_at_5"),
            "current_hit_rate_at_5": result["current"].get("hit_rate_at_5"),
            "current_ndcg_at_5": result["current"].get("ndcg_at_5"),
            "baseline_precision_at_5": result["baseline"].get("precision_at_5"),
            "n_degradations": len(result["degradations"]),
            "n_critical": len(result["critical_alerts"]),
        }

        df = pd.DataFrame([row])
        table_id = f"{os.getenv('GCP_PROJECT_ID', 'samara-a2d79')}.{dataset}.degradation_history"
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            autodetect=True,
        )
        client.load_table_from_dataframe(df, table_id, job_config=job_config).result()

    @task(task_id="send_degradation_alert", trigger_rule="all_success")
    def send_degradation_alert(result: dict):
        """Envia alerta se houver degradação detectada."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        if not result["degraded"]:
            return

        severity = "❌ CRÍTICO" if result["critical"] else "⚠️ ATENÇÃO"
        subject = f"[ML] {severity} — Degradação do Modelo Detectada"

        lines = [
            f"Degradação detectada em {result['check_time']}\n",
            f"Métricas atuais vs baseline:",
            f"  Precision@5: {result['current']['precision_at_5']} (baseline: {result['baseline']['precision_at_5']})",
            f"  Hit Rate@5:  {result['current']['hit_rate_at_5']} (baseline: {result['baseline']['hit_rate_at_5']})",
            f"  NDCG@5:      {result['current']['ndcg_at_5']} (baseline: {result['baseline']['ndcg_at_5']})",
            "",
        ]

        if result["degradations"]:
            lines.append("Quedas relativas detectadas:")
            for d in result["degradations"]:
                lines.append(f"  - {d['metric']}: queda de {d['drop_pct']}%")

        if result["critical_alerts"]:
            lines.append("\nAlertas críticos:")
            for a in result["critical_alerts"]:
                lines.append(f"  - {a}")

        lines.append("\nAção: retreinamento automático acionado.")
        AlertManager().send_all(subject, "\n".join(lines))

    @task(task_id="trigger_retrain_if_critical", trigger_rule="all_success")
    def trigger_retrain_if_critical(result: dict):
        """Aciona retreinamento automático se a degradação for crítica."""
        if not result["critical"]:
            return {"triggered": False}

        sys.path.insert(0, f"{PROJECT_ROOT}/retrain")
        from retrain_pipeline import RetrainPipeline

        pipeline = RetrainPipeline()
        run_id = pipeline.run(source="bigquery")

        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager
        AlertManager().notify_retrain_complete(
            run_id=run_id,
            metrics=result["current"],
        )
        return {"triggered": True, "run_id": run_id}

    # ── Pipeline ──────────────────────────────────────────────────────────────
    baseline = get_production_baseline()
    current = compute_current_metrics()
    result = detect_degradation(baseline, current)
    log_degradation_bigquery(result)
    send_degradation_alert(result)
    trigger_retrain_if_critical(result)


degradation_dag = degradation_detection()
