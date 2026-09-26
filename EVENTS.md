# 后端事件协议

事件名统一定义在两个不依赖数据库、Redis 或应用容器的 Python 模块中：

- [agent_flow/domain/event_names.py](agent_flow/domain/event_names.py)：`FlowEvent`，包含共享运行生命周期、LLM、工具、产物、人工确认及 SSE 控制事件；同时定义路由分组和动态事件命名函数。
- [im_backend/domain/event_names.py](im_backend/domain/event_names.py)：`IMEvent`，包含房间、会话、消息、收藏和文件事件。

常量都是普通 `str`。这次整理不改变线上事件名、负载、归档方式或 SSE 协议。IM 发布共享运行事件时引用 `FlowEvent`，不在 `IMEvent` 中重复定义；Agent Flow 不反向依赖 IM。

## 引用方式

Agent Flow 内部沿用本项目的 `domain` 导入路径：

```python
from domain.event_names import FlowEvent

await streams.publish(run_id, FlowEvent.AGENT_FINAL, {"final": text})
```

IM 业务代码直接引用两个模块：

```python
from agent_flow.domain.event_names import FlowEvent
from im_backend.domain.event_names import IMEvent

await room_events.publish(room_id, IMEvent.MESSAGE_CREATED, {"message": record})
await room_events.publish(room_id, FlowEvent.RUN_CREATED, {"run": run})
```

## 传输与存储

| 通道 | 用途 | 持久化 |
| --- | --- | --- |
| `run` | LLM、工具决策、最终输出、工具反馈等执行详情 | 持久事件通过 Redis 归档队列写入 `events`；`llm.delta` 只短期留在实时流 |
| `scope` | 会话或房间中的运行状态、消息、产物和审批通知 | 通过同一归档机制写入 `im_events` |
| 进程内 EventBus | 执行工具及获取人工审核结果 | 不直接归档；工具和产物由 `FrontendEventBridge` 镜像后进入上述通道 |
| SSE 控制帧 | 快照重建、快照结束和接收检查点 | 不进入事件历史或 DB |

持久事件先写 Redis，后台归档成功后 ACK；客户端 SSE 使用独立游标读取。名称集中不改变这条链路。

v2 运行/业务事件通常包含 `event_id`、`version`、`name`、`category`、`scope_id`、`run_id`、`conversation_id`、`message_id`、`execution_id`、`agent_id`、`payload` 和 `created_at`；没有关联对象时对应 ID 可为空。`scope` 事件还带 `room_id` 和 `trace`。`event_id` 是事件身份，SSE `id:` 是带代次的 Redis 读取游标，两者用途不同。

`BUSINESS_EVENTS` 决定 `EventStreamService.publish()` 直接路由到 `scope` 的运行状态事件。`TRACE_EVENT_PREFIXES` 将执行/回复生命周期标记为业务轨迹。`PROJECTED_EVENT_PREFIXES` 使产物及人工确认从 `run` 额外投影到 `scope`。这些集合统一维护在 Agent Flow 的事件定义模块中。

下面的负载列列出业务字段，不保证每条事件都有所有字段。业务轨迹在 `publish_scope()` 会裁剪正文，仅保留状态、关联 ID、步骤概况等；在 SSE `scope_delivery()` 中还会进一步返回摘要。最终回复正文应读取消息或 run 事件详情。

## 运行与编排事件（FlowEvent）

