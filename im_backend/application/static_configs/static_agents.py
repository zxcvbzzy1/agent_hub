from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()

from domain.agent_base import AgentBase  # type: ignore  # noqa: E402
from domain.context.context import ContextEngine  # type: ignore  # noqa: E402
from domain.context.providers import *  # type: ignore  # noqa: E402,F403
from domain.context.strategy import RecencyStrategy  # type: ignore  # noqa: E402
from domain.memory.short.default_short_term_memory import DefaultShortTermMemory  # type: ignore  # noqa: E402


operator_memory = DefaultShortTermMemory(["tool_respond", "agent_history"])
operator_context = ContextEngine(
    providers=[
        UserPromptProvider(),
        StateProvider(),
        AvailableToolsProvider(["system"]),
        HistoryProvider(operator_memory, "agent_history", FullHistoryStrategy()),
        ToolOutputProvider(operator_memory, "tool_respond", FullHistoryStrategy() | RecencyStrategy(15)),
    ],
    memory=operator_memory,
)

class OperatorExecutor(AgentBase):
    """负责系统操作步骤的 ReACT executor"""

    def _build_agent_prompt(self) -> str:
        return f"""
你是一个系统操作执行者，当前工作目录为：{self.work_path}
你可以使用 bash 工具执行命令来完成任务。

## 输出格式
用 JSON 严格按以下格式回复：
{{
  "think": "你的思考过程",
  "tool_calls": [
    {{
      "tool_name": "工具名",
      "arguments": {{"参数名": "参数值"}},
      "reasoning": "为什么调用这个工具"
    }}
  ],
  "is_finished": false
}}

## 任务完成时输出
{{
  "think": "...",
  "tool_calls": [],
  "is_finished": true,
  "finish_reason": "完成原因",
  "final": "最终结果"
}}
"""
    
operator = OperatorExecutor(
    id="operator",
    name="系统操作执行者",
    llm=None,
    context=operator_context,
)

operator.inject_attribute(description='系统操作执行者,可以使用 bash 工具执行命令来完成任务')
