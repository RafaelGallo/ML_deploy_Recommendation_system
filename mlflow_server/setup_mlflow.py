"""Register the current KNN model artifacts in MLflow on first startup."""
import os
import joblib
import mlflow
import mlflow.sklearn
from pathlib import Path

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODELS_DIR = Path(os.getenv("MODELS_DIR", "models"))

mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment("amazon-product-recommender")

model = joblib.load(MODELS_DIR / "knn_model.pkl")

with mlflow.start_run(run_name="initial-registration"):
    mlflow.log_param("n_neighbors", 20)
    mlflow.log_param("metric", "cosine")
    mlflow.log_param("tfidf_max_features", 500)
    mlflow.log_metrics({
        "precision_at_5": 0.7630,
        "recall_at_5": 0.1231,
        "f1_at_5": 0.2119,
        "hit_rate_at_5": 1.0000,
        "mean_cosine_similarity": 0.5716,
    })
    mlflow.sklearn.log_model(model, "knn_model", registered_model_name="knn-recommender")
    print("Model registered in MLflow successfully.")
