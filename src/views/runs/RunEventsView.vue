<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import EventTimeline from '@/components/workflow/EventTimeline.vue'
import { useRunsStore } from '@/stores/runs'

const route = useRoute()
const runs = useRunsStore()
const runId = computed(() => route.params.runId)
const events = computed(() => runs.eventsByRun[runId.value] || [])

onMounted(() => {
  runs.fetchRun(runId.value).catch(() => {})
  runs.connect(runId.value)
})
onUnmounted(() => runs.disconnect(runId.value))
</script>

<template>
  <main class="frame-page">
    <div class="frame-header">
      <div>
        <span class="eyebrow">Run Events</span>
        <h1>{{ runId }}</h1>
      </div>
      <a-tag color="blue">{{ events.length }} events</a-tag>
    </div>
    <a-card class="panel-card" :bordered="false">
      <EventTimeline :events="events" />
    </a-card>
  </main>
</template>

