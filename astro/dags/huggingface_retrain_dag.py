"""Run recommender retraining and upload artifacts to Hugging Face."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

PROJECT_ROOT = Path(
    os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1])
)
TRAIN_SOURCE = os.getenv("TRAIN_SOURCE", "bigquery")
TABLE_ID = os.getenv("TABLE_ID")
ALLOW_CSV_FALLBACK = os.getenv("ALLOW_CSV_FALLBACK", "false").lower() == "true"
HF_SPACE_REPO = os.getenv(
    "HF_SPACE_REPO",
    "gallorafael22/Model_ml_mlops_Recommendation_system",
)

DEFAULT_ARGS = {
    "owner": "rafael",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def run_command(command: list[str]) -> None:
    """Run a command from the project root and fail on errors."""
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


@dag(
    dag_id="huggingface_recommender_retrain",
    description="Retrain the recommender and upload artifacts to Hugging Face.",
    schedule="0 8 * * 1",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ml", "recommendation", "huggingface"],
)
def huggingface_recommender_retrain():
    """Define the optional Airflow flow for Hugging Face deployment."""

    @task(task_id="validate_project_root")
    def validate_project_root() -> str:
        """Validate that Airflow can access the project files."""
        retrain_script = PROJECT_ROOT / "retrain" / "retrain_pipeline.py"
        upload_script = PROJECT_ROOT / "scripts" / "upload_hf_artifacts.py"

        if not retrain_script.exists():
            raise FileNotFoundError(retrain_script)
        if not upload_script.exists():
            raise FileNotFoundError(upload_script)

        return str(PROJECT_ROOT)

    @task(task_id="run_retraining")
    def run_retraining(_: str) -> str:
        """Run the KNN retraining pipeline."""
        command = [
            sys.executable,
            "retrain/retrain_pipeline.py",
            "--source",
            TRAIN_SOURCE,
            "--log-level",
            "INFO",
        ]
        if TABLE_ID:
            command.extend(["--table-id", TABLE_ID])
        if ALLOW_CSV_FALLBACK:
            command.append("--allow-csv-fallback")

        run_command(command)
        return "retraining-complete"

    @task(task_id="upload_to_huggingface")
    def upload_to_huggingface(_: str) -> str:
        """Upload generated artifacts and restart the Hugging Face Space."""
        run_command(
            [
                sys.executable,
                "scripts/upload_hf_artifacts.py",
                "--repo-id",
                HF_SPACE_REPO,
                "--repo-type",
                "space",
                "--restart-space",
            ]
        )
        return "upload-complete"

    root = validate_project_root()
    retrained = run_retraining(root)
    upload_to_huggingface(retrained)


huggingface_recommender_retrain_dag = huggingface_recommender_retrain()
