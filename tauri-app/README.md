# AgentHub 桌面端（Tauri 2 + Vue 3）

基于 `IM_front` 复制独立演进的 Mac 桌面端，在 Web 功能（聊天 / 技能库 / 工具 / 登录）之上增加了三块桌面专属能力：

| 能力 | 说明 |
| --- | --- |
| 进程管理 | 顶栏「进程」页：托管 MongoDB 与 im_backend 的启动/停止/重启、实时日志、健康检查（含 mongo=memory 内存降级红色告警）、一键按序启动（mongod 端口就绪后再拉后端） |
| 系统通知 | 窗口未聚焦时，agent 回复 / 任务失败 / 等待人工确认会发 macOS 系统通知 |
| 本地文件 | 产物下载走系统保存对话框直接落盘 + 「在 Finder 中显示」；聊天输入框回形针按钮或直接拖文件进窗口，自动上传并以链接附进消息 |

## 运行（开发模式）

前置：本机已有 Node 20+、Rust 工具链（rustup）、MY_env conda 环境与 MongoDB 二进制（路径都可在 App 的「进程 → 设置」里改）。

```bash
cd tauri-app
npm install
npm run tauri dev
```

后端可以由 App 托管启动（进程页「一键启动全部」，或在设置里勾选「App 启动时自动拉起」），也可以继续用你自己终端里启动的实例——App 会把它们识别为「外部运行中」，只展示状态、不接管生命周期。

## 打包

```bash
npm run tauri build
```

注意：当前定位是「本机开发环境的桌面壳」，**不内嵌** Python/Mongo，打包产物仍依赖本机的 conda 环境与 mongod 路径。

## 设计边界（已确认）

- 前端源码从 `IM_front` 复制后独立演进（`src/desktop/` 为桌面专属层，其余结构与 Web 端一致）。
- 进程托管范围 = `mongod` + `im_backend`；由 App spawn 的子进程才允许 stop/restart，退出时是否随手关停可配置（默认开，外部实例不受影响）。
- 本地文件能力覆盖：产物保存、本地文件发送到对话、Finder 显示/打开；**不包含**「把本地目录授权为 agent 工作区」。
- 路由用 hash 模式（`tauri://` 协议下无服务端兜底路由）。

## 关键文件

- `src/desktop/` — 桌面能力层：`processes.js`（进程命令封装）、`notify.js`（通知）、`files.js` / `download.js`（本地文件）、`bootstrap.js`（启动初始化）
- `src/views/ProcessesView.vue` — 进程管理页
- `src-tauri/src/process_manager.rs` — Rust 侧进程托管（spawn / 日志环形缓冲 / 端口探测 / 退出清理）
- `src-tauri/capabilities/default.json` — fs / dialog / notification / opener 权限
