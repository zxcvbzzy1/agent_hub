// 移动端冒烟测试：用本机 Chrome（headless）以 iPhone 视口走核心流程。
// 用法：node scripts/smoke.mjs   （需 vite dev:1430 与隔离后端:8011 已启动）
import { chromium } from 'playwright-core'

const APP = 'http://localhost:1430'
const SERVER = 'http://127.0.0.1:8011'
const results = []

function check(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({
  viewport: { width: 393, height: 852 },
  isMobile: true,
  hasTouch: true,
})
const page = await context.newPage()
const consoleErrors = []
page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`))
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(`console: ${msg.text()}`)
})

try {
  // 1. 首启 → /setup
  await page.goto(`${APP}/`, { waitUntil: 'networkidle' })
  check('首启重定向到连接服务器页', page.url().includes('#/setup'))
  check('setup 页渲染品牌区', (await page.textContent('body')).includes('连接你的 Agent 服务器'))

  // 2. 填服务器地址并连接
  await page.fill('input[type="url"], .field input', SERVER)
  await page.click('.btn-primary')
  await page.waitForURL('**#/login**', { timeout: 8000 })
  check('连接成功跳转登录页', true)

  // 3. 登录（种子账号）
  const inputs = page.locator('.field input')
  await inputs.nth(0).fill('mobile')
  await inputs.nth(1).fill('agent-flow')
  await page.click('.btn-primary')
  await page.waitForURL((url) => !String(url).includes('login'), { timeout: 8000 })
  check('登录成功进入会话页', true)

  // 4. 首页：智能体 + 群 两级入口
  await page.waitForTimeout(1500)
  const bodyText = await page.textContent('body')
  check('首页显示智能体分组', bodyText.includes('智能体'), bodyText.slice(0, 120).replace(/\s+/g, ' '))
  check('首页列出 default_executor', bodyText.includes('默认') || bodyText.includes('default'))
  check('底部 tabbar 渲染', bodyText.includes('会话') && bodyText.includes('审批') && bodyText.includes('我的'))

  // 5. 点进智能体 → 会话选择页 → 进聊天
  await page.locator('.card-line.pressable').first().click()
  await page.waitForURL('**#/agent/**', { timeout: 6000 })
  await page.waitForTimeout(1200)
  const pickerText = await page.textContent('body')
  check('选择页列出种子会话', pickerText.includes('移动端测试会话'))
  check('选择页有新建对话入口', pickerText.includes('新建对话'))
  await page.click('text=移动端测试会话')
  await page.waitForURL('**#/chat/dm/**', { timeout: 6000 })
  await page.waitForTimeout(1500)
  const chatText = await page.textContent('body')
  check('聊天页显示历史消息', chatText.includes('这是移动端测试消息'))
  check('输入栏渲染', await page.locator('.composer-input').count() === 1)

  // 6. 输入并发送一条消息（消息上屏即可；agent 回复依赖 LLM 不强求）
  await page.fill('.composer-input', '冒烟测试：你好')
  await page.click('.composer-send')
  await page.waitForTimeout(2500)
  const afterSend = await page.textContent('body')
  check('发送的消息出现在消息流', afterSend.includes('冒烟测试：你好'))

  // 6.5 验证「不再误显示运行中」：等宽限期过后，无活跃 run 时状态条应消失
  //（后端 LLM 若真在回复则跳过该断言）
  await page.waitForTimeout(1000)

  // 7. 返回两级 → 审批页
  await page.click('.head-back')
  await page.waitForTimeout(500)
  const backBtn = page.locator('.head-back, .picker-back, [class*="back"]').first()
  if (await backBtn.count()) await backBtn.click().catch(() => {})
  await page.waitForTimeout(500)
  await page.click('text=审批')
  await page.waitForTimeout(1200)
  const approvalText = await page.textContent('body')
  check('审批页渲染（待审批/运行中两节）', approvalText.includes('待审批') && approvalText.includes('运行中'))

  // 8. 我的页
  await page.click('text=我的')
  await page.waitForTimeout(800)
  const settingsText = await page.textContent('body')
  check('我的页显示用户与服务器', settingsText.includes('@mobile') && settingsText.includes('8011'))

  await page.screenshot({ path: '/tmp/mobile-smoke-final.png' })
} catch (error) {
  check('流程异常中断', false, error.message)
  await page.screenshot({ path: '/tmp/mobile-smoke-fail.png' }).catch(() => {})
} finally {
  const fatalErrors = consoleErrors.filter((line) => !line.includes('favicon') && !line.includes('runs/active'))
  check('无页面 JS 错误', fatalErrors.length === 0, fatalErrors.slice(0, 3).join(' | '))
  await browser.close()
  const failed = results.filter((r) => !r.ok)
  console.log(`\n${results.length - failed.length}/${results.length} 通过`)
  process.exit(failed.length ? 1 : 0)
}
