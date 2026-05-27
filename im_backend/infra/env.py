from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_backend_env() -> None:
    """Load the project .env before importing agent_flow runtime modules."""

    repo_root = Path(__file__).resolve().parents[2]
    for env_path in (
        repo_root / ".env",
        repo_root / "im_backend" / ".env",
        repo_root / "agent_flow" / ".env",
    ):
        load_dotenv(env_path, override=False)
