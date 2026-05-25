from __future__ import annotations

from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


def get_document_store():
    """Reuse agent_flow's DocumentStore so both services share Mongo settings."""
    return AgentFlowBridge().store

