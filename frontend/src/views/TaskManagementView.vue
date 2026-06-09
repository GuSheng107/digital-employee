<script setup>
import { onActivated, onBeforeUnmount, onMounted, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import {
  getTasks,
  getTaskExecutors,
  getTaskDetail,
  enableTask,
  disableTask,
  updateTask,
  deleteTask,
  createTask,
  triggerTask,
} from '../api/runtime'
import { getSkills, getMcpServers } from '../api/skills'
import { formatTime as formatTimeFromUtils } from '../utils/format'

const filters = ref({
  keyword: '',
  scope: '',
  status: '',
  taskType: '',
})

const tasks = ref([])
const loading = ref(false)
const triggerLoadingTaskKey = ref('')
let triggerPollSeq = 0
const executors = ref({ bots: [], agents: [] })
const loadingExecutors = ref(false)
const skills = ref([])
const mcpServers = ref([])
const loadingSkills = ref(false)
const loadingMcpServers = ref(false)

// 本地临时存储 bot_task 相关数据，用于对话框
const botTaskData = ref({
  user_prompt: '',
  skill_names: [],
  mcp_server_ids: []
})

const pagination = ref({
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 1,
})

const dialogVisible = ref(false)
const dialogMode = ref('view')
const dialogSaving = ref(false)
const dialogForm = ref({})

// 记忆更新预览数据
const memoryUpdatePreview = ref(null)
const memoryUpdateChats = ref(null)
const skippedAiMessageIds = ref({})
const originalMemoryUpdatePrompt = ref('')
const memoryUpdateEdited = ref(false)
const showJsonEdit = ref(false)
const documentPreview = ref(null)
const documentEditContentRef = ref('')
const reviewMode = ref('review')
const reviewPrompt = ref('')
const reviewSuggestion = ref('')
const reviewModeConfig = ref(null)

const dialogTitle = computed(() => {
  if (dialogMode.value === 'create') return '新建任务'
  if (dialogMode.value === 'edit') return '编辑任务'
  return '任务详情'
})

const taskTableLoading = computed(() => loading.value || Boolean(triggerLoadingTaskKey.value))

const documentContentText = computed(() => {
  if (dialogForm.value.handler_name !== 'document_memory_extraction') return ''
  try {
    const data = JSON.parse(dialogForm.value.prompt_text || '{}')
    return data.content || dialogForm.value.prompt_text || ''
  } catch {
    return dialogForm.value.prompt_text || ''
  }
})

const documentEditContent = computed({
  get() {
    if (documentPreview.value && documentPreview.value.content) {
      return documentPreview.value.content
    }
    return documentContentText.value || ''
  },
  set(val) {
    if (documentPreview.value) {
      documentPreview.value.content = val
    }
    try {
      const data = JSON.parse(dialogForm.value.prompt_text || '{}')
      data.content = val
      dialogForm.value.prompt_text = JSON.stringify(data, null, 2)
    } catch {
      dialogForm.value.prompt_text = val
    }
  }
})

const isPeriodicType = computed(() => dialogForm.value.task_type === 'periodic')

function isReviewHandlerName(handlerName) {
  return handlerName === 'self_review_chat_memory' || handlerName === 'self_review_document_memory'
}

const statusFilterOptions = computed(() => {
  const all = [
    { label: '启用中', value: 'active' },
    { label: '执行中', value: 'running' },
    { label: '待执行', value: 'pending' },
    { label: '已暂停', value: 'paused' },
    { label: '已完成', value: 'completed' },
    { label: '失败', value: 'failed' },
  ]
  if (filters.value.taskType === 'periodic') {
    return all.filter(o => !['pending', 'completed'].includes(o.value))
  }
  if (filters.value.taskType === 'one_time') {
    return all.filter(o => !['active', 'paused'].includes(o.value))
  }
  return all
})

function scopeLabel(scope) {
  return { system: '系统级', user: '用户级' }[scope] || scope || '-'
}

function executorLabel(kind) {
  return { builtin: '内置执行器', bot: 'Bot', platform_agent: '平台 Agent' }[kind] || kind || '-'
}

function getExecutorName(task) {
  if (task.executor_kind === 'bot' && task.executor_id) {
    const bot = executors.value.bots.find(b => b.id === task.executor_id)
    return bot ? bot.name : executorLabel('bot')
  } else if (task.executor_kind === 'platform_agent' && task.executor_id) {
    const agent = executors.value.agents.find(a => a.id === task.executor_id)
    return agent ? agent.name : executorLabel('platform_agent')
  }
  return executorLabel(task.executor_kind)
}

function getMcpServerValue(server) {
  return server?.id || server?.server_id || server?.name || ''
}

function getMcpServerName(serverId) {
  const normalizedId = String(serverId || '')
  const server = mcpServers.value.find(item => {
    return [item.id, item.server_id, item.name].some(value => String(value || '') === normalizedId)
  })
  if (!server && Array.isArray(botTaskData.value.mcp_servers)) {
    const taskServer = botTaskData.value.mcp_servers.find(item => {
      return [item.id, item.server_id, item.name].some(value => String(value || '') === normalizedId)
    })
    if (taskServer) {
      return taskServer.name || taskServer.server_name || normalizedId || '-'
    }
  }
  return server?.name || server?.server_name || normalizedId || '-'
}

function isAiWorkTask(task) {
  return task?.task_type === 'one_time' && ['smart_reply', 'ai_draft'].includes(String(task?.task_key || ''))
}

function getTaskRequestId(task) {
  if (isAiWorkTask(task)) {
    return task?.task_id || task?.trace_id || task?.task_key
  }
  return task?.task_key
}
function getStatusTagType(status) {
  return {
    active: 'success', running: 'warning', pending: 'info', paused: 'info',
    completed: 'success', failed: 'danger', busy: 'warning',
    queued: 'info', cancel_requested: 'warning', cancelled: 'info',
  }[status] || 'info'
}

function getStatusLabel(status) {
  return {
    active: '启用中', running: '执行中', pending: '待执行', paused: '已暂停',
    completed: '已完成', failed: '失败', busy: '忙线',
    queued: '排队中', cancel_requested: '取消中', cancelled: '已取消',
  }[status] || status || '-'
}

function summarizePrompt(prompt, task = null) {
  const text = String(prompt || '').trim()
  if (task?.handler_name === 'memory_update') {
    const state = parseMemoryUpdatePromptState(text)
    return state === 'edited' ? '已编辑对话' : '全会话'
  }
  if (task?.handler_name === 'self_review_chat_memory' || task?.handler_name === 'self_review_document_memory') {
    const modeLabel = { review: '仅审查', dry_run: '预览补丁', patch: '自动修复' }
    try {
      const data = JSON.parse(text)
      if (data && typeof data === 'object' && data.review_mode) {
        return modeLabel[data.review_mode] || data.review_mode
      }
    } catch {}
    return '-'
  }
  if (!text) return '-'
  try {
    const data = JSON.parse(text)
    if (data.filename) return data.filename
    if (data.doc_id) return `文档: ${data.doc_id.slice(0, 8)}...`
  } catch {}
  return text.length > 48 ? `${text.slice(0, 48)}...` : text
}

function getPromptLabel(task) {
  if (task.handler_name === 'memory_update') return '用户会话'
  if (task.handler_name === 'document_memory_extraction') return '文档内容'
  if (task.handler_name === 'self_review_chat_memory') return '聊天记忆'
  if (task.handler_name === 'self_review_document_memory') return '文档记忆'
  return '提示词'
}

function resultText(task) {
  const text = task.error || task.result_text || task.last_run_message || '-'
  return String(text).replace(/^\[memory_update_manual_review\]\s*/, '')
}

function isSystemTask(task) { return task.task_scope === 'system' }
function isSystemHandlerTask(task) { 
  return task.handler_name === 'memory_update' || 
         task.handler_name === 'document_memory_extraction' ||
         task.handler_name === 'self_review_chat_memory' ||
         task.handler_name === 'self_review_document_memory'
}
function isFixedInfoTask(task) {
  return task.handler_name === 'memory_update' || task.handler_name === 'document_memory_extraction' ||
         task.handler_name === 'self_review_chat_memory' || task.handler_name === 'self_review_document_memory'
}
function getNotifyBotName(botKey) {
  if (!botKey) return '-'
  const bot = executors.value.bots.find(b => b.id === botKey)
  return bot ? bot.name : botKey
}
const isNotifyBotSupported = computed(() => {
  const h = dialogForm.value.handler_name
  return h === 'memory_update' || h === 'document_memory_extraction' ||
         h === 'self_review_chat_memory' || h === 'self_review_document_memory'
})
function isPeriodicTask(task) { return task.task_type === 'periodic' }
function isTaskEnabled(task) { return task.is_enabled }
function isTriggerLoading(task) {
  return Boolean(task?.task_key) && triggerLoadingTaskKey.value === task.task_key
}

function shouldWaitForRunning(task) {
  return isPeriodicTask(task)
}

function shouldPollAfterEnable(task, enabledAt) {
  const nextRunAt = Date.parse(task?.next_run_at || '')
  return Number.isFinite(nextRunAt) && nextRunAt <= enabledAt
}

function canEnable(task) {
  if (
    task.handler_name === 'memory_update' &&
    String(task.last_run_message || '').startsWith('[memory_update_manual_review]')
  ) {
    return false
  }
  return isPeriodicTask(task) && !isTaskEnabled(task)
}

function canDisable(task) {
  return isPeriodicTask(task) && isTaskEnabled(task) && task.status !== 'running'
}

function canEdit(task) {
  if (task.status === 'running' || task.run_state === 'running') return false
  if (task.handler_name === 'memory_update') return true
  if (task.handler_name === 'document_memory_extraction') {
    return task.status !== 'completed'
  }
  if (task.handler_name === 'self_review_chat_memory') return true
  if (task.handler_name === 'self_review_document_memory') return true
  // 其他系统任务不允许编辑
  if (isSystemTask(task)) return false
  if (isPeriodicTask(task) && isTaskEnabled(task)) return false
  // 已成功的一次性任务不允许编辑
  if (!isPeriodicTask(task) && task.status === 'completed') return false
  // 执行中的任务不允许编辑
  if (task.status === 'running' || task.run_state === 'running') return false
  return true
}

function canTrigger(task) {
  if (triggerLoadingTaskKey.value && triggerLoadingTaskKey.value !== task.task_key) return false
  if (task.handler_name === 'database_cleanup') return false
  if (
    task.handler_name === 'document_memory_extraction' &&
    String(task.document_convert_status || task.convert_status || '').trim() === 'converted'
  ) {
    return false
  }
  if (isPeriodicTask(task)) {
    return task.status !== 'running' && (isTaskEnabled(task) || task.status === 'failed')
  }
  return task.status === 'pending' || task.status === 'failed'
}

function canRetry(task) {
  return task.status === 'failed' && canTrigger(task)
}

const PROTECTED_HANDLERS = ['memory_update', 'self_review_chat_memory', 'self_review_document_memory', 'database_cleanup']

function canDelete(task) {
  if (PROTECTED_HANDLERS.includes(task.handler_name)) return false
  if (task.status === 'running') return false
  if (isPeriodicTask(task) && isTaskEnabled(task)) return false
  return true
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  try {
    const date = new Date(timeStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return timeStr
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function mergeTaskInList(updatedTask) {
  if (!updatedTask?.task_key) return
  const idx = tasks.value.findIndex(t => t.task_key === updatedTask.task_key)
  if (idx >= 0) {
    tasks.value.splice(idx, 1, { ...tasks.value[idx], ...updatedTask })
  }
  if (dialogVisible.value && dialogForm.value?.task_key === updatedTask.task_key) {
    dialogForm.value = { ...dialogForm.value, ...updatedTask }
  }
}

function hasNewRunResult(task, baselineTask) {
  if (!baselineTask) return true
  const currentLastRunAt = String(task?.last_run_at || '')
  const previousLastRunAt = String(baselineTask?.last_run_at || '')
  return currentLastRunAt && currentLastRunAt !== previousLastRunAt
}

async function pollTaskUntilRunning(taskKey, baselineTask = null) {
  const pollId = ++triggerPollSeq
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await sleep(attempt === 0 ? 500 : 1000)
    if (pollId !== triggerPollSeq) return { state: 'cancelled', task: null }
    const result = await getTaskDetail(taskKey)
    const task = result.task || {}
    mergeTaskInList(task)
    if (task.status === 'running' || task.run_state === 'running') {
      return { state: 'running', task }
    }
    if (['completed', 'failed'].includes(task.status) && hasNewRunResult(task, baselineTask)) {
      return { state: task.status, task }
    }
  }
  return { state: 'timeout', task: null }
}

async function triggerAndRefresh(task, successMessage) {
  const waitForRunning = shouldWaitForRunning(task)
  if (waitForRunning) {
    triggerLoadingTaskKey.value = task.task_key
  }
  try {
    const triggerResult = await triggerTask(task.task_key)
    const triggeredTask = triggerResult?.task || null
    if (triggeredTask) {
      mergeTaskInList(triggeredTask)
    }
    if (triggerResult?.ok === false) {
      ElMessage.error(triggerResult?.summary || triggeredTask?.last_run_message || '任务执行失败')
      return
    }
    ElMessage.success(successMessage)
    if (dialogVisible.value && dialogForm.value?.task_key === task.task_key) {
      dialogVisible.value = false
    }
    if (waitForRunning) {
      const pollResult = await pollTaskUntilRunning(task.task_key, task)
      if (pollResult.state === 'running') {
        ElMessage.success('任务已进入执行中')
      } else if (pollResult.state === 'failed') {
        ElMessage.error(pollResult.task?.last_run_message || '任务执行失败')
      }
    }
  } catch (error) {
    ElMessage.error(error?.message || '触发任务失败')
  } finally {
    await loadTasks()
    if (waitForRunning && triggerLoadingTaskKey.value === task.task_key) {
      triggerLoadingTaskKey.value = ''
    }
  }
}

async function loadTasks() {
  loading.value = true
  try {
    const result = await getTasks({
      keyword: filters.value.keyword,
      scope: filters.value.scope,
      status: filters.value.status,
      task_type: filters.value.taskType,
      page: pagination.value.page,
      page_size: pagination.value.page_size,
    })
    tasks.value = result.tasks || []
    pagination.value.total = result.total || 0
    pagination.value.total_pages = result.total_pages || 1
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loading.value = false
  }
}

async function loadExecutors() {
  loadingExecutors.value = true
  try {
    const result = await getTaskExecutors()
    executors.value = {
      bots: result.bots || [],
      agents: result.agents || [],
    }
  } catch (error) {
    console.error('Failed to load executors:', error)
  } finally {
    loadingExecutors.value = false
  }
}

async function loadSkills() {
  loadingSkills.value = true
  try {
    const result = await getSkills()
    const allSkills = result.skills || result || []
    // 过滤掉系统级 skill
    skills.value = allSkills.filter(skill => {
      return skill.scope !== 'system'
    })
  } catch (error) {
    console.error('Failed to load skills:', error)
  } finally {
    loadingSkills.value = false
  }
}

async function loadMcpServers() {
  loadingMcpServers.value = true
  try {
    const result = await getMcpServers()
    const allServers = result.servers || result || []
    // 过滤掉系统级 MCP 服务器
    mcpServers.value = allServers.filter(server => {
      const name = server.name || server.id || ''
      return !name.startsWith('system_') && !name.startsWith('_') && !name.includes('internal')
    })
  } catch (error) {
    console.error('Failed to load MCP servers:', error)
  } finally {
    loadingMcpServers.value = false
  }
}

function handleSearch() {
  pagination.value.page = 1
  loadTasks()
}

function handlePageChange(page) {
  pagination.value.page = page
  loadTasks()
}

function handleSizeChange(size) {
  pagination.value.page_size = size
  pagination.value.page = 1
  loadTasks()
}

async function openDialog(mode, task) {
  dialogMode.value = mode
  dialogForm.value = { ...task }
  memoryUpdatePreview.value = null
  memoryUpdateChats.value = null
  skippedAiMessageIds.value = {}
  originalMemoryUpdatePrompt.value = ''
  memoryUpdateEdited.value = false
  showJsonEdit.value = false
  documentPreview.value = null
  documentEditContentRef.value = ''
  reviewMode.value = 'review'
  reviewPrompt.value = ''
  reviewSuggestion.value = ''
  reviewModeConfig.value = null
  
  // 解析 bot_task 数据
  if (task.executor_kind === 'bot' && task.prompt_text) {
    botTaskData.value = parseBotTaskPrompt(task.prompt_text)
    if (Array.isArray(task.mcp_servers)) {
      botTaskData.value.mcp_servers = task.mcp_servers
    }
    if (Array.isArray(task.mcp_server_names)) {
      botTaskData.value.mcp_server_names = task.mcp_server_names
    }
  } else {
    botTaskData.value = {
      user_prompt: '',
      skill_names: [],
      mcp_server_ids: [],
      mcp_servers: [],
      mcp_server_names: []
    }
  }
  
  const taskDetailId = getTaskRequestId(task)
  if (task.executor_kind === 'bot' && taskDetailId) {
    try {
      const result = await getTaskDetail(taskDetailId)
      if (result.task) {
        dialogForm.value = { ...dialogForm.value, ...result.task }
        botTaskData.value = parseBotTaskPrompt(result.task.prompt_text)
        botTaskData.value.mcp_servers = Array.isArray(result.task.mcp_servers) ? result.task.mcp_servers : []
        botTaskData.value.mcp_server_names = Array.isArray(result.task.mcp_server_names) ? result.task.mcp_server_names : []
      }
    } catch (error) {
      console.error('Failed to load bot task detail:', error)
    }
  }

  if (task.handler_name === 'memory_update') {
    try {
      const result = await getTaskDetail(task.task_key)
      if (result.memory_update_preview) {
        memoryUpdatePreview.value = result.memory_update_preview
        
        if (result.task && result.task.prompt_text) {
          dialogForm.value.prompt_text = formatJson(result.task.prompt_text)
          originalMemoryUpdatePrompt.value = dialogForm.value.prompt_text
          initChatsFromJson()
        } else if (!task.prompt_text || task.prompt_text === '' || result.memory_update_preview.auto_generated) {
          resetMemoryUpdatePrompt()
        } else {
          const formatted = formatJson(task.prompt_text)
          originalMemoryUpdatePrompt.value = formatted
          dialogForm.value.prompt_text = formatted
          initChatsFromJson()
        }
      }
    } catch (error) {
      console.error('Failed to load memory update preview:', error)
    }
  } else if (task.handler_name === 'document_memory_extraction') {
    try {
      const result = await getTaskDetail(task.task_key)
      if (result.document_preview) {
        documentPreview.value = result.document_preview
        dialogForm.value.document_convert_status = result.document_preview.convert_status || ''
        documentEditContentRef.value = result.document_preview.content || ''
      }
      if (result.task && result.task.prompt_text) {
        dialogForm.value.prompt_text = formatJson(result.task.prompt_text)
        if (!documentEditContentRef.value) {
          try {
            const data = JSON.parse(result.task.prompt_text)
            documentEditContentRef.value = data.content || ''
          } catch {}
        }
      } else if (task.prompt_text) {
        dialogForm.value.prompt_text = formatJson(task.prompt_text)
        if (!documentEditContentRef.value) {
          try {
            const data = JSON.parse(task.prompt_text)
            documentEditContentRef.value = data.content || ''
          } catch {}
        }
      }
    } catch (error) {
      console.error('Failed to load document preview:', error)
      if (task.prompt_text) {
        dialogForm.value.prompt_text = formatJson(task.prompt_text)
        try {
          const data = JSON.parse(task.prompt_text)
          documentEditContentRef.value = data.content || ''
        } catch {}
      }
    }
  } else if (isReviewHandlerName(task.handler_name)) {
    try {
      const result = await getTaskDetail(task.task_key)
      const rawPrompt = result.task?.prompt_text || task.prompt_text || ''
      if (result.task) {
        dialogForm.value = { ...dialogForm.value, ...result.task }
      }
      if (result.review_mode_config) {
        reviewModeConfig.value = result.review_mode_config
      }
      dialogForm.value.prompt_text = rawPrompt
      parseReviewPromptText(rawPrompt)
    } catch (error) {
      console.error('Failed to load memory content:', error)
      if (task.prompt_text) {
        dialogForm.value.prompt_text = task.prompt_text
        parseReviewPromptText(task.prompt_text)
      }
    }
  }
  
  dialogVisible.value = true
}

// 获取友好的会话名称
function getChatName(chat) {
  const isGroup = chat.chat_type === 'group' || chat.chat_type === 'room'
  if (isGroup) {
    return `群聊[${chat.display_name || '未命名群聊'}]`
  } else {
    return `用户[${chat.display_name || '未命名用户'}]`
  }
}

// 从 JSON 初始化聊天数据
function initChatsFromJson() {
  try {
    const data = JSON.parse(dialogForm.value.prompt_text)
    memoryUpdateEdited.value = Boolean(data.is_user_edited)
    if (data.chats) {
      const rawChats = data.chats
      if (Array.isArray(rawChats)) {
        memoryUpdateChats.value = rawChats.map(c => normalizeChatFields(c))
      } else if (typeof rawChats === 'object') {
        memoryUpdateChats.value = Object.entries(rawChats).map(([chatId, chatData]) => {
          const mapped = normalizeChatFields(chatData)
          mapped.chat_id = chatId
          return mapped
        })
      }
    }
    skippedAiMessageIds.value = data.skipped_ai_message_ids || {}
  } catch (e) {
    console.error('Failed to parse prompt JSON:', e)
    memoryUpdateEdited.value = false
  }
}

function getModeDescription(mode) {
  if (reviewModeConfig.value?.modes?.[mode]?.description) {
    return reviewModeConfig.value.modes[mode].description
  }
  return ''
}

function getModePrompt(mode) {
  if (reviewModeConfig.value?.modes?.[mode]?.prompt) {
    return reviewModeConfig.value.modes[mode].prompt
  }
  if (reviewModeConfig.value?.default_prompt) {
    return reviewModeConfig.value.default_prompt
  }
  return ''
}

function syncReviewPromptFromMode(mode = reviewMode.value) {
  const prompt = getModePrompt(mode)
  if (prompt) {
    reviewPrompt.value = prompt
  }
  const desc = getModeDescription(mode)
  if (desc) {
    dialogForm.value.description = desc
  }
  dialogForm.value.prompt_text = buildReviewPromptText()
}

function parseReviewPromptText(raw) {
  reviewMode.value = 'review'
  reviewPrompt.value = ''
  reviewSuggestion.value = ''
  if (!raw) {
    syncReviewPromptFromMode('review')
    return
  }
  let parsedPrompt = ''
  try {
    const data = JSON.parse(raw)
    if (data && typeof data === 'object') {
      const m = String(data.review_mode || '').trim()
      if (['review', 'dry_run', 'patch'].includes(m)) {
        reviewMode.value = m
      }
      parsedPrompt = data.review_prompt || ''
      reviewSuggestion.value = String(data.review_suggestion || '').trim()
    }
  } catch {}
  reviewPrompt.value = getModePrompt(reviewMode.value) || parsedPrompt
  syncReviewPromptFromMode(reviewMode.value)
}

function buildReviewPromptText() {
  const obj = { review_mode: reviewMode.value, review_prompt: reviewPrompt.value }
  if (reviewSuggestion.value.trim()) {
    obj.review_suggestion = reviewSuggestion.value.trim()
  }
  return JSON.stringify(obj, null, 2)
}

function normalizeChatFields(chat) {
  return {
    chat_id: chat.chat_id || '',
    display_name: chat.chat_display_name || chat.display_name || chat.chat_name || '',
    chat_type: chat.chat_type || 'user',
    pairs: (chat.pairs || [])
      .filter(pair => {
        const q = stripAttachmentMarks(pair.question || '')
        const a = stripAttachmentMarks(pair.answer || '')
        return q || a
      })
      .map(pair => {
        const cleanedQ = stripAttachmentMarks(pair.question || '')
        const cleanedA = stripAttachmentMarks(pair.answer || '')
        return {
          pair_id: pair.pair_id || '',
          question: cleanedQ,
          answer: cleanedA,
          question_message_ids: Array.isArray(pair.question_message_ids) ? pair.question_message_ids : [],
          answer_message_ids: Array.isArray(pair.answer_message_ids) ? pair.answer_message_ids : [],
          question_time: pair.question_time || '',
          answer_time: pair.answer_time || '',
          question_sender: pair.question_sender || '用户',
          answer_sender: pair.answer_sender || '助理',
          question_edited: Boolean(pair.question_edited),
          answer_edited: Boolean(pair.answer_edited),
          direction: pair.direction === 'ai' ? 'bot' : (pair.direction || ''),
          time: pair.time || '',
          answer_feedback_status: pair.answer_feedback_status || '',
          answer_feedback_result: pair.answer_feedback_result || '',
          answer_feedback_reason: pair.answer_feedback_reason || '',
          answer_feedback_all_reasons: pair.answer_feedback_all_reasons || '',
          answer_feedback_count: pair.answer_feedback_count || 0,
        }
      }),
  }
}

const _ATTACHMENT_RE = /\[文件[^\]]*\]|\[图片[^\]]*\]/g

function stripAttachmentMarks(text) {
  return String(text || '').replace(_ATTACHMENT_RE, '').replace(/\s{2,}/g, ' ').trim()
}

function isAttachmentOnlyPair(pair) {
  const q = stripAttachmentMarks(pair.question || '')
  const a = stripAttachmentMarks(pair.answer || '')
  return !q && !a
}

// 同步可视化编辑到 JSON
function syncChatsToJson() {
  if (!memoryUpdateChats.value) return
  dialogForm.value.prompt_text = JSON.stringify(buildMemoryUpdatePromptData(), null, 2)
}

// 删除会话
function removeChat(chatIndex) {
  if (!memoryUpdateChats.value) return
  memoryUpdateChats.value.splice(chatIndex, 1)
  memoryUpdateEdited.value = true
  syncChatsToJson()
}

// 删除问答对
function removePair(chatIndex, pairIndex) {
  if (!memoryUpdateChats.value || !memoryUpdateChats.value[chatIndex]) return
  memoryUpdateChats.value[chatIndex].pairs.splice(pairIndex, 1)
  memoryUpdateEdited.value = true
  syncChatsToJson()
}

function onPairQuestionInput(chatIndex, pairIndex, value) {
  const pair = memoryUpdateChats.value?.[chatIndex]?.pairs?.[pairIndex]
  if (!pair) return
  pair.question = value
  pair.question_edited = true
  memoryUpdateEdited.value = true
  syncChatsToJson()
}

function onPairAnswerInput(chatIndex, pairIndex, value) {
  const pair = memoryUpdateChats.value?.[chatIndex]?.pairs?.[pairIndex]
  if (!pair) return
  pair.answer = value
  pair.answer_edited = true
  memoryUpdateEdited.value = true
  syncChatsToJson()
}

function pairStatus(pair) {
  const hasQuestion = Boolean((pair.question || '').trim())
  const hasAnswer = Boolean((pair.answer || '').trim())
  if (hasQuestion && hasAnswer) return '完整'
  if (hasQuestion) return '缺少回答'
  if (hasAnswer) return '缺少问题'
  return '空白'
}

function pairStatusType(pair) {
  return pairStatus(pair) === '完整' ? 'success' : 'warning'
}

function pairWillBeIncluded(pair) {
  return Boolean((pair.question || '').trim()) && Boolean((pair.answer || '').trim())
}

function pairFeedbackTag(pair) {
  const status = String(pair.answer_feedback_status || '').trim().toLowerCase()
  if (!status) return null
  const reason = String(pair.answer_feedback_all_reasons || pair.answer_feedback_reason || '').trim()
  const count = Number(pair.answer_feedback_count || 1)
  if (status === 'useful_only') return { label: '有效', type: 'success', reason: '' }
  if (status === 'useless_only') return { label: '无效', type: 'danger', reason }
  if (status === 'mixed') {
    const suffix = count > 1 ? ` (${count})` : ''
    return { label: `有争议${suffix}`, type: 'warning', reason }
  }
  return null
}

function pairQuestionPlaceholder(pair) {
  return (pair.answer || '').trim() ? '请补充缺失的问题' : '请输入问题'
}

function pairAnswerPlaceholder(pair) {
  return (pair.question || '').trim() ? '请补充缺失的回答' : '请输入回答'
}

function countCompletePairs(chat) {
  return (chat.pairs || []).filter(pair => pairWillBeIncluded(pair)).length
}

function openCreateDialog() {
  dialogMode.value = 'create'
  dialogForm.value = {
    task_type: 'periodic',
    task_name: '',
    description: '',
    executor_kind: 'bot',
    executor_id: '',
    schedule_type: 'interval_days',
    schedule_value: 1,
    schedule_time: '00:00',
    prompt_text: '',
    is_enabled: false,
  }
  // 重置 bot_task 临时数据
  botTaskData.value = {
    user_prompt: '',
    skill_names: [],
    mcp_server_ids: []
  }
  dialogVisible.value = true
}

// 解析 bot_task 数据从 prompt_text
function parseBotTaskPrompt(promptText) {
  if (!promptText) {
    return {
      user_prompt: '',
      skill_names: [],
      mcp_server_ids: []
    }
  }
  try {
    const data = JSON.parse(promptText)
    return {
      user_prompt: data.user_prompt || '',
      skill_names: data.skill_names || [],
      mcp_server_ids: data.mcp_server_ids || []
    }
  } catch {
    return {
      user_prompt: promptText,
      skill_names: [],
      mcp_server_ids: []
    }
  }
}

// 组装 bot_task prompt_text
function buildBotTaskPrompt() {
  return JSON.stringify({
    user_prompt: botTaskData.value.user_prompt,
    skill_names: botTaskData.value.skill_names,
    mcp_server_ids: botTaskData.value.mcp_server_ids
  }, null, 2)
}

async function handleEnable(task) {
  const enabledAt = Date.now()
  const waitForRunning = shouldPollAfterEnable(task, enabledAt)
  if (waitForRunning) {
    triggerLoadingTaskKey.value = task.task_key
  }
  try {
    await enableTask(task.task_key)
    ElMessage.success('任务已启用')
    if (waitForRunning) {
      const pollResult = await pollTaskUntilRunning(task.task_key, task)
      if (pollResult.state === 'running') {
        ElMessage.success('任务已进入执行中')
      } else if (pollResult.state === 'failed') {
        ElMessage.error(pollResult.task?.last_run_message || '任务执行失败')
      }
    }
  } catch (error) {
    ElMessage.error(error?.message || '启用失败')
  } finally {
    await loadTasks()
    if (waitForRunning && triggerLoadingTaskKey.value === task.task_key) {
      triggerLoadingTaskKey.value = ''
    }
  }
}

async function handleDisable(task) {
  try {
    await ElMessageBox.confirm('确定要停用这个任务吗？停用后将不再自动执行。', '停用确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await disableTask(task.task_key)
    ElMessage.success('任务已停用')
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '停用失败')
    }
  }
}

