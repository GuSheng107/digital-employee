<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  activeChat: {
    type: Object,
    default: null,
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
  manualReply: {
    type: String,
    default: '',
  },
  attachments: {
    type: Array,
    default: () => [],
  },
  sendingReply: {
    type: Boolean,
    default: false,
  },
  generatingAiReply: {
    type: Boolean,
    default: false,
  },
  botRunning: {
    type: Boolean,
    default: false,
  },
  replyMode: {
    type: String,
    default: 'manual',
  },
})

const emit = defineEmits([
  'add-attachments',
  'cancel-ai-draft',
  'generate-ai-reply',
  'remove-attachment',
  'send',
  'toggle-reply-mode',
  'update:manualReply',
])

const uploadInputRef = ref(null)

function handleEnterSend(event) {
  if (event?.isComposing) {
    return
  }
  if (!props.canManualReply || (!props.manualReply.trim() && !props.attachments.length) || props.sendingReply || isArchived.value) {
    return
  }
  event?.preventDefault()
  emit('send')
}

const isAiMode = computed(() => props.replyMode === 'ai')
const isArchived = computed(() => props.activeChat?.conversation_status === 'archived')
const canSend = computed(() => Boolean(
  props.canManualReply && (props.manualReply.trim() || props.attachments.length) && !isArchived.value
))

function openFilePicker() {
  uploadInputRef.value?.click()
}

function handleFileInput(event) {
  const files = Array.from(event?.target?.files || [])
  if (files.length) {
    emit('add-attachments', files)
  }
  if (event?.target) {
    event.target.value = ''
  }
}

function handlePaste(event) {
  const clipboardFiles = []
  for (const item of event?.clipboardData?.items || []) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        clipboardFiles.push(file)
      }
    }
  }
  if (clipboardFiles.length) {
    emit('add-attachments', clipboardFiles)
    event.preventDefault()
  }
}
</script>

<template>
  <footer class="composer">
    <el-alert
      v-if="activeChat?.last_send_error && activeChat?.conversation_status !== 'archived'"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 8px"
    >
      发送失败：当前会话已自动切换到手动模式，请先手动发送成功后再重新启用 AI
    </el-alert>
    <div v-if="attachments.length" class="composer-attachments">
      <article
        v-for="attachment in attachments"
        :key="attachment.id"
        class="composer-attachment"
      >
        <img
          v-if="attachment.kind === 'image' && attachment.previewUrl"
          class="composer-attachment__preview"
          :src="attachment.previewUrl"
          :alt="attachment.filename"
        />
        <video
          v-else-if="attachment.kind === 'video' && attachment.previewUrl"
          class="composer-attachment__preview"
          :src="attachment.previewUrl"
          muted
          preload="metadata"
        />
        <span v-else class="composer-attachment__icon">{{ attachment.kind === 'video' ? '🎬' : '📎' }}</span>
        <span class="composer-attachment__name">{{ attachment.filename }}</span>
        <button
          class="composer-attachment__remove"
          type="button"
          :disabled="sendingReply"
          @click="emit('remove-attachment', attachment.id)"
        >
          ×
        </button>
      </article>
    </div>
    <div class="composer-editor" @paste.capture="handlePaste">
      <el-input
        :model-value="manualReply"
        class="composer-input"
        type="textarea"
        :rows="4"
        :input-style="{ paddingRight: '56px' }"
        :disabled="!canManualReply || isArchived"
        :placeholder="botRunning ? (isAiMode ? 'AI 自动回复模式，手动回复已禁用' : (isArchived ? '归档会话不能发送回复' : '输入要发送给当前会话的手动回复，可粘贴图片或点 + 上传')) : '请先启动 Bot 服务'"
        @update:model-value="emit('update:manualReply', $event)"
        @keydown.enter.exact="handleEnterSend"
      />
      <button
        class="composer-plus"
        type="button"
        :disabled="!canManualReply || sendingReply || isArchived"
        @click="openFilePicker"
      >
        +
      </button>
      <input
        ref="uploadInputRef"
        class="composer-file-input"
        type="file"
        multiple
        @change="handleFileInput"
      />
    </div>
    <div class="composer-actions">
      <span v-if="activeChat?.chat_id === 'unknown'">该会话缺少 chat_id，不能主动发送。</span>
      <span v-else>{{ canManualReply ? 'Enter 发送，Shift + Enter 换行；支持粘贴图片和上传图片/视频/文件。' : isAiMode ? 'AI自动回复模式' : '需要启动 Bot 并切换到手动回复模式。' }}</span>
      <div class="composer-buttons">
        <el-button
          v-if="generatingAiReply"
          size="small"
          type="danger"
          @click="emit('cancel-ai-draft')"
        >
          取消生成
        </el-button>
        <el-button
          v-else
          size="small"
          :disabled="!canUseAi || !canManualReply || !activeChat || activeChat.chat_id === 'unknown'"
          @click="emit('generate-ai-reply')"
        >
          AI 生成回复
        </el-button>
        <el-button
          type="primary"
          :loading="sendingReply"
          :disabled="!canSend"
          @click="emit('send')"
        >
          发送回复
        </el-button>
        <el-tooltip :content="canUseAi ? '切换 AI/手动回复模式' : aiDisabledReason" placement="top">
          <el-switch
            :model-value="isAiMode"
            :disabled="!canUseAi"
            active-text="AI"
            inactive-text="手动"
            @change="canUseAi && emit('toggle-reply-mode', $event)"
            class="reply-mode-switch"
          />
        </el-tooltip>
      </div>
    </div>
  </footer>
</template>
