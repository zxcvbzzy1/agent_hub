from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_FLOW_ROOT = Path(
    os.getenv("AGENT_FLOW_ROOT", str(REPO_ROOT / "agent_flow"))
).expanduser().resolve()


def ensure_agent_flow_path() -> None:
    path = str(AGENT_FLOW_ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

