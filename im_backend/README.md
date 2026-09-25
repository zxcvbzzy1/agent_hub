# IM Backend

独立的 IM Agent Platform 后端。它保留 IM 房间、富消息、artifact、Claude Code / Codex 适配等产品逻辑，并通过 `infra/agent_flow_bridge/` 集中复用 `agent_flow` 的 Agent、Run、PlanOrchestrator、SSE 和 MongoDB 存储能力。

## 启动

```bash
IM_SSE_COOKIE_SECURE=false PYTHONPATH=. \
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m uvicorn im_backend.api.index:app --host 127.0.0.1 --port 8010
```

前端通过同源 `/api` 访问后端，Vite 默认代理到 `http://127.0.0.1:8010`。
本地 HTTP 启动后端需显式设置 `IM_SSE_COOKIE_SECURE=false`；生产 HTTPS 保持默认 `true`。
后端地址不同时，用 `IM_API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev` 启动前端，移除旧的跨源 `VITE_IM_API_BASE_URL`。

## 原生 EventSource

- 登录、注册及 Bearer `/api/im/auth/me` 设置 `im_sse_session`：HttpOnly、SameSite=Lax、Path=/api/im、host-only，期限不超过原会话剩余期限。网页登录恢复先完成 `/auth/me`；同页并发订阅共享初始化。
- 只有会话、房间和 run SSE 接口接受同源 Cookie；有 Authorization 时优先验证，验证失败不回退 Cookie。普通受保护 API 继续使用 Bearer。退出时撤销会话、删 Cookie 并关闭本地连接。
- 原生 EventSource 负责解析和网络重连。首次打开通过 `last_id` 恢复完整 IndexedDB 快照；浏览器自动重连的 `Last-Event-ID` 优先。`stream.reset` 清空浏览器内部 ID 和未完成快照，`stream.ready` 才允许提交完整快照；过滤事件通过 `stream.checkpoint` 推进游标。
- 收到事件的浏览器游标与已提交的本地检查点分别管理；IndexedDB 事务完成后才更新 localStorage。缓存无法使用时继续实时展示，刷新后从 Redis 全量缓存恢复。
- 原生连接进入 CLOSED 后，仅自动尝试一次 `/auth/me` 恢复，失败显示手动重新连接。正常 CONNECTING 重试交给浏览器。
- 后端需先部署，再发布前端；Redis 队列、缓存键和归档逻辑无迁移。部署后检查 SSE HTTP 错误、重连和 reset 次数，以及 `/health` 中已有缓存回源与归档指标；浏览器 Network 中应持续收到事件，不应依靠刷新。
- 生产使用 [Nginx 同源代理示例](../deploy/nginx.im.conf.example)，关闭缓冲、保持 15 秒心跳、读取超时 60 秒。Uvicorn 仅信任代理 IP 的转发头，以正确识别 HTTPS Origin。独立 agent_flow 接口不变。

## Redis 结构

所有键以 `REDIS_KEY_PREFIX`（默认 `agenthub`）开头。事件键还包含由目标数据库连接与库名计算的 `namespace`，防止不同数据库共用归档队列。事件流中的 `category` 为 `run` 或 `scope`。

| 键模式 | 类型 | 生命周期 | 用途 |
| --- | --- | --- | --- |
| `events:v3:{namespace}:{category}:{scope}:live` | Stream | 24 小时并限制长度 | SSE 实时增量；Stream ID 就是客户端游标。 |
| `...:meta` | Hash | 随流逻辑保留 | `generation` 用于删除后使旧游标失效；`watermark` 是本代最后生成的 Stream ID。旧 `high` 仅兼容读取。 |
| `...:user:{sha256(user_id)}` | Hash | 闲置 2 天 | 用户完整持久化历史。控制字段为 `__ready`、`__generation`、`__watermark`、构建期 `__token`；其余字段为 `event_id -> event JSON`。旧 `__high` 仅兼容读取。 |
| `...:readers` | Set | 闲置 2 天 | 当前 scope 已建立或正在建立的用户缓存键；发布事件时据此更新所有热缓存。 |
| `...:pending` | Hash | 不过期 | 尚未确认写入 DB 的 `event_id -> event JSON`，归档成功 ACK 后删除。 |
| `...:deleted` | Set | 不过期 | 删除墓碑，成员是 `event_id` 或 `*`，阻止延迟重试令事件复活。 |
| `events:v3:{namespace}:archive` | Stream + consumer group | 未确认数据不裁剪 | 唯一归档队列；字段描述 insert/delete 操作。DB 成功后原子 `XACK + XDEL`。 |
| `...:{category}:{scope}:dedup` | Hash | 24 小时 | `event_id -> Stream ID`，让重复发布返回原游标且不重复入队。 |
| `...:{category}:scopes` | Set | 长期 | 记录出现过的 scope，供清理流程发现事件范围。 |
| `events:v3:{namespace}:metrics` | Hash | 长期 | 缓存命中、回源、归档成功和失败计数。 |
| `events:v3:{namespace}:lock:*` | String/lock | 30 秒并续租 | 跨 worker 的缓存构建、流修改和归档互斥。 |

