<script setup lang="ts">
defineProps<{
  title: string
  status: 'ok' | 'error' | 'unknown'
  message?: string
  latency?: number | null
}>()
</script>

<template>
  <section class="status-card" :class="status">
    <div class="status-card__top">
      <span class="status-card__dot" />
      <span class="status-card__title">{{ title }}</span>
    </div>
    <div class="status-card__state">
      {{ status === 'ok' ? '正常' : status === 'error' ? '异常' : '未检测' }}
    </div>
    <p class="status-card__message">{{ message || '等待检测' }}</p>
    <span v-if="latency !== null && latency !== undefined" class="status-card__latency">
      {{ latency }} ms
    </span>
  </section>
</template>
