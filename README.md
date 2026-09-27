# AgentHub

AgentHub 是一个以 IM 聊天为交互入口的多 Agent 协作平台。用户可以通过单聊、群聊、@ Agent、收藏上下文、消息回复/引用、运行轨迹和产物卡片，驱动平台原生 Agent 执行网页、文档、代码修改、部署等任务。

项目由三部分组成：

- `IM_front/`：Vue 3 + Vite 前端，负责聊天工作台、Agent/工具/技能管理、SSE 事件消费和 Artifact 渲染。
- `im_backend/`：FastAPI IM 产品后端，负责认证、会话、房间、消息、收藏、产物、部署和工具/技能入口。
- `agent_flow/`：Agent 核心运行系统，负责 Agent、Context、Tool、Run、PlanOrchestrator、长期记忆、事件总线和工具执行。

## 演示

[视频演示地址](https://my.feishu.cn/file/A9mCbC95BoCs5HxkDyTc9U4Hn6c)

## 快速启动

### 环境要求

- Python：依赖项 `requirements.txt`
- Node.js：`IM_front/package.json` 要求 `^20.19.0 || >=22.12.0`
- MongoDB：默认连接 `mongodb://localhost:27017/`，启动 IM 后端前需要运行

常用环境变量：

| 变量 | 说明 | 默认值 |
| ---- | ---- | ------ |
| `VITE_IM_API_BASE_URL` | 同源 API 地址；网页 SSE 不支持跨源地址 | 空（同源） |
| `IM_API_PROXY_TARGET` | Vite 开发/预览代理的后端地址 | `http://127.0.0.1:8010` |
| `IM_SSE_COOKIE_SECURE` | SSE Cookie 是否仅通过 HTTPS 发送 | `true`（本地 HTTP 显式设为 `false`） |
| `IM_MONGO_URL` | IM 后端 MongoDB 地址 | `mongodb://localhost:27017/` |
| `IM_MONGO_DB` | IM 后端数据库名 | `im_backend` |
| `IM_ARTIFACT_ROOT` | IM artifact 文件目录 | `im_backend/storage/artifacts` |
| `IM_AGENT_WORKDIR` | Agent 默认工作目录 | 仓库上级目录 |
| `AGENT_FLOW_ROOT` | im_backend 引用的 Agent Flow 根目录 | `agent_flow/` |
| `AGENT_FLOW_MONGO_URL` | Agent Flow API MongoDB 地址 | `mongodb://localhost:27017/` |
| `AGENT_FLOW_MONGO_DB` | Agent Flow API 数据库名 | `agent_flow` |
| `LLM_BASE_URL` | LLM 服务地址 | `https://api.deepseek.com` |
| `DEEPSEEK_API` / `GLM_API` / `MINIMAX_API` | LLM API Key | 无 |

`im_backend` 启动时会按顺序读取 `.env`、`im_backend/.env`、`agent_flow/.env`。

### 启动 IM 后端

从仓库根目录执行：

```bash
IM_SSE_COOKIE_SECURE=false python -m uvicorn im_backend.api.index:app --host 127.0.0.1 --port 8010
```

健康检查：

```bash
curl http://127.0.0.1:8010/health
```

### 启动前端

```bash
cd IM_front
npm install
npm run dev
```

默认访问 Vite 输出的本地地址，通常是：

```text
http://127.0.0.1:5173
```

网页使用同源 `/api`，Vite 默认代理到 `http://127.0.0.1:8010`。后端地址不同时启动前端：

```bash
IM_API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev
```

移除旧的跨源 `VITE_IM_API_BASE_URL` 配置。生产 HTTPS 反向代理示例见 [deploy/nginx.im.conf.example](deploy/nginx.im.conf.example)，后端设置 `IM_SSE_COOKIE_SECURE=true`。

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 项目目录

```text
.
├── IM_front/              # Vue 3 前端应用
├── im_backend/            # IM 产品后端
├── agent_flow/            # Agent 核心运行系统
├── mid/                   # 中间层/实验性模块
├── tests/                 # 技能演示笔记本；Python 测试位于各模块 tests/
├── README.md              # 当前项目说明
└── .gitignore
```

### `IM_front/`

```text
IM_front/
├── src/api/               # HTTP client 与 IM API 封装
├── src/router/            # Vue Router 与鉴权跳转
├── src/stores/            # Pinia store，消息、房间、SSE、产物状态
├── src/views/             # ChatView、工具/技能/认证等页面
├── src/components/        # ArtifactCard 等通用组件
├── src/utils/             # runtime events 聚合、压缩、去重
├── package.json           # npm 脚本与依赖
└── vite.config.js         # Vite 配置
```

### `im_backend/`

```text
im_backend/
├── api/                   # FastAPI app、auth router、/api/im 路由
├── application/           # 应用服务：消息、房间、run、artifact、tool、skill
├── domain/                # IM 领域模型：conversation、message、room、agent
├── infra/                 # 存储、个人记忆配置与 Agent Flow bridge
├── storage/               # 本地 artifact 存储
└── tests/                 # IM 后端测试
```

### `agent_flow/`

```text
agent_flow/
├── api/                   # Agent Flow 原生 FastAPI 接口
├── application/           # Run、Agent、Context、Tool、Event 应用服务
├── domain/                # Agent、Tool、Event、Context、Memory 领域模型
├── infra/                 # EventBus、LLM、工具实现、部署、MongoDB
├── skills/                # Agent 技能文件
├── tests/                 # Agent Flow 模块测试
├── temp/                  # 部署、MCP 等运行时临时目录
└── README.md              # Agent Flow 子系统说明
```

## 技术架构

AgentHub 的整体形态是“IM 产品层 + Agent 运行核心”的组合。

```text
IM_front
  └─ HTTP / SSE
im_backend
  ├─ API Routes
  ├─ Application Services
  ├─ Domain Models
  ├─ Infra: storage / agent_flow_bridge
  └─ Bridge
agent_flow
  ├─ Application Services
  ├─ Domain: Agent / Tool / Context / Event / Memory
  └─ Infra: EventBus / LLM / Tool Handlers / Deploy / DB
```

### 分层思想

`im_backend` 和 `agent_flow` 都采用接近 DDD 的分层方式，但没有引入复杂的聚合根建模：

- `api/`：HTTP/SSE 适配层，只处理请求、响应、鉴权和路由挂载。
- `application/`：应用用例层，编排消息发送、群聊 dispatch、run 创建、artifact 转换等流程。
- `domain/`：领域模型层，定义 Agent、消息、房间、事件、工具、上下文、记忆等核心对象。
- `infra/`：基础设施层，负责 MongoDB 与文件存储适配器、LLM 客户端、事件总线、工具实现和部署。

在 `agent_flow` 内，依赖沿 `application → infra → domain` 指向更底层；`application` 也可以直接使用 `domain`。`domain` 不依赖其他两层，`infra` 不导入 `application`。`api/` 是三层之外的 HTTP 入口。长期记忆的 [应用服务](agent_flow/application/services/long_memory.py) 同时提供 `build_long_memory()`，连接 MongoDB 与文件系统适配器；[记忆存储](agent_flow/infra/memory/)只实现存取能力。

IM 的个人检索设置与管理查询属于 `im_backend`。IM 桥接把设置读取函数注入 Agent 运行时，`agent_flow` 的长期记忆用例只接收运行时选项，不依赖 IM 配置模块。新增 Python 测试放在各模块的 `tests/` 目录。

### EDA 事件驱动底座

`agent_flow` 的工具调用和运行状态基于事件驱动：

1. Agent 通过 ReACT 决策生成 tool calls。
2. `ToolEventFactory` 根据工具注册表生成 `infra.{field}.{tool}.{called|succeeded|failed|retrying}` 事件。
3. `EventBus` 异步发布事件。
4. `On_bind` 将事件绑定到具体工具实现。
5. 工具成功或失败后发布回调事件。
6. Agent 收到工具结果，写入 state / memory，继续下一轮推理。

运行事件、工具事件、人工确认事件和产物事件会进入后端事件流，并通过 SSE 推送给前端。

### 多 Agent 群聊编排

群聊任务由 `im_backend` 接收用户消息和 @ mentions，再通过 bridge 创建 Agent Flow run：

- 所有 Agent 都由 Agent Flow 原生运行时执行。
- `PlanOrchestrator` 负责 planner 计划拆解和 executor 调度。
- 计划以 DAG 形式执行，入度为 0 的 ready steps 可并发运行。
- 同一 executor 通过 lock 串行保护，减少状态污染。

### 前端运行时展示

前端以 `ChatView` 为主要工作台：

- `src/api/im.js` 封装 `/api/im` 接口。
- `src/stores/im.js` 管理会话、房间、消息、SSE、artifact 和运行事件。
- `src/utils/runtimeEvents.js` 负责流式事件压缩、trace 聚合、artifact 去重。
- `ArtifactCard.vue` 渲染 message、image、diff、document、web、deploy 等产物，并支持保存、回退、下载、部署停止/重启等操作。

## 主要接口

IM 后端入口：

- `GET /health`
- `/auth/*`：注册、登录、当前用户、退出
- `/api/im/agents`：Agent 列表、创建、删除、Builder
- `/api/im/conversations`：单聊会话、消息、回复、取消、重新生成、事件流
- `/api/im/rooms`：群聊房间、消息、dispatch、tasks、events、cancel
- `/api/im/favorites`：收藏上下文
- `/api/im/artifacts`：上传、下载、打包、diff apply、文档保存、版本历史
- `/api/im/deployments`：部署停止、重启、下载
- `/api/im/tools`：工具目录和配置
- `/api/im/skills`：技能文件 CRUD
- `/api/im/runs`：运行事件、确认请求与处理
- `/api/im/memory`：记忆查询、个人检索配置与召回测试

Agent Flow 独立 API 入口：

- `/api/tools`
- `/api/contexts`
- `/api/agents`
- `/api/runs`
- `/api/conversations`

## 测试与构建

前端构建：

```bash
cd IM_front
npm run build
```

LLM 相关测试应使用 mock 或测试替身，避免在单元测试中依赖真实 API key 和网络。

分层与长期记忆主干测试：

```bash
/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python -m pytest agent_flow/tests/test_layer_dependencies.py agent_flow/tests/test_long_memory.py im_backend/tests/test_memory_management.py -q
```

## 安全与运行注意事项

- 高风险工具调用通过运行时人工确认机制审批。
- 工具上传和动态工具执行需要在生产环境增加源码审查、签名校验或沙箱隔离。
- 文件、diff、deploy artifact 需要限制路径、大小和下载行为。
- IM 后端依赖 MongoDB；单元测试通过显式注入内存替身隔离数据库。
- SSE 高频事件已做前端合批和历史事件截断，长 run 场景仍建议增加分页、TTL 和容量限制。


<!-- @agent\_flow/domain/memory/  在这个文件夹里增加长期记忆模块，作为该文件夹里的一个单独的文件夹，这个长期记忆主要是与文件系统交互，在@agent\_flow/文件夹下创建store文件夹用于存储长期记忆文件。长期记忆分为3层架构L1,L2,L3。其中L3为底层原始数据，以md形式存内容;L2为存储在mongodb数据库里的集合结构，结构包含块ID，文件来源ID，文件路径，开始行数，结束行数，总token数，块内容等元属性， -->

<!-- [memory](/Users/zxcvbzzy1/Desktop/项目/AgentHub/agent_flow/domain/memory/)  在这个文件夹里增加长期记忆模块，作为该文件夹里的一个单独的文件夹，这个长期记忆主要是与文件系统交互，在 @agent_flow/ 文件夹下创建store文件夹用于存储长期记忆原始文件（按用户-房间-会话级别）。长期记忆分为3层架构L1,L2,L3。其中L3为底层原始数据，以md形式存内容;L2为存储在mongodb数据库里的集合结构，结构包含块ID，文件来源ID，文件路径，开始行数，结束行数，总token数，块内容，使用次数，标签等元属性，L1则为注入进智能体上下文的格式，类似 [providers.py](/Users/zxcvbzzy1/Desktop/项目/AgentHub/agent_flow/domain/context/providers.py) ,其中L2的记忆json结构设计，要支持更新，删除，过期，聚合等操作。长期记忆的来源为每次run的结果，用户问题与回答，以及run轨迹关联的think内容。如果有更好的设计向我确认，如果有需要清楚的设计边界像我确认，目前写业务主干代码，不用考虑极端测试场景。 -->
