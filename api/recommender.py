import os
import joblib
import numpy as np
import pandas as pd
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "models"))
DATA_PATH = Path(os.getenv("DATA_PATH", "output/df_products.csv"))


class KNNRecommender:
    def __init__(self):
        self.model = None
        self.feature_matrix = None
        self.tfidf = None
        self.scaler = None
        self.df_products = None
        self.loaded = False

    def load(self):
        try:
            self.model = joblib.load(MODELS_DIR / "knn_model.pkl")
            self.feature_matrix = joblib.load(MODELS_DIR / "feature_matrix.pkl")
            self.tfidf = joblib.load(MODELS_DIR / "tfidf_vectorizer.pkl")
            self.scaler = joblib.load(MODELS_DIR / "scaler.pkl")
            self.df_products = pd.read_csv(DATA_PATH)
            self.loaded = True
            logger.info("KNN model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load KNN model: {e}")
            raise

    def search_product(self, query: str) -> Optional[int]:
        if self.df_products is None:
            return None
        mask = self.df_products["name"].str.lower().str.contains(
            query.lower(), na=False
        )
        matches = self.df_products[mask]
        if matches.empty:
            return None
        return matches.index[0]

    def recommend(self, product_name: str, top_k: int = 5) -> List[Dict]:
        if not self.loaded:
            self.load()

        idx = self.search_product(product_name)
        if idx is None:
            return []

        product_vector = self.feature_matrix[idx]
        distances, indices = self.model.kneighbors(product_vector, n_neighbors=top_k + 1)

        recommendations = []
        for rank, (dist, rec_idx) in enumerate(
            zip(distances[0][1:], indices[0][1:]), start=1
        ):
            row = self.df_products.iloc[rec_idx]
            recommendations.append(
                {
                    "rank": rank,
                    "product_name": row.get("name", "Unknown"),
                    "asin": row.get("asins", ""),
                    "similarity_score": round(float(1 - dist), 4),
                    "avg_rating": row.get("avg_rating"),
                    "brand": row.get("brand"),
                    "categories": row.get("categories"),
                }
            )
        return recommendations

    def get_all_products(self) -> List[Dict]:
        if not self.loaded:
            self.load()
        return self.df_products[["asins", "name", "brand", "avg_rating"]].to_dict(
            orient="records"
        )


class NCFRecommender:
    def __init__(self):
        self.model = None
        self.user_encoder = None
        self.product_encoder = None
        self.rating_scaler = None
        self.df_products = None
        self.loaded = False

    def load(self):
        try:
            import tensorflow as tf

            self.model = tf.keras.models.load_model(MODELS_DIR / "ncf_model.keras")
            self.user_encoder = joblib.load(MODELS_DIR / "user_encoder.pkl")
            self.product_encoder = joblib.load(MODELS_DIR / "product_encoder.pkl")
            self.rating_scaler = joblib.load(MODELS_DIR / "rating_scaler.pkl")
            self.df_products = pd.read_csv(DATA_PATH)
            self.loaded = True
            logger.info("NCF model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load NCF model: {e}")
            raise

    def recommend(self, user_id: str, top_k: int = 5) -> List[Dict]:
        if not self.loaded:
            self.load()

        known_users = list(self.user_encoder.classes_)
        if user_id not in known_users:
            user_id = known_users[0]

        user_idx = self.user_encoder.transform([user_id])[0]
        n_products = len(self.product_encoder.classes_)

        user_arr = np.array([user_idx] * n_products)
        product_arr = np.arange(n_products)

        preds = self.model.predict([user_arr, product_arr], verbose=0).flatten()
        preds_denorm = self.rating_scaler.inverse_transform(preds.reshape(-1, 1)).flatten()

        top_indices = preds_denorm.argsort()[::-1][:top_k]
        product_asins = self.product_encoder.inverse_transform(top_indices)

        recommendations = []
        for rank, (asin, score) in enumerate(
            zip(product_asins, preds_denorm[top_indices]), start=1
        ):
            row = self.df_products[self.df_products["asins"] == asin]
            name = row["name"].values[0] if not row.empty else asin
            brand = row["brand"].values[0] if not row.empty else None
            recommendations.append(
                {
                    "rank": rank,
                    "product_name": name,
                    "asin": asin,
                    "predicted_rating": round(float(score), 4),
                    "brand": brand,
                }
            )
        return recommendations
