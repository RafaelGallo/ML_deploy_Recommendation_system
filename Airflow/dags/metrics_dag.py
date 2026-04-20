"""
DAG: Métricas do Modelo
Agenda: diário às 13:00 BRT
Calcula métricas KNN e NCF, salva no BigQuery, loga no MLflow,
envia relatório por Email e Telegram.
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
    dag_id="model_metrics",
    description="Calcula métricas KNN e NCF diariamente e envia relatório",
    schedule_interval="0 13 * * *",  # 13:00 BRT
    start_date=days_ago(1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["metrics", "knn", "ncf", "monitoring"],
)
def metrics_pipeline():

    @task(task_id="compute_knn_metrics")
    def compute_knn_metrics() -> dict:
        """Calcula métricas do modelo KNN (Precision, Recall, F1, Hit Rate, NDCG)."""
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
        ks = [1, 3, 5, 10]
        results = {}

        for k in ks:
            precisions, recalls, f1s, hits, ndcg_scores = [], [], [], [], []
            n_relevant_total = (df["avg_rating"] >= relevant_threshold).sum()

            for i in range(min(len(df), 30)):
                n_neighbors = min(k + 1, feature_matrix.shape[0])
                distances, indices = knn.kneighbors(feature_matrix[i], n_neighbors=n_neighbors)
                rec_idx = indices[0][1:]
                sims = 1 - distances[0][1:]

                relevant = (df.iloc[rec_idx]["avg_rating"] >= relevant_threshold).values
                tp = relevant.sum()

                prec = tp / len(rec_idx) if rec_idx.size > 0 else 0
                rec = tp / max(n_relevant_total, 1)
                f1 = 2 * prec * rec / max(prec + rec, 1e-8)
                hit = 1.0 if tp > 0 else 0.0

                # NDCG
                dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevant))
                ideal = sum(1 / np.log2(i + 2) for i in range(min(int(tp), k)))
                ndcg = dcg / max(ideal, 1e-8)

                precisions.append(prec)
                recalls.append(rec)
                f1s.append(f1)
                hits.append(hit)
                ndcg_scores.append(ndcg)

            results[f"knn_precision_at_{k}"] = round(float(np.mean(precisions)), 4)
            results[f"knn_recall_at_{k}"] = round(float(np.mean(recalls)), 4)
            results[f"knn_f1_at_{k}"] = round(float(np.mean(f1s)), 4)
            results[f"knn_hit_rate_at_{k}"] = round(float(np.mean(hits)), 4)
            results[f"knn_ndcg_at_{k}"] = round(float(np.mean(ndcg_scores)), 4)

        # Cobertura de catálogo
        results["knn_catalog_coverage"] = round(len(df) / max(len(df), 1), 4)
        results["knn_n_products"] = len(df)
        results["computed_at"] = datetime.now().isoformat()

        return results

    @task(task_id="compute_ncf_metrics")
    def compute_ncf_metrics() -> dict:
        """Calcula métricas do modelo NCF (RMSE, MAE, R², Precision, Recall, F1)."""
        import joblib
        import numpy as np
        import pandas as pd
        from pathlib import Path

        models_dir = Path(PROJECT_ROOT) / "models"

        try:
            import tensorflow as tf

            ncf = tf.keras.models.load_model(models_dir / "ncf_model.keras")
            user_enc = joblib.load(models_dir / "user_encoder.pkl")
            prod_enc = joblib.load(models_dir / "product_encoder.pkl")
            rating_scaler = joblib.load(models_dir / "rating_scaler.pkl")
            data_path = Path(PROJECT_ROOT) / "input" / "7817_1.csv"
            df_raw = pd.read_csv(data_path, low_memory=False)

            df_raw = df_raw[["reviews.username", "asins", "reviews.rating"]].dropna()
            df_raw.columns = ["user", "asin", "rating"]
            df_raw = df_raw[
                df_raw["user"].isin(user_enc.classes_) &
                df_raw["asin"].isin(prod_enc.classes_)
            ].sample(min(500, len(df_raw)), random_state=42)

            user_ids = user_enc.transform(df_raw["user"])
            prod_ids = prod_enc.transform(df_raw["asin"])
            y_true = df_raw["rating"].values.astype(float)

            preds = ncf.predict([user_ids, prod_ids], verbose=0).flatten()
            y_pred = rating_scaler.inverse_transform(preds.reshape(-1, 1)).flatten()
            y_pred = np.clip(y_pred, 1, 5)

            rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
            mae = float(np.mean(np.abs(y_true - y_pred)))
            ss_res = np.sum((y_true - y_pred) ** 2)
            ss_tot = np.sum((y_true - y_true.mean()) ** 2)
            r2 = float(1 - ss_res / max(ss_tot, 1e-8))

            y_true_bin = (y_true >= 4.0).astype(int)
            y_pred_bin = (y_pred >= 4.0).astype(int)
            tp = ((y_pred_bin == 1) & (y_true_bin == 1)).sum()
            fp = ((y_pred_bin == 1) & (y_true_bin == 0)).sum()
            fn = ((y_pred_bin == 0) & (y_true_bin == 1)).sum()
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = 2 * precision * recall / max(precision + recall, 1e-8)

            return {
                "ncf_rmse": round(rmse, 4),
                "ncf_mae": round(mae, 4),
                "ncf_r2": round(r2, 4),
                "ncf_precision": round(float(precision), 4),
                "ncf_recall": round(float(recall), 4),
                "ncf_f1": round(float(f1), 4),
                "ncf_n_samples": len(df_raw),
                "computed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "ncf_error": str(e),
                "ncf_available": False,
                "computed_at": datetime.now().isoformat(),
            }

    @task(task_id="log_metrics_mlflow")
    def log_metrics_mlflow(knn_metrics: dict, ncf_metrics: dict) -> dict:
        """Loga todas as métricas no MLflow."""
        import mlflow

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        mlflow.set_experiment("amazon-product-recommender-metrics")

        all_metrics = {**knn_metrics, **ncf_metrics}
        numeric_metrics = {
            k: v for k, v in all_metrics.items()
            if isinstance(v, (int, float)) and not k.endswith("_at")
        }

        with mlflow.start_run(run_name=f"daily-metrics-{datetime.now().strftime('%Y%m%d')}"):
            mlflow.log_metrics(numeric_metrics)
            mlflow.log_param("dag", "model_metrics")
            mlflow.log_param("date", datetime.now().strftime("%Y-%m-%d"))

        return all_metrics

    @task(task_id="save_metrics_bigquery")
    def save_metrics_bigquery(all_metrics: dict):
        """Salva o histórico de métricas no BigQuery."""
        import pandas as pd
        from google.cloud import bigquery

        client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID", "samara-a2d79"))
        dataset = os.getenv("BQ_DATASET", "amazon_reviews")

        row = {k: str(v) if not isinstance(v, (int, float)) else v
               for k, v in all_metrics.items()}
        row["date"] = datetime.now().strftime("%Y-%m-%d")
        row["dag_run"] = "model_metrics"

        df = pd.DataFrame([row])
        table_id = f"{os.getenv('GCP_PROJECT_ID', 'samara-a2d79')}.{dataset}.model_metrics_history"

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            autodetect=True,
        )
        client.load_table_from_dataframe(df, table_id, job_config=job_config).result()

    @task(task_id="send_metrics_report")
    def send_metrics_report(all_metrics: dict):
        """Envia relatório de métricas via Email e Telegram."""
        sys.path.insert(0, f"{PROJECT_ROOT}/alerts")
        from alert_manager import AlertManager

        knn_p5 = all_metrics.get("knn_precision_at_5", "N/A")
        knn_hr5 = all_metrics.get("knn_hit_rate_at_5", "N/A")
        knn_ndcg5 = all_metrics.get("knn_ndcg_at_5", "N/A")
        ncf_rmse = all_metrics.get("ncf_rmse", "N/A")
        ncf_f1 = all_metrics.get("ncf_f1", "N/A")

        subject = f"[ML] Métricas Diárias — {datetime.now().strftime('%d/%m/%Y')}"
        msg = (
            f"Relatório de Métricas do Modelo\n"
            f"{'='*40}\n\n"
            f"KNN — Content-Based Filtering\n"
            f"  Precision@5:  {knn_p5}\n"
            f"  Recall@5:     {all_metrics.get('knn_recall_at_5', 'N/A')}\n"
            f"  F1@5:         {all_metrics.get('knn_f1_at_5', 'N/A')}\n"
            f"  Hit Rate@5:   {knn_hr5}\n"
            f"  NDCG@5:       {knn_ndcg5}\n"
            f"  Precision@10: {all_metrics.get('knn_precision_at_10', 'N/A')}\n"
            f"  NDCG@10:      {all_metrics.get('knn_ndcg_at_10', 'N/A')}\n\n"
            f"NCF — Neural Collaborative Filtering\n"
            f"  RMSE:         {ncf_rmse}\n"
            f"  MAE:          {all_metrics.get('ncf_mae', 'N/A')}\n"
            f"  R²:           {all_metrics.get('ncf_r2', 'N/A')}\n"
            f"  Precision:    {all_metrics.get('ncf_precision', 'N/A')}\n"
            f"  F1:           {ncf_f1}\n"
        )

        AlertManager().send_all(subject, msg)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    knn = compute_knn_metrics()
    ncf = compute_ncf_metrics()
    all_m = log_metrics_mlflow(knn, ncf)
    save_metrics_bigquery(all_m)
    send_metrics_report(all_m)


metrics_dag = metrics_pipeline()
