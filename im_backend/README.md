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

## 聊天文件上传

聊天附件由 `application/services/file/` 管理，实体默认保存在仓库根目录
`upload/<file_id>/<安全文件名>`，`im_files.storage_path` 保存绝对路径。
后端与 Native、Claude Code、Codex 需共享本机文件系统；移动仓库后需迁移数据库内的绝对路径。

- `POST /api/im/files/upload`：Bearer 登录，multipart 字段 `file`；单文件最大 20 MiB。
- `GET /api/im/files?limit=50&before=<file_id>`：分页查询自己的已发送文件，返回
  `items`、`has_more`、`next_cursor`。
- `GET /api/im/files/{file_id}/download`：已发送文件允许所有登录用户下载，暂存文件仅上传者可下载。
- `DELETE /api/im/files/{file_id}`：仅上传者可删除实体，元数据保留为 `delete`，重复删除幂等。
- 单聊／群聊原消息接口接收 `content_parts: [{"type":"file","file_id":"..."}]`，
  支持与文本混合及纯附件消息，每条最多 10 个附件。服务端校验上传者并补齐可信属性。
  前端在既有 `metadata` 中携带 UUID `client_message_id`，网络重试沿用此值，避免重复入库。

`im_files` 保存文件身份、上传者、名称、类型、实际大小、绝对路径、状态、过期时间及创建／更新时间。
`im_conversation_files` 保存 `relation_id`、`file_id`、`message_id`、`conversation_id`、`room_id` 和时间戳。
索引在后端启动时幂等创建，其中 `(file_id, message_id)` 唯一。

上传为 `pending`；成功发送后为 `attached`，永久保留到上传者主动删除。
删除消息／会话／群聊只清除引用。删除实体先置 `deleting`，成功后置 `delete`；失败保留状态等待重试。
未发送文件 24 小时后过期，启动时和每小时由应用清理实体并保留删除记录，恢复中断的关联操作。
只有匹配消息／会话关联且状态有效的文件路径进入当前消息、历史或引用上下文；不自动读取内容、OCR、RAG 或发送视觉附件。

数据库内存兜底已全局移除。启动前必须运行 MongoDB（默认 `127.0.0.1:27017`），
可用 `IM_MONGO_URL` / `IM_MONGO_DB` 配置 IM 数据库。运行期间数据库故障返回 503。
单元测试可显式注入测试替身，集成测试使用独立临时数据库。

文件服务验证（会自动创建并删除 `im_file_test_<uuid>` 测试库，不操作业务库）：

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pytest im_backend/checks/file_upload_test.py im_backend/tests/test_prompting.py -v
npm --prefix IM_front run build
```

## Redis 运行时（第一阶段）

安装依赖后，将根目录 `redis.env.example` 中的配置加入 `.env`。
`REDIS_URL` 支持完整的 Redis URL；所有同一部署的 API worker 必须使用相同的
`REDIS_KEY_PREFIX`，测试和其他部署应使用不同前缀。Redis 不可用时服务启动失败，
请求阶段返回 503，不会降级到进程内事件队列。

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pip install -r agent_flow/requirements-api.txt
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m uvicorn im_backend.api.index:app --host 127.0.0.1 --port 8010 --workers 2
```

本阶段 worker 指 API 进程。Agent 任务仍由创建它的进程执行；Redis 不负责任务排队或
执行接管。共享工作目录仍使用原有文件系统。独立运行 `agent_flow.api` 时也要配置 Redis。

### 事件与续传

- `events:run:{runtime_scope_id}` 保存 Agent 事件；`events:scope:{scope_id}` 保存 IM 合流。
  键名前统一加配置前缀。群聊事件 scope 是 room ID；单聊是 conversation ID。
- 群聊先建立消息与 Run 的关联及 Redis 路由，再启动执行；运行事件发布到两个 Stream。
- 非增量事件继续归档 Mongo；`llm.delta`、`agent.delta` 仅保存 Redis。
- 每条 Stream 最多约 100,000 条，按最近 24 小时裁剪，并在闲置 24 小时后过期。
  数量限制可能缩短高流量会话的实际续传窗口。裁剪在写入和开始读取时执行。
- SSE `id` 是当前 Stream 的 Redis ID，JSON `event_id` 仍是业务去重 ID。
  客户端重连发送 `Last-Event-ID`；多个连接独立 `XREAD`，没有竞争消费组。
- 首次连接合并 Mongo 历史与 Redis 增量，发送 `stream.ready` 后进入实时流。
  游标过期发送 `stream.reset`，客户端清空事件视图并重新同步。历史 token 被裁剪后，
  只能恢复归档事件和最终消息。每 15 秒发送空闲心跳。
- 查询执行详情继续读取 Mongo，旧事件无需迁移；旧历史没有 token 续传能力。

### 状态、取消与确认

Redis `state:{kind}:{target_id}` 保存当前状态，`active` 索引活跃任务。
群聊 kind 为 `orchestration`、target 为 Run ID；单聊 kind 为 `dm_reply`、target 为用户消息 ID。
单聊的运行事件范围仍然是 conversation ID，两种 ID 不可混用。

取消接口返回 HTTP 202；`cancel_requested` 表示取消请求已登记，并非执行已停止。
所属进程每 500ms 检查控制记录，完成取消后再推送终态。人工确认记录也存放 Redis，
可以在任意 API worker 提交结果。运行监控和消息列表合并 Redis 当前状态与 Mongo 历史。

每个进程每 10 秒刷新心跳，心跳有效期 30 秒。失联任务由其他活跃进程标记中断，
不会自动接管或重跑。API 启动不再批量取消其他进程的任务。
上线前停止旧版本进程中的运行任务；没有 Redis 归属记录的旧运行中任务不迁移执行。

异步接口改造后，调用事件 `publish()`、Run 创建/查询/取消，以及会发布事件的 IM
业务方法时必须 `await`。纯 Mongo 历史读取仍保持同步。资源通过 FastAPI lifespan
初始化和关闭，测试中也应使用同一事件循环并管理 lifespan/运行时连接。

### 验证

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pytest agent_flow/api_services_test.py im_backend/tests/test_redis_runtime.py im_backend/tests/test_redis_im_integration.py im_backend/tests/test_run_monitor.py im_backend/tests/test_coding_unification_and_builder.py -v
cd IM_front
npm run build
```

第一组测试使用独立 Redis key 前缀并启动子进程验证跨进程广播与控制；第二组使用
独立 Mongo 测试数据库及临时上传目录验证真实 IM 接口。均不调用真实 LLM，结束时
只清理测试创建的命名空间，不使用 `FLUSHDB` 或 `FLUSHALL`。
