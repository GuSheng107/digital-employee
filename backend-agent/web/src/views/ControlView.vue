<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { getAiStatus, cancelAiWork, clearAiWork } from '../api/runtime'
import { urlWithAuthToken } from '../api/http'
import { getAgentLabel, formatTimeOnly } from '../utils/format'

const props = defineProps({
    agents: {
        type: Array,
        default: () => [],
    },
    bots: {
        type: Array,
        default: () => [],
    },
    botStatuses: {
        type: Object,
        default: () => ({}),
    },
    startingBots: {
        type: Set,
        default: () => new Set(),
    },
    stoppingBots: {
        type: Set,
        default: () => new Set(),
    },
})

const combinedTasks = computed(() => {
  // 确保先显示 active（包括 cancel_requested），然后显示 recent
  const tasks = [...(aiStatus.value.active || []), ...(aiStatus.value.recent || [])]
  const seen = new Set()
  const unique = []
  for (const task of tasks) {
    if (task?.trace_id && !seen.has(task.trace_id)) {
      seen.add(task.trace_id)
      unique.push(task)
    }
  }
  return unique.slice(0, 15)
})

function isActiveStatus(status) {
  return ['queued', 'running', 'cancel_requested'].includes(status)
}

const emit = defineEmits(['start-bot', 'stop-bot'])

const enabledBots = computed(() => props.bots.filter((bot) => Boolean(bot.is_active)))

const aiStatus = ref({ busy: false, active: [], recent: [] })
let aiStatusSource = null
let reconnectTimer = null
let streamStopped = false
const cancellingTasks = ref(new Set())
const clearingTasks = ref(new Set())

function isCancelling(traceId) {
  return cancellingTasks.value.has(traceId)
}

function isClearing(traceId) {
  return clearingTasks.value.has(traceId)
}

function getStatus(botKey) {
  return props.botStatuses[botKey] || { running: false, pid: null }
}

function promptPreview(prompt) {
  const text = String(prompt || '').trim()
  return text || '未设置提示词'
}

async function loadAiStatus() {
  try {
    aiStatus.value = await getAiStatus()
  } catch {
    aiStatus.value = { busy: false, active: [], recent: [] }
  }
}

async function handleCancel(traceId) {
    if (cancellingTasks.value.has(traceId)) {
        return
    }
    cancellingTasks.value.add(traceId)
    try {
        await cancelAiWork(traceId)
        ElMessage.success('已发送取消请求')
        await loadAiStatus()
    } catch (e) {
        ElMessage.error(String(e))
    } finally {
        cancellingTasks.value.delete(traceId)
    }
}

async function handleClear(traceId) {
    if (clearingTasks.value.has(traceId)) {
        return
    }
    clearingTasks.value.add(traceId)
    try {
        await clearAiWork(traceId)
        ElMessage.success('已清除任务')
        await loadAiStatus()
    } catch (e) {
        ElMessage.error(String(e))
    } finally {
        clearingTasks.value.delete(traceId)
    }
}

function taskDisplayName(task) {
  const convName = task.conv_display_name || ''
  const chatType = task.conv_chat_type || ''
  const senderName = task.conv_sender_name || ''
  if (chatType === 'group' && convName) {
    return senderName ? `${convName}:${senderName}` : convName
  }
  if (senderName) {
    return senderName
  }
  if (convName) {
    return convName
  }
  return task.chat_name || task.chat_id || '--'
}

function stageLabel(stage) {
  const map = {
    '接收消息': '接收消息',
    '等待 Agent 并发槽': '等待并发槽',
    '构建上下文并调用 Agent（流式）': 'Agent 推理中',
    '构建上下文并调用 Agent': 'Agent 推理中',
    '发送企微回复': '发送回复',
    '完成': '完成',
    '已截断': '已截断',
    '异常截断': '异常截断',
  }
  return map[stage] || stage
}

function statusType(status) {
  if (status === 'running') return 'primary'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'cancelled' || status === 'cancel_requested') return 'warning'
  return 'info'
}

function formatTime(iso) {
  return formatTimeOnly(iso)
}

function reasoningPreview(task) {
  const reasoning = String(task?.reasoning || '').trim()
  if (reasoning) return reasoning
  const stage = stageLabel(task?.stage || '')
  if (isActiveStatus(task?.status)) {
    return stage ? `当前阶段：${stage}` : 'Agent 正在工作...'
  }
  return task?.error ? `异常：${task.error}` : '暂无思考链记录'
}

function closeAiStatusStream() {
  if (aiStatusSource) {
    aiStatusSource.close()
    aiStatusSource = null
  }
}

function scheduleReconnect() {
  if (streamStopped || reconnectTimer) {
    return
  }
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    startAiStatusStream()
  }, 3000)
}

