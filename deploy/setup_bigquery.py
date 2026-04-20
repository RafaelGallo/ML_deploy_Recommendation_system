"""Script para criar dataset e tabelas no BigQuery e carregar os dados iniciais."""
import os
import sys
import pandas as pd
from google.cloud import bigquery

PROJECT_ID = os.getenv("GCP_PROJECT_ID") or sys.argv[1]
DATASET_ID = "amazon_reviews"
client = bigquery.Client(project=PROJECT_ID)


def create_dataset():
    dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    dataset_ref.location = "US"
    try:
        dataset = client.create_dataset(dataset_ref, exists_ok=True)
        print(f"Dataset {DATASET_ID} ready.")
    except Exception as e:
        print(f"Dataset error: {e}")


def upload_raw_reviews(csv_path: str = "input/7817_1.csv"):
    table_id = f"{PROJECT_ID}.{DATASET_ID}.product_reviews"
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [c.replace(".", "_").replace(" ", "_").lower() for c in df.columns]

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"Uploaded {len(df)} rows to {table_id}")


def upload_products(csv_path: str = "output/df_products.csv"):
    table_id = f"{PROJECT_ID}.{DATASET_ID}.df_products"
    df = pd.read_csv(csv_path)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"Uploaded {len(df)} products to {table_id}")


if __name__ == "__main__":
    create_dataset()
    upload_raw_reviews()
    upload_products()
    print("\nBigQuery setup complete!")
    print(f"Dataset: {PROJECT_ID}.{DATASET_ID}")
