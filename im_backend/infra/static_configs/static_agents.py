from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()

from domain.agent.plan.planAgent import PlanAgent # type: ignore  # noqa: E402
from domain.agent.plan.providers import * # type: ignore  # noqa: E402
from domain.agent_base import AgentBase  # type: ignore  # noqa: E402
from domain.context.context import ContextEngine  # type: ignore  # noqa: E402
from domain.context.providers import *  # type: ignore  # noqa: E402,F403
from domain.context.strategy import RecencyStrategy  # type: ignore  # noqa: E402
from domain.memory.short.default_short_term_memory import DefaultShortTermMemory  # type: ignore  # noqa: E402

nums = 1

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
    
operators =[]
for i in range(nums): 
  operator_memory = DefaultShortTermMemory(["tool_respond", "agent_history", "error", "skill"])
  operator_context = ContextEngine(
      providers=[
          StateProvider(),
          AvailableToolsProvider(["system"]),
          PinnedContextProvider(),
          UserPromptProvider(),
          SkillProvider(operator_memory),
          ErrorProvider(operator_memory),
          HistoryProvider(operator_memory, "agent_history", FullHistoryStrategy()),
          ToolOutputProvider(operator_memory, "tool_respond", FullHistoryStrategy() | RecencyStrategy(15)),
      ],
      memory=operator_memory,
  )
  operator = OperatorExecutor(
      id=f"operator_{i}",
      name=f"系统操作执行者_{i}",
      llm=None,
      context=operator_context,
  )
  operator.inject_attribute(description='系统操作执行者,可以使用 bash 工具执行命令来完成任务')
  operators.append(operator)


plan_nums = 1
plans =[]

for i in range(plan_nums):
   # 共享记忆：让 planner 与 executors 能看到工具反馈和历史结果。
  workflow_memory = DefaultShortTermMemory(["tool_respond", "agent_history", "error", "skill"])
  # plan agent 上下文，提供给 planner 用于决策和编排
  planner_context = ContextEngine(
      providers=[
          StateProvider(),
          AvailableExecutorsProvider(),
          AvailableToolsProvider(["system"]),
          PinnedContextProvider(),
          UserPromptProvider(),
          SkillProvider(workflow_memory),
          ErrorProvider(workflow_memory),
          PlanObservationProvider(),
          ExecutorStatusProvider(),
          HistoryProvider(workflow_memory, "agent_history", FullHistoryStrategy()),
          ToolOutputProvider(workflow_memory, "tool_respond", FullHistoryStrategy() | RecencyStrategy(15)),
      ],
      memory=workflow_memory,
  )
  planner = PlanAgent(
    id=f"plan_agent_{i}",
    name=f"任务编排者_{i}",
    llm=None,
    context=planner_context)
  planner.inject_attribute(description='计划编排智能体，负责创建计划')
  plans.append(planner)


