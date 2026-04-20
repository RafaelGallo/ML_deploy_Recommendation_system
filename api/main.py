import os
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from schemas import (
    RecommendRequest, RecommendResponse, ProductRecommendation,
    NCFRecommendRequest, NCFRecommendResponse, NCFRecommendation,
    HealthResponse, MetricsResponse, RetrainRequest, RetrainResponse,
)
from recommender import KNNRecommender, NCFRecommender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

knn = KNNRecommender()
ncf = NCFRecommender()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading KNN model...")
    knn.load()
    logger.info("KNN model ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Amazon Product Recommendation API",
    description="KNN + Neural Collaborative Filtering recommendation system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        models_loaded={"knn": knn.loaded, "ncf": ncf.loaded},
        version="1.0.0",
    )


@app.get("/products")
def list_products():
    try:
        products = knn.get_all_products()
        return {"total": len(products), "products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recommend/knn", response_model=RecommendResponse)
def recommend_knn(req: RecommendRequest):
    try:
        results = knn.recommend(req.product_name, req.top_k)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Product '{req.product_name}' not found. Check /products for available items.",
            )
        return RecommendResponse(
            query_product=req.product_name,
            model="KNN-Cosine",
            recommendations=[ProductRecommendation(**r) for r in results],
            total_found=len(results),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KNN error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recommend/ncf", response_model=NCFRecommendResponse)
def recommend_ncf(req: NCFRecommendRequest):
    try:
        if not ncf.loaded:
            ncf.load()
        results = ncf.recommend(req.user_id, req.top_k)
        return NCFRecommendResponse(
            user_id=req.user_id,
            model="NCF-Embedding",
            recommendations=[NCFRecommendation(**r) for r in results],
            total_found=len(results),
        )
    except Exception as e:
        logger.error(f"NCF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    return MetricsResponse(
        knn_metrics={
            "best_k": 20,
            "precision_at_5": 0.7630,
            "recall_at_5": 0.1231,
            "f1_at_5": 0.2119,
            "hit_rate_at_5": 1.0000,
            "mean_cosine_similarity": 0.5716,
        },
        ncf_metrics={
            "rmse": 0.9165,
            "mae": 0.5380,
            "r2": 0.1156,
            "precision": 0.9133,
            "recall": 0.8950,
            "f1": 0.9040,
        },
        dataset_info={
            "total_reviews": 1600,
            "unique_products": 54,
            "unique_users": 836,
            "rating_scale": "1-5",
            "source": "Amazon Product Reviews (Kaggle)",
        },
    )


@app.post("/retrain", response_model=RetrainResponse)
async def trigger_retrain(req: RetrainRequest, background_tasks: BackgroundTasks):
    from retrain_trigger import run_retrain
    background_tasks.add_task(run_retrain, req.source, req.table_id, req.notify)
    return RetrainResponse(
        status="accepted",
        message="Retraining started in background. You will be notified when complete.",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
