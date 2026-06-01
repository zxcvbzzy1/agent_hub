"""Inline artifact 收集与转换。

agent 在运行期间调用 agent_flow 的 `inline_artifact` 工具时，会通过
FrontendEventBridge 把 `artifacts.{type}` 事件镜像到运行事件流（"events" 集合）。
本模块负责在一次回复结束时，把这些事件转换成消息的 content_parts（type=artifact），
让 "agent 返回的消息" 真正带上内联产物并在刷新后依然可见。
"""

from __future__ import annotations

from typing import Any, Iterable

ARTIFACT_EVENT_PREFIX = "artifacts."
ARTIFACT_PART_TYPE = "artifact"
VALID_ARTIFACT_TYPES = {"message", "image", "diff", "document", "web"}


def is_artifact_event(event: dict[str, Any]) -> bool:
    return str(event.get("name", "")).startswith(ARTIFACT_EVENT_PREFIX)


def artifact_to_content_part(
    artifact: dict[str, Any],
    *,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把单个产物对象转换成一个 content_part。

    完整结构化产物放在 metadata.artifact 里，前端 ArtifactCard 据此渲染；
    同时把常用字段拍平到顶层，兼容已有的 content_part 读取逻辑。
    """

    artifact = dict(artifact or {})
    artifact_type = str(artifact.get("type", "")).strip().lower()
    base_metadata = dict(artifact.get("metadata") or {})
    part_metadata: dict[str, Any] = {
        **base_metadata,
        "artifact": artifact,
        "artifact_type": artifact_type,
        "editable": bool(artifact.get("editable", False)),
    }
    if source:
        part_metadata["artifact_source"] = source

    part: dict[str, Any] = {
        "type": ARTIFACT_PART_TYPE,
        "title": artifact.get("title", ""),
        "language": artifact.get("language", ""),
        "mime_type": artifact.get("mime_type", ""),
        "metadata": part_metadata,
    }
    if artifact_type in {"message", "document"}:
        part["text"] = artifact.get("content", "")
    elif artifact_type in {"image", "web"}:
        part["url"] = artifact.get("url", "")
    elif artifact_type == "diff":
        # diff 的前后内容保留在 metadata.artifact 里，after 拍平到 diff 字段做兜底。
        part["diff"] = artifact.get("after", "")
    return part


def collect_inline_artifact_parts(
    events: Iterable[dict[str, Any]] | None,
    *,
    since: float = 0.0,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """从运行事件中筛出 artifacts.* 并转换成 content_parts。

    - since: 只收集该时间戳之后产生的产物，用来把本次回复和历史回复区分开。
    - run_id: 可选，按 run_id 再过滤一层（DM 下 run_id 即 conversation_id）。
    """

    parts: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    ordered = sorted(events or [], key=lambda item: item.get("created_at") or 0)
    for event in ordered:
        if not is_artifact_event(event):
            continue
        created_at = event.get("created_at") or 0
        if since and created_at < since:
            continue
        payload = event.get("payload") or {}
        if run_id and payload.get("run_id") and payload.get("run_id") != run_id:
            continue
        artifact = payload.get("artifact") or {}
        if not artifact or str(artifact.get("type", "")).strip().lower() not in VALID_ARTIFACT_TYPES:
            continue
        event_id = event.get("event_id")
        if event_id:
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
        parts.append(
            artifact_to_content_part(
                artifact,
                source={
                    "event_id": event_id or "",
                    "agent_id": payload.get("agent_id", ""),
                    "run_id": payload.get("run_id", ""),
                    "created_at": created_at,
                },
            )
        )
    return parts
