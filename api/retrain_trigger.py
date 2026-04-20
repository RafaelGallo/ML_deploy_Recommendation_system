"""Run model retraining as a FastAPI background task."""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent if APP_DIR.name == "api" else APP_DIR
RETRAIN_DIR = PROJECT_DIR / "retrain"
ALERTS_DIR = PROJECT_DIR / "alerts"


def add_import_path(path: Path) -> None:
    """Add a directory to Python imports if it is not present."""
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


async def run_retrain(
    source: str = "bigquery",
    table_id: Optional[str] = None,
    notify: bool = True,
) -> str:
    """Run retraining and optionally notify the configured channels."""
    try:
        logger.info("Starting retraining from source: %s", source)
        add_import_path(RETRAIN_DIR)
        from retrain_pipeline import RetrainPipeline

        pipeline = RetrainPipeline()
        run_id = pipeline.run(source=source, table_id=table_id)

        if notify:
            add_import_path(ALERTS_DIR)
            from alert_manager import AlertManager

            alert = AlertManager()
            alert.send_all(
                subject="[ML] Retraining Complete",
                message=(
                    "Model retraining finished successfully.\n"
                    f"MLflow Run ID: {run_id}\n"
                    f"Source: {source}"
                ),
            )

        logger.info("Retraining complete. Run ID: %s", run_id)
        return run_id

    except Exception as exc:
        logger.error("Retraining failed: %s", exc)
        if notify:
            try:
                add_import_path(ALERTS_DIR)
                from alert_manager import AlertManager

                alert = AlertManager()
                alert.send_all(
                    subject="[ML] Retraining FAILED",
                    message=f"Model retraining failed with error:\n{str(exc)}",
                )
            except Exception:
                pass
        raise
