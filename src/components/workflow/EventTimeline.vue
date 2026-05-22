<script setup>
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons-vue'
import { runsApi } from '@/api/runs'
import JsonBlock from './JsonBlock.vue'

const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
  compact: {
    type: Boolean,
    default: false,
  },
  selectable: {
    type: Boolean,
    default: false,
  },
  showPayload: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['select'])

const sortedEvents = computed(() => {
  return [...props.events].sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
})
const resolving = ref({})
const locallyResolved = ref({})

const resolvedConfirmationIds = computed(() => {
  const ids = new Set(
    props.events
      .filter((event) => event.name === 'human.confirmation.resolved' && event.payload?.confirmation_id)
      .map((event) => event.payload.confirmation_id),
  )
  Object.keys(locallyResolved.value).forEach((id) => ids.add(id))
  return ids
})

function colorFor(name = '') {
  if (name.includes('failed')) return 'red'
  if (name.includes('finished')) return 'green'
  if (name.includes('generated') || name.includes('replanned')) return 'blue'
  if (name.includes('step')) return 'purple'
  return 'gray'
}

function iconFor(name = '') {
  if (name.includes('failed')) return CloseCircleOutlined
  if (name.includes('finished')) return CheckCircleOutlined
  if (name.includes('step')) return NodeIndexOutlined
  return ClockCircleOutlined
}

function eventTitle(event) {
  const step = event?.payload?.step
  if (step?.title) return `${event.name} · ${step.title}`
  if (event?.payload?.tool_name) return `${event.name} · ${event.payload.tool_name}`
  return event.name
}

function isConfirmationRequest(event) {
  return event.name === 'human.confirmation.requested' && event.payload?.status === 'pending'
}

function isConfirmationResolved(event) {
  const confirmationId = event?.payload?.confirmation_id
  return Boolean(confirmationId && resolvedConfirmationIds.value.has(confirmationId))
}

async function resolveConfirmation(event, approved) {
  const payload = event.payload || {}
  const key = payload.confirmation_id
  if (!payload.run_id || !key || isConfirmationResolved(event)) return
  resolving.value[key] = true
  try {
    await runsApi.resolveConfirmation(payload.run_id, payload.confirmation_id, {
      approved,
      reason: approved ? '前端批准执行' : '前端拒绝执行',
    })
    locallyResolved.value = { ...locallyResolved.value, [key]: true }
    message.success(approved ? '已批准工具执行' : '已拒绝工具执行')
  } finally {
    resolving.value[key] = false
  }
}

function selectEvent(event) {
  if (props.selectable) {
    emit('select', event)
  }
}
</script>

<template>
  <a-empty v-if="!sortedEvents.length" description="暂无事件" />
  <a-timeline v-else class="event-timeline">
    <a-timeline-item
      v-for="event in sortedEvents"
      :key="event.event_id || `${event.name}-${event.created_at}`"
      :color="colorFor(event.name)"
    >
      <template #dot>
        <component :is="iconFor(event.name)" />
      </template>
      <div
        class="event-row"
        :class="{ selectable: selectable }"
        @click="selectEvent(event)"
      >
        <div class="event-row-head">
          <a-tag :color="colorFor(event.name)">{{ event.name }}</a-tag>
          <span class="event-time">{{ event.created_at ? new Date(event.created_at * 1000).toLocaleTimeString() : '' }}</span>
        </div>
        <strong>{{ eventTitle(event) }}</strong>
        <a-space v-if="isConfirmationRequest(event)" class="confirmation-actions">
          <a-button
            size="small"
            type="primary"
            :loading="resolving[event.payload.confirmation_id]"
            :disabled="isConfirmationResolved(event) || resolving[event.payload.confirmation_id]"
            @click.stop="resolveConfirmation(event, true)"
          >
            批准
          </a-button>
          <a-button
            size="small"
            danger
            :loading="resolving[event.payload.confirmation_id]"
            :disabled="isConfirmationResolved(event) || resolving[event.payload.confirmation_id]"
            @click.stop="resolveConfirmation(event, false)"
          >
            拒绝
          </a-button>
        </a-space>
        <JsonBlock v-if="showPayload && !compact" :value="event.payload" />
      </div>
    </a-timeline-item>
  </a-timeline>
</template>
