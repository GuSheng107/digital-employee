<script setup>
import { FolderAdd, FolderOpened, Loading } from '@element-plus/icons-vue'
import { conversationAvatar, defaultConversationName, formatTime } from '../../utils/format'

defineProps({
  activeChatId: {
    type: String,
    default: '',
  },
  chats: {
    type: Array,
    default: () => [],
  },
  selectedChatIds: {
    type: Array,
    default: () => [],
  },
  hasMore: {
    type: Boolean,
    default: false,
  },
  loadingMore: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select', 'update:selectedChatIds', 'archive', 'unarchive', 'load-more'])

function toggleSelection(chatId, checked, selectedIds) {
  const current = new Set([...selectedIds])
  if (checked) {
    current.add(chatId)
  } else {
    current.delete(chatId)
  }
  emit('update:selectedChatIds', [...current])
}

function handleItemKeydown(event, chatId) {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return
  }
  event.preventDefault()
  emit('select', chatId)
}

function handleScroll(event) {
  const el = event.target
  if (!el) return
  const threshold = 60
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  if (nearBottom) {
    emit('load-more')
  }
}
</script>

<template>
  <aside class="conversation-list" @scroll.passive="handleScroll">
    <div
      v-for="chat in chats"
      :key="chat.chat_id"
      class="conversation-item"
      :class="{ active: activeChatId === chat.chat_id, archived: chat.conversation_status === 'archived' }"
      role="button"
      tabindex="0"
      @click="emit('select', chat.chat_id)"
      @keydown="handleItemKeydown($event, chat.chat_id)"
    >
      <el-checkbox
        v-if="chat.conversation_kind !== 'me'"
        class="conversation-check"
        :model-value="selectedChatIds.includes(chat.chat_id)"
        @click.stop
        @change="toggleSelection(chat.chat_id, $event, selectedChatIds)"
      />
      <span v-else class="conversation-check-placeholder" />
      <img :src="conversationAvatar(chat)" :alt="defaultConversationName(chat)" class="avatar avatar-image" />
      <span class="conversation-copy">
        <strong>{{ defaultConversationName(chat) }}</strong>
        <small>{{ formatTime(chat.last_at) }}</small>
        <em>{{ chat.last_message || '暂无内容' }}</em>
      </span>
      <span
        v-if="(chat.unread_count || 0) > 0 && activeChatId !== chat.chat_id"
        class="unread-dot"
      />
      <el-tooltip
        v-if="chat.conversation_kind !== 'me' && chat.conversation_status === 'archived'"
        content="取消归档"
        placement="top"
      >
        <el-button
          class="unarchive-button"
          type="success"
          size="small"
          link
          @click.stop
          @click="emit('unarchive', chat.chat_id)"
          circle
          :icon="FolderOpened"
        />
      </el-tooltip>
      <el-tooltip
        v-else-if="chat.conversation_kind !== 'me'"
        content="归档会话"
        placement="top"
      >
        <el-button
          class="archive-button"
          type="primary"
          size="small"
          link
          @click.stop
          @click="emit('archive', chat.chat_id)"
          circle
          :icon="FolderAdd"
        />
      </el-tooltip>
    </div>
    <div v-if="loadingMore" class="load-more-indicator">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    <p v-if="!chats.length && !loadingMore" class="empty-state">暂无会话，等待企微消息进入。</p>
  </aside>
</template>
