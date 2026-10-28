"""Ask for missing decisions through the host's shared human confirmation service."""
import json

from domain.tool import Tool, Tool_respond
from infra.config import bus, factory
from infra.event_bind import On_bind
from infra.tool.common_func import ask_question_input


ASK_USER = Tool(
    name="ask_user",
    field="human",
    description="当需求、设计边界或执行条件不清楚时向用户提问，也可以主动提问，等待回答后继续。每次 1～3 题，支持单选、多选和纯文本。选择题提供 2～4 项，系统自动追加‘其他’，用户可上传附件。不要自行猜测重要决策。",
    input_schema={
        "type": "object",
        "properties": {"questions": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1},
                "type": {"type": "string", "enum": ["single", "multiple", "text"]},
                "options": {"type": "array", "items": {"type": "string"},
                            "description": "选择题提供 2～4 个不同选项，不要包含‘其他’；纯文本题省略"},
            },
            "required": ["question", "type"],
        }}},
        "required": ["questions"],
    },
)

on_tool = On_bind()
factory._build_and_register_list([ASK_USER], bus)


@on_tool.on(factory.tool("ask_user").called())
async def ask_user(**kwargs):
    agent_id = kwargs["agent_id"]
    try:
        result = await ask_question_input(agent_id=agent_id, questions=kwargs.get("questions"))
    except (ValueError, EOFError, OSError) as exc:
        return factory.tool("ask_user").failed(Tool_respond(
            agent_id=agent_id, name="ask_user", success=False, respond=str(exc)))
    return factory.tool("ask_user").succeeded(Tool_respond(
        agent_id=agent_id, name="ask_user", success=True, respond=json.dumps(result, ensure_ascii=False)))