完整缓存只保存持久化展示事件；短期 token 增量留在 `live`。`watermark` 是快照与实时流的交接边界，不表示消费进度，也不要求对应记录仍留在 `live`。

运行控制使用独立键：`cache:v2:run:{run_id}` 是 5 秒 DB 状态快照，`cache:v2:generation:{run_id}` 防止失效期间旧数据回填；`control:v2:*`、`worker:*`、`confirmation:*` 分别保存任务租约、worker 心跳和人工确认，它们不属于事件完整缓存。

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

## Redis 运行时与三级轨迹

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

- `events:v3:{数据库命名空间}:run:{run_id}:live`：模型调用、思考、工具与智能体输出。持久化在 `events`；
  `llm.delta` / `agent.delta` 只短期保存在 Redis。
- `events:v3:{数据库命名空间}:scope:{scope_id}:live`：流程、任务、智能体生命周期，以及消息、审批、产物通知。
  持久化在 `im_events`，不会自动复制 run Stream。群聊 scope 是 room，单聊是 conversation。
- 事件带 `version=2`、run/scope/conversation/message 关联；每次智能体调用独立
  `execution_id`，步骤开始、结束与工具事件精确关联。同一智能体重复执行不会合并轨迹。
- Stream 默认保留最近 24 小时、约 100,000 条。SSE 使用带代次的 Redis ID 续传，`event_id` 去重，
  每 15 秒空闲心跳。摘要和 scope 重连优先使用完整缓存，仅冷缓存初始化回源 Mongo。
- 持久化事件先进入 Redis，归档队列由消费组异步批量落库并 ACK；发布单次最多等待 5 秒，
  共尝试 3 次。发布失败明确报错，未 ACK 事件持续保留，过期临时 token 不承诺恢复。

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

### 事件缓存与异步归档（v3）

RunStateCache 仍先写 Mongo，再失效/回填 Redis（TTL 5 秒）；以下策略只作用于事件。

- Redis 按用户和 scope/run 保存完整持久化历史，默认闲置两天过期；读取或新事件更新续期。
  临时 token 增量仍只保留在有长度/时间限制的实时流中。
- SSE 接收的是 `generation/redis-stream-id` 不透明游标。支持 `Last-Event-ID` 和 `last_id` 查询参数，
  请求头优先。有效游标直接续读；失效游标先 `stream.reset`，然后从完整缓存重放。
  仅缓存缺失时读取 Mongo：跨 worker 初始化锁合并 DB 与未归档事件，暂存缓存接收构建期间的新事件。
- 事件发布原子写入实时流、现存用户缓存和独立归档 Stream，不再等待 Mongo 写入。
  归档 Stream 每数据库一条、一个消费组，从 `0-0` 建组，不设 TTL，也不裁剪未确认记录。
  worker 默认每秒或累计 500 条进行幂等批量 upsert。只有确认成功的事件才 `XACK` + `XDEL`；
  不确定结果不确认，闲置 30 秒的 pending 记录通过 `XAUTOCLAIM` 接管。不会删除用户历史缓存。
- 事件详情/摘要读取包含尚未落库的数据。删除先持久化 tombstone 并登记可重试的 DB 删除任务，
  与归档串行协调、使用户缓存失效；在途 SSE 最迟在下一次事件/15 秒心跳发现代次变化后重建。
  删除标记与流代次不随两天 TTL 过期，避免旧事件复活。
- IM SSE 由服务端根据 Bearer 或同源 Cookie 确定 user_id。网页使用原生 EventSource；IndexedDB 原子保存展示事件
  和检查点，提交成功后才更新 localStorage 游标。只有完整快照可续读，多标签页事务合并，退出登录清理。
  独立 agent_flow API 保持现有访问方式，使用 service 缓存身份。

部署需要 Redis >= 6.2、`appendonly yes`、`appendfsync everysec`、`maxmemory-policy noeviction`。
每秒 AOF 接受约一秒灾难故障窗口；未落库数据依赖 Redis，因此不能把它当作可清空的普通缓存。
应用不会修改共享 Redis 的服务器配置。Redis 发布失败明确报错；Mongo 故障时保留并重试待归档数据。

`GET /health` 的 `event_archive` 返回 aof_enabled、queued、pending、oldest_age_seconds、cache_hits、cache_misses、
history_loads、archived、archive_failures。worker 每分钟检查积压，最老待写超过 60 秒时记录警告。
上线时停止旧生产者后统一切换，v3 不信任 v2 为完整缓存；首次读取按需重建。
回退前停止新事件生产，保持归档 worker 运行到 queued 和 pending 都为 0；不要清空共享 Redis。

附加验证：

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pytest im_backend/event_journal_test.py -v
npm --prefix IM_front run test:events
npm --prefix IM_front run build
```