| 常量 | 事件名 | 触发时机及主要字段 |
| --- | --- | --- |
| `WORKFLOW_STARTED` | `workflow.started` | 编排或单聊执行开始；`run_id`、`mode`、`agent_id`、`message_id` 等。scope 轨迹 |
| `WORKFLOW_FINISHED` | `workflow.finished` | 运行完成并完成业务收尾；scope 轨迹，回复正文不放入轨迹摘要 |
| `WORKFLOW_FAILED` | `workflow.failed` | 运行异常或被取消；`error`，取消时额外带 `cancelled: true`。scope 轨迹 |
| `WORKFLOW_EVENT` | `workflow.event` | 编排 action 缺失 `event_dispatch` 时的兜底名；正常内置动作不会使用。按当前默认路由进入 run |
| `RUN_CREATED` | `run.created` | IM 群聊派发完成，消息已关联 run；`message_id`、`run`，其中 run 仅保留 ID 和状态。scope 轨迹 |
| `RUN_CANCELLED` | `run.cancelled` | 历史兼容名称，仍参与业务事件分类；当前 native 取消路径实际发布 `workflow.failed` 并设置 `cancelled: true` |
| `TASK_UPDATED` | `task.updated` | 运行任务状态更新；`run_id`、`status`。scope 轨迹 |
| `PLAN_GENERATED` | `plan.generated` | 编排器接受生成的计划；`plan` 在 scope 中裁剪为步骤概况 |
| `PLAN_REPLANNED` | `plan.replanned` | 编排器接受调整后的计划；`plan` 在 scope 中裁剪为步骤概况 |
| `WAVE_COMPLETED` | `wave.completed` | 编排器同步计划状态，循环开始、批次结束及阻塞收尾均可能触发；不能用它单独判断实际执行了一个批次 |
| `PLAN_WAVE_COMPLETED` | `plan.wave.completed` | 一个 ready-step 并发批次执行完；原始负载有 `planner_id`、`completed_step_ids`、`plan`，scope 保留步骤概况 |
| `PLAN_STEP_STARTED` | `plan.step.started` | 步骤开始；`step`、`plan`，应用层补充 `execution_id`、`agent_id`。scope 轨迹 |
| `PLAN_STEP_OBSERVED` | `plan.step.observed` | 步骤执行后观察结果、状态更新；`step`、`plan`，scope 只保留步骤概况 |
| `PLAN_STEP_FAILED` | `plan.step.failed` | 应用层发现失败步骤，单个步骤在一次编排中只报告一次；`step_id`、`agent_id`、`execution_id` 等 |

`plan.generated` 是计划已被编排器接纳的状态事件；下面的 `planner.plan.generated` 是模型返回计划时的详情事件。

## 模型与智能体输出（FlowEvent）

由 `StreamingObservableLLMClient` 发布到 run 通道；附带 `agent_id`、`agent_name`、`agent_type` 等关联信息。

| 常量 | 事件名 | 含义及主要 payload |
| --- | --- | --- |
| `LLM_STARTED` | `llm.started` | 模型请求开始；`call_role`、`model` |
| `LLM_DELTA` | `llm.delta` | 流式增量；`call_role`、`delta`、`sequence`。通过 `no_store_publish()` 发布，不归档 |
| `LLM_COMPLETED` | `llm.completed` | 模型完整响应；`call_role`、`content`、`token_chunks` |
| `AGENT_THINK` | `agent.think` | executor 的结构化 `think`，解析失败时使用原始文本；`think` |
| `AGENT_TOOL_REASONING` | `agent.tool.reasoning` | executor 对一次工具调用给出的理由；`tool_name`、`reasoning`、`arguments` |
| `AGENT_FINAL` | `agent.final` | executor 声明任务完成；`final`、`finish_reason` |
| `PLANNER_PLAN_GENERATED` | `planner.plan.generated` | planner 生成计划的模型结果；`planner_id`、`steps`、`raw` |
| `PLANNER_REPLAN_REASONING` | `planner.replan.reasoning` | planner 重规划决策；`planner_id`、`action`、`reason`、`steps`、`raw` |
| `PLANNER_FINAL` | `planner.final` | planner 最终总结；`planner_id`、`final` |
| `LLM_STREAMING` | `llm.streaming` | **仅前端展示事件**：`runtimeEvents.js` 合并 `llm.delta` 得到；后端不发布、不归档。列入目录用于说明协议边界 |
| `AGENT_FAILED` | `agent.failed` | **历史兼容事件**：当前 native 后端没有发布点；当前执行失败使用 `agent.execution.failed` 或 `workflow.failed` |

## 执行与回复生命周期（FlowEvent）

这些事件进入 scope。`agent.execution.*` 描述一次智能体调用，`agent.reply.*` 描述 IM 单聊的一轮回复。它们由共享运行时统一分类，所以名称定义在 Agent Flow。

