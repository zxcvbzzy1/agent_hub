# AgentHub 人机协同研发流程总结

## 一、AI_collaboration 目录介绍

`AI_collaboration/` 用来沉淀 AgentHub 项目中的人机协同研发资料，包括原始协作记录、产品/技术文档图源，以及指导 AI 智能体工作的技能手册。

### 1. 顶层目录

```text
AI_collaboration/
├── README.md
├── raw/
├── product/
│   ├── PRD/
│   └── TDD/
└── skills/
```

| 目录 / 文件 | 放置内容 | 用途 |
| ----------- | -------- | ---- |
| `README.md` | 人机协同研发流程总结 | 说明协作模式、角色分工、流程和经验沉淀 |
| `raw/` | 原始协作记录 | 保存未经整理的一手材料，如对话历史、开发记录、会议/复盘笔记 |
| `product/` | 产品与技术设计产物 | 保存 PRD、TDD 相关图源和结构化设计材料 |
| `product/PRD/` | 产品需求文档相关图源 | 保存功能架构图、业务流程图、泳道图、状态流转图、异常处理流程图等 PRD 配套资产 |
| `product/TDD/` | 技术设计文档相关图源 | 保存系统架构图、数据关系图、模块依赖图、核心流程图、事件流转图、部署架构图、ER 图等 TDD 配套资产 |
| `skills/` | AI 智能体技能手册 | 保存面向智能体的工作规范、文档编写规范、画图规范、部署规范和文件编辑规范 |

### 2. `raw/` 原始材料

| 文件 | 内容 |
| ---- | ---- |
| `raw/claude_code_history.jsonl` | Claude Code / coding agent 协作过程中的原始历史记录 |
| `raw/record.md` | 人机协作过程中的文字记录、阶段性总结或补充说明 |

### 3. `product/PRD/` 产品图源

`product/PRD/` 存放智能体调用excalidraw mcp产生的 Excalidraw 图源，主要服务于 PRD 文档编写和产品评审。

典型内容包括：

- `AgentHub功能架构图.excalidraw`、`04-AgentHub-功能架构图.excalidraw`：AgentHub 产品功能架构图。
- `07-01-对话列表-业务流程泳道图.excalidraw`：对话列表业务流程。
- `07-02-单聊模式-业务流程泳道图.excalidraw`：单聊模式业务流程。
- `07-03-群聊模式-业务流程泳道图.excalidraw`：群聊模式业务流程。
- `07-04-消息与上下文-业务流程泳道图.excalidraw`：消息、引用、收藏上下文相关流程。
- `07-05-Orchestrator-业务流程泳道图.excalidraw`：Orchestrator 编排流程。
- `07-06-多Agent接入-业务流程泳道图.excalidraw`：多 Agent / 外部 Agent 接入流程。
- `07-07-产物预览编辑-业务流程泳道图.excalidraw`：Artifact 预览、编辑、保存、回退流程。
- `07-08-部署发布-业务流程泳道图.excalidraw`：部署发布流程。
- `07-单聊业务流程.excalidraw`、`07-群聊编排流程.excalidraw`、`07-运行状态流转.excalidraw`、`07-异常处理流程.excalidraw`：核心功能流程补充图。

### 4. `product/TDD/` 技术图源

`product/TDD/` 存放智能体调用excalidraw mcp产生的 Excalidraw 图源，主要服务于 TDD 文档编写、架构评审和技术交接。

典型内容包括：

- `02-系统架构图.excalidraw`、`02_架构图.excalidraw`：系统总体架构。
- `03-数据关系图.excalidraw`、`ER1.excalidraw`、`ER2.excalidraw`：数据关系和 ER 图。
- `04-模块依赖图.excalidraw`、`模块依赖图.excalidraw`：模块依赖关系。
- `05-核心业务流程图.excalidraw`：核心业务调用链和流程。
- `07-事件流转图.excalidraw`：EDA 事件、SSE、运行事件流转。
- `09-部署架构图.excalidraw`：前端、后端、Agent Flow、存储和外部服务的部署关系。

### 5. `skills/` 智能体技能说明

`skills/` 中的 Markdown 文件是给 AI 智能体使用的操作规范。它们不是业务文档，而是“如何工作”的手册。

| Skill 文件 | 作用 |
| ---------- | ---- |
| `PRD_skill.md` | PRD 文档专家手册。规定 PRD 的标准目录、章节写法、分段输出、进度追踪、需求澄清、验收标准和 Excalidraw 图表要求。用于指导智能体把原始需求整理成可开发、可测试的产品需求文档。 |
| `TDD_skill.md` | TDD 技术文档专家手册。规定 TDD 必须以源码为准，说明源码取证顺序、AgentHub 三系统边界、类 DDD 分层、EDA 事件机制、标准章节、测试/性能/风险设计和图表要求。用于指导智能体把 PRD 和源码整理成技术设计文档。 |
| `excalidraw.md` | Excalidraw 画图技能。规定架构图、流程图、泳道图、ER 图等必须使用 Excalidraw MCP 生成，不能用 ASCII 图；同时约束字体、文本元素、容器绑定和图形表达方式。 |
| `safe_file_editing.md` | 安全文件读写与编辑规范。要求智能体优先使用专用文件编辑/补丁工具，避免用 bash heredoc 塞大段文本，减少误写、覆盖和解析失败。 |
| `bash_command_discipline.md` | Bash 命令拆分纪律。要求启动服务、等待就绪、测试验证分步执行，不把长驻服务、sleep、curl、pytest 等串成一条难定位的长命令。 |
| `backend_service_deploy.md` | 后端服务部署技能。规定如何用常驻命令部署 FastAPI、Flask、Node 等服务，要求使用 `$PORT` 占位、监听 `127.0.0.1`，并生成可预览、可重启的部署产物。 |
| `static_web_deploy.md` | 静态网页部署技能。规定如何把静态站点真实部署为可预览的 deploy 产物，要求确认 `index.html`、资源路径自洽，并通过部署卡片支持关闭和重启。 |