function handleEdit(task) {
  if (isSystemTask(task) && !isSystemHandlerTask(task)) {
    openDialog('view', task)
  } else {
    openDialog('edit', task)
  }
}

function handleViewDetail(task) {
  openDialog('view', task)
}

const SYSTEM_TASK_HANDLERS = [
  'memory_update',
  'document_memory_extraction',
  'self_review_chat_memory',
  'self_review_document_memory',
]

async function handleTrigger() {
  try {
    if (dialogForm.value.handler_name === 'memory_update') {
      await ElMessageBox.confirm(
        '即将执行记忆更新任务。注意：任务将使用截止到上一个整点的会话数据（封盘时间）。该任务耗时较久，请耐心等待。',
        '任务执行确认',
        {
          confirmButtonText: '确认执行',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    } else if (SYSTEM_TASK_HANDLERS.includes(dialogForm.value.handler_name)) {
      await ElMessageBox.confirm(
        '该任务耗时较久，请耐心等待。',
        '任务执行确认',
        {
          confirmButtonText: '确认执行',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    }
    
    await triggerAndRefresh({ ...dialogForm.value }, '任务已触发!')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '触发任务失败')
    }
  }
}

async function handleRetry(task) {
  try {
    await triggerAndRefresh({ ...task }, '任务已重新发起')
  } catch (error) {
    ElMessage.error(error?.message || '重试任务失败')
  }
}

async function refreshMemoryUpdatePreview() {
  if (!dialogForm.value.task_key) return
  try {
    const result = await getTaskDetail(dialogForm.value.task_key)
    if (result.memory_update_preview) {
      memoryUpdatePreview.value = result.memory_update_preview
      // 重置为原始数据
      resetMemoryUpdatePrompt()
      ElMessage.success('会话数据已刷新')
    }
  } catch (error) {
    ElMessage.error(error?.message || '刷新失败')
  }
}

function formatJson(jsonStr) {
  if (!jsonStr || jsonStr === '') return ''
  try {
    const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr
    return JSON.stringify(obj, null, 2)
  } catch {
    return jsonStr
  }
}

function parseMemoryUpdatePromptState(promptText) {
  if (!String(promptText || '').trim()) return 'default'
  try {
    const data = JSON.parse(promptText)
    return data?.is_user_edited ? 'edited' : 'default'
  } catch {
    return 'default'
  }
}

function uniqueList(items) {
  return Array.from(new Set((items || []).map(item => String(item || '').trim()).filter(Boolean)))
}

function buildExtractionMessageIds() {
  const result = {}
  for (const chat of memoryUpdateChats.value || []) {
    const chatId = String(chat.chat_id || '').trim()
    if (!chatId) continue
    const ids = []
    for (const pair of chat.pairs || []) {
      if (!pairWillBeIncluded(pair)) continue
      ids.push(...(Array.isArray(pair.question_message_ids) ? pair.question_message_ids : []))
      ids.push(...(Array.isArray(pair.answer_message_ids) ? pair.answer_message_ids : []))
    }
    const uniqueIds = uniqueList(ids)
    if (uniqueIds.length) {
      result[chatId] = uniqueIds
    }
  }
  return result
}

function buildMemoryUpdatePromptData() {
  return {
    cutoff_time: memoryUpdatePreview.value?.cutoff_time || '',
    chats: memoryUpdateChats.value || [],
    extraction_message_ids: buildExtractionMessageIds(),
    skipped_ai_message_ids: skippedAiMessageIds.value || {},
    is_user_edited: memoryUpdateEdited.value,
  }
}

function resetMemoryUpdatePrompt() {
  const preview = memoryUpdatePreview.value
  if (!preview || !preview.chats) return

  const chats = Object.entries(preview.chats).map(([chatId, chatData]) => {
    const mapped = normalizeChatFields(chatData)
    mapped.chat_id = chatId
    return mapped
  })

  memoryUpdateChats.value = chats
  skippedAiMessageIds.value = preview.skipped_ai_message_ids || {}
  memoryUpdateEdited.value = false

  const promptData = buildMemoryUpdatePromptData()
  originalMemoryUpdatePrompt.value = formatJson(promptData)
  dialogForm.value.prompt_text = originalMemoryUpdatePrompt.value
}

async function handleDialogSave() {
  if (dialogForm.value.task_type === 'periodic') {
    if (!dialogForm.value.schedule_time) {
      ElMessage.warning('执行时间不能为空')
      return
    }
    if (!dialogForm.value.schedule_value || dialogForm.value.schedule_value < 1) {
      ElMessage.warning('间隔天数不能小于1')
      return
    }
  }

  dialogSaving.value = true
  try {
    // 确保可视化编辑的内容同步到 JSON
    if (dialogForm.value.handler_name === 'memory_update' && !showJsonEdit.value) {
      syncChatsToJson()
    }
    
    // 组装 bot 任务的 prompt_text；系统底层任务保留原始 JSON。
    const isBotTask = dialogForm.value.executor_kind === 'bot'
    let promptText = isBotTask ? buildBotTaskPrompt() : (dialogForm.value.prompt_text || '')
    if (dialogForm.value.handler_name === 'self_review_chat_memory' || dialogForm.value.handler_name === 'self_review_document_memory') {
      promptText = buildReviewPromptText()
    }
    
    const data = {
      name: dialogForm.value.task_name,
      description: dialogForm.value.description,
      executor_kind: dialogMode.value === 'create' ? 'bot' : dialogForm.value.executor_kind,
      executor_id: dialogForm.value.executor_id,
      prompt_text: promptText,
      skill_names: isBotTask ? botTaskData.value.skill_names : [],
      mcp_server_ids: isBotTask ? botTaskData.value.mcp_server_ids : [],
      task_type: dialogForm.value.task_type,
      notify_bot_key: dialogForm.value.notify_bot_key || '',
    }

    if (data.task_type === 'periodic') {
      data.schedule_type = dialogForm.value.schedule_type
      data.schedule_value = dialogForm.value.schedule_value
      data.schedule_time = dialogForm.value.schedule_time
      // 如果后端支持 is_enabled 字段，则传递
      if (dialogForm.value.is_enabled !== undefined) {
        data.is_enabled = dialogForm.value.is_enabled
      }
    }

    if (dialogMode.value === 'create') {
      await createTask(data)
      ElMessage.success('任务已创建')
    } else if (dialogMode.value === 'edit') {
      await updateTask(dialogForm.value.task_key, data)
      ElMessage.success('任务已更新')
    }
    dialogVisible.value = false
    loadTasks()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    dialogSaving.value = false
  }
}

async function handleDelete(task) {
  try {
    await ElMessageBox.confirm('确定要删除这个任务吗？删除后不可恢复。', '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteTask(getTaskRequestId(task))
    ElMessage.success('任务已删除')
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '删除失败')
    }
  }
}

function switchToEdit() {
  dialogMode.value = 'edit'
}

function onDocumentContentInput(val) {
  if (documentPreview.value) {
    documentPreview.value.content = val
  }
  try {
    const data = JSON.parse(dialogForm.value.prompt_text || '{}')
    data.content = val
    dialogForm.value.prompt_text = JSON.stringify(data, null, 2)
  } catch {
    dialogForm.value.prompt_text = val
  }
}

onMounted(() => { 
  loadTasks() 
  loadExecutors()
  loadSkills()
  loadMcpServers()
})
onActivated(() => { 
  loadTasks() 
  loadExecutors()
  loadSkills()
  loadMcpServers()
})
onBeforeUnmount(() => {
  triggerPollSeq += 1
  triggerLoadingTaskKey.value = ''
})

// 监听消息变化，自动同步到 JSON
watch(
  memoryUpdateChats,
  () => {
    if (!showJsonEdit.value) {
      syncChatsToJson()
    }
  },
  { deep: true }
)

watch(reviewMode, (newMode) => {
  if (isReviewHandlerName(dialogForm.value.handler_name)) {
    syncReviewPromptFromMode(newMode)
    return
  }
  const desc = getModeDescription(newMode)
  if (desc) dialogForm.value.description = desc
})
</script>

<template>
  <section class="task-management">
    <div class="header">
      <div class="header-left">
        <h2>任务管理</h2>
        <span class="header-hint">💡 点击"详情"可查看任务详情并立即执行</span>
      </div>
      <el-button type="primary" @click="openCreateDialog">新建任务</el-button>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.scope" placeholder="任务级别" clearable>
        <el-option label="系统级" value="system" />
        <el-option label="用户级" value="user" />
      </el-select>
      <el-select v-model="filters.taskType" placeholder="任务周期" clearable>
        <el-option label="周期任务" value="periodic" />
        <el-option label="一次性任务" value="one_time" />
      </el-select>
      <el-select v-model="filters.status" placeholder="执行状态" clearable>
        <el-option v-for="opt in statusFilterOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-input v-model="filters.keyword" placeholder="输入任务名称、提示词或会话名称" clearable />
      <el-button type="primary" @click="handleSearch">查询</el-button>
    </div>

    <div class="table-container">
      <div class="table-scroll">
        <el-table :data="tasks" stripe style="width: 100%" height="100%" scrollbar-always-on v-loading="taskTableLoading">
        <el-table-column label="任务周期" width="110" align="center">
          <template #default="{ row }">
            {{ row.task_type === 'periodic' ? '周期任务' : '一次性任务' }}
          </template>
        </el-table-column>
        <el-table-column prop="task_name" label="任务名称" width="160" align="center" />
        <el-table-column label="任务级别" width="100" align="center">
          <template #default="{ row }">{{ scopeLabel(row.task_scope) }}</template>
        </el-table-column>
        <el-table-column label="执行器" width="180">
          <template #default="{ row }">{{ getExecutorName(row) }}</template>
        </el-table-column>
        <el-table-column label="执行周期" width="110" align="center">
          <template #default="{ row }">{{ row.cycle_label || '-' }}</template>
        </el-table-column>
        <el-table-column prop="description" label="任务说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="提示词" min-width="180">
          <template #default="{ row }">
            <el-tooltip v-if="row.prompt_text || row.handler_name === 'memory_update'" :content="row.prompt_text || '全会话'" placement="top" show-after="300">
              <span class="task-prompt-text">{{ summarizePrompt(row.prompt_text, row) }}</span>
            </el-tooltip>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="任务状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="300">
          <template #default="{ row }">{{ formatTime(row.created_at) || '-' }}</template>
        </el-table-column>
        <el-table-column label="执行时间" width="300">
          <template #default="{ row }">{{ formatTime(row.started_at || row.last_run_at) || '-' }}</template>
        </el-table-column>
        <el-table-column label="执行结果" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ resultText(row) }}</template>
        </el-table-column>
        <el-table-column label="下次执行" width="300">
          <template #default="{ row }">{{ formatTime(row.next_run_at) || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="340" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEnable(row)" type="success" size="small" @click="handleEnable(row)">启用</el-button>
            <el-button v-if="canDisable(row)" type="warning" size="small" @click="handleDisable(row)">停用</el-button>
            <el-button
              v-if="canRetry(row)"
              type="danger"
              size="small"
              :loading="isTriggerLoading(row)"
              @click="handleRetry(row)"
            >
              重试
            </el-button>
            <el-button
              v-if="canEdit(row)"
              type="primary"
              size="small"
              @click="openDialog('edit', row)"
            >
              编辑
            </el-button>
            <el-button type="info" size="small" @click="openDialog('view', row)">详情</el-button>
            <el-button v-if="canDelete(row)" type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!tasks.length && !taskTableLoading" class="empty">暂无任务</div>
      </div>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="1100px" :close-on-click-modal="false">
      <el-form :model="dialogForm" label-width="100px">
        <!-- Task 4: 记忆更新任务的任务类型不可编辑 -->
        <template v-if="dialogMode !== 'view' && !isFixedInfoTask(dialogForm)">
          <el-form-item label="任务类型">
            <el-radio-group v-model="dialogForm.task_type">
              <el-radio value="one_time">一次性任务</el-radio>
              <el-radio value="periodic">周期任务</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="任务类型">
            <span>{{ dialogForm.task_type === 'periodic' ? '周期任务' : '一次性任务' }}</span>
          </el-form-item>
        </template>

        <el-form-item label="任务名称">
          <template v-if="dialogMode !== 'view' && !isFixedInfoTask(dialogForm)">
            <el-input v-model="dialogForm.task_name" maxlength="200" />
          </template>
          <template v-else>{{ dialogForm.task_name }}</template>
        </el-form-item>

        <el-form-item label="执行器">
          <template v-if="dialogMode !== 'view' && !isFixedInfoTask(dialogForm)">
            <template v-if="isSystemHandlerTask(dialogForm)">
              <el-tag type="info" size="large">平台 Agent</el-tag>
            </template>
            <template v-else>
              <el-select
                v-model="dialogForm.executor_id"
                placeholder="选择 Bot"
                style="width: 200px"
              >
                <el-option
                  v-for="bot in executors.bots"
                  :key="bot.id"
                  :label="bot.name"
                  :value="bot.id"
                />
              </el-select>
            </template>
          </template>
          <template v-else>{{ getExecutorName(dialogForm) }}</template>
        </el-form-item>

        <!-- Bot 任务的技能和 MCP 服务器选择 -->
        <template v-if="dialogForm.executor_kind === 'bot'">
          <el-form-item label="技能">
            <template v-if="dialogMode !== 'view'">
              <el-select
                v-model="botTaskData.skill_names"
                multiple
                placeholder="选择技能（可选）"
                style="width: 100%"
                :loading="loadingSkills"
              >
                <el-option
                  v-for="skill in skills"
                  :key="skill.name || skill"
                  :label="skill.display_name || skill.name || skill"
                  :value="skill.name || skill"
                />
              </el-select>
            </template>
            <template v-else>
              <el-tag v-for="name in botTaskData.skill_names" :key="name" style="margin-right: 5px;">
                {{ name }}
              </el-tag>
              <span v-if="!botTaskData.skill_names || botTaskData.skill_names.length === 0">-</span>
            </template>
          </el-form-item>
          <el-form-item label="MCP 服务器">
            <template v-if="dialogMode !== 'view'">
              <el-select
                v-model="botTaskData.mcp_server_ids"
                multiple
                placeholder="选择 MCP 服务器（可选）"
                style="width: 100%"
                :loading="loadingMcpServers"
              >
                <el-option
                  v-for="server in mcpServers"
                  :key="getMcpServerValue(server)"
                  :label="server.name || server.server_name || getMcpServerValue(server)"
                  :value="getMcpServerValue(server)"
                />
              </el-select>
            </template>
            <template v-else>
              <el-tag v-for="id in botTaskData.mcp_server_ids" :key="id" style="margin-right: 5px;">
                {{ getMcpServerName(id) }}
              </el-tag>
              <span v-if="!botTaskData.mcp_server_ids || botTaskData.mcp_server_ids.length === 0">-</span>
            </template>
          </el-form-item>
        </template>

        <template v-if="isPeriodicType">
          <el-form-item label="间隔天数">
            <template v-if="dialogMode !== 'view'">
              <el-input-number v-model="dialogForm.schedule_value" :min="1" :max="365" />
            </template>
            <template v-else>{{ dialogForm.schedule_value }}</template>
          </el-form-item>

          <el-form-item label="执行时间">
            <template v-if="dialogMode !== 'view'">
              <el-time-picker
                v-model="dialogForm.schedule_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择执行时间"
              />
            </template>
            <template v-else>{{ dialogForm.schedule_time }}</template>
          </el-form-item>
        </template>

        <el-form-item label="任务说明">
          <template v-if="dialogMode !== 'view' && !isFixedInfoTask(dialogForm)">
            <el-input v-model="dialogForm.description" type="textarea" :rows="3" maxlength="2000" />
          </template>
          <template v-else>{{ dialogForm.description || '-' }}</template>
        </el-form-item>

        <!-- 记忆更新任务的特殊编辑界面 -->
        <template v-if="dialogForm.handler_name === 'memory_update'">
          <el-divider content-position="left">
            <span class="divider-title">📅 时间信息</span>
          </el-divider>
          <el-form-item label="会话数据截止时间">
            <template v-if="memoryUpdatePreview">
              <div class="time-info">
                <el-tag type="info" size="large">
                  {{ formatTime(memoryUpdatePreview.cutoff_time) }}
                </el-tag>
                <div class="current-time">
                  <span class="label">当前时间:</span>
                  <span class="value">{{ formatTime(memoryUpdatePreview.current_time) }}</span>
                </div>
              </div>
            </template>
            <template v-else>-</template>
          </el-form-item>

          <template v-if="memoryUpdatePreview">
            <el-divider content-position="left">
              <span class="divider-title">📊 数据概览</span>
            </el-divider>
            <el-form-item>
              <div class="data-summary">
                <div class="summary-card">
                  <div class="icon">📋</div>
                  <div class="info">
                    <div class="number">{{ memoryUpdatePreview.chat_count }}</div>
                    <div class="label">会话数</div>
                  </div>
                </div>
                <div class="summary-card">
                  <div class="icon">💬</div>
                  <div class="info">
                    <div class="number">{{ memoryUpdatePreview.total_message_count }}</div>
                    <div class="label">消息数</div>
                  </div>
                </div>
                <div class="summary-card">
                  <div class="icon">🧠</div>
                  <div class="info">
                    <div class="number">{{ memoryUpdatePreview.selected_pair_count || 0 }}</div>
                    <div class="label">本批问答对</div>
                  </div>
                </div>
              </div>
            </el-form-item>
            <el-form-item v-if="memoryUpdatePreview.is_truncated">
              <el-alert
                :title="`当前批次已按限制截断：送入 ${memoryUpdatePreview.selected_pair_count || 0} 组问答 / ${memoryUpdatePreview.selected_message_count || 0} 条消息，剩余 ${memoryUpdatePreview.omitted_pair_count || 0} 组问答 / ${memoryUpdatePreview.omitted_message_count || 0} 条消息待人工处理。`"
                type="warning"
                show-icon
                :closable="false"
              />
            </el-form-item>
          </template>
          
          <el-divider content-position="left">
            <span class="divider-title">📝 提示词数据</span>
          </el-divider>
          <el-form-item :label="getPromptLabel(dialogForm)">
            <template v-if="memoryUpdateChats && memoryUpdateChats.length > 0">
              <div class="message-list-editor" :class="{ 'is-readonly': dialogMode === 'view' }">
                <div v-for="(chat, chatIndex) in memoryUpdateChats" :key="chatIndex" class="chat-section">
                  <div class="chat-header">
                    <div class="chat-title-wrap">
                      <span class="chat-title">{{ getChatName(chat) }}</span>
                      <span class="chat-hint">将送入提炼: {{ countCompletePairs(chat) }} / {{ (chat.pairs || []).length }}</span>
                    </div>
                    <el-button
                      v-if="dialogMode !== 'view'"
                      type="danger" 
                      size="small" 
                      @click="removeChat(chatIndex)"
                    >删除会话</el-button>
                  </div>
                  
                  <div v-if="chat.pairs && chat.pairs.length > 0">
                    <div v-for="(pair, pairIndex) in chat.pairs" :key="pair.pair_id || pairIndex" class="qa-pair">
                      <div class="qa-header">
                        <div class="pair-meta">
                          <el-tag type="primary" size="small">{{ pair.question_sender || '用户' }}</el-tag>
                          <el-tag type="success" size="small">{{ pair.answer_sender || '助理' }}</el-tag>
                          <el-tag :type="pairStatusType(pair)" size="small">{{ pairStatus(pair) }}</el-tag>
                          <el-tag v-if="pairWillBeIncluded(pair)" type="success" size="small">会送入记忆</el-tag>
                          <el-tag v-else type="info" size="small">暂不送入记忆</el-tag>
                          <el-tooltip v-if="pairFeedbackTag(pair) && pairFeedbackTag(pair).reason" :content="pairFeedbackTag(pair).reason" placement="top" :show-after="300">
                            <el-tag :type="pairFeedbackTag(pair).type" size="small" class="pair-feedback-tag">{{ pairFeedbackTag(pair).label }}</el-tag>
                          </el-tooltip>
                          <el-tag v-else-if="pairFeedbackTag(pair)" :type="pairFeedbackTag(pair).type" size="small" class="pair-feedback-tag">{{ pairFeedbackTag(pair).label }}</el-tag>
                        </div>
                        <el-button
                          v-if="dialogMode !== 'view'"
                          type="danger" 
                          size="small" 
                          text 
                          @click="removePair(chatIndex, pairIndex)"
                        >删除</el-button>
                      </div>
                      <div class="qa-question">
                        <div class="qa-label">
                          <span>❓</span>
                          <span>问题</span>
                        </div>
                        <div class="qa-subtitle">{{ pair.question_time || '无原始提问时间' }}</div>
                        <template v-if="dialogMode !== 'view'">
                          <el-input 
                            :model-value="pair.question"
                            @update:model-value="value => onPairQuestionInput(chatIndex, pairIndex, value)"
                            type="textarea" 
                            :rows="2"
                            :placeholder="pairQuestionPlaceholder(pair)"
                            class="qa-input"
                          />
                        </template>
                        <template v-else>
                          <div class="qa-text-view">{{ pair.question || '-' }}</div>
                        </template>
                      </div>
                      <div class="qa-answer">
                        <div class="qa-label answer">
                          <span>💬</span>
                          <span>回答</span>
                        </div>
                        <div class="qa-subtitle">{{ pair.answer_time || '无原始回答时间' }}</div>
                        <template v-if="dialogMode !== 'view'">
                          <el-input 
                            :model-value="pair.answer"
                            @update:model-value="value => onPairAnswerInput(chatIndex, pairIndex, value)"
                            type="textarea" 
                            :rows="2"
                            :placeholder="pairAnswerPlaceholder(pair)"
                            class="qa-input"
                          />
                        </template>
                        <template v-else>
                          <div class="qa-text-view">{{ pair.answer || '-' }}</div>
                        </template>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="dialogMode !== 'view'" class="json-edit-toggle">
                <el-checkbox v-model="showJsonEdit">显示 JSON 预览</el-checkbox>
              </div>
              <div v-if="dialogMode !== 'view' && showJsonEdit" class="prompt-text-view">{{ dialogForm.prompt_text || '-' }}</div>
            </template>
            <template v-else>
              <div class="prompt-text-view">{{ dialogForm.prompt_text || '-' }}</div>
            </template>
          </el-form-item>
          
          <!-- 编辑模式下提供快捷操作 -->
          <template v-if="dialogMode === 'edit'">
            <el-form-item>
              <div class="action-buttons">
                <el-button type="primary" size="default" @click="refreshMemoryUpdatePreview">
                  <span class="btn-icon">🔄</span>
                  重新获取会话数据
                </el-button>
                <el-button type="default" size="default" @click="resetMemoryUpdatePrompt">
                  <span class="btn-icon">📝</span>
                  重置为原始数据
                </el-button>
              </div>
            </el-form-item>
          </template>
          <el-form-item label="通知Bot">
            <template v-if="dialogMode !== 'view'">
              <el-select v-model="dialogForm.notify_bot_key" clearable placeholder="选择通知Bot" style="width: 100%;">
                <el-option v-for="bot in executors.bots" :key="bot.id" :label="bot.name" :value="bot.id" />
              </el-select>
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">任务完成后通过Bot通知任务结果</div>
            </template>
            <template v-else>{{ getNotifyBotName(dialogForm.notify_bot_key) }}</template>
          </el-form-item>
        </template>

        <!-- 其他任务的普通编辑界面 -->
        <template v-else-if="dialogForm.handler_name === 'document_memory_extraction'">
          <el-divider content-position="left">
            <span class="divider-title">📄 文档信息</span>
          </el-divider>
          <template v-if="documentPreview">
            <el-form-item label="文件名">
              <span>{{ documentPreview.filename || '-' }}</span>
            </el-form-item>
            <el-form-item label="文件类型">
              <span>{{ documentPreview.file_type || '-' }}</span>
            </el-form-item>
            <el-form-item label="文件大小">
              <span>{{ documentPreview.file_size ? `${(documentPreview.file_size / 1024).toFixed(1)} KB` : '-' }}</span>
            </el-form-item>
          </template>
          <el-divider content-position="left">
            <span class="divider-title">📝 文档内容</span>
          </el-divider>
          <el-form-item v-if="dialogMode !== 'view'">
            <el-alert
              title="这里修改的是本次提取任务使用的文本，不会覆盖已上传的原始文档文件。"
              type="info"
              show-icon
              :closable="false"
            />
          </el-form-item>
          <el-form-item label="文档内容">
            <template v-if="documentPreview && documentPreview.error">
              <el-alert :title="documentPreview.error" type="error" show-icon :closable="false" />
            </template>
            <template v-else-if="dialogMode !== 'view'">
              <el-input 
                v-model="documentEditContentRef" 
                type="textarea" 
                :rows="20"
                placeholder="文档内容..."
                class="memory-prompt-input"
                @input="onDocumentContentInput"
              />
              <div v-if="!documentEditContentRef && documentPreview && !documentPreview.content" class="doc-content-fallback">
                <el-alert title="文档内容为空，请检查文件是否存在或格式是否受支持" type="warning" show-icon :closable="false" />
              </div>
            </template>
            <template v-else>
              <div class="prompt-text-view document-content-view">{{ documentPreview?.content || documentContentText || '-' }}</div>
            </template>
          </el-form-item>
          <el-form-item label="通知Bot">
            <template v-if="dialogMode !== 'view'">
              <el-select v-model="dialogForm.notify_bot_key" clearable placeholder="选择通知Bot" style="width: 100%;">
                <el-option v-for="bot in executors.bots" :key="bot.id" :label="bot.name" :value="bot.id" />
              </el-select>
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">任务完成后通过Bot通知任务结果</div>
            </template>
            <template v-else>{{ getNotifyBotName(dialogForm.notify_bot_key) }}</template>
          </el-form-item>
        </template>
        <template v-else-if="dialogForm.handler_name === 'self_review_chat_memory'">
          <el-form-item label="审查模式">
            <template v-if="dialogMode !== 'view'">
              <el-radio-group v-model="reviewMode">
                <el-radio-button value="review">
                  <el-tooltip content="只出报告，不修改任何记忆文件" placement="top">
                    <span>仅审查</span>
                  </el-tooltip>
                </el-radio-button>
                <el-radio-button value="dry_run">
                  <el-tooltip content="模拟执行补丁，输出预览但不实际写入" placement="top">
                    <span>预览补丁</span>
                  </el-tooltip>
                </el-radio-button>
                <el-radio-button value="patch">
                  <el-tooltip content="审查后自动应用安全补丁到记忆文件" placement="top">
                    <span>自动修复</span>
                  </el-tooltip>
                </el-radio-button>
              </el-radio-group>
            </template>
            <template v-else>
              <el-tag :type="reviewMode === 'patch' ? 'success' : reviewMode === 'dry_run' ? 'warning' : 'info'" size="small">
                {{ reviewMode === 'patch' ? '自动修复' : reviewMode === 'dry_run' ? '预览补丁' : '仅审查' }}
              </el-tag>
            </template>
          </el-form-item>
          <el-form-item :label="getPromptLabel(dialogForm)">
            <template v-if="dialogMode !== 'view'">
              <el-input v-model="reviewPrompt" type="textarea" :rows="6" readonly placeholder="审查提示词由审查模式自动生成" />
            </template>
            <template v-else>
              <div v-if="reviewPrompt" class="prompt-text-view">{{ reviewPrompt }}</div>
              <el-alert
                v-else
                title="暂无自定义审查提示词，将使用默认审查逻辑"
                type="info"
                show-icon
                :closable="false"
              />
            </template>
          </el-form-item>
          <el-form-item label="审核建议">
            <template v-if="dialogMode !== 'view'">
              <el-input v-model="reviewSuggestion" type="textarea" :rows="3" placeholder="填写审核重点方向，如：用户反馈记忆提取不准确，重点检查相关记忆是否缺失。留空则不注入。" />
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">将作为重点参照的审核方向注入到审查提示词中，留空则不注入</div>
            </template>
            <template v-else>
              <div v-if="reviewSuggestion" class="prompt-text-view">{{ reviewSuggestion }}</div>
              <el-alert
                v-else
                title="未设置审核建议"
                type="info"
                show-icon
                :closable="false"
              />
            </template>
          </el-form-item>
          <el-form-item label="通知Bot">
            <template v-if="dialogMode !== 'view'">
              <el-select v-model="dialogForm.notify_bot_key" clearable placeholder="选择通知Bot" style="width: 100%;">
                <el-option v-for="bot in executors.bots" :key="bot.id" :label="bot.name" :value="bot.id" />
              </el-select>
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">任务完成后通过Bot通知任务结果</div>
            </template>
            <template v-else>{{ getNotifyBotName(dialogForm.notify_bot_key) }}</template>
          </el-form-item>
        </template>
        <template v-else-if="dialogForm.handler_name === 'self_review_document_memory'">
          <el-form-item label="审查模式">
            <template v-if="dialogMode !== 'view'">
              <el-radio-group v-model="reviewMode">
                <el-radio-button value="review">
                  <el-tooltip content="只出报告，不修改任何记忆文件" placement="top">
                    <span>仅审查</span>
                  </el-tooltip>
                </el-radio-button>
                <el-radio-button value="dry_run">
                  <el-tooltip content="模拟执行补丁，输出预览但不实际写入" placement="top">
                    <span>预览补丁</span>
                  </el-tooltip>
                </el-radio-button>
                <el-radio-button value="patch">
                  <el-tooltip content="审查后自动应用安全补丁到记忆文件" placement="top">
                    <span>自动修复</span>
                  </el-tooltip>
                </el-radio-button>
              </el-radio-group>
            </template>
            <template v-else>
              <el-tag :type="reviewMode === 'patch' ? 'success' : reviewMode === 'dry_run' ? 'warning' : 'info'" size="small">
                {{ reviewMode === 'patch' ? '自动修复' : reviewMode === 'dry_run' ? '预览补丁' : '仅审查' }}
              </el-tag>
            </template>
          </el-form-item>
          <el-form-item :label="getPromptLabel(dialogForm)">
            <template v-if="dialogMode !== 'view'">
              <el-input v-model="reviewPrompt" type="textarea" :rows="6" readonly placeholder="审查提示词由审查模式自动生成" />
            </template>
            <template v-else>
              <div v-if="reviewPrompt" class="prompt-text-view">{{ reviewPrompt }}</div>
              <el-alert
                v-else
                title="暂无自定义审查提示词，将使用默认审查逻辑"
                type="info"
                show-icon
                :closable="false"
              />
            </template>
          </el-form-item>
          <el-form-item label="审核建议">
            <template v-if="dialogMode !== 'view'">
              <el-input v-model="reviewSuggestion" type="textarea" :rows="3" placeholder="填写审核重点方向，如：用户反馈记忆提取不准确，重点检查相关记忆是否缺失。留空则不注入。" />
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">将作为重点参照的审核方向注入到审查提示词中，留空则不注入</div>
            </template>
            <template v-else>
              <div v-if="reviewSuggestion" class="prompt-text-view">{{ reviewSuggestion }}</div>
              <el-alert
                v-else
                title="未设置审核建议"
                type="info"
                show-icon
                :closable="false"
              />
            </template>
          </el-form-item>
          <el-form-item label="通知Bot">
            <template v-if="dialogMode !== 'view'">
              <el-select v-model="dialogForm.notify_bot_key" clearable placeholder="选择通知Bot" style="width: 100%;">
                <el-option v-for="bot in executors.bots" :key="bot.id" :label="bot.name" :value="bot.id" />
              </el-select>
              <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">任务完成后通过Bot通知任务结果</div>
            </template>
            <template v-else>{{ getNotifyBotName(dialogForm.notify_bot_key) }}</template>
          </el-form-item>
        </template>
        <template v-else>
          <!-- Bot 任务的提示词编辑 -->
          <template v-if="dialogForm.executor_kind === 'bot'">
            <el-form-item :label="getPromptLabel(dialogForm)">
              <template v-if="dialogMode !== 'view'">
                <el-input v-model="botTaskData.user_prompt" type="textarea" :rows="8" placeholder="输入用户提示..." />
              </template>
              <template v-else>
                <div class="prompt-text-view">{{ botTaskData.user_prompt || dialogForm.prompt_text || '-' }}</div>
              </template>
            </el-form-item>
            <!-- 显示组装后的 JSON（仅在编辑模式下可选显示） -->
            <template v-if="dialogMode !== 'view'">
              <el-form-item label="组装后 JSON">
                <div class="prompt-text-view">{{ buildBotTaskPrompt() }}</div>
              </el-form-item>
            </template>
          </template>
          <!-- 其他任务的提示词编辑 -->
          <template v-else>
            <el-form-item :label="getPromptLabel(dialogForm)">
              <template v-if="dialogMode !== 'view'">
                <el-input v-model="dialogForm.prompt_text" type="textarea" :rows="8" />
              </template>
              <template v-else>
                <div class="prompt-text-view">{{ dialogForm.prompt_text || '-' }}</div>
              </template>
            </el-form-item>
          </template>
        </template>

        <template v-if="dialogMode === 'view'">
          <el-form-item label="任务状态">
            <el-tag :type="getStatusTagType(dialogForm.status)" size="small">{{ getStatusLabel(dialogForm.status) }}</el-tag>
          </el-form-item>
          <el-form-item label="创建时间">{{ formatTime(dialogForm.created_at) || '-' }}</el-form-item>
          <el-form-item label="上次执行">{{ formatTime(dialogForm.last_run_at) || '-' }}</el-form-item>
          <el-form-item label="执行结果">
            <div class="result-text">{{ resultText(dialogForm) }}</div>
          </el-form-item>
          <el-form-item v-if="dialogForm.task_type === 'periodic'" label="下次执行">{{ formatTime(dialogForm.next_run_at) || '-' }}</el-form-item>
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">
            {{ dialogMode === 'view' ? '关闭' : '取消' }}
          </el-button>
          <el-button
            v-if="dialogMode === 'view' && canTrigger(dialogForm)"
            type="success"
            :loading="isTriggerLoading(dialogForm)"
            @click="dialogForm.status === 'failed' ? handleRetry(dialogForm) : handleTrigger()"
          >
            {{ dialogForm.status === 'failed' ? '重试' : '立即执行' }}
          </el-button>
          <el-button
            v-if="dialogMode !== 'view'"
            type="primary"
            :loading="dialogSaving"
            @click="handleDialogSave"
          >
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>
