<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '@/components/TabBar.vue'

const route = useRoute()
const showTabBar = computed(() => Boolean(route.meta.tab))
</script>

<template>
  <div class="app-shell">
    <RouterView v-slot="{ Component }">
      <component :is="Component" />
    </RouterView>
    <TabBar v-if="showTabBar" />
  </div>
</template>

<style scoped>
.app-shell {
  height: 100%;
}
</style>
