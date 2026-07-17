<script setup>
import { computed, onMounted, onActivated, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import {
  getBots,
  getPlatformSettings,
  restoreDeletedBots,
  savePlatformSettings,
  getDocuments,
  getDocumentsConfig,
  uploadDocuments,
  deleteDocument,
  downloadDocumentBlob,
} from '../api/runtime'
import { useRuntimeConsole } from '../composables/useRuntimeConsole'

const props = defineProps({
  agents: {
    type: Array,
    default: () => [],
  },
})

const { refreshAll } = useRuntimeConsole()
const savingPlatformSettings = ref(false)
const loadingSettings = ref(false)
const platformSettings = ref({
    context_length_limit: null,
    platform_agent_provider: '',
    platform_agent_timeout_seconds: null,
    platform_agent_max_iterations: null,
    document_max_characters: 5000,
    memory_update_max_pairs: 100,
    memory_update_max_chars: 15000,
    thread_pool_max_workers: null,
    attachment_reply: false,
    guest_account_enabled: false,
    feedback_alert_enabled: false,
    feedback_alert_threshold: 3,
    feedback_alert_window_minutes: 60,
    feedback_alert_cooldown_minutes: 30,
    logging_level: 'INFO',
    agent_max_reasoning_chars: null,
    agent_max_output_chars: null,
    agent_max_stream_chunks: null,
    agent_truncation_notice: "",
    agent_reply_notice: "",
    agent_fallback_text: "",
    skills_max_script_output_chars: null,
    agent_compression_transcript_max_chars: null,
    agent_max_cache_size: null,
    agent_recent_context_max_chars: null,
    agent_recent_context_max_messages: null,
    agent_recent_context_fetch_multiplier: null,
    agent_context_message_max_chars: null,
    agent_summary_in_prompt_max_chars: null,
    agent_system_prompt_max_chars: null,
    runtime_max_system_task_concurrency: null,
    skills_max_tool_description_chars: null,
    memory_query_expansion_enabled: false,
})

const deletedBots = ref([])
const restoringBots = ref(false)
const loadingDeletedBots = ref(false)

const selectedDeletedBotKeys = computed(() =>
  deletedBots.value.filter((bot) => bot._selected).map((bot) => bot.bot_key),
)

const documents = ref([])
const loadingDocuments = ref(false)
const docManagerVisible = ref(false)
const uploadingDocuments = ref(false)
const deletingDocIds = ref(new Set())
const fileInputRef = ref(null)
const docConfig = ref({
  allowed_extensions: ['.doc', '.docx', '.txt', '.md', '.json', '.csv'],
  max_file_size: 10 * 1024 * 1024,
  max_characters: 5000,
})



const recentDocuments = computed(() => documents.value.slice(0, 5))

const activeAgents = computed(() => props.agents.filter((agent) => Boolean(agent.is_active)))

onMounted(async () => {
  await Promise.all([loadPlatformSettings(), loadDeletedBots(), loadDocumentList(), loadDocConfig()])
})

onActivated(async () => {
  await Promise.all([loadPlatformSettings(), loadDeletedBots(), loadDocumentList(), loadDocConfig()])
})

async function loadDeletedBots() {
  loadingDeletedBots.value = true
  try {
    const res = await getBots({ include_deleted: true })
    deletedBots.value = (res.bots || [])
      .filter((bot) => bot.bot_deleted)
      .map((bot) => ({ ...bot, _selected: false }))
  } catch (error) {
    console.error('加载已删除 Bot 失败:', error)
  } finally {
    loadingDeletedBots.value = false
  }
}

async function restoreSelectedBots() {
  if (!selectedDeletedBotKeys.value.length) return
  try {
    await ElMessageBox.confirm(
      `确定要恢复选中的 ${selectedDeletedBotKeys.value.length} 个 Bot 吗？恢复后 Bot 将重新出现在配置页面，但已归档的会话状态不会改变。`,
      '确认恢复',
      { confirmButtonText: '确认恢复', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  restoringBots.value = true
  try {
    await restoreDeletedBots(selectedDeletedBotKeys.value)
    ElMessage.success('Bot 已恢复')
    await loadDeletedBots()
    await refreshAll()
  } catch (error) {
    ElMessage.error(String(error))
  } finally {
    restoringBots.value = false
  }
}

async function loadPlatformSettings() {
    loadingSettings.value = true
    try {
        const res = await getPlatformSettings()
        const settings = res.settings || {}
        platformSettings.value = {
            // 基础配置
            context_length_limit: Number.isInteger(Number(settings.context_length_limit))
                ? Number(settings.context_length_limit)
                : null,
            platform_agent_provider: settings.platform_agent_provider ?? '',
            platform_agent_timeout_seconds: Number.isInteger(Number(settings.platform_agent_timeout_seconds))
                ? Number(settings.platform_agent_timeout_seconds)
                : null,
            platform_agent_max_iterations: Number.isInteger(Number(settings.platform_agent_max_iterations))
                ? Number(settings.platform_agent_max_iterations)
                : null,
            document_max_characters: Number.isInteger(Number(settings.document_max_characters))
                ? Number(settings.document_max_characters)
                : 5000,
            memory_update_max_pairs: Number.isInteger(Number(settings.memory_update_max_pairs))
                ? Number(settings.memory_update_max_pairs)
                : 100,
            memory_update_max_chars: Number.isInteger(Number(settings.memory_update_max_chars))
                ? Number(settings.memory_update_max_chars)
                : 15000,
            thread_pool_max_workers: Number.isInteger(Number(settings.thread_pool_max_workers))
                ? Number(settings.thread_pool_max_workers)
                : null,
            attachment_reply: !!settings.attachment_reply,
            guest_account_enabled: !!settings.guest_account_enabled,
            feedback_alert_enabled: !!settings.feedback_alert_enabled,
            feedback_alert_threshold: Number.isInteger(Number(settings.feedback_alert_threshold))
                ? Number(settings.feedback_alert_threshold)
                : 3,
            feedback_alert_window_minutes: Number.isInteger(Number(settings.feedback_alert_window_minutes))
                ? Number(settings.feedback_alert_window_minutes)
                : 60,
            feedback_alert_cooldown_minutes: Number.isInteger(Number(settings.feedback_alert_cooldown_minutes))
                ? Number(settings.feedback_alert_cooldown_minutes)
                : 30,
            logging_level: settings.logging_level || 'INFO',
            // Agent 输出控制
            agent_max_reasoning_chars: Number.isInteger(Number(settings.agent_max_reasoning_chars))
                ? Number(settings.agent_max_reasoning_chars)
                : null,
            agent_max_output_chars: Number.isInteger(Number(settings.agent_max_output_chars))
                ? Number(settings.agent_max_output_chars)
                : null,
            agent_max_stream_chunks: Number.isInteger(Number(settings.agent_max_stream_chunks))
                ? Number(settings.agent_max_stream_chunks)
                : null,
            agent_truncation_notice: settings.agent_truncation_notice ?? '',
            agent_reply_notice: settings.agent_reply_notice ?? '',
            agent_fallback_text: settings.agent_fallback_text ?? '',
            // Skills 配置
            skills_max_script_output_chars: Number.isInteger(Number(settings.skills_max_script_output_chars))
                ? Number(settings.skills_max_script_output_chars)
                : null,
            agent_compression_transcript_max_chars: Number.isInteger(Number(settings.agent_compression_transcript_max_chars))
                ? Number(settings.agent_compression_transcript_max_chars)
                : null,
            agent_max_cache_size: Number.isInteger(Number(settings.agent_max_cache_size))
                ? Number(settings.agent_max_cache_size)
                : null,
            agent_recent_context_max_chars: Number.isInteger(Number(settings.agent_recent_context_max_chars))
                ? Number(settings.agent_recent_context_max_chars)
                : null,
            agent_recent_context_max_messages: Number.isInteger(Number(settings.agent_recent_context_max_messages))
                ? Number(settings.agent_recent_context_max_messages)
                : null,
            agent_recent_context_fetch_multiplier: Number.isInteger(Number(settings.agent_recent_context_fetch_multiplier))
                ? Number(settings.agent_recent_context_fetch_multiplier)
                : null,
            agent_context_message_max_chars: Number.isInteger(Number(settings.agent_context_message_max_chars))
                ? Number(settings.agent_context_message_max_chars)
                : null,
            agent_summary_in_prompt_max_chars: Number.isInteger(Number(settings.agent_summary_in_prompt_max_chars))
                ? Number(settings.agent_summary_in_prompt_max_chars)
                : null,
            agent_system_prompt_max_chars: Number.isInteger(Number(settings.agent_system_prompt_max_chars))
                ? Number(settings.agent_system_prompt_max_chars)
                : null,
            runtime_max_system_task_concurrency: Number.isInteger(Number(settings.runtime_max_system_task_concurrency))
                ? Number(settings.runtime_max_system_task_concurrency)
                : null,
            skills_max_tool_description_chars: Number.isInteger(Number(settings.skills_max_tool_description_chars))
                ? Number(settings.skills_max_tool_description_chars)
                : null,
            memory_query_expansion_enabled: !!settings.memory_query_expansion_enabled,
        }
    } catch (error) {
        console.error('加载系统设置失败:', error)
    } finally {
        loadingSettings.value = false
    }
}

async function savePlatformSettingsChange() {
    if (savingPlatformSettings.value) return
    if (platformSettings.value.thread_pool_max_workers == null) {
        ElMessage.error('请先设置最大并发任务量')
        return
    }
    savingPlatformSettings.value = true
    try {
        const saveData = {
            platform_agent_provider: platformSettings.value.platform_agent_provider || '',
            thread_pool_max_workers: Number(platformSettings.value.thread_pool_max_workers),
            attachment_reply: !!platformSettings.value.attachment_reply,
            guest_account_enabled: !!platformSettings.value.guest_account_enabled,
            feedback_alert_enabled: !!platformSettings.value.feedback_alert_enabled,
            memory_query_expansion_enabled: !!platformSettings.value.memory_query_expansion_enabled,
            feedback_alert_threshold: Number(platformSettings.value.feedback_alert_threshold || 3),
            feedback_alert_window_minutes: Number(platformSettings.value.feedback_alert_window_minutes || 60),
            feedback_alert_cooldown_minutes: Number(platformSettings.value.feedback_alert_cooldown_minutes || 30),
            logging_level: platformSettings.value.logging_level || 'INFO',
        }
        // 基础配置
        if (platformSettings.value.context_length_limit != null) {
            saveData.context_length_limit = Number(platformSettings.value.context_length_limit)
        }
        if (platformSettings.value.platform_agent_timeout_seconds != null) {
            saveData.platform_agent_timeout_seconds = Number(platformSettings.value.platform_agent_timeout_seconds)
        }
        if (platformSettings.value.platform_agent_max_iterations != null) {
            saveData.platform_agent_max_iterations = Number(platformSettings.value.platform_agent_max_iterations)
        }
        if (platformSettings.value.document_max_characters != null) {
            saveData.document_max_characters = Number(platformSettings.value.document_max_characters)
        }
        if (platformSettings.value.memory_update_max_pairs != null) {
            saveData.memory_update_max_pairs = Number(platformSettings.value.memory_update_max_pairs)
        }
        if (platformSettings.value.memory_update_max_chars != null) {
            saveData.memory_update_max_chars = Number(platformSettings.value.memory_update_max_chars)
        }
        // Agent 输出控制
        if (platformSettings.value.agent_max_reasoning_chars != null) {
            saveData.agent_max_reasoning_chars = Number(platformSettings.value.agent_max_reasoning_chars)
        }
        if (platformSettings.value.agent_max_output_chars != null) {
            saveData.agent_max_output_chars = Number(platformSettings.value.agent_max_output_chars)
        }
        if (platformSettings.value.agent_max_stream_chunks != null) {
            saveData.agent_max_stream_chunks = Number(platformSettings.value.agent_max_stream_chunks)
        }
        if (platformSettings.value.agent_truncation_notice) {
            saveData.agent_truncation_notice = platformSettings.value.agent_truncation_notice
        }
        if (platformSettings.value.agent_reply_notice) {
            saveData.agent_reply_notice = platformSettings.value.agent_reply_notice
        }
        if (platformSettings.value.agent_fallback_text) {
            saveData.agent_fallback_text = platformSettings.value.agent_fallback_text
        }
        if (platformSettings.value.skills_max_script_output_chars != null) {
            saveData.skills_max_script_output_chars = Number(platformSettings.value.skills_max_script_output_chars)
        }
        if (platformSettings.value.agent_compression_transcript_max_chars != null) {
            saveData.agent_compression_transcript_max_chars = Number(platformSettings.value.agent_compression_transcript_max_chars)
        }
        if (platformSettings.value.agent_max_cache_size != null) {
            saveData.agent_max_cache_size = Number(platformSettings.value.agent_max_cache_size)
        }
        if (platformSettings.value.agent_recent_context_max_chars != null) {
            saveData.agent_recent_context_max_chars = Number(platformSettings.value.agent_recent_context_max_chars)
        }
        if (platformSettings.value.agent_recent_context_max_messages != null) {
            saveData.agent_recent_context_max_messages = Number(platformSettings.value.agent_recent_context_max_messages)
        }
        if (platformSettings.value.agent_recent_context_fetch_multiplier != null) {
            saveData.agent_recent_context_fetch_multiplier = Number(platformSettings.value.agent_recent_context_fetch_multiplier)
        }
        if (platformSettings.value.agent_context_message_max_chars != null) {
            saveData.agent_context_message_max_chars = Number(platformSettings.value.agent_context_message_max_chars)
        }
        if (platformSettings.value.agent_summary_in_prompt_max_chars != null) {
            saveData.agent_summary_in_prompt_max_chars = Number(platformSettings.value.agent_summary_in_prompt_max_chars)
        }
        if (platformSettings.value.agent_system_prompt_max_chars != null) {
            saveData.agent_system_prompt_max_chars = Number(platformSettings.value.agent_system_prompt_max_chars)
        }
        if (platformSettings.value.runtime_max_system_task_concurrency != null) {
            saveData.runtime_max_system_task_concurrency = Number(platformSettings.value.runtime_max_system_task_concurrency)
        }
        if (platformSettings.value.skills_max_tool_description_chars != null) {
            saveData.skills_max_tool_description_chars = Number(platformSettings.value.skills_max_tool_description_chars)
        }
        await savePlatformSettings(saveData)
        await loadPlatformSettings()
        await loadDocConfig()
        await refreshAll()
        ElMessage.success('系统设置已保存')
    } catch (error) {
        const msg = error?.message || String(error)
        ElMessage.error(msg)
    } finally {
        savingPlatformSettings.value = false
    }
}

function openUpdateUrl() {
  window.open('https://git.dianplus.cn/shanfan/wecom-bot-agent', '_blank')
}

async function handleAttachmentReplyChange(val) {
  if (val) {
    try {
      await ElMessageBox.confirm(
        '本系统当前版本暂不支持多模态理解，开启后只针对用户提的文本问题做回复。',
        '提示',
        { confirmButtonText: '确认开启', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      platformSettings.value.attachment_reply = false
      return
    }
  }
  platformSettings.value.attachment_reply = val
}

async function loadDocumentList() {
  loadingDocuments.value = true
  try {
    const res = await getDocuments()
    documents.value = res.documents || []
  } catch (error) {
    console.error('加载文档列表失败:', error)
  } finally {
    loadingDocuments.value = false
  }
}

async function loadDocConfig() {
  try {
    const res = await getDocumentsConfig()
    if (res) {
      docConfig.value = res
    }
  } catch (error) {
    console.error('加载文档配置失败:', error)
  }
}

function openDocumentManager() {
  docManagerVisible.value = true
}

function closeDocumentManager() {
  docManagerVisible.value = false
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

async function handleFileChange(event) {
  const fileList = event.target.files
  if (!fileList || fileList.length === 0) return

  const allowedExts = docConfig.value.allowed_extensions
  const maxSize = docConfig.value.max_file_size
  const validFiles = []

  for (const file of fileList) {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!allowedExts.includes(ext)) {
      ElMessage.error(`文件 ${file.name} 类型不支持，仅支持 ${allowedExts.join('、')}`)
      event.target.value = ''
      return
    }
    if (file.size > maxSize) {
      ElMessage.error(`文件 ${file.name} 大小超过 ${maxSize / (1024 * 1024)}MB 限制`)
      event.target.value = ''
      return
    }
    validFiles.push(file)
  }

  if (validFiles.length === 0) {
    event.target.value = ''
    return
  }

  // 显示确认弹窗
  try {
    await ElMessageBox.confirm(
      '上传的文档最好不要有图片，当前版本不支持多模态记忆。确认继续上传？',
      '确认上传',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    event.target.value = ''
    return
  }

  uploadingDocuments.value = true
  try {
    await uploadDocuments(validFiles)
    ElMessage.success(`成功上传 ${validFiles.length} 个文件，请前往「任务管理」界面执行文档提取任务`)
    await loadDocumentList()
  } catch (error) {
    if (error !== 'confirm') {
      ElMessage.error(String(error))
    }
  } finally {
    uploadingDocuments.value = false
    event.target.value = ''
  }
}

async function handleDeleteDocument(doc) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档「${doc.filename}」吗？删除后不可恢复。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  deletingDocIds.value.add(doc.id)
  try {
    await deleteDocument(doc.id)
    ElMessage.success('文档已删除')
    await loadDocumentList()
  } catch (error) {
    const msg = error?.message || String(error)
    ElMessage.error(msg)
  } finally {
    deletingDocIds.value.delete(doc.id)
  }
}

async function handleDownloadDocument(doc) {
  try {
    const blob = await downloadDocumentBlob(doc.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = doc.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDocDate(dateStr) {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hour = String(date.getHours()).padStart(2, '0')
    const minute = String(date.getMinutes()).padStart(2, '0')
    return `${year}-${month}-${day} ${hour}:${minute}`
  } catch {
    return dateStr
  }
}

function formatDeletedDate(dateStr) {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  } catch {
    return dateStr
  }
}


</script>

<template>
  <section class="console-view settings-page" v-loading="loadingSettings">
    <div class="settings-plain">
      <section class="settings-section">
        <header class="settings-section__header">
          <h2>基础运行</h2>
          <p>平台 Agent、任务并发、文档和记忆更新预算。</p>
        </header>
        <div class="settings-section__body">
          <div class="settings-switch-group">
            <div class="settings-switch-card">
              <label>附件回复</label>
              <el-switch
                v-model="platformSettings.attachment_reply"
                @change="handleAttachmentReplyChange"
                size="large"
              />
            </div>
            <div class="settings-switch-card">
              <label>游客账号</label>
              <el-switch
                v-model="platformSettings.guest_account_enabled"
                size="large"
              />
            </div>
            <div class="settings-switch-card">
              <label>反馈告警</label>
              <el-switch
                v-model="platformSettings.feedback_alert_enabled"
                size="large"
              />
            </div>
            <div class="settings-switch-card">
              <label>查询扩展</label>
              <el-switch
                v-model="platformSettings.memory_query_expansion_enabled"
                size="large"
              />
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>会话上下文限制</label>
              <el-input
                v-model="platformSettings.context_length_limit"
                readonly
                placeholder="当前配置由系统决定"
                size="large"
              />
            </div>
            <div class="settings-field settings-field--flex">
              <label>平台 Agent</label>
              <el-select
                v-model="platformSettings.platform_agent_provider"
                placeholder="选择平台 Agent"
                size="large"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="agent in activeAgents"
                  :key="agent.provider_key"
                  :label="agent.label || agent.provider_name || agent.provider_key"
                  :value="agent.provider_key"
                />
              </el-select>
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>最大并发任务量</label>
              <el-input-number
                v-model="platformSettings.thread_pool_max_workers"
                :min="10"
                :max="30"
                :step="1"
                style="width: 100%"
              />
            </div>
            <div class="settings-field settings-field--flex">
              <label>Agent 超时（秒）</label>
              <el-input-number
                v-model="platformSettings.platform_agent_timeout_seconds"
                :min="10"
                :max="600"
                :step="10"
                style="width: 100%"
              />
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>最大迭代次数</label>
              <el-input-number
                v-model="platformSettings.platform_agent_max_iterations"
                :min="1"
                :max="50"
                :step="1"
                style="width: 100%"
              />
              <div class="settings-hint">Agent 单次请求最大工具调用轮数</div>
            </div>
            <div class="settings-field settings-field--flex">
              <label>日志级别</label>
              <el-select
                v-model="platformSettings.logging_level"
                placeholder="选择日志级别"
                size="large"
                style="width: 100%"
              >
                <el-option label="INFO" value="INFO" />
                <el-option label="WARNING" value="WARNING" />
                <el-option label="ERROR" value="ERROR" />
              </el-select>
              <div class="settings-hint">设置为 WARNING 或 ERROR 可以减少控制台日志输出</div>
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>文档最大字符数</label>
              <el-input-number
                v-model="platformSettings.document_max_characters"
                :min="500"
                :max="500000"
                :step="500"
                style="width: 100%"
              />
              <div class="settings-hint">文档上传后的可提取文本字符上限，前后端提示会按此值同步。</div>
            </div>
            <div class="settings-field settings-field--flex">
              <label>记忆更新最大问答对</label>
              <el-input-number
                v-model="platformSettings.memory_update_max_pairs"
                :min="1"
                :max="5000"
                :step="10"
                style="width: 100%"
              />
              <div class="settings-hint">单次 memory_update 最多进入提炼的问答对数量。</div>
            </div>
          </div>

          <div class="settings-row-inline settings-row-inline--compact">
            <div class="settings-field settings-field--flex">
              <label>无用反馈阈值</label>
              <el-input-number
                v-model="platformSettings.feedback_alert_threshold"
                :min="1"
                :max="20"
                :step="1"
                style="width: 100%"
              />
            </div>
            <div class="settings-field settings-field--flex">
              <label>告警窗口（分钟）</label>
              <el-input-number
                v-model="platformSettings.feedback_alert_window_minutes"
                :min="1"
                :max="1440"
                :step="5"
                style="width: 100%"
              />
            </div>
            <div class="settings-field settings-field--flex">
              <label>告警冷却（分钟）</label>
              <el-input-number
                v-model="platformSettings.feedback_alert_cooldown_minutes"
                :min="1"
                :max="1440"
                :step="5"
                style="width: 100%"
              />
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>记忆更新最大字符数</label>
              <el-input-number
                v-model="platformSettings.memory_update_max_chars"
                :min="1000"
                :max="500000"
                :step="1000"
                style="width: 100%"
              />
              <div class="settings-hint">单次 memory_update 送入 memory-creator 的近似字符预算。</div>
            </div>
            <div class="settings-field settings-field--flex">
              <label>说明</label>
              <el-input
                model-value="超限时会暂停自动记忆更新，并提醒到任务管理人工处理下一批。"
                readonly
                type="textarea"
                :rows="3"
              />
            </div>
          </div>

          <div class="settings-submit-row">
            <el-button
              type="primary"
              size="large"
              class="settings-submit-button"
              :loading="savingPlatformSettings"
              @click="savePlatformSettingsChange"
            >
              保存系统设置
            </el-button>
          </div>
        </div>
      </section>

      <section class="settings-section">
        <header class="settings-section__header">
          <h2>Agent 与工具限制</h2>
          <p>控制上下文、输出截断、MCP、Skills 和后台系统任务。</p>
        </header>
        <div class="settings-section__body">
            <!-- Agent 上下文相关配置 -->
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>压缩转录最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_compression_transcript_max_chars"
                        :min="1000"
                        :max="50000"
                        :step="500"
                        style="width: 100%"
                    />
                    <div class="settings-hint">历史对话压缩时输入转录文本的最大字符数</div>
                </div>
            </div>
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>Agent 最大缓存数量</label>
                    <el-input-number
                        v-model="platformSettings.agent_max_cache_size"
                        :min="1"
                        :max="100"
                        :step="1"
                        style="width: 100%"
                    />
                    <div class="settings-hint">Agent 内部记忆和工具调用的缓存条目上限</div>
                </div>
                <div class="settings-field settings-field--flex">
                    <label>最近对话最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_recent_context_max_chars"
                        :min="500"
                        :max="50000"
                        :step="100"
                        style="width: 100%"
                    />
                    <div class="settings-hint">不经过压缩的最近对话上下文总字符上限</div>
                </div>
            </div>
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>最近对话最大消息数</label>
                    <el-input-number
                        v-model="platformSettings.agent_recent_context_max_messages"
                        :min="1"
                        :max="100"
                        :step="1"
                        style="width: 100%"
                    />
                    <div class="settings-hint">不经过压缩保留的最近对话消息条数</div>
                </div>
                <div class="settings-field settings-field--flex">
                    <label>历史消息获取倍率</label>
                    <el-input-number
                        v-model="platformSettings.agent_recent_context_fetch_multiplier"
                        :min="1"
                        :max="10"
                        :step="1"
                        style="width: 100%"
                    />
                    <div class="settings-hint">从数据库读取历史消息时的倍率因子，用于最终筛选前的初步获取</div>
                </div>
            </div>
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>单条消息最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_context_message_max_chars"
                        :min="100"
                        :max="10000"
                        :step="100"
                        style="width: 100%"
                    />
                    <div class="settings-hint">上下文中单条消息超过此值会被截断</div>
                </div>
                <div class="settings-field settings-field--flex">
                    <label>提示词中摘要字符限制</label>
                    <el-input-number
                        v-model="platformSettings.agent_summary_in_prompt_max_chars"
                        :min="100"
                        :max="10000"
                        :step="100"
                        style="width: 100%"
                    />
                    <div class="settings-hint">放入提示词中的历史摘要部分的最大字符数</div>
                </div>
            </div>
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>系统提示词最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_system_prompt_max_chars"
                        :min="100"
                        :max="100000"
                        :step="1000"
                        style="width: 100%"
                    />
                    <div class="settings-hint">系统提示词（system prompt）的字符数上限</div>
                </div>
            </div>
            <!-- Agent 输出控制 -->
            <div class="settings-row-inline">
                <div class="settings-field settings-field--flex">
                    <label>推理链最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_max_reasoning_chars"
                        :min="100"
                        :max="100000"
                        :step="1000"
                        style="width: 100%"
                    />
                    <div class="settings-hint">Agent 推理过程（思考链）的字符数上限，同时用于推导模型最大输出 token 数（÷2）</div>
                </div>
                <div class="settings-field settings-field--flex">
                    <label>AI 回复最大字符数</label>
                    <el-input-number
                        v-model="platformSettings.agent_max_output_chars"
                        :min="100"
                        :max="50000"
                        :step="500"
                        style="width: 100%"
                    />
                    <div class="settings-hint">Agent 最终给用户回复的字符数上限</div>
                </div>
            </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>流式输出最大分块数</label>
              <el-input-number
                v-model="platformSettings.agent_max_stream_chunks"
                :min="10"
                :max="5000"
                :step="100"
                style="width: 100%"
              />
              <div class="settings-hint">流式输出时分块的数量上限，超出将停止输出</div>
            </div>
            <div class="settings-field settings-field--flex">
              <label>内容截断提示</label>
              <el-input
                v-model="platformSettings.agent_truncation_notice"
                placeholder="例如: [内容已截断]"
              />
              <div class="settings-hint">当输出或上下文内容被截断时，末尾追加的提示文本</div>
            </div>
          </div>

          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>技能脚本输出上限</label>
              <el-input-number
                v-model="platformSettings.skills_max_script_output_chars"
                :min="100"
                :max="20000"
                :step="500"
                style="width: 100%"
              />
              <div class="settings-hint">Skill 脚本执行时控制台输出的字符数上限</div>
            </div>
            <div class="settings-field settings-field--flex">
              <label>回复追加提示</label>
              <el-input
                v-model="platformSettings.agent_reply_notice"
                readonly
                placeholder="当前配置由系统决定"
                type="textarea"
                :rows="2"
              />
              <div class="settings-hint">每条 AI 回复末尾自动追加的提示文本（当前为只读，由系统管理）</div>
            </div>
          </div>

          <div class="settings-field">
            <label>异常时降级回复</label>
            <el-input
              v-model="platformSettings.agent_fallback_text"
              placeholder="例如: 抱歉，我暂时无法回答您的问题"
              type="textarea"
              :rows="2"
            />
            <div class="settings-hint">Agent 发生严重异常无法正常回复时，返回给用户的降级文本</div>
          </div>

          <!-- 运行时配置 -->
          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>系统任务最大并发数</label>
              <el-input-number
                v-model="platformSettings.runtime_max_system_task_concurrency"
                :min="1"
                :max="100"
                :step="1"
                style="width: 100%"
              />
              <div class="settings-hint">记忆更新等系统级后台任务同时执行的数量上限</div>
            </div>
          </div>

          <!-- Skills 配置 -->
          <div class="settings-row-inline">
            <div class="settings-field settings-field--flex">
              <label>工具描述文本上限</label>
              <el-input-number
                v-model="platformSettings.skills_max_tool_description_chars"
                :min="100"
                :max="50000"
                :step="100"
                style="width: 100%"
              />
              <div class="settings-hint">Skills 中工具（Tool）描述文本的字符数上限</div>
            </div>
          </div>

          <div class="settings-submit-row">
            <el-button
              type="primary"
              size="large"
              class="settings-submit-button"
              :loading="savingPlatformSettings"
              @click="savePlatformSettingsChange"
            >
              保存Agent设置
            </el-button>
          </div>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-row settings-row--stack">
          <div class="settings-row__header">
            <div class="settings-row__content">
              <strong>文档管理</strong>
              <p>展示最近上传的文档，点击管理可上传、下载和删除。</p>
            </div>
            <el-button plain @click="openDocumentManager">管理</el-button>
          </div>
          <div class="document-list" v-loading="loadingDocuments">
            <div v-if="recentDocuments.length === 0" class="empty-inline">暂无上传文档</div>
            <div v-for="doc in recentDocuments" :key="doc.id" class="document-item">
              <span class="document-name">{{ doc.filename }}</span>
              <small class="document-time">{{ formatDocDate(doc.created_at) }}</small>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-section">
        <header class="settings-section__header">
          <h2>恢复已删除的 Bot</h2>
          <p>此处显示所有已逻辑删除的 Bot，恢复后 Bot 将重新出现在配置页面，但已归档的会话状态不会改变。</p>
        </header>
        <div class="settings-section__body" v-loading="loadingDeletedBots">
          <div v-if="deletedBots.length === 0" class="empty-inline">暂无已删除的 Bot</div>
          <div v-else class="deleted-bot-list">
            <div v-for="bot in deletedBots" :key="bot.bot_key" class="deleted-bot-item">
              <el-checkbox v-model="bot._selected" />
              <span class="deleted-bot-name">{{ bot.name }}</span>
              <span class="deleted-bot-time">删除于 {{ formatDeletedDate(bot.deleted_at) }}</span>
            </div>
            <div class="settings-submit-row">
              <el-button
                type="primary"
                :loading="restoringBots"
                :disabled="!selectedDeletedBotKeys.length"
                @click="restoreSelectedBots"
              >
                恢复选中 ({{ selectedDeletedBotKeys.length }})
              </el-button>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-row">
          <div class="settings-row__content">
            <strong>获取更新</strong>
          </div>
          <el-button plain @click="openUpdateUrl">
            获取更新
          </el-button>
        </div>
      </section>
    </div>

    <el-dialog
      v-model="docManagerVisible"
      title="文档管理"
      width="680px"
      :close-on-click-modal="false"
      @close="closeDocumentManager"
    >
      <div class="doc-manager">
        <div class="doc-manager__toolbar">
          <el-button type="primary" :loading="uploadingDocuments" @click="triggerFileInput">
            上传文件
          </el-button>
          <input
            ref="fileInputRef"
            type="file"
            multiple
            :accept="docConfig.allowed_extensions.join(',')"
            style="display: none"
            @change="handleFileChange"
          />
          <span class="doc-manager__hint">支持 {{ docConfig.allowed_extensions.join('、') }}，单个文件最大 {{ (docConfig.max_file_size / (1024 * 1024)).toFixed(0) }}MB，字符数不超过 {{ docConfig.max_characters }}</span>
        </div>

        <div class="doc-manager__list" v-loading="loadingDocuments">
          <div v-if="documents.length === 0" class="empty-inline">暂无上传文档</div>
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="doc-manager__item"
          >
            <div class="doc-manager__item-info">
              <span class="doc-manager__item-name">{{ doc.filename }}</span>
              <span class="doc-manager__item-meta">
                {{ formatFileSize(doc.file_size) }} · {{ formatDocDate(doc.created_at) }}
              </span>
            </div>
            <div class="doc-manager__item-actions">
              <el-button link type="primary" @click="handleDownloadDocument(doc)">下载</el-button>
              <el-button
                link
                type="danger"
                :loading="deletingDocIds.has(doc.id)"
                @click="handleDeleteDocument(doc)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>


  </section>
</template>
