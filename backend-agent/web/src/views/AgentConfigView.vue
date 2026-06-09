<script setup>
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { QuestionFilled } from '@element-plus/icons-vue'
import { batchDeleteAgents, getAgent, getAgentCapabilities, getAgentProviderSchemas } from '../api/runtime'
import { useRuntimeConsole } from '../composables/useRuntimeConsole'
import { formatTime } from '../utils/format'

const props = defineProps({
  agents: {
    type: Array,
    default: () => [],
  },
})

const {
  loadingAgents,
  savingAgent,
  loadAgents,
  handleSaveAgent,
  handleToggleAgent,
  handleTestAgent,
  pagination,
} = useRuntimeConsole()

const dialogVisible = ref(false)
const isEdit = ref(false)
const editingAgent = ref(null)
const originalApiKeyCipher = ref('')
const keyword = ref('')
const selectedAgents = ref([])
const tableRef = ref(null)
const isLoadingEditData = ref(false)
const loadingSearch = ref(false)
const loadingEditDialog = ref(false)
const pageLoading = ref(false)
const tableLoading = ref(false)
const detectedCapabilities = ref(null)
const capabilityDetecting = ref(false)
const capabilityDetectionFailed = ref(false)
const providerSchemas = ref({})
const lastAutoCapabilitiesJson = ref('')
const lastDetectedModelSignature = ref('')
let detectTimer = 0

const PROVIDER_DEFAULTS = {
  temperature: 0.2,
  timeout_seconds: 60,
  max_retries: 1,
  reasoning_effort: '',
}

const providerTypes = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'claude', label: 'Claude (Anthropic)' },
  { value: 'gemini', label: 'Gemini (Google)' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'dashscope', label: 'DashScope (通义千问)' },
  { value: 'zhipu', label: '智谱 GLM' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'moonshot', label: 'Kimi (Moonshot)' },
  { value: 'openai_compatible', label: '自定义 / 本地模型' },
]

const reasoningEffortOptions = [
  { value: '', label: '关闭思考' },
  { value: 'low', label: '低思考强度' },
  { value: 'medium', label: '中思考强度' },
  { value: 'high', label: '高思考强度' },
]

const SYSTEM_MANAGED_MODEL_PARAM_KEYS = ['max_tokens', 'max_output_tokens', 'max_completion_tokens']
const noBaseUrlTypes = ['openai', 'dashscope', 'zhipu', 'minimax', 'claude', 'gemini', 'deepseek']
const providerModelDocs = {
  openai: 'https://platform.openai.com/docs/api-reference',
  claude: 'https://docs.anthropic.com/en/docs/about-claude/models',
  gemini: 'https://ai.google.dev/gemini-api/docs/models/gemini',
  deepseek: 'https://api-docs.deepseek.com/',
  dashscope: 'https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-calling-api',
  zhipu: 'https://bigmodel.cn/dev/api/normal-model/glm-4',
  minimax: 'https://platform.minimaxi.com/docs/api-reference/api-overview',
  moonshot: 'https://platform.kimi.com/docs/api/overview',
  openai_compatible: '',
}

watch(
  () => props.agents,
  () => {
    tableRef.value?.clearSelection?.()
  },
)

const editingAgentMountedBots = computed(() => {
  return Array.isArray(editingAgent.value?.mounted_bot_names) ? editingAgent.value.mounted_bot_names : []
})

const currentProviderSchema = computed(() => {
  return providerSchemas.value[editingAgent.value?.provider_type] || { fields: [], description: '' }
})

const customParamsHelpText = computed(() => {
  const providerType = editingAgent.value?.provider_type || ''
  const defaultText = `${currentProviderSchema.value.description || '透传给 Provider API 的附加参数。'} 上方控件会同步写入这里，也可以直接手工编辑 JSON。仅保留有值字段；不要手动填写空对象、空数组或无效参数。最大输出 token 统一由系统设置管理，不要在此填写 max_tokens、max_output_tokens 或 max_completion_tokens。`
  if (providerType === 'dashscope') {
    return 'DashScope / 百炼参数会透传给模型调用。上方控件会同步写入这里，也可以直接手工编辑 JSON；未填写的字段不会透传。最大输出 token 统一由系统设置管理。'
  }
  if (providerType === 'openai') {
    return 'OpenAI 参数会直接透传给模型调用。上方控件会同步写入这里，也可以直接手工编辑 JSON；未填写的字段不会透传。最大输出 token 统一由系统设置管理。'
  }
  if (providerType === 'openai_compatible') {
    return '自定义 / 本地模型建议仅在 JSON 中传入目标 API 确定支持的参数。上方控件会同步写入 JSON；未填写的字段不会透传。最大输出 token 统一由系统设置管理。'
  }
  if (providerType === 'claude') {
    return 'Claude 仅建议传官方明确支持的参数，例如 `top_p`、`top_k`。未填写的字段不会透传。'
  }
  if (providerType === 'gemini') {
    return 'Gemini 建议仅传官方明确支持的生成参数，例如 `top_p`、`top_k`。未填写的字段不会透传；最大输出 token 统一由系统设置管理。'
  }
  if (providerType === 'zhipu') {
    return '智谱 GLM 建议仅传官方明确支持的参数。未填写的字段不会透传。'
  }
  return defaultText
})

