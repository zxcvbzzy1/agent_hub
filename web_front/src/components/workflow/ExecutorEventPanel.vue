<script setup>
import { computed } from 'vue'
import EventTimeline from './EventTimeline.vue'

const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
  executorId: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '执行者事件',
  },
  selectable: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select'])

const filteredEvents = computed(() => {
  if (!props.executorId) return props.events
  const exact = props.events.filter((event) => {
    const payload = event.payload || {}
    const step = payload.step || {}
    return (
      payload.executor_id === props.executorId ||
      step.executor_id === props.executorId ||
      JSON.stringify(payload).includes(props.executorId)
    )
  })
  return exact.length ? exact : props.events
})
</script>

<template>
  <section class="embedded-panel">
    <div class="card-title-row">
      <span>{{ title }}</span>
      <a-tag>{{ executorId || 'all' }}</a-tag>
    </div>
    <EventTimeline
      :events="filteredEvents"
      compact
      :selectable="selectable"
      @select="event => emit('select', event)"
      
    />
  </section>
</template>
