"""Declaration only; event handler registration lives in tools_attach_methods."""
from domain.tool import Tool
from infra.config import bus, factory
from infra.event_bind import On_bind
from infra.tool.builtin.long_memory import MANAGE_MEMORY
from domain.runtime_hooks import get_memory_commands
from domain.tool import Tool_respond





MANAGE_MEMORY = Tool(
    name="manage_memory", field="memory",
    description="查询长期记忆，或在用户明确要求记住、更正、忘记时修改记忆。修改时必须引用当前用户原话 request_quote。"
                "更正/忘记须先 search 确定 block_id；目标不明确时询问用户。自动归档关闭不影响这些明确操作。",
    input_schema={"type": "object", "additionalProperties": False, "properties": {
        "operation": {"type": "string", "enum": ["search", "remember", "correct", "forget"]},
        "query": {"type": "string"}, "content": {"type": "string"},
        "block_id": {"type": "string"}, "request_quote": {"type": "string"},
    }, "required": ["operation"]},
)


on_tool = On_bind()
factory._build_and_register_list([MANAGE_MEMORY], bus)



@on_tool.on(factory.tool("manage_memory").called())
async def manage_memory(**kwargs):
    service = get_memory_commands()
    name, agent_id = "manage_memory", kwargs.get("agent_id", "")
    try:
        if service is None:
            raise ValueError("长期记忆服务未启用")
        result = await service.execute(**{k: kwargs[k] for k in
            ("operation", "query", "content", "block_id", "request_quote") if k in kwargs})
        return factory.tool(name).succeeded(Tool_respond(agent_id, name, True, result))
    except (ValueError, KeyError) as exc:
        return factory.tool(name).failed(Tool_respond(agent_id, name, False, str(exc)))
    except Exception:
        import logging
        logging.getLogger(__name__).exception("记忆操作失败")
        return factory.tool(name).failed(Tool_respond(agent_id, name, False, "记忆服务暂时不可用，请重试"))

