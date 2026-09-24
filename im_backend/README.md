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

## Redis 运行时与三级轨迹（v2）

配置根目录 `redis.env.example` 中的 `REDIS_URL` 和 `REDIS_KEY_PREFIX`。
同一部署的 worker 共享前缀，测试使用独立前缀。MongoDB 仍可使用单机部署，
不需要副本集、事务或 Outbox。Agent 由创建它的 API worker 执行，不自动接管或重跑。

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m uvicorn im_backend.api.index:app --host 127.0.0.1 --port 8010 --workers 2
```

### 数据与职责

- Mongo `runs` 是编排和单聊执行状态的事实来源。每次单聊回复及重新生成都有独立
  `run_id`；消息的 `run_id` 指向当前尝试，`source_message_id` 用于查找全部尝试。
- `RunStateService` 先更新 Mongo，再删除 Redis 快照。点查未命中才回填，列表直接查库。
  `cache:v2:run:{run_id}` 默认 TTL 5 秒；失效代次和条件回填阻止并发旧查询污染缓存。
  代次标记的 TTL 长于回填窗口，因此删除后不会永久遗留缓存元数据。
- 缓存操作超时 0.5 秒，删除共尝试 3 次。失败时记录日志并依靠 TTL 收敛；查询回源。
  这不是强一致或崩溃补偿方案，数据库提交到缓存失效之间仍可能短暂旧读。
- `RedisExecutionControl` 只维护 `control:v2:{kind}:{run_id}`、活跃索引、心跳、取消和审批。
  缓存删除不影响控制记录。kind 为 `orchestration` 或 `dm_reply`，两者均以 run ID 定位。
  取消依旧返回 202，所属 worker 每 500ms 检查信号。业务数据和最终事件处理完后才释放控制。
  启动和执行控制依赖 Redis；缓存降级不意味着允许绕过抢占启动任务。

### 两条事件通道

- `events:v2:run:{run_id}`：模型调用、思考、工具与智能体输出。持久化在 `events`；
  `llm.delta` / `agent.delta` 只短期保存在 Redis。
- `events:v2:scope:{scope_id}`：流程、任务、智能体生命周期，以及消息、审批、产物通知。
  持久化在 `im_events`，不会自动复制 run Stream。群聊 scope 是 room，单聊是 conversation。
- 事件带 `version=2`、run/scope/conversation/message 关联；每次智能体调用独立
  `execution_id`，步骤开始、结束与工具事件精确关联。同一智能体重复执行不会合并轨迹。
- Stream 默认保留最近 24 小时、约 100,000 条。SSE 使用 Redis ID 续传，`event_id` 去重，
  每 15 秒空闲心跳。摘要和 scope 重连会补查数据库，包括已经归档但推送失败的事件。
- 持久化事件先归档，再推送；推送单次最多等待 1 秒，共尝试 3 次。失败不改变已完成业务状态，
  没有持久化重试队列，未归档事件和过期 token 不承诺恢复。

### 查询与界面

- 房间/会话现有 `/events` SSE 只返回 scope；默认界面只显示业务轨迹名称。
- `GET /api/im/runs/{run_id}/events?view=summary&execution_id=...&limit=100&after=...`
  返回 `{items, next_cursor}`，不含正文；`limit` 最大 200。省略 `view` 仍兼容旧全量查询。
- `GET /api/im/runs/{run_id}/events/stream` 是摘要 SSE，可选 `execution_id`。
- `GET /api/im/runs/{run_id}/events/{event_id}` 返回单事件正文。
- `GET /api/im/scopes/{scope_id}/events/{event_id}` 返回业务事件详情。
- 首次展开 scope 获取名称并订阅摘要；再点击单条名称才加载正文。同一 run 共享连接，
  全部折叠或切换会话关闭连接。逐 token 增量不列行，最终内容归档后可查看。
- 正常回复、产物和人工确认仍直接可见。独立 agent_flow 新增
  `/api/runs/{run_id}/scope/events`，原 run SSE 保留执行事件。

### 发布与验证

先停止接收新执行，等待或取消旧版本任务，再配套更新前后端和重启所有 worker。
不要让新旧 worker 混跑。新版键空间隔离旧镜像；不清空共享 Redis。
旧 Mongo 事件保留但不在新轨迹中展示，历史聊天消息照常显示，不迁移运行中的旧任务。

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pytest agent_flow/api_services_test.py im_backend/tests/test_redis_runtime.py im_backend/tests/test_redis_im_integration.py im_backend/tests/test_run_monitor.py im_backend/tests/test_coding_unification_and_builder.py -v
node --test IM_front/checks/trace_client_check.mjs
cd IM_front
npm run build
```

后端测试使用独立 Redis 前缀、Mongo 测试数据库及临时上传目录，模型/执行器使用替身。
覆盖跨进程广播与控制、缓存竞争及故障、摘要分页与重连、重复调用、重新生成和删除。
测试只清理自己的命名空间，不使用 `FLUSHDB` 或 `FLUSHALL`。

乐观锁版本控制


[客户端连接] 
     │
     ├── 携带 last_id (旧游标)
     │
     ├── 校验游标有效性 (first <= last_id <= high)
     │      ├─ [有效] ──► 跳过全量拉取，直接从 last_id 继续监听
     │      └─ [失效] ──► 发送 stream.reset，全量对齐 (DB+Redis) ──► 游标强行推至 high
     │
     ├── 进入增量循环 (XREAD key: last_id)
     │      └─ 每收到一条新消息 ──► last_id = cursor (向前推进)
     │
     └── [网络中断/重连] ──► 客户端携带最新的 last_id 重新请求！