| 常量 | 事件名 | 含义及主要字段 |
| --- | --- | --- |
| `AGENT_EXECUTION_STARTED` | `agent.execution.started` | 进入 `EventStreamService.execution()`；`agent_id`、`phase`、`step_id`，事件信封带独立 `execution_id` |
| `AGENT_EXECUTION_FINISHED` | `agent.execution.finished` | 调用正常结束；相同关联信息 |
| `AGENT_EXECUTION_FAILED` | `agent.execution.failed` | 调用抛异常，或 execute 阶段结束后 `is_finished` 明确为 false；异常时带 `error` |
| `AGENT_EXECUTION_CANCELLED` | `agent.execution.cancelled` | 调用因 `CancelledError` 退出 |
| `AGENT_REPLY_PENDING` | `agent.reply.pending` | IM 创建待执行回复；`message_id`、`agent_id` |
| `AGENT_REPLY_STARTED` | `agent.reply.started` | IM 回复任务开始；`message_id`、`agent_id`、`run_id` |
| `AGENT_REPLY_FINISHED` | `agent.reply.finished` | IM 回复消息已写入；`message_id`、`agent_id`、`run_id`。完整回复通过 `message.created` 提供 |

## 工具与人工审核（FlowEvent 和动态命名）

`ToolEventFactory` 使用 `tool_event_name(prefix, field, tool_name, suffix)` 生成内部事件。一般格式为 `infra.{field}.{tool_name}.{suffix}`；field 和 tool_name 中的 `_` 转为 `.`，缺失 field 使用 `unknown`，空 prefix 不产生开头的点。例如 `rag_search` 的调用事件可以是 `infra.search.rag.search.called`。

| 后缀 / 常量 | EventBus 动态事件 | 镜像到 run 的事件 | 含义 |
| --- | --- | --- | --- |
| `ToolEventSuffix.CALLED` / `TOOL_CALLED` | `{base}.called` | `tool.called` | 请求执行工具；原始参数作为 `arguments` |
| `ToolEventSuffix.SUCCEEDED` / `TOOL_SUCCEEDED` | `{base}.succeeded` | `tool.succeeded` | 工具成功；`respond`、`success` |
| `ToolEventSuffix.FAILED` / `TOOL_FAILED` | `{base}.failed` | `tool.failed` | 工具失败或被人工审核拒绝；`respond`、`success` |
| `ToolEventSuffix.RETRYING` / `TOOL_RETRYING` | `{base}.retrying` | `tool.retrying` | 工具重试事件，供工具显式调用；不表示所有工具都有自动重试 |

镜像事件还带 `tool_name`、`tool_field`、`event_name`（内部动态名称）、`frontend_event_name`（公开名称）、`agent_id`、`run_id`、`created_at`。后缀列表和镜像映射分别是 `TOOL_EVENT_SUFFIXES`、`TOOL_SUFFIX_TO_EVENT`；回调订阅使用 `tool_event_pattern()`，产物订阅使用 `ARTIFACT_EVENT_PATTERN`，不在调用方拼接事件模式。

| 常量 / 构造函数 | 事件名 | 含义及负载 |
| --- | --- | --- |
| `human_tool_event(tool_name)` | `human.{tool_name}` | 工具执行前进入人工审核处理器；使用原始工具名，保留 `_`；`tool_name`、`called_event_name`、`arguments`。进程内事件 |
| `HUMAN_BASH` | `human.bash` | 上述动态协议的内置 bash 审核处理器订阅名；安全命令也会经过此入口，但不一定弹出网页确认 |
| `HUMAN_BASH_CONFIRMED` | `human.bash.confirmed` | bash 审核结果；`approved`、`reason`。进程内返回事件 |
| `human_rejected_event(event_name)` | `{原事件名}.human_rejected` | 审核拒绝且无法反查工具描述时的兜底结果；`approved: false`、`reason`。一般拒绝路径使用工具的 `.failed` |
| `HUMAN_CONFIRMATION_REQUESTED` | `human.confirmation.requested` | 网页人工确认记录创建后发布；`confirmation_id`、`tool_name`、`called_event_name`、`arguments`、`status` 等 |
| `HUMAN_CONFIRMATION_RESOLVED` | `human.confirmation.resolved` | 确认记录首次被处理；包含 `approved`、`reason` 等确认结果 |

网页确认事件在 run 中保留详情，并投影到 scope 通知；投影时去掉 `arguments`。原生工具的人工审批流程继续使用这些事件。

## 产物事件（FlowEvent）

事件名称由 `ARTIFACT_EVENTS[artifact_type]` 统一映射。工具先发到 EventBus，桥接后进入 run 并投影到 scope；单聊在收尾时还会把产物收集进回复消息。

公共 payload 包括 `artifact_type`、`artifact`、`run_id`、`agent_id`、`event_name`、`frontend_event_name` 和 `created_at`。

