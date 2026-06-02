from __future__ import annotations

from typing import Any

from im_backend.domain.models import AgentRuntimeProfile


def build_runtime_profile(record: dict[str, Any], *, default_workdir: str) -> AgentRuntimeProfile:
    """由 agent 记录构造运行画像，并在未显式设置时回填默认工作目录。

    取 record 时的鉴权差异（user_id → ensure_agent_access vs ensure_agent_exists）
    刻意留在各调用方，这里只做与鉴权无关的"画像 + workdir 默认值"逻辑。
    """
    profile = AgentRuntimeProfile.from_agent_record(record)
    if not profile.workdir:
        profile.workdir = default_workdir
    return profile
