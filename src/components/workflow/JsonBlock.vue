<script setup>
defineProps({
  value: {
    type: [Object, Array, String, Number, Boolean],
    default: '',
  },
})

function stringify(value) {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}
</script>

<template>
  <pre class="json-block">{{ stringify(value) }}</pre>
</template>

