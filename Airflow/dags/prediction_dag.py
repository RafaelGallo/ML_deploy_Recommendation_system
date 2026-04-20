"""
DAG: Previsão em Lote (Batch Prediction)
Agenda: diário às 18:00 BRT
Gera recomendações para todos os produtos (KNN) e usuários ativos (NCF),
salva os resultados no BigQuery para consumo pela API.
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
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": [os.getenv("EMAIL_RECIPIENTS", "").split(",")[0]],
}


@dag(
    dag_id="batch_prediction",
    description="Gera recomendações em lote para todos produtos e usuários ativos",
    schedule_interval="0 18 * * *",  # 18:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["prediction", "batch", "knn", "ncf", "bigquery"],
)
def batch_prediction():

    @task(task_id="load_active_users")
    def load_active_users() -> dict:
        """Carrega usuários ativos dos últimos 90 dias do BigQuery."""
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")
        table = os.getenv("BQ_TABLE", "product_reviews")

        query = f"""
            SELECT DISTINCT reviews_username AS user_id
            FROM `{dataset}.{table}`
            WHERE reviews_username IS NOT NULL
            ORDER BY user_id
            LIMIT 500
        """
        rows = list(client.query(query).result())
        users = [r["user_id"] for r in rows]
        return {"users": users, "count": len(users)}

    @task(task_id="generate_knn_predictions")
    def generate_knn_predictions() -> dict:
        """Gera top-10 recomendações KNN para todos os produtos."""
        import joblib
        import pandas as pd
        from pathlib import Path

        models_dir = Path(PROJECT_ROOT) / "models"
        data_path = Path(PROJECT_ROOT) / "output" / "df_products.csv"

        knn = joblib.load(models_dir / "knn_model.pkl")
        feature_matrix = joblib.load(models_dir / "feature_matrix.pkl")
        df = pd.read_csv(data_path)

        records = []
        run_date = datetime.now().strftime("%Y-%m-%d")

        for idx in range(len(df)):
            product_row = df.iloc[idx]
            n_neighbors = min(11, feature_matrix.shape[0])
            distances, indices = knn.kneighbors(feature_matrix[idx], n_neighbors=n_neighbors)

            for rank, (dist, rec_idx) in enumerate(
                zip(distances[0][1:], indices[0][1:]), start=1
            ):
                rec_row = df.iloc[rec_idx]
                records.append({
                    "source_asin": str(product_row.get("asins", "")),
                    "source_product": str(product_row.get("name", "")),
                    "recommended_asin": str(rec_row.get("asins", "")),
                    "recommended_product": str(rec_row.get("name", "")),
                    "rank": rank,
                    "similarity_score": round(float(1 - dist), 4),
                    "model": "knn",
                    "run_date": run_date,
                })

        output_path = f"{PROJECT_ROOT}/output/knn_predictions_{run_date}.csv"
        pd.DataFrame(records).to_csv(output_path, index=False)

        return {"output_path": output_path, "total_records": len(records), "model": "knn"}

    @task(task_id="generate_ncf_predictions")
    def generate_ncf_predictions(active_users: dict) -> dict:
        """Gera top-10 recomendações NCF para todos os usuários ativos."""
        import joblib
        import numpy as np
        import pandas as pd
        from pathlib import Path

        models_dir = Path(PROJECT_ROOT) / "models"
        data_path = Path(PROJECT_ROOT) / "output" / "df_products.csv"

        try:
            import tensorflow as tf

            ncf = tf.keras.models.load_model(models_dir / "ncf_model.keras")
            user_enc = joblib.load(models_dir / "user_encoder.pkl")
            prod_enc = joblib.load(models_dir / "product_encoder.pkl")
            rating_scaler = joblib.load(models_dir / "rating_scaler.pkl")
            df_products = pd.read_csv(data_path)

            known_users = set(user_enc.classes_)
            users = [u for u in active_users["users"] if u in known_users]
            n_products = len(prod_enc.classes_)
            run_date = datetime.now().strftime("%Y-%m-%d")
            top_k = 10
            records = []

            for user_id in users[:200]:
                user_idx = user_enc.transform([user_id])[0]
                user_arr = np.array([user_idx] * n_products)
                prod_arr = np.arange(n_products)
                preds = ncf.predict([user_arr, prod_arr], verbose=0).flatten()
                preds_denorm = rating_scaler.inverse_transform(preds.reshape(-1, 1)).flatten()
                top_indices = preds_denorm.argsort()[::-1][:top_k]
                product_asins = prod_enc.inverse_transform(top_indices)

                for rank, (asin, score) in enumerate(
                    zip(product_asins, preds_denorm[top_indices]), start=1
                ):
                    row = df_products[df_products["asins"] == asin]
                    name = row["name"].values[0] if not row.empty else asin
                    records.append({
                        "user_id": user_id,
                        "recommended_asin": asin,
                        "recommended_product": name,
                        "rank": rank,
                        "predicted_rating": round(float(score), 4),
                        "model": "ncf",
                        "run_date": run_date,
                    })

            output_path = f"{PROJECT_ROOT}/output/ncf_predictions_{run_date}.csv"
            pd.DataFrame(records).to_csv(output_path, index=False)
            return {"output_path": output_path, "total_records": len(records), "model": "ncf"}

        except Exception as e:
            return {"error": str(e), "total_records": 0, "model": "ncf"}

    @task(task_id="save_predictions_bigquery")
    def save_predictions_bigquery(knn_result: dict, ncf_result: dict):
        """Salva todas as previsões no BigQuery."""
        import pandas as pd
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=True,
        )

        if knn_result.get("output_path"):
            df_knn = pd.read_csv(knn_result["output_path"])
            client.load_table_from_dataframe(
                df_knn,
                f"{os.getenv('GCP_PROJECT_ID', 'samara-a2d79')}.{dataset}.knn_recommendations",
                job_config=job_config,
            ).result()

        if ncf_result.get("output_path"):
            df_ncf = pd.read_csv(ncf_result["output_path"])
            client.load_table_from_dataframe(
                df_ncf,
                f"{os.getenv('GCP_PROJECT_ID', 'samara-a2d79')}.{dataset}.ncf_recommendations",
                job_config=bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                    autodetect=True,
                ),
            ).result()

        return {
            "knn_saved": knn_result.get("total_records", 0),
            "ncf_saved": ncf_result.get("total_records", 0),
        }

    @task(task_id="send_prediction_report")
    def send_prediction_report(save_result: dict, knn_result: dict):
        """Envia resumo do batch de previsões."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        subject = f"[ML] Previsões em Lote — {datetime.now().strftime('%d/%m/%Y')}"
        msg = (
            f"Batch de previsões concluído!\n\n"
            f"KNN Recomendações salvas: {save_result.get('knn_saved', 0):,}\n"
            f"NCF Recomendações salvas: {save_result.get('ncf_saved', 0):,}\n"
            f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"Recomendações disponíveis no BigQuery:\n"
            f"  - amazon_reviews.knn_recommendations\n"
            f"  - amazon_reviews.ncf_recommendations\n"
        )
        AlertManager().send_all(subject, msg)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    users = load_active_users()
    knn_preds = generate_knn_predictions()
    ncf_preds = generate_ncf_predictions(users)
    saved = save_predictions_bigquery(knn_preds, ncf_preds)
    send_prediction_report(saved, knn_preds)


prediction_dag = batch_prediction()
