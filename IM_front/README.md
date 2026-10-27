# vue-project

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Recommended Browser Setup

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### 局域网访问

在提供前端服务的机器上运行：

```sh
npm run dev -- --host 0.0.0.0
```

其他机器打开 `http://<服务机器的局域网 IP>:5173`（以启动日志的实际端口为准）。预览构建时使用 `npm run preview -- --host 0.0.0.0`。

保持 `VITE_IM_API_BASE_URL` 为空，让浏览器通过同源 `/api` 访问后端；Vite 会代理到服务机器上的 `http://127.0.0.1:8010`。后端地址不同时，通过 `IM_API_PROXY_TARGET` 配置代理目标，避免浏览器请求访问者自己机器上的 `localhost`。

HTTP 环境启动后端时设置 `IM_SSE_COOKIE_SECURE=false`，让事件流认证 Cookie 能正常工作，启动命令见仓库根目录 README；HTTPS 部署保持默认值 `true`。

局域网 HTTP 页面通常不是安全上下文，`crypto.randomUUID()` 可能不可用。前端通过 `src/utils/uuid.js` 统一生成 ID，原生方法不可用时使用 `crypto.getRandomValues()` 生成 UUID v4，无需修改浏览器安全设置。

### Compile and Minify for Production

```sh
npm run build
```
