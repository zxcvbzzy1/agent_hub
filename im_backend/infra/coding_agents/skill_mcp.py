"""把 recall_skill 接进 coding agent 工具循环的“按次注入”接线。

设计要点（隔离）：绝不写任何全局文件——
  - Claude Code：用 `--mcp-config <项目内json>` + `--strict-mcp-config`，不调用
    `claude mcp add`，因此不会写进 ~/.claude.json，其他项目的 claude 看不到。
  - Codex：用 `-c mcp_servers.skill.*` 运行时覆盖 + `--ignore-user-config`，不写
    ~/.codex/config.toml，其他项目的 codex 也看不到（也顺带不吃用户全局的 node_repl）。

MCP server 脚本在 agent_flow 内（infra/skill/mcp_server.py），用当前后端解释器
（sys.executable，即 MY_env）作为子进程拉起，从同一 skills 目录检索。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from im_backend.infra.agent_flow_bridge.pathing import AGENT_FLOW_ROOT

SERVER_NAME = "skill"
TOOL_FQN = f"mcp__{SERVER_NAME}__recall_skill"  # Claude 里 MCP 工具名：mcp__<server>__<tool>

_SERVER_SCRIPT = AGENT_FLOW_ROOT / "infra" / "skill" / "mcp_server.py"
_CONFIG_DIR = AGENT_FLOW_ROOT / "temp" / "mcp"
_CONFIG_PATH = _CONFIG_DIR / "skill.mcp.json"


def _python() -> str:
    return sys.executable or "python3"


def available() -> bool:
    return _SERVER_SCRIPT.is_file()


def _claude_mcp_config_file() -> str:
    """生成（覆盖）项目内的 mcp-config json，返回其路径。非全局位置。"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {
        "mcpServers": {
            SERVER_NAME: {"command": _python(), "args": [str(_SERVER_SCRIPT)]}
        }
    }
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(_CONFIG_PATH)


def claude_args() -> list[str]:
    """Claude Code：按次注入 skill MCP，并放行该工具、严格只用本配置。"""
    if not available():
        return []
    return [
        "--mcp-config", _claude_mcp_config_file(),
        "--strict-mcp-config",
        "--allowedTools", TOOL_FQN,
    ]


def codex_args() -> list[str]:
    """Codex：运行时覆盖注入 skill MCP，并忽略用户全局配置。

    codex 的 `-c key=value` 把 value 按 JSON 解析，故 command 用带引号的 JSON 字符串、
    args 用 JSON 数组。这些覆盖仅本次生效，不落 ~/.codex/config.toml。
    """
    if not available():
        return []
    return [
        "--ignore-user-config",
        "-c", f"mcp_servers.{SERVER_NAME}.command={json.dumps(_python(), ensure_ascii=False)}",
        "-c", f"mcp_servers.{SERVER_NAME}.args={json.dumps([str(_SERVER_SCRIPT)], ensure_ascii=False)}",
    ]
