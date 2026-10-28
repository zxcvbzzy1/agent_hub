import asyncio
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from domain.event import Event, EventBusPort
from domain.runtime_hooks import get_human_approval_provider, get_run_context_provider
from domain.tool import Tool_respond


def normalize_questions(questions: Any) -> list[dict[str, Any]]:
    """Canonical IDs belong to the server, not the model or the browser."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
        raise ValueError("每次必须提供 1～3 个问题")
    result = []
    for index, raw in enumerate(questions, 1):
        if not isinstance(raw, dict):
            raise ValueError("问题必须是对象")
        question = raw.get("question")
        kind = raw.get("type", "single")
        if (not isinstance(question, str) or not question.strip() or not isinstance(kind, str) or
                kind not in {"single", "multiple", "text"}):
            raise ValueError("问题必须包含非空题干及有效题型")
        options = raw.get("options", [])
        if not isinstance(options, list):
            raise ValueError("备选项必须是数组")
        if kind == "text":
            if options:
                raise ValueError("纯文本题不能包含备选项")
        elif not 2 <= len(options) <= 4:
            raise ValueError("选择题必须提供 2～4 个备选项")
        if any(not isinstance(o, str) or not o.strip() or o.strip() == "其他" for o in options):
            raise ValueError("备选项必须是非空文本，“其他”由系统追加")
        labels = [o.strip() for o in options]
        if len(set(labels)) != len(labels):
            raise ValueError("备选项不能重复")
        choices = [{"id": f"o{i}", "label": label} for i, label in enumerate(labels, 1)]
        if kind != "text":
            choices.append({"id": "other", "label": "其他"})
        result.append({"id": f"q{index}", "question": question.strip(), "type": kind, "options": choices})
    return result


def validate_question_answers(questions, answers) -> list[dict[str, Any]]:
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise ValueError("请回答全部问题")
    by_id = {}
    for answer in answers:
        if not isinstance(answer, dict) or not isinstance(answer.get("question_id"), str):
            raise ValueError("答案缺少问题 ID")
        if answer["question_id"] in by_id:
            raise ValueError("同一问题不能重复回答")
        by_id[answer["question_id"]] = answer
    if set(by_id) != {q["id"] for q in questions}:
        raise ValueError("答案与原问题不匹配")
    result = []
    for question in questions:
        answer = by_id[question["id"]]
        selected = answer.get("selected_option_ids", [])
        text = answer.get("text", "")
        if not isinstance(text, str) or not isinstance(selected, list) or any(not isinstance(v, str) for v in selected):
            raise ValueError("答案格式无效")
        text = text.strip()
        choices = {option["id"]: option["label"] for option in question["options"]}
        if len(selected) != len(set(selected)) or any(v not in choices for v in selected):
            raise ValueError("答案包含重复或不存在的选项")
        if question["type"] == "text":
            if selected or not text:
                raise ValueError("纯文本题必须填写回答，不能选择选项")
        else:
            if not selected or (question["type"] == "single" and len(selected) != 1):
                raise ValueError("请选择有效数量的选项")
            if "other" in selected and not text:
                raise ValueError("选择“其他”时必须填写内容")
            if "other" not in selected and text:
                raise ValueError("补充文本仅用于“其他”选项")
        ordered = [key for key in choices if key in selected]
        result.append({"question_id": question["id"], "question": question["question"],
                       "selected_option_ids": ordered, "selected_options": [choices[key] for key in ordered],
                       "text": text})
    return result


_terminal_question_lock = asyncio.Lock()


async def ask_question_input(*, agent_id: str, questions: list) -> dict:
    """Use the existing host provider; only interactive standalone runs use stdin."""
    from infra.runtime.control import ensure_execution_active

    await ensure_execution_active()
    provider = get_human_approval_provider()
    context = get_run_context_provider()
    run_id = context.run_id_for_agent(agent_id) if context else ""
    if provider is not None and run_id and callable(getattr(provider, "request_question", None)):
        result = await provider.request_question(run_id=run_id, agent_id=agent_id, tool_name="ask_user",
            called_event_name="infra.human.ask_user.called", arguments={"questions": questions})
    else:
        normalized = normalize_questions(questions)
        if not sys.stdin or not sys.stdin.isatty():
            raise ValueError("ask_user 不可用：没有网页问答上下文或可交互终端")

        def read_answers():
            answers = []
            for q in normalized:
                while True:
                    print(q["question"])
                    for i, option in enumerate(q["options"], 1):
                        print(f"{i}. {option['label']}")
                    try:
                        selected = []
                        text = ""
                        if q["type"] == "text":
                            text = input("回答：")
                        else:
                            raw = input("选择序号（多选用逗号分隔）：")
                            indexes = [int(v.strip()) for v in raw.replace("，", ",").split(",")]
                            if any(i < 1 or i > len(q["options"]) for i in indexes):
                                raise ValueError("选项序号无效")
                            selected = [q["options"][i - 1]["id"] for i in indexes]
                            if "other" in selected:
                                text = input("其他：")
                        answer = {"question_id": q["id"], "selected_option_ids": selected, "text": text}
                        validate_question_answers([q], [answer])
                        answers.append(answer)
                        break
                    except ValueError as exc:
                        print(str(exc))
            return {"answers": validate_question_answers(normalized, answers), "attachments": []}

        async with _terminal_question_lock:
            result = await asyncio.to_thread(read_answers)
    await ensure_execution_active()
    return result


async def ask_human_input(prompt: str) -> str:
    """异步包装 input，避免在 async 事件链路里直接阻塞事件循环。"""
    return await asyncio.to_thread(input, prompt)


@dataclass
class HumanAuditResult:
    approved: bool
    reason: str


@dataclass
class HumanInputContext:
    tool_name: str
    called_event_name: str
    arguments: dict[str, Any]


_human_input_context: ContextVar[HumanInputContext | None] = ContextVar(
    "human_input_context",
    default=None,
)


def parse_human_results(human_results: Any) -> HumanAuditResult:
    if not human_results:
        return HumanAuditResult(False, "未找到人机协作确认处理器")

    results = human_results if isinstance(human_results, list) else [human_results]

    for result in results:
        if isinstance(result, Exception):
            return HumanAuditResult(False, f"人机协作确认异常: {result}")
        if isinstance(result, bool):
            reason = "用户已确认" if result else "用户拒绝执行"
            return HumanAuditResult(result, reason)
        if isinstance(result, Event):
            data = result.unpack()
            approved = bool(data.get("approved", False))
            reason = data.get("reason") or ("用户已确认" if approved else "用户拒绝执行")
            return HumanAuditResult(approved, reason)
        if isinstance(result, dict):
            approved = bool(result.get("approved", False))
            reason = result.get("reason") or ("用户已确认" if approved else "用户拒绝执行")
            return HumanAuditResult(approved, reason)

    return HumanAuditResult(False, "人机协作确认处理器返回格式无效")


async def ask_web_human_input(prompt: str) -> str:
    """通过网页端等待人类输入；没有网页上下文时回落到终端 input。"""
    context = _human_input_context.get()
    if context is None:
        return await ask_human_input(prompt)

    approval_provider = get_human_approval_provider()
    run_context_provider = get_run_context_provider()
    agent_id = context.arguments.get("agent_id", "")
    run_id = ""
    if run_context_provider is not None and agent_id:
        run_id = run_context_provider.run_id_for_agent(agent_id)
    if approval_provider is None or not run_id:
        return await ask_human_input(prompt)

    result = await approval_provider.request_approval(
        run_id=run_id,
        agent_id=agent_id,
        tool_name=context.tool_name,
        called_event_name=context.called_event_name,
        arguments=context.arguments,
    )
    approved = bool(result.get("approved"))
    reason = result.get("reason", "")
    if approved:
        return "yes"
    return f"no {reason}".strip()


class HumanApprovalService:
    """人类确认服务；替换 input_func 即可切换确认策略。"""

    def __init__(
        self,
        input_func=ask_web_human_input,
    ) -> None:
        self.input_func = input_func
        self._lock = asyncio.Lock()

    async def input(self, prompt: str) -> str:
        async with self._lock:
            return await self.input_func(prompt)

# 外部调用的确认服务实例
human_approval_service = HumanApprovalService()



# 中间件逻辑，发送人机协作事件并等待确认结果；如果未通过审核则发送工具执行失败事件
class HumanCollaborationAuditor:
    """工具执行前的人机协作审核器。"""

    def __init__(self, factory, bus: EventBusPort | None) -> None:
        self.factory = factory
        self.bus = bus

    async def handle(self, event: Event, call_next):
        """执行完整的人机协作审核 middleware 流程。"""
        audit_result = await self.audit(event)
        if audit_result.approved:
            return await call_next()

        return await self.reject(event, audit_result.reason)

    async def audit(self, event: Event) -> HumanAuditResult:
        arguments = event.unpack()
        if not event.name.endswith(".called"):
            return HumanAuditResult(True, "无需人机协作审核")

        try:
            spec = self.factory.get_spec(event.name)
        except KeyError:
            return HumanAuditResult(True, "未找到工具描述，跳过人机协作审核")
        tool_name = spec.tool_name

        if not spec.tool_metadata.get("require_human_confirm"):
            return HumanAuditResult(True, "工具未要求人机协作审核")
        if self.bus is None:
            return HumanAuditResult(False, "工具要求人机协作审核，但 EventBus 未注入")

        human_event_name = f"human.{tool_name}"
        print(f"[HUMAN] 正在启动人工审核 {human_event_name}")
        token = _human_input_context.set(
            HumanInputContext(
                tool_name=tool_name,
                called_event_name=event.name,
                arguments=arguments,
            )
        )
        try:
            human_results = await self.bus.publish_one(
                Event(
                    name=human_event_name,
                    payload={
                        "tool_name": tool_name,
                        "called_event_name": event.name,
                        "arguments": arguments,
                    },
                )
            )
        finally:
            _human_input_context.reset(token)

        return parse_human_results(human_results)

    async def reject(self, event: Event, reason: str):
        arguments = event.unpack()
        try:
            spec = self.factory.get_spec(event.name)
        except KeyError:
            return Event(
                name=f"{event.name}.human_rejected",
                payload={"approved": False, "reason": reason},
            )
        tool_name = spec.tool_name
        respond = Tool_respond(
            agent_id=arguments.get("agent_id", ""),
            name=tool_name,
            success=False,
            respond=reason,
        )
        return await self.factory.tool(tool_name).emit_failed(respond)
