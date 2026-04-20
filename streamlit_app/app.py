import os
import requests
import streamlit as st
import pandas as pd

API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(
    page_title="Amazon Product Recommender",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {font-size: 2.5rem; font-weight: bold; color: #FF9900;}
    .sub-header {font-size: 1.1rem; color: #555;}
    .metric-card {
        background: #f8f9fa; border-radius: 10px;
        padding: 1rem; margin: 0.5rem 0;
        border-left: 4px solid #FF9900;
    }
    .rec-card {
        background: #fff; border-radius: 8px;
        padding: 1rem; margin: 0.4rem 0;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def check_api():
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        return r.status_code == 200, r.json()
    except Exception:
        return False, {}


def get_products():
    try:
        r = requests.get(f"{API_URL}/products", timeout=10)
        return r.json().get("products", [])
    except Exception:
        return []


def get_knn_recommendations(product_name: str, top_k: int):
    try:
        r = requests.post(
            f"{API_URL}/recommend/knn",
            json={"product_name": product_name, "top_k": top_k},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json(), None
        return None, r.json().get("detail", "Unknown error")
    except Exception as e:
        return None, str(e)


def get_ncf_recommendations(user_id: str, top_k: int):
    try:
        r = requests.post(
            f"{API_URL}/recommend/ncf",
            json={"user_id": user_id, "top_k": top_k},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json(), None
        return None, r.json().get("detail", "Unknown error")
    except Exception as e:
        return None, str(e)


def get_metrics():
    try:
        r = requests.get(f"{API_URL}/metrics", timeout=5)
        return r.json()
    except Exception:
        return {}


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🛒 Recommendation System")
    st.markdown("---")

    api_ok, api_info = check_api()
    if api_ok:
        st.success("API Online")
        knn_ready = api_info.get("models_loaded", {}).get("knn", False)
        ncf_ready = api_info.get("models_loaded", {}).get("ncf", False)
        st.markdown(f"- KNN Model: {'✅' if knn_ready else '⏳'}")
        st.markdown(f"- NCF Model: {'✅' if ncf_ready else '⏳'}")
    else:
        st.error("API Offline")

    st.markdown("---")
    mode = st.radio(
        "Recommendation Mode",
        ["Content-Based (KNN)", "Collaborative (NCF)", "Model Metrics", "Retraining"],
    )

    st.markdown("---")
    top_k = st.slider("Number of recommendations", min_value=1, max_value=20, value=5)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-header">🛒 Amazon Product Recommender</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Powered by KNN + Neural Collaborative Filtering · Amazon Reviews Dataset</p>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ── Content-Based KNN ─────────────────────────────────────────────────────────
if mode == "Content-Based (KNN)":
    st.subheader("🔍 Find Similar Products")

    products = get_products()
    product_names = sorted(set(p.get("name", "") for p in products if p.get("name")))

    col1, col2 = st.columns([3, 1])
    with col1:
        if product_names:
            selected = st.selectbox("Select a product:", product_names)
        else:
            selected = st.text_input("Enter product name:", placeholder="e.g. Fire Tablet")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_btn = st.button("Get Recommendations", type="primary", use_container_width=True)

    if search_btn and selected:
        with st.spinner("Finding similar products..."):
            result, error = get_knn_recommendations(selected, top_k)

        if error:
            st.error(f"Error: {error}")
        elif result:
            st.success(f"Top {len(result['recommendations'])} products similar to **{selected}**")
            st.markdown("---")

            for rec in result["recommendations"]:
                similarity_pct = int(rec["similarity_score"] * 100)
                stars = "⭐" * round(rec.get("avg_rating") or 0)

                st.markdown(
                    f"""
                    <div class="rec-card">
                        <b>#{rec['rank']} {rec['product_name']}</b><br>
                        <small>Brand: {rec.get('brand') or 'N/A'} &nbsp;|&nbsp;
                        Rating: {rec.get('avg_rating') or 'N/A'} {stars}</small><br>
                        <small>ASIN: {rec['asin']}</small>
                        <div style="margin-top:8px;">
                            <div style="background:#eee;border-radius:4px;height:8px;">
                                <div style="background:#FF9900;width:{similarity_pct}%;height:8px;border-radius:4px;"></div>
                            </div>
                            <small>Similarity: {similarity_pct}%</small>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ── NCF Collaborative Filtering ───────────────────────────────────────────────
elif mode == "Collaborative (NCF)":
    st.subheader("👤 Personalized Recommendations for User")

    user_id = st.text_input(
        "Enter User ID:",
        placeholder="e.g. A1FWKBYUKXJXBR",
        help="User ID from Amazon reviews",
    )
    search_btn = st.button("Get Personalized Recommendations", type="primary")

    if search_btn:
        if not user_id.strip():
            st.warning("Please enter a user ID.")
        else:
            with st.spinner("Generating personalized recommendations..."):
                result, error = get_ncf_recommendations(user_id.strip(), top_k)

            if error:
                st.error(f"Error: {error}")
            elif result:
                st.success(
                    f"Top {len(result['recommendations'])} recommendations for user **{user_id}**"
                )
                if result["user_id"] != user_id:
                    st.info("User not in training data — showing recommendations for a similar user.")

                for rec in result["recommendations"]:
                    rating_bar = int((rec["predicted_rating"] / 5) * 100)
                    st.markdown(
                        f"""
                        <div class="rec-card">
                            <b>#{rec['rank']} {rec['product_name']}</b><br>
                            <small>Brand: {rec.get('brand') or 'N/A'} &nbsp;|&nbsp; ASIN: {rec['asin']}</small>
                            <div style="margin-top:8px;">
                                <div style="background:#eee;border-radius:4px;height:8px;">
                                    <div style="background:#00a8e0;width:{rating_bar}%;height:8px;border-radius:4px;"></div>
                                </div>
                                <small>Predicted Rating: {rec['predicted_rating']:.2f} / 5.0</small>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# ── Model Metrics ─────────────────────────────────────────────────────────────
elif mode == "Model Metrics":
    st.subheader("📊 Model Performance Metrics")

    metrics = get_metrics()
    if not metrics:
        st.error("Could not fetch metrics from API.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### KNN — Content-Based Filtering")
            knn_m = metrics.get("knn_metrics", {})
            knn_df = pd.DataFrame(
                {
                    "Metric": ["Best K", "Precision@5", "Recall@5", "F1@5", "Hit Rate@5", "Mean Cosine Sim"],
                    "Value": [
                        knn_m.get("best_k"),
                        knn_m.get("precision_at_5"),
                        knn_m.get("recall_at_5"),
                        knn_m.get("f1_at_5"),
                        knn_m.get("hit_rate_at_5"),
                        knn_m.get("mean_cosine_similarity"),
                    ],
                }
            )
            st.dataframe(knn_df, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("#### NCF — Neural Collaborative Filtering")
            ncf_m = metrics.get("ncf_metrics", {})
            ncf_df = pd.DataFrame(
                {
                    "Metric": ["RMSE", "MAE", "R²", "Precision", "Recall", "F1"],
                    "Value": [
                        ncf_m.get("rmse"),
                        ncf_m.get("mae"),
                        ncf_m.get("r2"),
                        ncf_m.get("precision"),
                        ncf_m.get("recall"),
                        ncf_m.get("f1"),
                    ],
                }
            )
            st.dataframe(ncf_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### Dataset Information")
        info = metrics.get("dataset_info", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Reviews", info.get("total_reviews", 0))
        c2.metric("Unique Products", info.get("unique_products", 0))
        c3.metric("Unique Users", info.get("unique_users", 0))
        c4.metric("Source", "Kaggle")

# ── Retraining ────────────────────────────────────────────────────────────────
elif mode == "Retraining":
    st.subheader("🔄 Model Retraining")
    st.info("Trigger model retraining using fresh data from BigQuery.")

    col1, col2 = st.columns(2)
    with col1:
        source = st.selectbox("Data Source", ["bigquery", "csv"])
        table_id = st.text_input(
            "BigQuery Table ID (optional)",
            placeholder="project.dataset.table",
        )
    with col2:
        notify = st.checkbox("Send notifications when complete", value=True)
        st.markdown("<br>", unsafe_allow_html=True)
        retrain_btn = st.button("Start Retraining", type="primary", use_container_width=True)

    if retrain_btn:
        with st.spinner("Submitting retraining job..."):
            try:
                r = requests.post(
                    f"{API_URL}/retrain",
                    json={"source": source, "table_id": table_id or None, "notify": notify},
                    timeout=15,
                )
                if r.status_code == 200:
                    st.success("Retraining job submitted! You will receive an email/Telegram alert when done.")
                else:
                    st.error(f"Error: {r.json().get('detail')}")
            except Exception as e:
                st.error(f"Could not reach API: {e}")
