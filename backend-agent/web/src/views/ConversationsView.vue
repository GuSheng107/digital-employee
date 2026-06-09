<script setup>
import { computed, ref, nextTick } from 'vue'
import { Document, Edit, Loading } from '@element-plus/icons-vue'
import ChatThread from '../components/chat/ChatThread.vue'
import ConversationList from '../components/chat/ConversationList.vue'
import ReplyComposer from '../components/chat/ReplyComposer.vue'
import { defaultConversationName } from '../utils/format'

const props = defineProps({
  activeChat: {
    type: Object,
    default: null,
  },
  activeBotKey: {
    type: String,
    default: '',
  },
  activeBotStatus: {
    type: Object,
    default: () => ({ running: false, pid: null }),
  },
  bots: {
    type: Array,
    default: () => [],
  },
  botStatuses: {
    type: Object,
    default: () => {},
  },
  activeChatId: {
    type: String,
    default: '',
  },
  activeChatReplyMode: {
    type: String,
    default: 'manual',
  },
  canManualReply: {
    type: Boolean,
    default: false,
  },
  canUseAi: {
    type: Boolean,
    default: true,
  },
  aiDisabledReason: {
    type: String,
    default: '',
  },
  chats: {
    type: Array,
    default: () => [],
  },
  manualReply: {
    type: String,
    default: '',
  },
  replyAttachments: {
    type: Array,
    default: () => [],
  },
  generatingAiReply: {
    type: Boolean,
    default: false,
  },
  sendingReply: {
    type: Boolean,
    default: false,
  },
  selectedChatIds: {
    type: Array,
    default: () => [],
  },
  deletingChats: {
    type: Boolean,
    default: false,
  },
  loadingChats: {
    type: Boolean,
    default: false,
  },
  loadingChatDetail: {
    type: Boolean,
    default: false,
  },
  hasMore: {
    type: Boolean,
    default: false,
  },
  loadingMore: {
    type: Boolean,
    default: false,
  },
  compressingContext: {
    type: Boolean,
    default: false,
  },
  status: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits([
  'cancel-ai-draft',
  'compress-context',
  'generate-ai-reply',
  'delete-selected-chats',
  'rename-chat',
  'rename-user',
  'select-chat',
  'select-bot',
  'update:selectedChatIds',
  'send-manual-reply',
  'update:manualReply',
  'toggle-reply-mode',
  'mark-all-bot-read',
  'archive-chat',
  'unarchive-chat',
  'add-reply-attachments',
  'load-more-chats',
  'remove-reply-attachment',
])

const editingName = ref(false)
const editNameValue = ref('')
const nameInputRef = ref(null)

const contextCompressionDisabledReason = computed(() => {
  if (!props.activeChat) return '请先选择会话'
  if (props.activeChat.conversation_status === 'archived') {
    return '已归档会话不能压缩上下文'
  }
  const replyMode = String(props.activeChat.reply_mode || props.activeChatReplyMode || 'manual').trim().toLowerCase()
  if (replyMode !== 'ai') {
    return '手动回复模式不触发上下文压缩'
  }
  return ''
})

function startEditName() {
  if (!props.activeChat) return
  editNameValue.value = props.activeChat.display_name || ''
  editingName.value = true
  nextTick(() => {
    nameInputRef.value?.focus()
  })
}

function finishEditName() {
  if (!editingName.value) return
  editingName.value = false
  if (!props.activeChat) return
  const trimmed = editNameValue.value.trim()
  const defaultName = defaultConversationName(props.activeChat)
  if (trimmed === (props.activeChat.display_name || '')) return
  if (!props.activeChat.display_name && trimmed === defaultName) return
  emit('rename-chat', trimmed)
}

function handleReplyModeChange(val) {
  emit('toggle-reply-mode', val ? 'ai' : 'manual')
}

function handleCompressContext() {
  if (contextCompressionDisabledReason.value || props.compressingContext) return
  emit('compress-context')
}

function formatUnreadBadge(total) {
  if (!total || total <= 0) return ''
  if (total > 99) return '99+'
  return String(total)
}
</script>

<template>
  <section class="stack">
    <el-card class="panel chat-panel" shadow="never">
      <template #header>
        <div class="panel-title split">
          <span>
            <el-icon><Document /></el-icon>
            会话列表
          </span>
          <div class="header-actions">
            <el-button
              type="danger"
              plain
              :disabled="!selectedChatIds.length"
              :loading="deletingChats"
              @click="emit('delete-selected-chats')"
            >
              删除选中 {{ selectedChatIds.length || '' }}
            </el-button>
          </div>
        </div>
      </template>

      <div class="chat-grid">
        <aside class="bot-column">
          <div class="column-header column-header-bot">
            <div>
              <p class="column-label">BOT</p>
              <strong class="column-title">{{ bots.length }} 个机器人</strong>
            </div>
          </div>
          <div class="bot-column-list">
            <button
              v-for="bot in bots"
              :key="bot.bot_key"
              :class="{ active: bot.bot_key === activeBotKey, 'bot-deleted': bot.bot_deleted }"
              @click="emit('select-bot', bot.bot_key)"
            >
              <span v-if="bot.bot_deleted" class="bot-status-dot bot-status-deleted"></span>
              <span v-else class="bot-status-dot" :class="{ 'bot-status-online': botStatuses[bot.bot_key]?.running, 'bot-status-offline': !botStatuses[bot.bot_key]?.running }"></span>
              <strong>{{ bot.name }}</strong>
              <span v-if="bot.bot_deleted" class="bot-deleted-tag">已删除</span>
              <em v-if="(bot.unread_total || 0) > 0" class="bot-unread-badge">{{ formatUnreadBadge(bot.unread_total) }}</em>
            </button>
          </div>
        </aside>

        <div class="conversation-column">
          <div class="column-header column-header-conversation conversation-column-header">
            <div>
              <p class="column-label">消息列表</p>
              <strong class="column-title">{{ chats.length }} 个会话</strong>
            </div>
            <button
              class="read-all-btn"
              :disabled="!bots.some(bot => bot.bot_key === activeBotKey && (bot.unread_total || 0) > 0)"
              @click="emit('mark-all-bot-read')"
            >
              批量已读
            </button>
          </div>
          <div v-if="loadingChats" class="conversation-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
          <ConversationList
            v-else
            :active-chat-id="activeChatId"
            :chats="chats"
            :selected-chat-ids="selectedChatIds"
            :has-more="hasMore"
            :loading-more="loadingMore"
            @select="emit('select-chat', $event)"
            @update:selected-chat-ids="emit('update:selectedChatIds', $event)"
            @archive="emit('archive-chat', $event)"
            @unarchive="emit('unarchive-chat', $event)"
            @load-more="emit('load-more-chats')"
          />
        </div>

        <section class="thread-panel">
          <header class="thread-header">
            <div class="thread-title-area">
              <p class="eyebrow">Current Chat</p>
              <div v-if="editingName && activeChat" class="thread-name-edit">
                <el-input
                  ref="nameInputRef"
                  v-model="editNameValue"
                  size="small"
                  placeholder="输入会话名"
                  @blur="finishEditName"
                  @keydown.enter="finishEditName"
                />
              </div>
              <h2 v-else class="thread-name-display">
                {{ activeChat ? defaultConversationName(activeChat) : '未选择会话' }}
                <el-icon v-if="activeChat" class="edit-name-icon" @click="startEditName"><Edit /></el-icon>
              </h2>
            </div>
          </header>

          <div v-if="activeChat" class="context-meter">
            <div>
              <span>上下文使用率</span>
              <strong>
                {{ activeChat.context?.used_chars || 0 }} / {{ activeChat.context?.limit_chars || 0 }}
              </strong>
            </div>
            <el-progress
              :percentage="Math.min(100, Math.round(((activeChat.context?.used_chars || 0) / Math.max(1, activeChat.context?.limit_chars || 1)) * 1000) / 10)"
              :stroke-width="8"
            />
            <el-tooltip
              :disabled="!contextCompressionDisabledReason"
              :content="contextCompressionDisabledReason"
              placement="top"
            >
              <span class="context-meter__compress-action">
                <el-button
                  size="small"
                  :disabled="compressingContext || Boolean(contextCompressionDisabledReason)"
                  :loading="compressingContext"
                  @click="handleCompressContext"
                >
                  手动压缩
                </el-button>
              </span>
            </el-tooltip>
          </div>

          <ChatThread :chat="activeChat" :loading="loadingChatDetail" @rename-user="emit('rename-user', $event)" />

          <ReplyComposer
            :active-chat="activeChat"
            :reply-mode="activeChatReplyMode"
            :bot-running="activeBotStatus.running"
            :can-manual-reply="canManualReply"
            :can-use-ai="canUseAi"
            :ai-disabled-reason="aiDisabledReason"
            :generating-ai-reply="generatingAiReply"
            :manual-reply="manualReply"
            :attachments="replyAttachments"
            :sending-reply="sendingReply"
            @add-attachments="emit('add-reply-attachments', $event)"
            @cancel-ai-draft="emit('cancel-ai-draft')"
            @generate-ai-reply="emit('generate-ai-reply')"
            @remove-attachment="emit('remove-reply-attachment', $event)"
            @send="emit('send-manual-reply')"
            @update:manual-reply="emit('update:manualReply', $event)"
            @toggle-reply-mode="handleReplyModeChange"
          />
        </section>
      </div>
    </el-card>
  </section>
</template>

