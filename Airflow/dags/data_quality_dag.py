"""
DAG: Monitoramento de Qualidade dos Dados
Agenda: diariamente às 19:00 BRT
Verifica o BigQuery e alerta se houver anomalias nos dados.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow/project")

DEFAULT_ARGS = {
    "owner": "rafael",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": True,
    "email": [os.getenv("EMAIL_RECIPIENTS", "").split(",")[0]],
}


@dag(
    dag_id="amazon_data_quality_check",
    description="Verificação diária de qualidade dos dados no BigQuery",
    schedule_interval="0 19 * * *",  # 19:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["data-quality", "bigquery", "monitoring"],
)
def data_quality_pipeline():

    @task(task_id="check_bigquery_table")
    def check_bigquery_table() -> dict:
        """Verifica volume e qualidade da tabela no BigQuery."""
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")
        table = os.getenv("BQ_TABLE", "product_reviews")

        query = f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT asins) AS unique_products,
                COUNT(DISTINCT reviews_username) AS unique_users,
                AVG(CAST(reviews_rating AS FLOAT64)) AS avg_rating,
                COUNTIF(reviews_text IS NULL) AS null_reviews,
                MAX(PARSE_DATE('%Y-%m-%d', SUBSTR(dateAdded, 1, 10))) AS latest_date
            FROM `{dataset}.{table}`
        """

        row = list(client.query(query).result())[0]
        stats = {
            "total_rows": row["total_rows"],
            "unique_products": row["unique_products"],
            "unique_users": row["unique_users"],
            "avg_rating": round(float(row["avg_rating"] or 0), 2),
            "null_reviews": row["null_reviews"],
            "latest_date": str(row["latest_date"]),
        }

        return stats

    @task(task_id="validate_thresholds")
    def validate_thresholds(stats: dict) -> dict:
        """Verifica se os dados estão dentro dos limites esperados."""
        alerts = []

        if stats["total_rows"] < 1000:
            alerts.append(f"Volume baixo: {stats['total_rows']} rows (esperado >= 1000)")
        if stats["unique_products"] < 30:
            alerts.append(f"Poucos produtos: {stats['unique_products']} (esperado >= 30)")
        if stats["null_reviews"] / max(stats["total_rows"], 1) > 0.3:
            alerts.append(f"Muitas reviews nulas: {stats['null_reviews']}")
        if stats["avg_rating"] < 1.0 or stats["avg_rating"] > 5.0:
            alerts.append(f"Rating médio fora do range: {stats['avg_rating']}")

        return {**stats, "alerts": alerts, "healthy": len(alerts) == 0}

    @task(task_id="send_quality_report")
    def send_quality_report(result: dict):
        """Envia relatório diário de qualidade."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        status = "✅ OK" if result["healthy"] else "⚠️ ATENÇÃO"
        subject = f"[ML] {status} — Relatório Diário de Dados"
        message = (
            f"Relatório de Qualidade — {datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"Total de reviews: {result['total_rows']:,}\n"
            f"Produtos únicos: {result['unique_products']}\n"
            f"Usuários únicos: {result['unique_users']}\n"
            f"Rating médio: {result['avg_rating']}\n"
            f"Reviews nulas: {result['null_reviews']}\n"
            f"Data mais recente: {result['latest_date']}\n"
        )

        if result["alerts"]:
            message += f"\nProblemas encontrados:\n"
            for a in result["alerts"]:
                message += f"  - {a}\n"

        AlertManager().send_all(subject, message)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    stats = check_bigquery_table()
    validated = validate_thresholds(stats)
    send_quality_report(validated)


quality_dag = data_quality_pipeline()
