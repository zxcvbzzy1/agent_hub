from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import ContentPartType


@dataclass
class ContentPart:
    type: ContentPartType
    text: str = ""
    language: str = ""
    url: str = ""
    name: str = ""
    mime_type: str = ""
    size: int = 0
    artifact_id: str = ""
    diff: str = ""
    title: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentPart":
        return cls(
            type=data.get("type", "text"),
            text=data.get("text", ""),
            language=data.get("language", ""),
            url=data.get("url", ""),
            name=data.get("name", ""),
            mime_type=data.get("mime_type", ""),
            size=int(data.get("size", 0) or 0),
            artifact_id=data.get("artifact_id", ""),
            diff=data.get("diff", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}) or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "language": self.language,
            "url": self.url,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
            "artifact_id": self.artifact_id,
            "diff": self.diff,
            "title": self.title,
            "description": self.description,
            "metadata": self.metadata,
        }

