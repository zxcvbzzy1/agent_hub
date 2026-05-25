# IM Backend

独立的 IM Agent Platform 后端。它保留 IM 房间、富消息、artifact、Claude Code / Codex 适配等产品逻辑，并通过 `infra/agent_flow_bridge/` 集中复用 `agent_flow` 的 Agent、Run、PlanOrchestrator、SSE 和 MongoDB 存储能力。

## 启动

```bash
PYTHONPATH=/Users/zxcvbzzy1/Desktop/项目/ByteDance_AgentHub \
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m uvicorn im_backend.api.index:app --host 127.0.0.1 --port 8010
```

前端默认连接 `http://127.0.0.1:8010`，也可以通过 `IM_front/.env` 设置：

```text
VITE_IM_API_BASE_URL=http://127.0.0.1:8010
```

## API

- `GET /health`
- `GET /api/im/agents`
- `POST /api/im/rooms`
- `GET /api/im/rooms`
- `GET /api/im/rooms/{room_id}`
- `GET /api/im/rooms/{room_id}/messages`
- `POST /api/im/rooms/{room_id}/messages`
- `POST /api/im/rooms/{room_id}/dispatch`
- `GET /api/im/rooms/{room_id}/stream`
- `POST /api/im/messages/{message_id}/actions`
- `POST /api/im/artifacts/upload`
- `GET /api/im/artifacts/{artifact_id}`

## 安全默认值

Claude Code / Codex agent 第一版默认需要人工确认；未确认前只生成确认卡片，不直接启动外部 CLI。Runner 的命令构造使用只读/计划模式，不使用危险跳权参数。
