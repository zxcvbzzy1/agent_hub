# AgentHub Mobile（Tauri 2 + Vue 3）

面向手机的精简客户端：**只有聊天**——会话列表、消息流、产物预览、危险命令审批、运行中断。技能库/工具/收藏/文件编辑等重操作留在桌面端与 Web 端。

## 页面结构（小屏拆分）

| 页面 | 说明 |
| --- | --- |
| 连接服务器 | 首次启动填 Mac 的局域网地址（如 `http://192.168.x.x:8010`），测试 `/health` 通过后进入登录；地址存 localStorage，设置页可改 |
| 登录/注册 | 同一后端账号体系 |
| 会话 tab | 单聊 + 群聊合并收件箱：未读徽标、最近活跃排序、运行中绿点、搜索 |
| 聊天页（全屏推入） | 气泡消息流 + markdown 渲染；产物收成 chip 点开全屏预览；运行中显示 typing 指示与状态条（可中断、可看运行过程时间线 sheet）；危险命令审批卡片浮在输入框上方；群聊支持 @ 提及 |
| 审批 tab | 全局聚合：待审批（允许/拒绝）+ 运行中的任务（可中断），tab 徽标实时计数 |
| 我的 tab | 用户信息、服务器地址、退出登录 |

## 运行

```bash
cd iphone
npm install
npm run dev        # 浏览器手机视口调试（vite, 端口 1430）
npm run tauri dev  # 桌面窗口（iPhone 尺寸 393×852）
```

手机真机调试（浏览器即可）：`npm run dev -- --host`，手机访问 `http://<Mac局域网IP>:1430`，服务器地址填 `http://<Mac局域网IP>:8010`。

> iOS 原生工程（`tauri ios init` + Xcode 签名）按约定留到后续阶段。

## 设计边界（已确认）

- 交互范围：看对话、发消息、产物预览、审批、中断运行；**不做**创建/删除 agent、建群、上传文件、收藏等重操作。
- UI 纯手写（无组件库），设计 tokens 在 `src/assets/theme.css`；iOS 质感：毛玻璃吸顶/底栏、大圆角卡片、indigo→blue 渐变主色、安全区适配。
- 后端地址运行时可配（localStorage `agent-im-server`），axios 拦截器动态注入 baseURL。
- 依赖后端分支 `mac_platform_support` 的 `GET /api/im/runs/active` 与 `POST /api/im/runs/{id}/cancel`。

## 关键文件

- `src/stores/chat.js` — 核心 store：SSE 流（高频增量 80ms 合批）、消息窗口懒加载、发送/中断、审批聚合、未读
- `src/views/ChatView.vue` — 聊天页（气泡/产物 chip/审批卡/时间线 sheet/@ 提及）
- `src/components/ArtifactPreview.vue` — 全屏产物预览（document/image/diff/web/video）
- `src/views/ApprovalsView.vue` — 审批中心 + 运行中任务
- `src/api/http.js` — 动态 baseURL + silentHttp（轮询不弹错）
