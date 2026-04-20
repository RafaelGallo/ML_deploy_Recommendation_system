"""Retrain recommendation artifacts from BigQuery or CSV data."""

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import MinMaxScaler

from bigquery_pipeline import BigQueryPipeline

load_dotenv()

logger = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "models"))
DATA_PATH = Path(os.getenv("DATA_PATH", "output/df_products.csv"))
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "file:mlruns")
MLFLOW_FALLBACK_URI = os.getenv("MLFLOW_FALLBACK_TRACKING_URI", "file:mlruns")


class RetrainPipeline:
    """Train and persist the KNN recommender artifacts."""

    def __init__(self) -> None:
        """Configure MLflow and data access clients."""
        self.configure_mlflow()
        self.bq = BigQueryPipeline()

    def configure_mlflow(self) -> None:
        """Configure MLflow and fall back to a local store if unavailable."""
        mlflow.set_tracking_uri(MLFLOW_URI)
        try:
            mlflow.set_experiment("amazon-product-recommender")
        except Exception as exc:
            if MLFLOW_URI == MLFLOW_FALLBACK_URI:
                raise
            logger.warning(
                "MLflow URI %s unavailable: %s. Falling back to %s.",
                MLFLOW_URI,
                exc,
                MLFLOW_FALLBACK_URI,
            )
            mlflow.set_tracking_uri(MLFLOW_FALLBACK_URI)
            mlflow.set_experiment("amazon-product-recommender")

    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare product rows for feature extraction."""
        df = df.copy()
        df["all_reviews"] = df["all_reviews"].fillna("").astype(str)
        df["avg_rating"] = df["avg_rating"].fillna(df["avg_rating"].median())
        df["total_helpful"] = df["total_helpful"].fillna(0)
        df["review_count"] = df["review_count"].fillna(1)
        return df.reset_index(drop=True)

    def build_features(self, df: pd.DataFrame):
        """Build text and numeric features for nearest-neighbor search."""
        tfidf = TfidfVectorizer(
            max_features=500,
            min_df=2,
            ngram_range=(1, 2),
            lowercase=True,
            stop_words="english",
        )
        text_matrix = tfidf.fit_transform(df["all_reviews"])

        scaler = MinMaxScaler()
        num_features = scaler.fit_transform(
            df[["avg_rating", "total_helpful", "review_count"]]
        )

        feature_matrix = hstack([text_matrix, csr_matrix(num_features)])
        return feature_matrix, tfidf, scaler

    def train_knn(self, feature_matrix, n_neighbors: int = 20) -> NearestNeighbors:
        """Fit the cosine-distance nearest-neighbor model."""
        model = NearestNeighbors(
            n_neighbors=min(n_neighbors, feature_matrix.shape[0]),
            metric="cosine",
            algorithm="brute",
            n_jobs=-1,
        )
        model.fit(feature_matrix)
        return model

    def evaluate_knn(
        self,
        model: NearestNeighbors,
        feature_matrix,
        df: pd.DataFrame,
        k: int = 5,
    ) -> dict:
        """Calculate lightweight recommendation quality metrics."""
        precisions = []
        hit_rates = []
        cosine_sims = []

        relevant_threshold = df["avg_rating"].quantile(0.6)

        for index in range(min(len(df), 20)):
            distances, indices = model.kneighbors(
                feature_matrix[index],
                n_neighbors=k + 1,
            )
            rec_indices = indices[0][1:]
            sims = 1 - distances[0][1:]

            relevant_recs = (
                df.iloc[rec_indices]["avg_rating"] >= relevant_threshold
            ).sum()
            precisions.append(relevant_recs / k)
            hit_rates.append(1.0 if relevant_recs > 0 else 0.0)
            cosine_sims.extend(sims.tolist())

        return {
            "precision_at_5": round(float(np.mean(precisions)), 4),
            "hit_rate_at_5": round(float(np.mean(hit_rates)), 4),
            "mean_cosine_similarity": round(float(np.mean(cosine_sims)), 4),
            "n_products": len(df),
        }

    def save_artifacts(
        self,
        model: NearestNeighbors,
        feature_matrix,
        tfidf: TfidfVectorizer,
        scaler: MinMaxScaler,
        df: pd.DataFrame,
    ) -> None:
        """Persist model artifacts and the product dataset."""
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

        joblib.dump(model, MODELS_DIR / "knn_model.pkl")
        joblib.dump(feature_matrix, MODELS_DIR / "feature_matrix.pkl")
        joblib.dump(tfidf, MODELS_DIR / "tfidf_vectorizer.pkl")
        joblib.dump(scaler, MODELS_DIR / "scaler.pkl")
        df.to_csv(DATA_PATH, index=False)
        logger.info("Model artifacts saved to %s", MODELS_DIR)
        logger.info("Product data saved to %s", DATA_PATH)

    def run(
        self,
        source: str = "bigquery",
        table_id: Optional[str] = None,
        allow_csv_fallback: bool = False,
    ) -> str:
        """Run the full retraining workflow and return the MLflow run id."""
        logger.info("Starting retraining pipeline from %s", source)

        df_raw = self.bq.load(
            source=source,
            table_id=table_id,
            allow_csv_fallback=allow_csv_fallback,
        )
        df = self.preprocess(df_raw)
        logger.info("Preprocessed %s products", len(df))

        feature_matrix, tfidf, scaler = self.build_features(df)
        knn_model = self.train_knn(feature_matrix, n_neighbors=20)
        metrics = self.evaluate_knn(knn_model, feature_matrix, df)

        with mlflow.start_run() as run:
            mlflow.log_param("n_neighbors", 20)
            mlflow.log_param("tfidf_max_features", 500)
            mlflow.log_param("metric", "cosine")
            mlflow.log_param("data_source", source)
            mlflow.log_param("n_products", len(df))
            if table_id:
                mlflow.log_param("table_id", table_id)

            mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(knn_model, "knn_model")

            run_id = run.info.run_id
            logger.info("MLflow run: %s", run_id)

        self.save_artifacts(knn_model, feature_matrix, tfidf, scaler, df)
        logger.info("Retraining complete. Run ID: %s", run_id)
        return run_id


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for manual retraining."""
    parser = argparse.ArgumentParser(description="Retrain the recommender model.")
    parser.add_argument("--source", choices=["bigquery", "csv"], default="bigquery")
    parser.add_argument("--table-id", default=None)
    parser.add_argument("--allow-csv-fallback", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    """Run retraining from the command line."""
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    pipeline = RetrainPipeline()
    run_id = pipeline.run(
        source=args.source,
        table_id=args.table_id,
        allow_csv_fallback=args.allow_csv_fallback,
    )
    print(f"Done. Run ID: {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

