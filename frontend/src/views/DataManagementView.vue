<script setup>
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { ChatDotRound, Coin, Document, FolderOpened } from '@element-plus/icons-vue'
import { formatBytes } from '../utils/format'

const props = defineProps({
  dataOverview: {
    type: Object,
    default: null,
  },
  tokenUsage: {
    type: Object,
    default: null,
  },
  botStatuses: {
    type: Object,
    default: () => ({}),
  },
  optimizingData: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['optimize-data'])

const manualReplies = computed(() => props.dataOverview?.manual_replies || 0)
const aiReplies = computed(() => props.dataOverview?.ai_replies || 0)
const totalReplies = computed(() => manualReplies.value + aiReplies.value)
const manualRatio = computed(() => totalReplies.value ? `${Math.round((manualReplies.value / totalReplies.value) * 100)}%` : '0%')
const aiRatio = computed(() => totalReplies.value ? `${Math.round((aiReplies.value / totalReplies.value) * 100)}%` : '0%')

const uploadedDocuments = computed(() => props.dataOverview?.uploaded_documents || 0)
const convertedDocuments = computed(() => props.dataOverview?.converted_documents || 0)
const convertedMessages = computed(() => props.dataOverview?.converted_messages || 0)
const unconvertedMessages = computed(() => props.dataOverview?.unconverted_messages || 0)
const memoryUpdateCount = computed(() => props.dataOverview?.memory_update_count || 0)
const documentExtractionCount = computed(() => props.dataOverview?.document_extraction_count || 0)
const convertedDocumentRate = computed(() => props.dataOverview?.document_conversion_rate || 0)
const convertedMessageRate = computed(() => props.dataOverview?.message_conversion_rate || 0)

const aiTaskTotal = computed(() => props.dataOverview?.ai_task_total || 0)
const aiTaskCompleted = computed(() => props.dataOverview?.ai_task_completed || 0)
const aiTaskFailed = computed(() => props.dataOverview?.ai_task_failed || 0)
const aiTaskRunning = computed(() => props.dataOverview?.ai_task_running || 0)
const runningBotCount = computed(() => {
  return Object.values(props.botStatuses || {}).filter((status) => status?.running).length
})

async function confirmOptimize() {
  await ElMessageBox.confirm(
    '该操作会先停止所有正在运行的 Bot，然后执行以下清理：\n• 物理清除 3 个月以前的所有用户对话\n• 物理清除已删除超过 3 个月的 Bot 及其关联数据\n• 清除 3 个月前的 Token 消耗记录\n• 清除 15 天前的所有项目日志\n• 执行 SQLite VACUUM 优化数据库大小\n\n优化完成后不会自动恢复 Bot，需要你回到工作台手动启动。该操作不可恢复，确认执行？',
    '确认优化数据库',
    {
      confirmButtonText: '确认清理并优化',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
  emit('optimize-data')
}

function formatNumber(n) {
  if (n == null || n === 0) return '0'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function formatPercent(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '0%'
  return `${Math.round(num)}%`
}
</script>

<template>
  <section class="console-view">
    <div class="data-overview-grid">
      <el-card class="panel console-panel" shadow="never">
        <template #header>
          <div class="panel-title">
            <span><el-icon><FolderOpened /></el-icon>数据库概览</span>
          </div>
        </template>

        <div class="data-hero">
          <div>
            <p class="eyebrow">SQLite Database</p>
            <h2>{{ formatBytes(dataOverview?.size_bytes || 0) }}</h2>
            <span class="mono-text">{{ dataOverview?.path || '-' }}</span>
          </div>
          <el-button type="danger" :loading="optimizingData" @click="confirmOptimize">
            优化数据库
          </el-button>
        </div>

        <div class="metric-row metric-row--quad">
          <div>
            <span>会话数</span>
            <strong>{{ dataOverview?.conversations || 0 }}</strong>
          </div>
          <div>
            <span>消息数</span>
            <strong>{{ dataOverview?.messages || 0 }}</strong>
          </div>
          <div>
            <span>日志数</span>
            <strong>{{ dataOverview?.logs || 0 }}</strong>
          </div>
          <div>
            <span>近 30 天 AI 任务</span>
            <strong>{{ dataOverview?.recent_ai_tasks || 0 }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--quad">
          <div>
            <span>Bot 总数</span>
            <strong>{{ dataOverview?.bot_count || 0 }}</strong>
          </div>
          <div>
            <span>启用 Bot</span>
            <strong>{{ dataOverview?.enabled_bot_count ?? dataOverview?.active_bot_count ?? 0 }}</strong>
          </div>
          <div>
            <span>运行中 Bot</span>
            <strong>{{ runningBotCount }}</strong>
          </div>
          <div>
            <span>启用任务数</span>
            <strong>{{ (dataOverview?.enabled_periodic_tasks || 0) + (dataOverview?.enabled_one_time_tasks || 0) }}</strong>
          </div>
        </div>
      </el-card>

      <el-card class="panel console-panel" shadow="never">
        <template #header>
          <div class="panel-title">
            <span><el-icon><Coin /></el-icon>Token 消耗</span>
          </div>
        </template>

        <div class="metric-row metric-row--quad">
          <div>
            <span>输入 Token</span>
            <strong>{{ formatNumber(tokenUsage?.input_tokens || 0) }}</strong>
          </div>
          <div>
            <span>输出 Token</span>
            <strong>{{ formatNumber(tokenUsage?.output_tokens || 0) }}</strong>
          </div>
          <div>
            <span>聊天与任务</span>
            <strong>{{ formatNumber(tokenUsage?.bot_tokens || 0) }}</strong>
          </div>
          <div>
            <span>系统与维护</span>
            <strong>{{ formatNumber(tokenUsage?.system_tokens || 0) }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--triple token-time-row">
          <div class="token-time-card">
            <span>总消耗</span>
            <small>{{ tokenUsage?.total_range_label || '-' }}</small>
            <strong>{{ formatNumber(tokenUsage?.total_tokens || 0) }}</strong>
          </div>
          <div class="token-time-card">
            <span>周消耗</span>
            <small>{{ tokenUsage?.weekly_range_label || '-' }}</small>
            <strong>{{ formatNumber(tokenUsage?.weekly_tokens || 0) }}</strong>
          </div>
          <div class="token-time-card">
            <span>月消耗</span>
            <small>{{ tokenUsage?.monthly_range_label || '-' }}</small>
            <strong>{{ formatNumber(tokenUsage?.monthly_tokens || 0) }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--triple">
          <div>
            <span>模型调用记录</span>
            <strong>{{ tokenUsage?.record_count || 0 }}</strong>
          </div>
          <div>
            <span>平均单次调用</span>
            <strong>{{ formatNumber(tokenUsage?.avg_tokens_per_record || 0) }}</strong>
          </div>
          <div>
            <span>最高单次调用</span>
            <strong>{{ formatNumber(tokenUsage?.max_tokens_per_record || 0) }}</strong>
          </div>
        </div>
      </el-card>

      <el-card class="panel console-panel" shadow="never">
        <template #header>
          <div class="panel-title">
            <span><el-icon><Document /></el-icon>记忆量</span>
          </div>
        </template>

        <div class="metric-row metric-row--quad">
          <div>
            <span>上传文档数</span>
            <strong>{{ uploadedDocuments }}</strong>
          </div>
          <div>
            <span>已转换文档数</span>
            <strong>{{ convertedDocuments }}</strong>
          </div>
          <div>
            <span>已转换记录数</span>
            <strong>{{ convertedMessages }}</strong>
          </div>
          <div>
            <span>未转换消息数</span>
            <strong>{{ unconvertedMessages }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--quad">
          <div>
            <span>文档转换率</span>
            <strong>{{ formatPercent(convertedDocumentRate) }}</strong>
          </div>
          <div>
            <span>消息转换率</span>
            <strong>{{ formatPercent(convertedMessageRate) }}</strong>
          </div>
          <div>
            <span>记忆更新次数</span>
            <strong>{{ memoryUpdateCount }}</strong>
          </div>
          <div>
            <span>文档提取次数</span>
            <strong>{{ documentExtractionCount }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--dual">
          <div>
            <span>记忆包注入成功</span>
            <strong>{{ dataOverview?.memory_pack_injection_success_count || 0 }}</strong>
          </div>
          <div>
            <span>记忆包注入失败</span>
            <strong>{{ dataOverview?.memory_pack_injection_failed_count || 0 }}</strong>
          </div>
        </div>
      </el-card>

      <el-card class="panel console-panel" shadow="never">
        <template #header>
          <div class="panel-title">
            <span><el-icon><ChatDotRound /></el-icon>任务量</span>
          </div>
        </template>

        <div class="metric-row metric-row--dual">
          <div>
            <span>人工回复</span>
            <strong>{{ manualReplies }}</strong>
          </div>
          <div>
            <span>AI 回复</span>
            <strong>{{ aiReplies }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--triple">
          <div>
            <span>总回复量</span>
            <strong>{{ totalReplies }}</strong>
          </div>
          <div>
            <span>人工占比</span>
            <strong>{{ manualRatio }}</strong>
          </div>
          <div>
            <span>AI 占比</span>
            <strong>{{ aiRatio }}</strong>
          </div>
        </div>

        <div class="metric-row metric-row--quad">
          <div>
            <span>AI 任务总数</span>
            <strong>{{ aiTaskTotal }}</strong>
          </div>
          <div>
            <span>已完成任务</span>
            <strong>{{ aiTaskCompleted }}</strong>
          </div>
          <div>
            <span>失败任务</span>
            <strong>{{ aiTaskFailed }}</strong>
          </div>
          <div>
            <span>进行中/排队</span>
            <strong>{{ aiTaskRunning }}</strong>
          </div>
        </div>

      </el-card>
    </div>
  </section>
</template>
