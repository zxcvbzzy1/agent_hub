export function executionHealthLabel(health) {
  if (health?.status === 'suspected') return `执行连接异常，正在确认（${health.failed_probes || 0}/5）`
  if (health?.status === 'unavailable') return '运行状态暂不可确认，等待连接恢复'
  if (health?.status === 'lost') return '执行进程连续五次无响应，正在停止'
  return ''
}