| 常量 | 事件名 | artifact 内容 |
| --- | --- | --- |
| `ARTIFACTS_MESSAGE` | `artifacts.message` | 普通消息产物；`title`、`content`。构造器支持此类型，但当前工具声明给模型的枚举未包含 message |
| `ARTIFACTS_IMAGE` | `artifacts.image` | 图片；`title`、`url`、`alt` |
| `ARTIFACTS_DIFF` | `artifacts.diff` | 代码对比；`before`、`after`、`file_path`、`language` |
| `ARTIFACTS_DOCUMENT` | `artifacts.document` | 文档；`content`、`format`、`language`、`editable` |
| `ARTIFACTS_WEB` | `artifacts.web` | 网页预览；`url` 或 `html`、`preview_title` |
| `ARTIFACTS_DEPLOY` | `artifacts.deploy` | 部署结果；`deployment_id`、`url`、`port`、`status`、`kind`、`error` 等，由 deploy 工具发布 |

## IM 业务事件（IMEvent）

均由 IM 服务发布到 scope；通常为 `trace=false`，保留业务 payload。房间事件 scope 为 room ID，会话事件 scope 为 conversation ID；消息/收藏/文件事件使用其关联会话或房间。

| 常量 | 事件名 | 触发时机及 payload |
| --- | --- | --- |
| `ROOM_CREATED` | `room.created` | 房间创建；`room` |
| `ROOM_UPDATED` | `room.updated` | 房间标题、成员或配置更新；`room` |
| `CONVERSATION_CREATED` | `conversation.created` | 单聊/群聊会话创建，包括收藏派生会话；`conversation` |
| `CONVERSATION_UPDATED` | `conversation.updated` | 会话标题、置顶、归档等更新；`conversation` |
| `MESSAGE_CREATED` | `message.created` | 用户、Agent 或系统消息落库；`message`，供客户端实时合并消息 |
| `MESSAGE_REGENERATED` | `message.regenerated` | 重生成时旧回复清理完、用户消息重置后发布；`message_id`、`removed` |
| `MESSAGE_ACTION` | `message.action` | 记录回复、引用、复制、展开或应用 diff 等消息动作；`message_id`、`action` |
| `FAVORITE_CREATED` | `favorite.created` | 收藏创建；`favorite` |
| `FAVORITE_UPDATED` | `favorite.updated` | 收藏内容或启用状态更新；`favorite` |
| `FAVORITE_DELETED` | `favorite.deleted` | 收藏删除；`favorite_id` |
| `FILE_DELETED` | `file.deleted` | 文件实体删除完成后通知各关联 scope；`file_id` |

## SSE 控制事件（FlowEvent）

由 `RedisRuntime.stream()` 直接产生，只有 `name` 和 `payload`，不带普通事件的 `event_id`。

| 常量 | 事件名 | 用途 |
| --- | --- | --- |
| `STREAM_RESET` | `stream.reset` | 开始完整快照前清空旧状态；`payload.reason` 为 `initial` 或 `cursor_expired`，同时发送空 `id:` 清除浏览器游标 |
| `STREAM_READY` | `stream.ready` | 初始化完成，可切换到实时接收；有效游标续读也会收到。`payload.scope_id` 和 SSE `id:` 给出连接范围及检查点 |
| `STREAM_CHECKPOINT` | `stream.checkpoint` | 某条事件被过滤或去重时推进接收检查点；payload 为 `{}`，SSE `id:` 为新游标，不进入展示历史 |

心跳是 SSE 注释 `: heartbeat`，没有事件名，不应作为普通事件订阅或存储。

## 维护约定

1. 新事件先在所属模块增加常量，发布、订阅、名称比较和路由分类均引用常量。
2. 动态工具或人工审核事件调用统一构造函数；不要在业务代码中再拼字符串。
3. 同步更新本文档，说明发布方、通道、主要 payload 和是否归档。
4. 前端 JS 仍使用现有字符串协议。本次仅整理后端；新增需网页处理的事件还应更新 `IM_front/src/utils/runtimeEvents.js` 的订阅/展示配置。
5. 兼容性测试可保留明确的字符串断言，用于验证重构没有改变网络协议。`agent_flow/event_names_test.py` 检查后端生产代码不重新引入分散的事件名称或动态模板。
