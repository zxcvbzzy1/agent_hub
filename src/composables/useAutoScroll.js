import { nextTick, watch } from 'vue'

export function useAutoScroll(containerRef, source, options = {}) {
  const scrollToBottom = async (behavior = options.behavior || 'smooth') => {
    await nextTick()
    const container = containerRef.value?.$el || containerRef.value
    if (!container) return
    container.scrollTo?.({
      top: container.scrollHeight,
      behavior,
    })
  }

  if (source) {
    watch(source, () => scrollToBottom(), { flush: 'post' })
  }

  return { scrollToBottom }
}
