"""IM-owned automatic archiving policy and immutable task workspace settings."""
from __future__ import annotations

import os
from pathlib import Path


def validate_workdir(value):
    if not isinstance(value, (str, Path)):
        raise ValueError("工作目录必须是路径字符串")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("工作目录必须是后端已有的绝对路径")
    path = path.resolve()
    if not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError("工作目录不存在或无法读写")
    return str(path)


def capture_run_options(store, metadata, *, conversation_id="", room=None, default_workdir="", agent=None):
    metadata = dict(metadata or {})
    conversation = store.find_one("im_conversations", {"conversation_id": conversation_id}) or {}
    enabled = metadata.get("memory_write_enabled", conversation.get("memory_write_enabled", False))
    if type(enabled) is not bool:
        raise ValueError("memory_write_enabled 必须是布尔值")
    if room:
        path = (room.get("metadata") or {}).get("workdir") or default_workdir
    else:
        path = ((agent or {}).get("metadata") or {}).get("workdir") or default_workdir
    # Never trust a client-supplied snapshot: resolve it from current server settings.
    metadata["run_options"] = {"memory_write_enabled": enabled, "workdir": validate_workdir(path)}
    metadata.pop("memory_write_enabled", None)
    return metadata
