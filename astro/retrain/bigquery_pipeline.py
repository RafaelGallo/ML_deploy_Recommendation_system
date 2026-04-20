"""Load recommendation training data from BigQuery or CSV files."""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BigQueryPipeline:
    """Load product review data from BigQuery and CSV sources."""

    def __init__(self) -> None:
        """Read BigQuery configuration from environment variables."""
        self.project = os.getenv("GCP_PROJECT_ID", "samara-a2d79")
        self.dataset = os.getenv("BQ_DATASET", "amazon_reviews")
        self.table = os.getenv("BQ_TABLE", "product_reviews")

    def configure_google_credentials(self) -> None:
        """Configure Google credentials from a file path or secret value."""
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            expanded_path = Path(credentials_path).expanduser()
            if expanded_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(expanded_path)
                return

        raw_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        encoded_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64")
        if encoded_credentials and not raw_credentials:
            raw_credentials = base64.b64decode(encoded_credentials).decode("utf-8")

        if not raw_credentials:
            return

        json.loads(raw_credentials)
        output_path = Path(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS_PATH", "/tmp/gcp-key.json")
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(raw_credentials, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(output_path)

    def resolve_table_id(self, table_id: Optional[str] = None) -> str:
        """Return the fully qualified BigQuery table id."""
        return table_id or f"{self.project}.{self.dataset}.{self.table}"

    def load_data(self, table_id: Optional[str] = None) -> pd.DataFrame:
        """Load aggregated product data from BigQuery."""
        from google.cloud import bigquery

        self.configure_google_credentials()
        client = bigquery.Client(project=self.project)
        full_table = self.resolve_table_id(table_id)

        query = f"""
            SELECT
                asins,
                name,
                brand,
                categories,
                AVG(CAST(reviews_rating AS FLOAT64)) AS avg_rating,
                SUM(reviews_numHelpful) AS total_helpful,
                COUNT(*) AS review_count,
                STRING_AGG(reviews_text, ' ') AS all_reviews
            FROM `{full_table}`
            WHERE reviews_text IS NOT NULL
                AND asins IS NOT NULL
            GROUP BY asins, name, brand, categories
            HAVING COUNT(*) >= 2
            ORDER BY review_count DESC
        """

        logger.info("Querying BigQuery table: %s", full_table)
        df = client.query(query).to_dataframe()
        logger.info("Loaded %s products from BigQuery", len(df))
        return df

    def upload_new_reviews(
        self,
        csv_path: str,
        table_id: Optional[str] = None,
    ) -> None:
        """Append new review rows from a CSV file into BigQuery."""
        from google.cloud import bigquery

        self.configure_google_credentials()
        client = bigquery.Client(project=self.project)
        full_table = self.resolve_table_id(table_id)

        df = pd.read_csv(csv_path)
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            autodetect=True,
        )

        job = client.load_table_from_dataframe(df, full_table, job_config=job_config)
        job.result()
        logger.info("Uploaded %s rows to %s", len(df), full_table)

    def load_from_csv(self, csv_path: Optional[str] = None) -> pd.DataFrame:
        """Load product data from a local CSV file."""
        path = csv_path or os.getenv("DATA_PATH", "output/df_products.csv")
        logger.info("Loading data from CSV: %s", path)
        return pd.read_csv(path)

    def load(
        self,
        source: str = "bigquery",
        table_id: Optional[str] = None,
        allow_csv_fallback: bool = False,
    ) -> pd.DataFrame:
        """Load training data from BigQuery or CSV."""
        if source == "bigquery":
            try:
                return self.load_data(table_id)
            except Exception as exc:
                if allow_csv_fallback:
                    logger.warning(
                        "BigQuery load failed: %s. Falling back to CSV.",
                        exc,
                    )
                    return self.load_from_csv()
                raise RuntimeError("BigQuery load failed during retraining.") from exc

        if source == "csv":
            return self.load_from_csv()

        raise ValueError(f"Unsupported retraining source: {source}")

