"""Start the FastAPI API and Streamlit UI for Hugging Face Spaces."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
API_PORT = "8000"
UI_PORT = os.getenv("PORT", "7860")


def start_process(command: list[str], cwd: Path) -> subprocess.Popen:
    """Start a child process and stream its output to the container logs."""
    return subprocess.Popen(command, cwd=str(cwd))


def stop_processes(processes: list[subprocess.Popen]) -> None:
    """Terminate any child processes that are still running."""
    for process in processes:
        if process.poll() is None:
            process.terminate()


def main() -> int:
    """Run the API and UI until one process exits."""
    os.environ.setdefault("API_URL", f"http://127.0.0.1:{API_PORT}")

    processes = [
        start_process(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                API_PORT,
            ],
            APP_DIR / "api",
        ),
        start_process(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "streamlit_app/app.py",
                "--server.address=0.0.0.0",
                f"--server.port={UI_PORT}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            APP_DIR,
        ),
    ]

    def handle_signal(signum: int, frame: object) -> None:
        """Stop child processes when the container receives a shutdown signal."""
        del signum, frame
        stop_processes(processes)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    exit_code = 0
    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    exit_code = code
                    return exit_code
            time.sleep(1)
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
