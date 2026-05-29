from __future__ import annotations
from im_backend.application.static_configs.static_agents import operator

# Each context item may contain:
# {
#   "context_id": "my_context",
#   "kind": "executor",
#   "name": "My Context",
#   "engine": context_engine,
#   "user_id": "optional-im-user-id",
#   "metadata": {},
# }
CONTEXTS = []


# Each agent item may contain:
# {
#   "agent": agent_instance,
#   "agent_type": "executor",
#   "context_id": "my_context",
#   "user_id": "optional-im-user-id",
#   "metadata": {},
# }
AGENTS = [{
  "agent": operator,
  "agent_type": "executor",
  "context_id": "operator_context",
  "user_id": "72002b50-21b9-4300-a66f-5763395efed1",
  "metadata": {},
},
]