function startAiStatusStream() {
  closeAiStatusStream()
  if (typeof EventSource === 'undefined') {
    loadAiStatus()
    scheduleReconnect()
    return
  }
  try {
    aiStatusSource = new EventSource(urlWithAuthToken('/api/ai/status/stream'))
    aiStatusSource.onmessage = (event) => {
      try {
        aiStatus.value = JSON.parse(event.data)
      } catch {
        // Ignore malformed frames and keep the last good payload.
      }
    }
    aiStatusSource.onerror = () => {
      closeAiStatusStream()
      scheduleReconnect()
    }
  } catch {
    scheduleReconnect()
  }
}

onMounted(() => {
  streamStopped = false
  loadAiStatus()
  startAiStatusStream()
})

onActivated(() => {
  loadAiStatus()
  streamStopped = false
  startAiStatusStream()
})

onDeactivated(() => {
  streamStopped = true
  closeAiStatusStream()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
})

onBeforeUnmount(() => {
  streamStopped = true
  closeAiStatusStream()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
})
</script>

<template>
  <section class="console-view">
    <div class="console-grid">
      <el-card class="panel console-panel" shadow="never">
        <template #header>
          <div class="panel-title split">
            <span>已启用 Bot</span>
          </div>
        </template>

        <div v-if="enabledBots.length" class="bot-card-grid">
          <article v-for="bot in enabledBots" :key="bot.bot_key" class="bot-service-card">
            <header class="bot-service-head">
              <div>
                <h3>{{ bot.name }}</h3>
                <p>{{ getAgentLabel(bot.agent_provider, agents) }}</p>
              </div>
              <el-tag :type="getStatus(bot.bot_key).running ? 'success' : 'info'" effect="dark" round>
                {{ getStatus(bot.bot_key).running ? '运行中' : '已停止' }}
              </el-tag>
            </header>

            <div class="metric-row metric-row--bot">
              <div>
                <span>MCP 数</span>
                <strong>{{ bot.enabled_mcp_count || 0 }}</strong>
              </div>
              <div>
                <span>Skills 数</span>
                <strong>{{ bot.enabled_skill_count || 0 }}</strong>
              </div>
              <div>
                <span>PID</span>
                <strong>{{ getStatus(bot.bot_key).pid || '-' }}</strong>
              </div>
            </div>

            <div class="prompt-preview">
              <span>提示词</span>
              <p :title="promptPreview(bot.system_prompt)">{{ promptPreview(bot.system_prompt) }}</p>
            </div>

            <footer class="actions bot-card-actions">
              <el-button
                type="success"
                :icon="VideoPlay"
                :disabled="getStatus(bot.bot_key).running || startingBots.has(bot.bot_key)"
                :loading="startingBots.has(bot.bot_key)"
                @click="emit('start-bot', bot.bot_key)"
              >
                启动服务
              </el-button>
              <el-button
                type="danger"
                :icon="VideoPause"
                :disabled="!getStatus(bot.bot_key).running || stoppingBots.has(bot.bot_key)"
                :loading="stoppingBots.has(bot.bot_key)"
                @click="emit('stop-bot', bot.bot_key)"
              >
                停止服务
              </el-button>
            </footer>
          </article>
        </div>

        <div v-else class="empty-block">
          <strong>暂无已启用 Bot</strong>
          <span>请先在 Bot 配置页面启用 Bot，再回到工作台查看运行状态。</span>
        </div>
      </el-card>

      <el-card class="panel console-panel" shadow="never">
        <template #header>
            <div class="panel-title split">
                <span>任务列表</span>
                <el-tag v-if="aiStatus.busy" type="warning" effect="dark" round size="small">运行中</el-tag>
            </div>
        </template>

        <div v-if="combinedTasks.length" class="task-list">
            <article v-for="task in combinedTasks" :key="task.trace_id" 
                     class="task-item" 
                     :class="{'task-item--active': isActiveStatus(task.status)}">
                <div class="task-item__head">
                    <strong>{{ taskDisplayName(task) }}</strong>
                    <el-tag :type="statusType(task.status)" round size="small">{{ stageLabel(task.stage) }}</el-tag>
                </div>
                <p class="task-item__question">{{ (task.question || '').slice(0, 100) }}</p>
                <pre class="task-item__answer">{{ reasoningPreview(task) }}</pre>
                <div class="task-item__meta">
                    <span>TraceId: {{ task.trace_id.slice(0, 8) }}...</span>
                    <span>{{ formatTime(task.started_at) }}</span>
                    <el-button v-if="isActiveStatus(task.status)" 
                               size="small" text type="danger" 
                               :loading="isCancelling(task.trace_id)" 
                               :disabled="isCancelling(task.trace_id)"
                               @click="handleCancel(task.trace_id)">
                        取消
                    </el-button>
                    <el-button v-else
                               size="small" text type="info" 
                               :loading="isClearing(task.trace_id)" 
                               :disabled="isClearing(task.trace_id)"
                               @click="handleClear(task.trace_id)">
                        清除
                    </el-button>
                </div>
            </article>
        </div>

        <div v-else class="empty-block empty-block--large">
            <strong>暂无任务</strong>
            <span>Bot 运行后，Agent 的调用任务会实时展示在这里。</span>
        </div>
      </el-card>
    </div>
  </section>
</template>
