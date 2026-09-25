from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRuntimeProfile:
    agent_id: str
    avatar_url: str = ""
    capabilities: list[str] = field(default_factory=list)
    workdir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_agent_record(cls, record: dict[str, Any]) -> "AgentRuntimeProfile":
        metadata = record.get("metadata", {}) or {}
        return cls(
            agent_id=record.get("agent_id", ""),
            avatar_url=metadata.get("avatar_url", ""),
            capabilities=metadata.get("capabilities", []) or [],
            workdir=metadata.get("workdir", ""),
            metadata=metadata,
        )
