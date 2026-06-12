// 桌面端能力入口：所有 Tauri 专属调用都经过这里，保持「在普通浏览器里打开也不报错」。
// （npm run dev 直接在浏览器调试时 isTauri 为 false，桌面按钮自动隐藏/降级。）
export const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
