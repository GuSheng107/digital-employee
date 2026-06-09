<script setup>
import { computed, reactive } from 'vue'
import { Edit } from '@element-plus/icons-vue'
import { urlWithAuthToken } from '../../api/http'
import { displayUserName, formatTime } from '../../utils/format'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['rename-user'])

const replyStatusLabel = computed(() => {
  return props.message.reply_status === 'replied' ? '已回复' : '未回复'
})

const userDisplayName = computed(() => {
  return props.message.sender_display_name || displayUserName(props.message.sender_name, props.message.sender_id)
})

const canRenameUser = computed(() => {
  return props.message.direction === 'user' && props.message.sender_id && props.message.sender_id !== 'unknown'
})

const botReplySourceLabel = computed(() => {
  return props.message.reply_source === 'manual' ? '手动' : 'AI'
})

const messageParts = computed(() => {
  const parts = Array.isArray(props.message?.metadata?.parts) ? props.message.metadata.parts : []
  if (parts.length) {
    const hasText = parts.some(p => p.type === 'text' && (p.text || '').trim())
    if (hasText) {
      return parts.filter(p => p.type === 'text' && (p.text || '').trim())
    }
    return parts
  }
  return [{ type: 'text', text: props.message.content || '' }]
})

const feedbackTag = computed(() => {
  const fb = props.message?.feedback
  if (!fb) return null
  const result = String(fb.result || '').toLowerCase()
  const reason = String(fb.reason || '').trim()
  const count = Number(fb.count || 1)
  if (result === 'useful') {
    return { label: '有效', type: 'success', reason: '' }
  }
  if (result === 'useless') {
    return { label: '无效', type: 'danger', reason }
  }
  if (result === 'mixed') {
    const suffix = count > 1 ? ` (${count})` : ''
    return { label: `有争议${suffix}`, type: 'warning', reason: reason || '' }
  }
  return null
})

const imageErrors = reactive(new Set())

function onImageError(index) {
  imageErrors.add(index)
}

function isImageFailed(part, index) {
  return imageErrors.has(index) || (!part.preview_url && !part.url) || part.oversized
}

const FILE_ICON_MAP = {
  'application/pdf': '📄',
  'application/msword': '📝',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📝',
  'application/vnd.ms-excel': '📊',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '📊',
  'application/vnd.ms-powerpoint': '📊',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': '📊',
  'application/zip': '🗜️',
  'application/x-rar-compressed': '🗜️',
  'application/x-7z-compressed': '🗜️',
  'application/gzip': '🗜️',
  'application/x-tar': '🗜️',
}

function fileIcon(mime) {
  if (!mime) return '📎'
  const lower = mime.toLowerCase()
  for (const [key, icon] of Object.entries(FILE_ICON_MAP)) {
    if (lower === key) return icon
  }
  if (lower.startsWith('text/')) return '📝'
  if (lower.startsWith('image/')) return '🖼️'
  if (lower.startsWith('video/')) return '🎬'
  if (lower.startsWith('audio/')) return '🎵'
  return '📎'
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return ''
  const n = Number(bytes)
  if (isNaN(n)) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function handleRenameUser() {
  if (!canRenameUser.value) return
  emit('rename-user', {
    sender_id: props.message.sender_id,
    sender_name: props.message.sender_name,
    sender_display_name: userDisplayName.value,
    sender_custom_display_name: props.message.sender_custom_display_name || '',
  })
}

function authUrl(url) {
  return url ? urlWithAuthToken(url) : ''
}
</script>

<template>
  <div class="message-row" :class="message.direction === 'user' ? 'left' : 'right'">
    <div class="message-meta">
      <template v-if="message.direction === 'user'">
        <span class="message-user-name">
          {{ userDisplayName }}
          <button
            v-if="canRenameUser"
            type="button"
            class="message-user-edit"
            title="编辑用户显示名"
            @click.stop="handleRenameUser"
          >
            <el-icon><Edit /></el-icon>
          </button>
        </span>
        | {{ formatTime(message.created_at) }}
      </template>
      <template v-else>
        {{ botReplySourceLabel }}
        <el-tag v-if="feedbackTag" :type="feedbackTag.type" size="small" class="feedback-tag">
          {{ feedbackTag.label }}
        </el-tag>
        | {{ formatTime(message.created_at) }}
      </template>
      <span v-if="message.direction === 'user'" class="reply-status" :class="message.reply_status === 'replied' ? 'reply-status--done' : 'reply-status--pending'">
        {{ replyStatusLabel }}
      </span>
    </div>
    <div class="bubble">
      <template v-for="(part, index) in messageParts" :key="`${message.id || message.created_at}-${index}`">
        <div v-if="part.type === 'text'" class="bubble-text">{{ part.text }}</div>
        <div v-else-if="part.type === 'image'" class="bubble-image-block">
          <template v-if="!isImageFailed(part, index)">
            <img
              class="bubble-image"
              :src="authUrl(part.preview_url || part.url)"
              :alt="`图片 ${index + 1}`"
              @error="onImageError(index)"
            />
          </template>
          <div v-else class="bubble-image-fallback">
            {{ part.oversized ? '图片过大，无法预览' : '图片加载失败' }}
          </div>
        </div>
        <div v-else-if="part.type === 'video'" class="bubble-video-block">
          <video
            v-if="part.url && !part.oversized"
            class="bubble-video"
            :src="authUrl(part.url)"
            controls
            preload="metadata"
          />
          <div v-else class="bubble-image-fallback">{{ part.oversized ? '视频超过大小限制' : '视频加载失败' }}</div>
        </div>
        <div v-else-if="part.type === 'audio'" class="bubble-audio-block">
          <audio
            v-if="part.url && !part.oversized"
            class="bubble-audio"
            :src="authUrl(part.url)"
            controls
            preload="metadata"
          />
          <div v-else class="bubble-image-fallback">{{ part.oversized ? '音频超过大小限制' : '音频加载失败' }}</div>
        </div>
        <div v-else-if="part.type === 'file'" class="bubble-file-block">
          <a
            v-if="part.url"
            class="bubble-file-card"
            :href="authUrl(part.url)"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="bubble-file-icon">{{ fileIcon(part.mime_type) }}</span>
            <span class="bubble-file-info">
              <span class="bubble-file-name">{{ part.filename || '附件' }}</span>
              <span v-if="formatFileSize(part.size)" class="bubble-file-size">{{ formatFileSize(part.size) }}</span>
            </span>
          </a>
          <div v-else class="bubble-image-fallback">文件链接不可用</div>
        </div>
        <div v-else class="bubble-unknown-attachment">
          <span class="bubble-unknown-icon">📎</span>
          <span>未知附件</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.feedback-tag {
  margin-left: 6px;
  vertical-align: middle;
}
</style>
