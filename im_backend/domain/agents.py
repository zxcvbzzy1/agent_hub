from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import AgentKind, now_ts


@dataclass
class AgentRuntimeProfile:
    agent_id: str
    agent_kind: AgentKind = "native"
    avatar_url: str = ""
    capabilities: list[str] = field(default_factory=list)
    workdir: str = ""
    permission_profile: str = "human_confirm"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_agent_record(cls, record: dict[str, Any]) -> "AgentRuntimeProfile":
        metadata = record.get("metadata", {}) or {}
        return cls(
            agent_id=record.get("agent_id", ""),
            agent_kind=metadata.get("agent_kind", "native"),
            avatar_url=metadata.get("avatar_url", ""),
            capabilities=metadata.get("capabilities", []) or [],
            workdir=metadata.get("workdir", ""),
            permission_profile=metadata.get("permission_profile", "human_confirm"),
            metadata=metadata,
        )


@dataclass
class CodingAgentEvent:
    type: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "created_at": self.created_at,
        }
