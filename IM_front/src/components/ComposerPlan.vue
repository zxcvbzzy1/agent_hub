<script setup>
import { computed, ref, useId, watch } from 'vue'
import {
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  LoadingOutlined, MinusCircleOutlined, RightOutlined,
} from '@ant-design/icons-vue'

const props = defineProps({ plan: Object, targetKey: String })
defineEmits(['retry'])
const open = ref(false)
const listId = useId()
watch(() => [props.targetKey, props.plan?.runId], () => { open.value = false })
const statuses = {
  pending: ['待执行', ClockCircleOutlined], in_progress: ['执行中', LoadingOutlined],
  done: ['已完成', CheckCircleOutlined], failed: ['失败', CloseCircleOutlined],
  skipped: ['已跳过', MinusCircleOutlined], cancelled: ['已取消', MinusCircleOutlined],
}
const rows = computed(() => (props.plan?.steps || []).map(step => {
  const interrupted = props.plan.terminal && step.status === 'in_progress'
  const [label, icon] = interrupted ? ['已中断', MinusCircleOutlined]
    : props.plan.terminal && step.status === 'pending' ? ['未执行', ClockCircleOutlined]
      : (statuses[step.status] || ['状态未知', ClockCircleOutlined])
  return { ...step, label, icon, running: !props.plan.terminal && step.status === 'in_progress' }
}))
</script>

<template>
  <section v-if="plan" class="composer-plan">
    <div v-if="open" :id="listId" class="plan-details" role="region" aria-label="当前全部计划" tabindex="0">
      <ol v-if="rows.length" class="plan-steps">
        <li v-for="(step, index) in rows" :key="step.step_id || index" class="plan-step" :class="{ running: step.running }">
          <div class="step-heading">
            <component :is="step.icon" class="step-icon" />
            <strong>{{ index + 1 }}. {{ step.title || step.step_id || '未命名步骤' }}</strong>
            <span class="step-status">{{ step.label }}</span>
          </div>
          <div class="step-executor">执行者：{{ step.executor_name || step.executor_id || '未指定' }}</div>
          <p v-if="step.instruction" class="step-description">{{ step.instruction }}</p>
          <p v-if="step.status_reason" class="step-description">{{ step.status_reason }}</p>
        </li>
      </ol>
      <p v-else class="plan-empty">{{ plan.loading ? '正在加载计划…' : plan.phase === 'generating' ? '计划生成中，步骤将自动显示' : '暂无计划步骤' }}</p>
      <div v-if="plan.error" class="plan-load-state">部分计划状态加载失败 <button type="button" @click="$emit('retry')">重试</button></div>
      <div v-else-if="plan.loading && rows.length" class="plan-load-state">正在同步计划…</div>
    </div>
    <button type="button" class="plan-summary" :aria-expanded="open" :aria-controls="listId" @click="open = !open">
      <RightOutlined :rotate="open ? -90 : 0" />
      <span class="plan-summary-text" :title="plan.summary" aria-live="polite">{{ plan.summary }}</span>
      <span class="plan-toggle-label">{{ open ? '收起' : '全部计划' }}</span>
    </button>
  </section>
</template>

<style scoped>
.composer-plan { min-width: 0; flex: 0 0 auto; color: var(--muted, #707782); font-size: 12px; }
.plan-summary { display: flex; align-items: center; gap: 6px; width: 100%; min-width: 0; padding: 3px 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.plan-summary:hover { color: var(--text, #30343b); }
.plan-summary:focus-visible { outline: 2px solid var(--accent, #5685ac); outline-offset: 3px; border-radius: 4px; }
.plan-summary-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plan-toggle-label { flex-shrink: 0; }
.plan-details { max-height: 240px; overflow-y: auto; overscroll-behavior: contain; margin-bottom: 6px; padding: 8px 10px; border: 1px solid var(--border-color, #e8e8e8); border-radius: 10px; background: var(--surface, rgba(255, 255, 255, .94)); backdrop-filter: blur(18px); }
.plan-steps { list-style: none; padding: 0; margin: 0; }
.plan-step { padding: 8px 4px; overflow-wrap: anywhere; }
.plan-step + .plan-step { border-top: 1px solid var(--border-color, #e8e8e8); }
.step-heading { display: flex; align-items: baseline; gap: 6px; }
.step-heading strong { min-width: 0; flex: 1; font-weight: 500; color: var(--text, #30343b); }
.step-status, .step-icon { flex-shrink: 0; }
.running .step-status, .running .step-icon { color: var(--accent, #5685ac); }
.step-executor { margin: 4px 0 0 18px; }
.step-description { margin: 4px 0 0 18px; white-space: pre-wrap; line-height: 1.6; }
.plan-empty { margin: 8px 0; }
.plan-load-state { padding-top: 5px; }
.plan-load-state button { color: inherit; background: none; border: 0; text-decoration: underline; cursor: pointer; }
</style>