---

# 二、角色分工

## 1. 人类角色

项目负责人承担：

### 产品经理

负责：

* 提出需求
* 明确目标
* 确认边界
* 验收功能

例如：

* Agent 群聊设计
* Skill 系统设计
* Artifact 设计
* Diff 编辑能力

---

### 架构师

负责：

* 技术路线决策
* 模块边界划分
* 技术方案选择

例如：

* Skill 采用记忆召回还是固定 Prompt
* Context 隔离方案
* Tool 系统设计
* EventBus 架构

---

### QA 测试

负责：

* 功能验证
* Bug 发现
* 性能测试
* 用户体验验证

例如：

* 上下文泄漏
* Agent 状态残留
* Deploy Artifact 异常
* SSE 卡顿问题

---

# 三、AI 团队角色

## 1. Plan Agent

负责：

* 理解需求
* 拆解任务
* 制定执行计划

输出：

* 任务列表
* 实施方案
* Agent 分工

---

## 2. Orchestrator

负责：

* 调度执行者
* 管理执行状态
* 汇总执行结果

职责类似：

* 技术负责人
* 项目经理

---

## 3. Executor Agent

负责：

* 实际编码
* Bug 修复
* 功能开发

可分为：

### Frontend Agent

负责：

* Vue
* UI
* 页面交互

---

### Backend Agent

负责：

* FastAPI
* MongoDB
* SSE

---

### Code Agent

负责：

* Claude Code
* Codex

完成复杂开发任务。

---

## 4. Review Agent

负责：

* 审查结果
* 检查遗漏
* 收敛方案

通常由能力更强模型承担。

---

# 四、协作流程

## 阶段一：需求提出

项目负责人提出：

* 新功能
* Bug
* 优化建议

例如：

```text
增加 Skill 系统
增加 Diff 编辑器
增加 Deploy Artifact
```

---

## 阶段二：方案讨论

AI 分析需求。

输出：

### 问题分析

例如：

```text
为什么会发生上下文泄漏
```

---

### 多种方案

例如：

```text
方案1
方案2
方案3
```

---

### 风险评估

例如：

```text
实现成本
兼容性
维护成本
```

---

## 阶段三：人工决策

项目负责人：

```text
选择方案
调整边界
补充约束
```

例如：

```text
选择方案1
采用按 Run 隔离
```

---

## 阶段四：并行开发

多个 Agent 并行执行。

示意：

Plan Agent
↓
Orchestrator
↓
├─ Frontend
├─ Backend
├─ Tool
├─ Skill
└─ Deploy

各 Agent 独立开发。

---

## 阶段五：结果收敛

由高级模型负责：

### Review

检查：

* 功能遗漏
* 代码一致性
* 接口兼容性

---

### Merge

统一输出最终方案。

---

## 阶段六：人工验收

项目负责人测试：

### 功能

是否符合需求。

### 性能

是否存在卡顿。

### 体验

是否符合预期。

---

## 阶段七：问题反馈

发现问题后：

```text
workflow 目前有几个问题...
```

进入下一轮开发。

---

# 五、研发循环

整个项目采用持续迭代模式。

流程如下：

需求提出
↓
方案讨论
↓
人工决策
↓
并行开发
↓
收敛评审
↓
人工验收
↓
Bug反馈
↓
下一轮迭代

形成闭环。

---

# 六、核心设计原则

## 原则一：先设计，后编码

避免：

```text
一句需求直接写代码
```

采用：

```text
需求
↓
PRD
↓
技术方案
↓
任务拆解
↓
开发
```

---

## 原则二：复杂任务拆分

不追求单 Agent 完成全部工作。

采用：

```text
规划
↓
执行
↓
审查
```

模式。

---

## 原则三：所有状态可追踪

包括：

* Event
* Run
* Tool Call
* Artifact

全部可回溯。

---

## 原则四：上下文隔离

保证：

```text
不同 Run
不同会话
不同 Agent
```

状态独立。

避免信息污染。

---

## 原则五：人始终拥有最终决策权

AI：

* 提供建议
* 提供实现

人：

* 决定方向
* 决定边界
* 决定是否接受

---

# 七、项目演进路径

项目经历了以下阶段：

## 第一阶段

Agent 聊天系统

---

## 第二阶段

Agent 群聊与编排

---

## 第三阶段

Artifact 系统

支持：

* 文档
* Diff
* 图片
* 网页
* Deploy

---

## 第四阶段

Skill 系统

支持：

* Skill Registry
* Skill Retriever
* Memory Integration

---

## 第五阶段

协同文件编辑

支持：

* Diff
* 版本历史
* 一键应用

---

## 第六阶段

Agent 自举能力

支持：

* 创建 Agent
* 创建 Skill
* 编写 PRD
* 自动开发

形成 Agent 开发 Agent 的能力。

---

# 八、总结

AgentHub 的研发过程，本质上是一种新型的软件开发模式：

人类负责：

* 产品
* 架构
* 决策
* 验收

AI 负责：

* 分析
* 设计
* 编码
* 修复

双方形成持续协作闭环。

最终目标不是“让 AI 替代开发者”，而是构建一个能够持续自我扩展、自我演进的人机协同研发系统。
