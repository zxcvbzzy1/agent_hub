<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import ExecutorEventPanel from '@/components/workflow/ExecutorEventPanel.vue'
import { useRunsStore } from '@/stores/runs'

const route = useRoute()
const runs = useRunsStore()
const runId = computed(() => route.params.runId)
const executorId = computed(() => route.params.executorId || '')
const events = computed(() => runs.eventsByRun[runId.value] || [])

onMounted(() => runs.connect(runId.value))
onUnmounted(() => runs.disconnect(runId.value))
</script>

<template>
  <main class="frame-page embedded-frame-page">
    <ExecutorEventPanel :events="events" :executor-id="executorId" title="Executor / Step 事件视图" />
  </main>
</template>

