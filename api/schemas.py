from pydantic import BaseModel
from typing import List, Optional


class RecommendRequest(BaseModel):
    product_name: str
    top_k: int = 5


class ProductRecommendation(BaseModel):
    rank: int
    product_name: str
    asin: str
    similarity_score: float
    avg_rating: Optional[float] = None
    brand: Optional[str] = None
    categories: Optional[str] = None


class RecommendResponse(BaseModel):
    query_product: str
    model: str
    recommendations: List[ProductRecommendation]
    total_found: int


class NCFRecommendRequest(BaseModel):
    user_id: str
    top_k: int = 5


class NCFRecommendation(BaseModel):
    rank: int
    product_name: str
    asin: str
    predicted_rating: float
    brand: Optional[str] = None


class NCFRecommendResponse(BaseModel):
    user_id: str
    model: str
    recommendations: List[NCFRecommendation]
    total_found: int


class HealthResponse(BaseModel):
    status: str
    models_loaded: dict
    version: str


class MetricsResponse(BaseModel):
    knn_metrics: dict
    ncf_metrics: dict
    dataset_info: dict


class RetrainRequest(BaseModel):
    source: str = "bigquery"
    table_id: Optional[str] = None
    notify: bool = True


class RetrainResponse(BaseModel):
    status: str
    message: str
    run_id: Optional[str] = None
