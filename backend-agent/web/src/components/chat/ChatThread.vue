<script setup>
import { watch, nextTick, ref, onMounted } from 'vue'
import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  chat: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['rename-user'])

const messageListRef = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

let prevMessageCount = 0

watch(() => props.chat?.messages?.length, (newLen) => {
  if ((newLen || 0) > prevMessageCount) {
    scrollToBottom()
  }
  prevMessageCount = newLen || 0
})

watch(() => props.chat?.chat_id, () => {
  prevMessageCount = props.chat?.messages?.length || 0
  scrollToBottom()
})

onMounted(() => {
  prevMessageCount = props.chat?.messages?.length || 0
  scrollToBottom()
})
</script>

<template>
  <div ref="messageListRef" class="message-list">
    <p v-if="loading" class="empty-state">加载会话详情中...</p>
    <MessageBubble
      v-for="message in loading ? [] : (chat?.messages || [])"
      :key="message.id"
      :message="message"
      @rename-user="emit('rename-user', $event)"
    />
    <p v-if="!loading && chat && !chat.messages?.length" class="empty-state">该会话暂无消息。</p>
    <p v-if="!chat" class="empty-state">选择左侧会话后查看消息。</p>
  </div>
</template>
