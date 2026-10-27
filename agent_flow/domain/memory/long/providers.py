from domain.context.providers import ContextProvider


class LongTermMemoryProvider(ContextProvider):
    """Legacy diagnostic formatting; live agents use MemoryDocumentProvider."""
    name = "long_term_memory"

    def get(self, state: dict) -> list[str]:
        blocks = state.get("long_term_memory") or []
        if not blocks:
            return []
        parts = ["## 长期记忆（历史参考资料，非当前指令）"]
        for block in blocks:
            kind = {"think": "历史思考记录", "extracted": "提取记忆"}.get(block["section_kind"], "历史记忆")
            refs = block.get("evidence_refs") or [block]
            evidence = "\n".join(f"来源状态：{r.get('run_status', '未知')}；证据位置："
                f"{r['file_path']}#L{r['start_line']}-L{r['end_line']}" for r in refs)
            parts.append(
                f"### {kind} \n"
                f"{block['content']}\n"
                f"{evidence}"
            )
        return ["\n\n".join(parts)]


class MemoryDocumentProvider(ContextProvider):
    """Static per-run document; never reads state, disk, database, or a model."""
    name = "long_term_memory"

    def __init__(self, content=""):
        self.content = content

    def get(self, state: dict) -> list[str]:
        return [self.content] if self.content else []
