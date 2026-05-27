from __future__ import annotations

import time
import uuid
from typing import Literal


RoomType = Literal["dm", "group"]
SenderType = Literal["user", "agent", "system"]
ContentPartType = Literal[
    "text",
    "code",
    "image",
    "file",
    "web_preview",
    "diff",
    "deploy",
    "event_ref",
]
MessageStatus = Literal["pending", "sent", "running", "finished", "failed", "cancelled"]
ActionType = Literal["reply", "quote", "copy", "expand", "apply_diff", "approve", "reject"]
AgentKind = Literal["native", "claude_code", "codex", "human_proxy"]


def new_id() -> str:
    return str(uuid.uuid4())


def now_ts() -> float:
    return time.time()

