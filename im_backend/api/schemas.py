from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""
    avatar_url: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class ContentPartRequest(BaseModel):
    type: Literal["text", "code", "image", "file", "web_preview", "diff", "deploy", "event_ref"] = "text"
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoomCreateRequest(BaseModel):
    type: Literal["group"] = "group"
    title: str = ""
    member_agent_ids: list[str] = Field(default_factory=list)
    created_by: str = "user"
    avatar_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConversationCreateRequest(BaseModel):
    title: str = ""
    avatar_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreateRequest(BaseModel):
    sender_type: Literal["user", "agent", "system"] = "user"
    sender_id: str = "user"
    content_parts: list[ContentPartRequest]
    mentions: list[str] = Field(default_factory=list)
    reply_to: str = ""
    quote_of: str = ""
    run_id: str = ""
    status: str = "sent"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchRequest(BaseModel):
    message_id: str
    planner_agent_id: str = "default_planner"
    context_id: str = "default_step"
    max_replan_rounds: int = 3
    auto_start: bool = True
    approved: bool = False


class ReplyRequest(BaseModel):
    message_id: str
    auto_start: bool = True


class MessageActionRequest(BaseModel):
    action_type: Literal["reply", "quote", "copy", "expand", "apply_diff", "approve", "reject"]
    actor_id: str = "user"
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactUploadRequest(BaseModel):
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"
