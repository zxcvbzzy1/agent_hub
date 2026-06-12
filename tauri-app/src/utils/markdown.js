// 统一的 Markdown 渲染入口：markdown-it 解析 + highlight.js 代码高亮 + DOMPurify 兜底防 XSS。
// 全站消息/卡片共用同一条渲染管线，安全审查只需看这一处。
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import 'highlight.js/styles/github.css'
import '@/assets/markdown.css'

const md = new MarkdownIt({
  // 不信任 markdown 源里的原始 HTML（即便如此仍会经 DOMPurify 兜底）
  html: false,
  linkify: true,
  breaks: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {
        // 高亮失败时退回默认转义
      }
    }
    try {
      return `<pre class="hljs"><code>${hljs.highlightAuto(code).value}</code></pre>`
    } catch {
      return ''
    }
  },
})

// 外链统一新开 + noopener
const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

const PURIFY_OPTS = {
  USE_PROFILES: { html: true },
  ADD_ATTR: ['target', 'rel', 'class'],
}

export function renderMarkdown(text) {
  if (text == null || text === '') return ''
  try {
    // trim：markdown-it 块级输出结尾带 '\n'，在 white-space: pre-wrap 容器下会渲染成空行
    return DOMPurify.sanitize(md.render(String(text)).trim(), PURIFY_OPTS)
  } catch {
    return ''
  }
}

// 行内 markdown（无块级包裹，用于短文本），同样经过净化。
export function renderMarkdownInline(text) {
  if (text == null || text === '') return ''
  try {
    return DOMPurify.sanitize(md.renderInline(String(text)), PURIFY_OPTS)
  } catch {
    return ''
  }
}

// 判断一个 document 产物是否应按 markdown 渲染：依据 format / mime_type / 文件后缀，
// 「明显不是 markdown 的其它格式」（py/js/json 等）保持原样的纯文本/代码预览。
export function looksLikeMarkdownDoc(artifact = {}) {
  const fmt = String(artifact.format || '').toLowerCase()
  const mime = String(artifact.mime_type || '').toLowerCase()
  const fp = String(artifact.file_path || artifact?.metadata?.file_path || '').toLowerCase()
  return (
    fmt === 'md' ||
    fmt === 'markdown' ||
    mime.includes('markdown') ||
    fp.endsWith('.md') ||
    fp.endsWith('.markdown')
  )
}