function createEmptyAgent(providerKey = '') {
  return {
    provider_key: providerKey,
    label: '',
    provider_type: providerTypes[0].value,
    provider_name: '',
    model: '',
    base_url: '',
    api_key: '',
    temperature: PROVIDER_DEFAULTS.temperature,
    timeout_seconds: PROVIDER_DEFAULTS.timeout_seconds,
    max_retries: PROVIDER_DEFAULTS.max_retries,
    reasoning_effort: PROVIDER_DEFAULTS.reasoning_effort,
    model_kwargs_json: '',
    capabilities_json: '',
    built_in_tools_json: '',
    is_active: false,
    mounted_bot_names: [],
    mounted_bot_keys: [],
    mounted_bot_count: 0,
    is_bound_to_bot: false,
    is_platform_agent: false,
    platform_agent_task_count: 0,
    platform_agent_task_names: [],
    last_test_status: '',
    last_test_time: '',
    last_test_trace_id: '',
  }
}

function parseJsonObject(text) {
  const raw = String(text || '').trim()
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function parseBuiltinTools(text) {
  const raw = String(text || '').trim()
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function builtinToolEnabled(toolType) {
  if (!editingAgent.value) return false
  return parseBuiltinTools(editingAgent.value.built_in_tools_json).some(t => t.type === toolType)
}

function toggleBuiltinTool(toolType, enabled) {
  if (!editingAgent.value) return
  let tools = parseBuiltinTools(editingAgent.value.built_in_tools_json)
  if (enabled) {
    if (!tools.some(t => t.type === toolType)) {
      tools.push({ type: toolType })
    }
  } else {
    tools = tools.filter(t => t.type !== toolType)
  }
  editingAgent.value.built_in_tools_json = tools.length
    ? JSON.stringify(tools, null, 2)
    : ''
}

function sanitizeJsonText(text, emptyKinds = ['object']) {
  const raw = String(text || '').trim()
  if (!raw) return ''
  try {
    const parsed = JSON.parse(raw)
    if (emptyKinds.includes('object') && parsed && typeof parsed === 'object' && !Array.isArray(parsed) && !Object.keys(parsed).length) {
      return ''
    }
    if (emptyKinds.includes('array') && Array.isArray(parsed) && !parsed.length) {
      return ''
    }
    if (parsed == null) {
      return ''
    }
    return JSON.stringify(parsed, null, 2)
  } catch {
    return raw
  }
}

function stringifyJsonObject(value) {
  const entries = Object.entries(value || {}).filter(([, fieldValue]) => fieldValue !== '' && fieldValue != null)
  if (!entries.length) return ''
  return JSON.stringify(Object.fromEntries(entries), null, 2)
}

function removeSystemManagedModelParams(value = {}) {
  const next = { ...(value || {}) }
  for (const key of SYSTEM_MANAGED_MODEL_PARAM_KEYS) {
    delete next[key]
  }
  return next
}

function sanitizeModelKwargsJson(text) {
  return stringifyJsonObject(removeSystemManagedModelParams(parseJsonObject(text)))
}

function modelKwargsObject() {
  return removeSystemManagedModelParams(parseJsonObject(editingAgent.value?.model_kwargs_json))
}

function providerFieldValue(fieldKey) {
  return modelKwargsObject()[fieldKey] ?? ''
}

function setProviderFieldValue(fieldKey, value) {
  if (!editingAgent.value) return
  const next = modelKwargsObject()
  if (value === '' || value == null) {
    delete next[fieldKey]
  } else {
    next[fieldKey] = value
  }
  editingAgent.value.model_kwargs_json = stringifyJsonObject(next)
}

function reasoningEffortValue() {
  return providerFieldValue('reasoning_effort') ?? ''
}

function setReasoningEffortValue(value) {
  if (!editingAgent.value) return
  editingAgent.value.reasoning_effort = value
  setProviderFieldValue('reasoning_effort', value)
}

function providerFieldNumberValue(fieldKey) {
  const value = providerFieldValue(fieldKey)
  if (value === '') return undefined
  const num = Number(value)
  return Number.isFinite(num) ? num : undefined
}

function normalizeAgentPayload(agent = {}, fallback = {}) {
  const temperature = Number(agent.temperature)
  const timeoutSeconds = Number(agent.timeout_seconds)
  const maxRetries = Number(agent.max_retries)
  const payload = {
    ...createEmptyAgent(),
    ...fallback,
    ...agent,
    provider_key: agent.provider_key ?? fallback.provider_key ?? '',
    label: agent.label ?? '',
    provider_type: agent.provider_type ?? '',
    provider_name: agent.provider_name ?? '',
    model: agent.model ?? '',
    base_url: agent.base_url ?? '',
    api_key: agent.api_key ?? '',
    temperature: Number.isFinite(temperature) ? temperature : null,
    timeout_seconds: Number.isInteger(timeoutSeconds) ? timeoutSeconds : null,
    max_retries: Number.isInteger(maxRetries) ? maxRetries : null,
    reasoning_effort: agent.reasoning_effort ?? '',
    is_active: Boolean(agent.is_active),
    mounted_bot_names: Array.isArray(agent.mounted_bot_names) ? agent.mounted_bot_names : [],
    mounted_bot_keys: Array.isArray(agent.mounted_bot_keys) ? agent.mounted_bot_keys : [],
    mounted_bot_count: Number(agent.mounted_bot_count || 0),
    is_bound_to_bot: Boolean(agent.is_bound_to_bot),
    is_platform_agent: Boolean(agent.is_platform_agent),
    platform_agent_task_count: Number(agent.platform_agent_task_count || 0),
    platform_agent_task_names: Array.isArray(agent.platform_agent_task_names) ? agent.platform_agent_task_names : [],
    last_test_status: agent.last_test_status ?? '',
    last_test_time: agent.last_test_time ?? '',
    last_test_trace_id: agent.last_test_trace_id ?? '',
    built_in_tools_json: agent.built_in_tools_json ?? '',
  }
  payload.model_kwargs_json = sanitizeModelKwargsJson(payload.model_kwargs_json)
  
  // 从 model_kwargs_json 中读取 reasoning_effort 并初始化到编辑对象中
  if (agent.model_kwargs_json) {
    try {
      const kwargs = removeSystemManagedModelParams(JSON.parse(agent.model_kwargs_json))
      if (kwargs.reasoning_effort) {
        payload.reasoning_effort = kwargs.reasoning_effort
      }
    } catch {
      // 忽略解析错误
    }
  }
  
  return payload
}

function isMountedByBot(agent) {
  return Boolean(agent?.is_bound_to_bot)
}

function isPlatformAgent(agent) {
  return props.platformSettings?.platform_agent_provider === agent?.provider_key
}

function canSelectAgent(row) {
  return !isMountedByBot(row)
}

function isAgentRestricted(agent) {
  return isEdit.value && (isMountedByBot(agent) || isPlatformAgent(agent))
}

function modelPlaceholder() {
  if (!editingAgent.value) return '输入模型名'
  if (editingAgent.value.provider_type === 'openai') return '例如：gpt-4.1-mini'
  if (editingAgent.value.provider_type === 'claude') return '例如：claude-sonnet-4-5'
  if (editingAgent.value.provider_type === 'gemini') return '例如：gemini-2.5-flash'
  if (editingAgent.value.provider_type === 'deepseek') return '例如：deepseek-chat'
  if (editingAgent.value.provider_type === 'dashscope') return '例如：qwen-plus'
  return '输入自定义或本地模型名'
}

function modelDocsUrl() {
  return providerModelDocs[editingAgent.value?.provider_type] || ''
}

function handleProviderTypeChange() {
  if (editingAgent.value) {
    editingAgent.value.model = ''
    editingAgent.value.api_key = ''
    editingAgent.value.provider_name = ''
    if (noBaseUrlTypes.includes(editingAgent.value.provider_type)) {
      editingAgent.value.base_url = ''
    }
  }
  detectedCapabilities.value = null
  capabilityDetectionFailed.value = false
  lastAutoCapabilitiesJson.value = ''
  lastDetectedModelSignature.value = ''
}

function currentModelSignature() {
  return `${editingAgent.value?.provider_type || ''}::${editingAgent.value?.model || ''}`
}

function resetCapabilityDetectionState() {
  detectedCapabilities.value = null
  capabilityDetectionFailed.value = false
}

function shouldReplaceCapabilitiesJson() {
  const current = editingAgent.value?.capabilities_json?.trim() || ''
  return !current || current === lastAutoCapabilitiesJson.value
}

function scheduleDetectCapabilities(force = false) {
  window.clearTimeout(detectTimer)
  detectTimer = window.setTimeout(() => {
    detectCapabilities(force)
  }, 2000)
}

async function detectCapabilities(force = false) {
  if (!editingAgent.value?.model || !editingAgent.value?.provider_type) {
    resetCapabilityDetectionState()
    lastDetectedModelSignature.value = ''
    return
  }
  if (!force && editingAgent.value.capabilities_json?.trim()) {
    resetCapabilityDetectionState()
    return
  }
  capabilityDetecting.value = true
  capabilityDetectionFailed.value = false
  const signature = currentModelSignature()
  try {
    const result = await getAgentCapabilities(editingAgent.value.model, editingAgent.value.provider_type)
    detectedCapabilities.value = result
    lastDetectedModelSignature.value = signature
    const detectedJson = buildDetectedCapabilitiesJson(result)
    lastAutoCapabilitiesJson.value = detectedJson
    if (shouldReplaceCapabilitiesJson()) {
      editingAgent.value.capabilities_json = detectedJson
    }
    if (!result.auto_detected) {
      capabilityDetectionFailed.value = true
      ElMessage.warning({
        message: `模型 "${editingAgent.value.model}" 未在能力注册表中找到，已回退到提供商默认能力（仅文本）。如需启用多模态，请手动填写模型能力。`,
        duration: 6000,
      })
    }
  } catch {
    detectedCapabilities.value = null
    capabilityDetectionFailed.value = true
    lastDetectedModelSignature.value = signature
    ElMessage.warning({
      message: `模型 "${editingAgent.value.model}" 能力自动检测失败，多模态输入已禁用。如需启用，请手动填写模型能力。`,
      duration: 6000,
    })
  } finally {
    capabilityDetecting.value = false
  }
}

function isMultimodalSupported() {
  if (editingAgent.value?.capabilities_json?.trim()) return true
  if (capabilityDetectionFailed.value) return false
  if (!detectedCapabilities.value) return false
  const caps = detectedCapabilities.value.capabilities || []
  return caps.some((cap) => ['IMAGE_INPUT', 'VIDEO_INPUT', 'DOCUMENT_INPUT', 'AUDIO_INPUT'].includes(cap))
}

function buildDetectedCapabilitiesJson(result = detectedCapabilities.value) {
  if (!result) return ''
  const caps = Array.isArray(result.capabilities)
    ? result.capabilities
    : []
  if (!caps.length) return ''
  return JSON.stringify(caps, null, 2)
}

async function openCreateDialog() {
  isEdit.value = false
  originalApiKeyCipher.value = ''
  editingAgent.value = null
  dialogVisible.value = true
  await new Promise((resolve) => setTimeout(resolve, 0))
  editingAgent.value = createEmptyAgent()
  scheduleDetectCapabilities(true)
}

async function openEditDialog(agent) {
  if (loadingEditDialog.value) return
  isEdit.value = true
  originalApiKeyCipher.value = ''
  editingAgent.value = null
  dialogVisible.value = true

  await new Promise((resolve) => setTimeout(resolve, 0))
  loadingEditDialog.value = true
  isLoadingEditData.value = true

  try {
    const freshAgent = await getAgent(agent.provider_key)
    if (freshAgent) {
      originalApiKeyCipher.value = String(freshAgent.api_key || '')
      editingAgent.value = normalizeAgentPayload(freshAgent, { provider_key: agent.provider_key })
      // 确保 reasoning_effort 从 model_kwargs_json 正确同步
      if (editingAgent.value.model_kwargs_json) {
        try {
          const kwargs = removeSystemManagedModelParams(JSON.parse(editingAgent.value.model_kwargs_json))
          if (kwargs.reasoning_effort) {
            editingAgent.value.reasoning_effort = kwargs.reasoning_effort
          }
        } catch {
          // 忽略解析错误
        }
      }
      scheduleDetectCapabilities(true)
    }
  } catch (error) {
    ElMessage.error(`获取 Agent 数据失败：${error?.message || error}`)
  } finally {
    isLoadingEditData.value = false
    loadingEditDialog.value = false
  }
}

function getWarningTitle(agent) {
  if (isPlatformAgent(agent)) {
    if (agent.platform_agent_task_count > 0) {
      return `⚠️ 平台 Agent（绑定 ${agent.platform_agent_task_count} 个任务）`
    }
    return '⚠️ 平台 Agent'
  }
  return `⚠️ Agent 已被 ${agent.mounted_bot_count} 个 Bot 挂载`
}

function closeDialog() {
  dialogVisible.value = false
  loadingEditDialog.value = false
  setTimeout(() => {
    editingAgent.value = null
    originalApiKeyCipher.value = ''
    resetCapabilityDetectionState()
    lastAutoCapabilitiesJson.value = ''
    lastDetectedModelSignature.value = ''
    window.clearTimeout(detectTimer)
  }, 100)
}

async function saveAgent() {
  if (!editingAgent.value) return
  if (!editingAgent.value.label) {
    ElMessage.error('请输入名称')
    return
  }
  if (!editingAgent.value.provider_type) {
    ElMessage.error('请选择 Agent 调用类型')
    return
  }
  if (!editingAgent.value.model) {
    ElMessage.error('请输入模型名')
    return
  }
  if (!isEdit.value && !editingAgent.value.api_key) {
    ElMessage.error('请输入 API Key')
    return
  }
  if (!noBaseUrlTypes.includes(editingAgent.value.provider_type) && !editingAgent.value.base_url) {
    ElMessage.error('请输入 Base URL')
    return
  }

  const agentToSave = { ...editingAgent.value }
  if (agentToSave.temperature != null && agentToSave.temperature !== '') {
    agentToSave.temperature = Number(agentToSave.temperature)
  }
  if (agentToSave.timeout_seconds != null && agentToSave.timeout_seconds !== '') {
    agentToSave.timeout_seconds = Number(agentToSave.timeout_seconds)
  }
  if (agentToSave.max_retries != null && agentToSave.max_retries !== '') {
    agentToSave.max_retries = Number(agentToSave.max_retries)
  }

  // 将 reasoning_effort 保存到 model_kwargs_json 中
  let modelKwargs = {}
  if (agentToSave.model_kwargs_json) {
    try {
      modelKwargs = removeSystemManagedModelParams(JSON.parse(agentToSave.model_kwargs_json))
    } catch {
      // 解析失败时使用空对象
    }
  }
  if (agentToSave.reasoning_effort) {
    modelKwargs.reasoning_effort = agentToSave.reasoning_effort
  } else {
    modelKwargs.reasoning_effort = ""
  }
  agentToSave.model_kwargs_json = JSON.stringify(modelKwargs, null, 2)

  agentToSave.model_kwargs_json = sanitizeJsonText(agentToSave.model_kwargs_json, ['object'])
  agentToSave.capabilities_json = sanitizeJsonText(agentToSave.capabilities_json, ['array'])
  if (!agentToSave.capabilities_json || !agentToSave.capabilities_json.trim()) {
    const detectedCapsJson = buildDetectedCapabilitiesJson()
    if (detectedCapsJson) {
      agentToSave.capabilities_json = detectedCapsJson
    }
  }
  agentToSave.capabilities_json = sanitizeJsonText(agentToSave.capabilities_json, ['array'])
  if (!agentToSave.capabilities_json) {
    delete agentToSave.capabilities_json
  }
  agentToSave.built_in_tools_json = sanitizeJsonText(agentToSave.built_in_tools_json, ['array'])
  if (!agentToSave.built_in_tools_json) {
    delete agentToSave.built_in_tools_json
  }

  if (isEdit.value) {
    if (agentToSave.api_key === originalApiKeyCipher.value) {
      delete agentToSave.api_key
    } else if (!agentToSave.api_key) {
      ElMessage.error('请输入新的 API Key')
      return
    }
    if (!isMountedByBot(agentToSave)) {
      agentToSave.is_active = false
      agentToSave.last_test_status = ''
      agentToSave.last_test_time = ''
      agentToSave.last_test_trace_id = ''
    }
  }

  const success = await handleSaveAgent(agentToSave, isEdit.value ? 'edit' : 'new')
  if (success) {
    closeDialog()
  }
}

async function handlePageChange(page) {
  await loadAgents(page, pagination.page_size, keyword.value)
}

async function handleSizeChange(size) {
  await loadAgents(1, size, keyword.value)
}

async function testConnection(agent) {
  tableLoading.value = true
  try {
    await handleTestAgent(agent.provider_key)
  } finally {
    tableLoading.value = false
  }
}

async function toggleAgent(agent) {
  if (isMountedByBot(agent)) {
    ElMessage.warning('已被 Bot 挂载的 Agent 不可停用')
    return
  }
  const newIsActive = !agent.is_active
  tableLoading.value = true
  try {
    const success = await handleToggleAgent(agent.provider_key, newIsActive)
    if (success) {
      ElMessage.success(newIsActive ? 'Agent 已启用' : 'Agent 已停用')
    }
  } finally {
    tableLoading.value = false
  }
}

function handleSelectionChange(selection) {
  selectedAgents.value = selection
}

async function handleSearch() {
  loadingSearch.value = true
  try {
    await loadAgents(1, pagination.page_size, keyword.value)
  } catch {
    ElMessage.error('搜索失败')
  } finally {
    loadingSearch.value = false
  }
}

async function loadProviderSchemas() {
  try {
    providerSchemas.value = await getAgentProviderSchemas()
  } catch (error) {
    ElMessage.error(`获取 Provider 参数配置失败：${error?.message || error}`)
  }
}

async function batchDelete() {
  if (!selectedAgents.value.length) {
    ElMessage.warning('请先选择要删除的 Agent')
    return
  }

  const hasRestrictedAgent = selectedAgents.value.some((agent) => isMountedByBot(agent))
  if (hasRestrictedAgent) {
    ElMessage.warning('选中的 Agent 中包含已被 Bot 挂载，无法删除')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedAgents.value.length} 条 Agent 配置吗？`,
      '确认删除',
      {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )

    const providerKeys = selectedAgents.value.map((agent) => agent.provider_key)
    const result = await batchDeleteAgents(providerKeys)
    ElMessage.success(`成功删除 ${result.deleted_count} 条 Agent 配置`)
    await loadAgents(pagination.page, pagination.page_size, keyword.value)
    selectedAgents.value = []
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = error?.message || '删除失败'
      ElMessageBox.alert(errorMsg, '删除失败', {
        type: 'error',
        confirmButtonText: '确定',
      })
    }
  }
}

onMounted(() => {
  loadProviderSchemas()
  loadAgents(1, 10)
})

onActivated(() => {
  loadProviderSchemas()
  loadAgents(1, 10)
})

watch(
  () => [dialogVisible.value, editingAgent.value?.provider_type, editingAgent.value?.model],
  ([visible, providerType, model], [, prevProviderType, prevModel]) => {
    if (!visible || !editingAgent.value) return
    if (!providerType || !model) {
      resetCapabilityDetectionState()
      return
    }
    if (providerType === prevProviderType && model === prevModel) return
    if (shouldReplaceCapabilitiesJson()) {
      editingAgent.value.capabilities_json = ''
    }
    resetCapabilityDetectionState()
    scheduleDetectCapabilities(true)
  },
)
</script>

<template>
  <div class="agent-config" v-loading="pageLoading">
    <div class="header">
      <h2>Agent 配置</h2>
      <div class="actions">
        <el-input
          v-model="keyword"
          placeholder="搜索 Agent 名称、模型或提供方"
          style="width: 260px; margin-right: 10px"
          clearable
          @keyup.enter="handleSearch"
        />
        <el-button type="default" :loading="loadingSearch" @click="handleSearch">查询</el-button>
        <el-button type="primary" @click="openCreateDialog">新增</el-button>
        <el-button type="danger" :disabled="selectedAgents.length === 0" @click="batchDelete">
          删除
        </el-button>
      </div>
    </div>

    <div v-if="loadingAgents" class="loading">正在加载 Agent 配置...</div>

    <div v-else class="table-container">
      <el-table
        ref="tableRef"
        v-loading="tableLoading"
        :data="agents"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" :selectable="canSelectAgent" />
        <el-table-column prop="provider_type" label="模型提供方" width="220">
          <template #default="{ row }">
            <el-tag size="small">
              {{
                (row.provider_type === 'openai_compatible' && row.provider_name)
                  ? row.provider_name
                  : (providerTypes.find((item) => item.value === row.provider_type)?.label || row.provider_type)
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="label" label="名称" width="160" />
        <el-table-column prop="model" label="模型" min-width="220" />
        <el-table-column label="连接状态" width="120">
          <template #default="{ row }">
            <span v-if="row.last_test_status === 'success'" style="color: #67c23a">已连接</span>
            <span v-else style="color: #909399">未连接</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '已启用' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180" prop="created_at">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180" prop="updated_at">
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="380">
          <template #header>
            <div class="operation-header">
              <span>操作</span>
              <el-tooltip content="先新增 Agent，再点击连通性测试，确认可用后再启用。" placement="top">
                <el-icon class="operation-header__icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <template #default="{ row }">
            <el-button type="primary" size="small" link :disabled="loadingEditDialog || isAgentRestricted(row)" @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-button type="warning" size="small" link @click="testConnection(row)">
              测试连接
            </el-button>
            <template v-if="row.is_active">
              <el-button type="primary" size="small" link disabled>启用</el-button>
              <el-button type="danger" size="small" link :disabled="isAgentRestricted(row)" @click="toggleAgent(row)">停用</el-button>
            </template>
            <template v-else>
              <el-button type="primary" size="small" link :disabled="isAgentRestricted(row)" @click="toggleAgent(row)">启用</el-button>
              <el-button type="danger" size="small" link disabled>停用</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!agents.length" class="empty">
        暂无 Agent 配置，点击“新增”创建一条记录。
      </div>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑 Agent' : '新增 Agent'"
      width="980px"
      :close-on-click-modal="false"
      align-center
      top="5vh"
    >
      <el-form
        v-if="editingAgent"
        v-loading="loadingEditDialog"
        element-loading-text="正在加载 Agent 数据..."
        :model="editingAgent"
        label-width="160px"
      >
        <el-alert
          v-if="isMountedByBot(editingAgent) || isPlatformAgent(editingAgent)"
          type="error"
          :closable="false"
          style="margin-bottom: 16px"
          :title="getWarningTitle(editingAgent)"
        >
          <template #default>
            <div v-if="isPlatformAgent(editingAgent)">
              <p style="font-weight: bold; margin-bottom: 8px">该 Agent 为平台 Agent，仅允许编辑名称和 Provider 名称。</p>
              <div v-if="editingAgent.platform_agent_task_count > 0" style="margin-top: 8px">
                <p style="font-weight: bold; margin-bottom: 4px">当前绑定的系统任务：</p>
                <ul style="margin-left: 16px; padding-left: 0; list-style: none">
                  <li v-for="(task, index) in editingAgent.platform_agent_task_names" :key="index" style="padding: 4px 0">
                    • {{ task }}
                  </li>
                </ul>
              </div>
            </div>
            <div v-else>
              <p style="font-weight: bold; margin-bottom: 8px">该 Agent 已被 Bot 挂载，仅允许编辑名称和 Provider 名称。</p>
              <p>挂载的 Bot：{{ editingAgentMountedBots.join(', ') }}</p>
            </div>
          </template>
        </el-alert>

        <el-form-item label="名称">
          <el-input v-model="editingAgent.label" placeholder="展示名称" />
        </el-form-item>

        <el-form-item v-if="editingAgent.provider_type === 'openai_compatible'" label="Provider 名称">
          <el-input v-model="editingAgent.provider_name" placeholder="例如：Ollama、本地网关、自建代理" />
        </el-form-item>

        <el-form-item label="Provider 类型">
          <el-select
            v-model="editingAgent.provider_type"
            placeholder="选择 Agent 调用类型"
            style="width: 100%"
            :disabled="isAgentRestricted(editingAgent)"
            @change="handleProviderTypeChange"
          >
            <el-option
              v-for="type in providerTypes"
              :key="type.value"
              :label="type.label"
              :value="type.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="模型">
          <div class="model-picker" :class="{ 'model-picker--with-help': modelDocsUrl() }">
            <el-input
              v-model="editingAgent.model"
              :placeholder="modelPlaceholder()"
              :disabled="isAgentRestricted(editingAgent)"
              @blur="detectCapabilities"
            />
            <el-tooltip v-if="modelDocsUrl()" content="查看模型文档" placement="top">
              <a
                class="model-help-link"
                :href="modelDocsUrl()"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="查看模型文档"
              >
                <el-icon><QuestionFilled /></el-icon>
              </a>
            </el-tooltip>
          </div>
        </el-form-item>

        <el-form-item v-if="editingAgent && !noBaseUrlTypes.includes(editingAgent.provider_type)" label="Base URL">
          <el-input v-model="editingAgent.base_url" placeholder="输入 Base URL" :disabled="isAgentRestricted(editingAgent)" />
        </el-form-item>

        <el-form-item label="API Key">
          <el-input
            v-model="editingAgent.api_key"
            type="password"
            show-password
            placeholder="输入 API Key"
            :disabled="isAgentRestricted(editingAgent)"
          />
        </el-form-item>

        <el-form-item label="温度">
          <el-input-number
            v-model="editingAgent.temperature"
            :min="0"
            :max="1"
            :step="0.1"
            :precision="1"
            style="width: 100%"
            :disabled="isAgentRestricted(editingAgent)"
          />
        </el-form-item>

        <el-form-item label="超时（秒）">
          <el-input-number
            v-model="editingAgent.timeout_seconds"
            :min="1"
            :max="300"
            style="width: 100%"
            :disabled="isAgentRestricted(editingAgent)"
          />
        </el-form-item>

        <el-form-item label="重试次数">
          <el-input-number
            v-model="editingAgent.max_retries"
            :min="0"
            :max="10"
            style="width: 100%"
            :disabled="isAgentRestricted(editingAgent)"
          />
        </el-form-item>

        <el-form-item label="思考强度">
          <el-select
            :model-value="reasoningEffortValue()"
            placeholder="选择思考强度"
            style="width: 100%"
            :disabled="isAgentRestricted(editingAgent)"
            clearable
            @update:model-value="(value) => setReasoningEffortValue(value || '')"
          >
            <el-option
              v-for="option in reasoningEffortOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="form-item-tip">
            控制模型的思考强度。关闭思考时将使用标准模式。仅支持思考能力的模型（如 OpenAI o 系列）。
          </div>
        </el-form-item>

        <el-divider content-position="left">高级参数</el-divider>

        <template v-if="currentProviderSchema.fields.length">
          <el-form-item
            v-for="field in currentProviderSchema.fields"
            :key="field.key"
            :label="field.label"
          >
            <el-select
              v-if="field.kind === 'select'"
              :model-value="providerFieldValue(field.key)"
              placeholder="留空表示不设置"
              style="width: 100%"
              :disabled="isAgentRestricted(editingAgent)"
              clearable
              @update:model-value="(value) => setProviderFieldValue(field.key, value || '')"
            >
              <el-option
                v-for="option in field.options || []"
                :key="option"
                :label="option"
                :value="option"
              />
            </el-select>
            <el-input-number
              v-else-if="field.kind === 'number' || field.kind === 'integer'"
              :model-value="providerFieldNumberValue(field.key)"
              :min="field.min"
              :max="field.max"
              :step="field.step || 1"
              :precision="field.kind === 'integer' ? 0 : 2"
              style="width: 100%"
              :disabled="isAgentRestricted(editingAgent)"
              @update:model-value="(value) => setProviderFieldValue(field.key, value ?? '')"
            />
            <el-switch
              v-else-if="field.kind === 'boolean'"
              :model-value="Boolean(providerFieldValue(field.key))"
              :disabled="isAgentRestricted(editingAgent)"
              @update:model-value="(value) => setProviderFieldValue(field.key, value)"
            />
            <el-input
              v-else-if="field.kind !== 'builtin_tools'"
              :model-value="providerFieldValue(field.key)"
              :placeholder="field.placeholder || '留空表示不设置'"
              :disabled="isAgentRestricted(editingAgent)"
              @update:model-value="(value) => setProviderFieldValue(field.key, value)"
            />
            <template v-else-if="field.kind === 'builtin_tools'">
              <el-form-item label="Web 搜索">
                <el-switch
                  :model-value="builtinToolEnabled('web_search_preview')"
                  :disabled="isAgentRestricted(editingAgent)"
                  @update:model-value="(v) => toggleBuiltinTool('web_search_preview', v)"
                />
                <div class="form-item-tip">启用后模型可调用 OpenAI 内置 Web 搜索。仅官方 OpenAI API 支持。</div>
              </el-form-item>
              <el-form-item label="文件搜索">
                <el-switch
                  :model-value="builtinToolEnabled('file_search')"
                  :disabled="isAgentRestricted(editingAgent)"
                  @update:model-value="(v) => toggleBuiltinTool('file_search', v)"
                />
                <div class="form-item-tip">启用后模型可搜索已上传的文件。需在 OpenAI 平台配置向量库。</div>
              </el-form-item>
              <el-form-item label="代码解释器">
                <el-switch
                  :model-value="builtinToolEnabled('code_interpreter')"
                  :disabled="isAgentRestricted(editingAgent)"
                  @update:model-value="(v) => toggleBuiltinTool('code_interpreter', v)"
                />
                <div class="form-item-tip">启用后模型可执行代码并返回结果。</div>
              </el-form-item>
              <div v-if="field.help" class="form-item-tip">{{ field.help }}</div>
            </template>
            <div v-if="field.help" class="form-item-tip">
              {{ field.help }}
            </div>
          </el-form-item>
        </template>

        <el-form-item label="自定义参数">
          <el-input
            v-model="editingAgent.model_kwargs_json"
            type="textarea"
            :rows="3"
            placeholder='留空则不透传。示例：&#10;{&#10;  "reasoning_effort": "high",&#10;  "top_p": 0.9&#10;}'
            :disabled="isAgentRestricted(editingAgent)"
          />
          <div class="form-item-tip">
            {{ customParamsHelpText }}
          </div>
        </el-form-item>

        <el-form-item label="模型能力">
          <el-input
            v-model="editingAgent.capabilities_json"
            type="textarea"
            :rows="2"
            placeholder='留空则自动检测。示例：&#10;["IMAGE_INPUT", "TOOL_CALLING"]'
            :disabled="isAgentRestricted(editingAgent)"
          />
          <div class="form-item-tip">
            可选值包括：`IMAGE_INPUT`、`VIDEO_INPUT`、`DOCUMENT_INPUT`、`AUDIO_INPUT`、`TOOL_CALLING`。
          </div>
          <div v-if="capabilityDetecting" class="form-item-tip form-item-tip--info">正在检测模型能力...</div>
          <div v-else-if="capabilityDetectionFailed" class="form-item-tip form-item-tip--warn">
            自动检测失败，多模态输入已禁用。如需启用，请手动填写模型能力。
          </div>
          <div v-else-if="detectedCapabilities && !detectedCapabilities.auto_detected" class="form-item-tip form-item-tip--warn">
            自动检测未命中注册表，当前按保守能力处理。如需启用多模态，请手动填写模型能力。
          </div>
          <div v-else-if="detectedCapabilities?.auto_detected && isMultimodalSupported()" class="form-item-tip form-item-tip--success">
            已自动检测到该模型支持多模态输入。
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="closeDialog">取消</el-button>
        <el-button type="primary" :loading="savingAgent" :disabled="savingAgent" @click="saveAgent">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
