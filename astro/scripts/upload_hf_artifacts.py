"""Upload retrained model artifacts to a Hugging Face repository."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACTS = [
    "models/knn_model.pkl",
    "models/feature_matrix.pkl",
    "models/tfidf_vectorizer.pkl",
    "models/scaler.pkl",
    "output/df_products.csv",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Hugging Face artifact upload."""
    parser = argparse.ArgumentParser(
        description="Upload recommender artifacts to Hugging Face.",
    )
    parser.add_argument(
        "--repo-id",
        default=os.getenv(
            "HF_SPACE_REPO",
            "gallorafael22/Model_ml_mlops_Recommendation_system",
        ),
        help="Hugging Face repository id.",
    )
    parser.add_argument(
        "--repo-type",
        default=os.getenv("HF_REPO_TYPE", "space"),
        choices=["space", "dataset", "model"],
        help="Hugging Face repository type.",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        dest="artifacts",
        help="Artifact path to upload. Can be repeated.",
    )
    parser.add_argument(
        "--commit-message",
        default="Update retrained recommender artifacts",
        help="Commit message used in the Hugging Face repository.",
    )
    parser.add_argument(
        "--restart-space",
        action="store_true",
        help="Restart the Space after uploading artifacts.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def stage_artifacts(artifact_paths: list[str], staging_dir: Path) -> list[Path]:
    """Copy existing artifacts into a temporary upload folder."""
    staged_paths = []

    for artifact in artifact_paths:
        source = Path(artifact)
        if not source.exists():
            logger.warning("Artifact not found and skipped: %s", source)
            continue

        destination = staging_dir / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        staged_paths.append(destination)

    return staged_paths


def restart_space(api: HfApi, repo_id: str) -> None:
    """Restart a Hugging Face Space when the client supports it."""
    try:
        api.restart_space(repo_id=repo_id)
        logger.info("Requested Space restart: %s", repo_id)
    except AttributeError:
        logger.warning("Installed huggingface_hub does not support restart_space.")
    except Exception as exc:
        logger.warning("Could not restart Space %s: %s", repo_id, exc)


def main() -> int:
    """Upload artifacts and optionally restart the target Space."""
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required to upload artifacts.")

    artifact_paths = args.artifacts or DEFAULT_ARTIFACTS
    api = HfApi(token=token)

    with tempfile.TemporaryDirectory() as temp_dir:
        staging_dir = Path(temp_dir)
        staged_paths = stage_artifacts(artifact_paths, staging_dir)
        if not staged_paths:
            raise RuntimeError("No artifacts found to upload.")

        logger.info("Uploading %s artifacts to %s", len(staged_paths), args.repo_id)
        api.upload_folder(
            folder_path=str(staging_dir),
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            commit_message=args.commit_message,
        )

    if args.restart_space and args.repo_type == "space":
        restart_space(api, args.repo_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
