<script setup>
import { computed, onMounted, onActivated, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { Connection, EditPen, Plus, RefreshRight, Remove, UploadFilled } from '@element-plus/icons-vue'
import {
  deleteMcpServer,
  getMcpServers,
  importMcpServers,
  saveMcpServer,
  testMcpServerConnection,
  toggleMcpServer,
} from '../api/runtime'

const originalConfigFingerprint = ref('')

const MCP_DEFAULTS = {
  server_type: 'stdio',
  transport: 'stdio',
}

function createEmptyServer() {
  return {
    server_id: '',
    name: '',
    server_type: MCP_DEFAULTS.server_type,
    config: {
      transport: MCP_DEFAULTS.transport,
      command: '',
      args: [],
      url: '',
      headers: {},
    },
    tools: [],
    is_active: false,
  }
}

const servers = ref([])
const dialogVisible = ref(false)
const dialogMode = ref('new')
const editingServer = ref(createEmptyServer())
const importJson = ref('')
const pageLoading = ref(false)
const dialogLoading = ref(false)
const headerRows = ref([])

const sortedServers = computed(() => {
  return [...servers.value].sort((a, b) => {
    const aIsSystem = isSystemServer(a)
    const bIsSystem = isSystemServer(b)
    if (aIsSystem && !bIsSystem) return -1
    if (!aIsSystem && bIsSystem) return 1
    return 0
  })
})

const mcpTypes = [
  { value: 'stdio', label: '标准输入输出 (stdio)' },
  { value: 'http', label: 'HTTP 服务' },
  { value: 'sse', label: 'SSE' },
  { value: 'streamable_http', label: 'Streamable HTTP' },
]

const dialogTitle = computed(() => {
  if (dialogMode.value === 'new') return '新增 MCP 服务'
  if (dialogMode.value === 'import') return '导入 MCP 服务'
  if (isSystemServer(editingServer.value)) return '查看 MCP 服务'
  return '编辑 MCP 服务'
})

const activeTypeLabel = computed(() => {
  return mcpTypes.find((item) => item.value === editingServer.value.server_type)?.label || editingServer.value.server_type
})

const dialogTools = computed(() => {
  return Array.isArray(editingServer.value.tools) ? editingServer.value.tools : []
})

function isMountedByBot(server) {
  return Boolean(server?.is_bound_to_bot)
}

function isSystemServer(server) {
  return server?.scope === 'system'
}

function mountedBotText(server) {
  return (server?.mounted_bot_names || []).join(', ')
}

function buildConfigFingerprint(server) {
  return JSON.stringify({
    server_type: server?.server_type || 'stdio',
    config: {
      command: server?.config?.command || '',
      args: Array.isArray(server?.config?.args) ? server.config.args : [],
      url: server?.config?.url || '',
      headers: server?.config?.headers && typeof server.config.headers === 'object' ? server.config.headers : {},
    },
  })
}

function createHeaderRow(key = '', value = '') {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    key,
    value,
  }
}

function cloneServer(server) {
  const source = server ? JSON.parse(JSON.stringify(server)) : createEmptyServer()
  return {
    server_id: source.server_id || '',
    name: source.name || '',
    server_type: source.server_type || 'stdio',
    config: {
      transport: source.config?.transport || source.server_type || 'stdio',
      command: source.config?.command || '',
      args: Array.isArray(source.config?.args) ? [...source.config.args] : [],
      url: source.config?.url || '',
      headers: source.config?.headers && typeof source.config.headers === 'object' ? { ...source.config.headers } : {},
    },
    tools: Array.isArray(source.tools) ? source.tools : [],
    is_active: Boolean(source.is_active),
  }
}

function syncHeaderRowsFromConfig() {
  const headers = editingServer.value.config?.headers || {}
  const entries = Object.entries(headers)
  headerRows.value = entries.length ? entries.map(([key, value]) => createHeaderRow(key, String(value || ''))) : [createHeaderRow()]
}

function syncTransportFromType() {
  if (!editingServer.value.config) {
    editingServer.value.config = {}
  }
  editingServer.value.config.transport = editingServer.value.server_type
}

function openNewDialog() {
  dialogMode.value = 'new'
  editingServer.value = cloneServer(null)
  originalConfigFingerprint.value = buildConfigFingerprint(editingServer.value)
  importJson.value = ''
  syncHeaderRowsFromConfig()
  dialogVisible.value = true
}

function openImportDialog() {
  dialogMode.value = 'import'
  editingServer.value = cloneServer(null)
  originalConfigFingerprint.value = buildConfigFingerprint(editingServer.value)
  importJson.value = ''
  headerRows.value = []
  dialogVisible.value = true
}

function openEditDialog(server) {
  dialogMode.value = 'edit'
  editingServer.value = cloneServer(server)
  originalConfigFingerprint.value = buildConfigFingerprint(editingServer.value)
  importJson.value = ''
  syncHeaderRowsFromConfig()
  dialogVisible.value = true
}

function closeDialog() {
  dialogVisible.value = false
}

function resetDialogState() {
  editingServer.value = cloneServer(null)
  originalConfigFingerprint.value = ''
  importJson.value = ''
  headerRows.value = []
  dialogLoading.value = false
}

function changeServerType(serverType) {
  editingServer.value.server_type = serverType
  syncTransportFromType()
  if (serverType === 'stdio') {
    editingServer.value.config.url = ''
    editingServer.value.config.headers = {}
    syncHeaderRowsFromConfig()
    return
  }
  editingServer.value.config.command = ''
  editingServer.value.config.args = []
  if (!editingServer.value.config.headers || typeof editingServer.value.config.headers !== 'object') {
    editingServer.value.config.headers = {}
  }
  syncHeaderRowsFromConfig()
}

function addHeaderRow() {
  headerRows.value.push(createHeaderRow())
}

function removeHeaderRow(id) {
  headerRows.value = headerRows.value.filter((row) => row.id !== id)
  if (!headerRows.value.length) {
    headerRows.value.push(createHeaderRow())
  }
}

function normalizeHeaders() {
  const headers = {}
  headerRows.value.forEach((row) => {
    const key = String(row.key || '').trim()
    const value = String(row.value || '').trim()
    if (key) {
      headers[key] = value
    }
  })
  editingServer.value.config.headers = headers
}

function invalidateCurrentTools() {
  if (dialogMode.value !== 'edit') {
    return
  }
  editingServer.value.is_active = false
  editingServer.value.tools = []
}

function normalizeArgs() {
  const args = Array.isArray(editingServer.value.config?.args) ? editingServer.value.config.args : []
  editingServer.value.config.args = args.map((item) => String(item || '').trim()).filter(Boolean)
}

function parseArgsInput(value) {
  editingServer.value.config.args = String(value || '')
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function argsText() {
  return Array.isArray(editingServer.value.config?.args) ? editingServer.value.config.args.join('\n') : ''
}

function buildSavePayload() {
  normalizeHeaders()
  normalizeArgs()
  syncTransportFromType()

  const payload = {
    server_id: editingServer.value.server_id || undefined,
    name: String(editingServer.value.name || '').trim(),
    server_type: editingServer.value.server_type,
    is_active: Boolean(editingServer.value.is_active),
    config: {},
  }

  if (editingServer.value.server_type === 'stdio') {
    payload.config = {
      transport: 'stdio',
      command: String(editingServer.value.config.command || '').trim(),
      args: editingServer.value.config.args || [],
    }
  } else {
    payload.config = {
      transport: editingServer.value.server_type,
      url: String(editingServer.value.config.url || '').trim(),
      headers: editingServer.value.config.headers || {},
    }
  }

  return payload
}

function canEnableServer(server) {
  return Array.isArray(server?.tools) && server.tools.length > 0
}

function formatMcpErrorMessage(error, fallback) {
  const message = error?.message || fallback
  if (message.includes('MCP server name must be unique')) {
    return '服务名称已存在'
  }
  return message
}

async function loadServers() {
  pageLoading.value = true
  try {
    const response = await getMcpServers()
    servers.value = response.servers || []
  } catch (error) {
    ElMessage.error(formatMcpErrorMessage(error, '加载 MCP 服务列表失败'))
  } finally {
    pageLoading.value = false
  }
}

async function handleImport() {
  try {
    const parsed = JSON.parse(importJson.value)
    dialogLoading.value = true
    const response = await importMcpServers(parsed)
    ElMessage.success(`成功导入 ${response.imported?.length || 0} 个 MCP 服务`)
    closeDialog()
    await loadServers()
  } catch (error) {
    if (error instanceof SyntaxError) {
      ElMessage.error('JSON 解析失败，请检查格式')
    } else {
      ElMessage.error(formatMcpErrorMessage(error, '导入失败'))
    }
  } finally {
    dialogLoading.value = false
  }
}

async function handleSaveServer() {
  const payload = buildSavePayload()
  if (!payload.name) {
    ElMessage.warning('请输入服务名称')
    return
  }

  if (payload.server_type === 'stdio' && !payload.config.command) {
    ElMessage.warning('请输入启动命令')
    return
  }

  if (payload.server_type !== 'stdio' && !payload.config.url) {
    ElMessage.warning('请输入服务 URL')
    return
  }

  dialogLoading.value = true
  try {
    const isEditMode = dialogMode.value === 'edit'
    const response = await saveMcpServer(payload)
    const savedServer = response.server || null

    ElMessage.success('保存成功')
    if (isEditMode && savedServer && !savedServer.is_active && Array.isArray(savedServer.tools) && savedServer.tools.length === 0) {
      ElMessage.info('已自动禁用服务并清空工具列表，请重新刷新工具。')
    }
    closeDialog()
    await loadServers()
  } catch (error) {
    ElMessage.error(formatMcpErrorMessage(error, '保存失败'))
  } finally {
    dialogLoading.value = false
  }
}

async function handleSave() {
  if (dialogMode.value === 'import') {
    await handleImport()
    return
  }
  await handleSaveServer()
}

async function handleDelete(server) {
  try {
    await ElMessageBox.confirm(`确定要删除服务 "${server.name}" 吗？`, '确认删除', {
      type: 'warning',
    })
    pageLoading.value = true
    await deleteMcpServer(server.server_id)
    ElMessage.success('删除成功')
    await loadServers()
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = error?.message || '删除失败'
      ElMessage.error(errorMsg)
    }
  } finally {
    pageLoading.value = false
  }
}

async function handleToggle(server, isActive) {
  pageLoading.value = true
  try {
    let targetServer = server
    if (isActive && !canEnableServer(server)) {
      ElMessage.info('正在刷新工具列表...')
      const testResult = await testMcpServerConnection(server.server_id)
      if (!testResult?.tool_count) {
        throw new Error('未获取到可用工具，请检查服务配置后重试。')
      }
      const response = await getMcpServers()
      servers.value = response.servers || []
      targetServer = servers.value.find((item) => item.server_id === server.server_id) || targetServer
    }
    await toggleMcpServer(targetServer.server_id, isActive)
    ElMessage.success(isActive ? '已启用' : '已禁用')
    await loadServers()
  } catch (error) {
    ElMessage.error(isActive ? `连接测试失败，无法启用：${error.message || '未知错误'}` : (error.message || '操作失败'))
    await loadServers()
  } finally {
    pageLoading.value = false
  }
}

async function refreshServerTools(server) {
  pageLoading.value = true
  try {
    if (dialogVisible.value && dialogMode.value === 'edit' && editingServer.value.server_id === server.server_id) {
      const payload = buildSavePayload()
      if (!payload.name) {
        throw new Error('请先填写服务名称。')
      }
      if (payload.server_type === 'stdio' && !payload.config.command) {
        throw new Error('请先填写启动命令。')
      }
      if (payload.server_type !== 'stdio' && !payload.config.url) {
        throw new Error('请先填写服务 URL。')
      }
      dialogLoading.value = true
      const response = await saveMcpServer(payload)
      editingServer.value = cloneServer(response.server || editingServer.value)
      originalConfigFingerprint.value = buildConfigFingerprint(editingServer.value)
      syncHeaderRowsFromConfig()
      dialogLoading.value = false
    }
    ElMessage.info('正在刷新工具列表...')
    const testResult = await testMcpServerConnection(server.server_id)
    if (!testResult?.tool_count) {
      throw new Error('未获取到可用工具，请检查服务配置后重试。')
    }
    ElMessage.success('工具列表刷新成功')
    await loadServers()
    if (dialogVisible.value && dialogMode.value === 'edit' && editingServer.value.server_id === server.server_id) {
      const refreshed = servers.value.find((item) => item.server_id === server.server_id)
      if (refreshed) {
        editingServer.value = cloneServer(refreshed)
        syncHeaderRowsFromConfig()
      }
    }
  } catch (error) {
    ElMessage.error(`刷新失败：${formatMcpErrorMessage(error, '未知错误')}`)
  } finally {
    pageLoading.value = false
    dialogLoading.value = false
  }
}

watch(
  () => buildConfigFingerprint(editingServer.value),
  (value) => {
    if (!dialogVisible.value || dialogMode.value !== 'edit' || !originalConfigFingerprint.value) {
      return
    }
    if (value !== originalConfigFingerprint.value) {
      invalidateCurrentTools()
    }
  },
)

watch(
  headerRows,
  () => {
    normalizeHeaders()
  },
  { deep: true },
)

onMounted(() => {
  loadServers()
})

onActivated(() => {
  loadServers()
})
</script>

<template>
  <div class="mcp-config-view" v-loading="pageLoading">
    <div class="header">
      <div>
        <h2>MCP 服务配置</h2>
        <p>统一管理服务接入方式、请求参数和工具发现结果。</p>
      </div>
      <div class="actions">
        <el-button :icon="RefreshRight" @click="loadServers">刷新列表</el-button>
        <el-button type="primary" :icon="Plus" @click="openNewDialog">新增服务</el-button>
        <el-button :icon="UploadFilled" @click="openImportDialog">导入配置</el-button>
      </div>
    </div>

    <div class="cards-container">
      <el-card v-for="server in sortedServers" :key="server.server_id" class="mcp-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <div class="server-info">
              <div class="server-title-row">
                <span class="server-name">{{ server.name }}</span>
                <el-tag v-if="isSystemServer(server)" type="warning" size="small">系统</el-tag>
                <el-tag :type="server.is_active ? 'success' : 'info'" size="small">
                  {{ server.is_active ? '已启用' : '已禁用' }}
                </el-tag>
                <el-tag v-if="server.mounted_bot_count" type="danger" size="small">Mounted {{ server.mounted_bot_count }}</el-tag>
              </div>
              <span class="server-subtitle">{{ server.server_type === 'stdio' ? '本地命令服务' : '远程连接服务' }}</span>
            </div>
            <el-switch :model-value="server.is_active" :disabled="isSystemServer(server) || (isMountedByBot(server) && server.is_active)" @change="handleToggle(server, $event)" />
          </div>
        </template>

        <div class="card-body">
          <div class="config-preview">
            <div v-if="server.config?.command" class="config-item">
              <span class="config-label">命令</span>
              <code class="config-value">{{ server.config.command }}</code>
            </div>
            <div v-if="server.config?.args?.length" class="config-item">
              <span class="config-label">参数</span>
              <code class="config-value">{{ server.config.args.join(' ') }}</code>
            </div>
            <div v-if="server.config?.url" class="config-item">
              <span class="config-label">URL</span>
              <span class="config-value text">{{ server.config.url }}</span>
            </div>
          </div>

          <div class="server-type-tags">
            <el-tag type="warning" size="small">
              {{ mcpTypes.find((item) => item.value === server.server_type)?.label || server.server_type }}
            </el-tag>
          </div>

          <div class="tool-summary">
            <span class="tool-count">{{ Array.isArray(server.tools) ? server.tools.length : 0 }} 个工具</span>
            <div class="tools-list" v-if="Array.isArray(server.tools) && server.tools.length">
              <el-tag v-for="tool in server.tools.slice(0, 4)" :key="tool.name" size="small">{{ tool.name }}</el-tag>
              <el-tag v-if="server.tools.length > 4" size="small" type="info">+{{ server.tools.length - 4 }}</el-tag>
            </div>
            <span v-else class="tool-empty">尚未发现工具</span>
          </div>

          <div class="card-footer">
            <el-button size="small" :icon="RefreshRight" @click="refreshServerTools(server)" :disabled="isSystemServer(server)">刷新工具</el-button>
            <div class="footer-actions">
              <el-button size="small" :icon="EditPen" @click="openEditDialog(server)">
                {{ isSystemServer(server) ? '查看' : '编辑' }}
              </el-button>
              <el-button size="small" type="danger" @click="handleDelete(server)" :disabled="isSystemServer(server)">删除</el-button>
            </div>
          </div>
        </div>
      </el-card>

      <div v-if="sortedServers.length === 0" class="mcp-empty-state">
        <el-icon size="64"><Connection /></el-icon>
        <p>暂无 MCP 服务，请点击“新增服务”或“导入配置”</p>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="760px"
      :close-on-click-modal="false"
      align-center
      class="mcp-dialog"
      body-class="mcp-dialog-body"
      :style="{ maxHeight: 'calc(100vh - 48px)' }"
      @closed="resetDialogState"
    >
      <div v-if="dialogMode === 'import'" class="import-content">
        <el-alert type="info" :closable="false">
          导入内容应为 `mcpServers` 对象。系统会按现有规范写入服务配置。
        </el-alert>
        <el-input v-model="importJson" type="textarea" :rows="14" placeholder="请粘贴 JSON 配置" />
      </div>

      <div v-else class="editor-shell" v-loading="dialogLoading">
        <section class="editor-main">
          <el-alert
            v-if="isMountedByBot(editingServer)"
            type="warning"
            :closable="false"
            style="margin-bottom: 16px"
            :title="`Mounted by bots: ${mountedBotText(editingServer)}`"
            description="Only the server name can be edited while this MCP is mounted by bots."
          />
          <div class="section-header">
            <strong>基础配置</strong>
            <span>{{ activeTypeLabel }}</span>
          </div>

          <el-form label-position="top" class="editor-form">
            <div class="form-grid two">
              <el-form-item label="服务名称">
                <el-input v-model="editingServer.name" placeholder="例如：howtocook-mcp" :disabled="isSystemServer(editingServer)" />
              </el-form-item>
              <el-form-item label="服务类型">
                <el-select :model-value="editingServer.server_type" @change="changeServerType" placeholder="请选择服务类型" :disabled="isSystemServer(editingServer)">
                  <el-option v-for="type in mcpTypes" :key="type.value" :label="type.label" :value="type.value" />
                </el-select>
              </el-form-item>
            </div>

            <template v-if="editingServer.server_type === 'stdio'">
              <el-form-item label="启动命令">
                <el-input v-model="editingServer.config.command" placeholder="例如：npx" :disabled="isSystemServer(editingServer)" />
              </el-form-item>
              <el-form-item label="启动参数">
                <el-input
                  type="textarea"
                  :rows="5"
                  :model-value="argsText()"
                  placeholder="每行一个参数，例如：&#10;-y&#10;@modelcontextprotocol/server-filesystem&#10;D:\\workspace"
                  @input="parseArgsInput"
                  :disabled="isMountedByBot(editingServer) || isSystemServer(editingServer)"
                />
              </el-form-item>
            </template>

            <template v-else>
              <el-form-item label="服务 URL">
                <el-input v-model="editingServer.config.url" placeholder="例如：https://example.com/mcp" :disabled="isSystemServer(editingServer)" />
              </el-form-item>

              <div class="headers-panel">
                <div class="section-header">
                  <strong>请求头</strong>
                  <span>可选，按键值对填写</span>
                </div>
                <div class="header-rows">
                  <div v-for="row in headerRows" :key="row.id" class="header-row">
                    <el-input v-model="row.key" placeholder="Header 名称，例如 Authorization" :disabled="isSystemServer(editingServer)" />
                    <el-input v-model="row.value" placeholder="Header 值，例如 Bearer xxx" :disabled="isSystemServer(editingServer)" />
                    <el-button :icon="Remove" circle :disabled="isMountedByBot(editingServer) || isSystemServer(editingServer)" @click="removeHeaderRow(row.id)" />
                  </div>
                </div>
                <el-button class="add-header-btn" :icon="Plus" :disabled="isMountedByBot(editingServer) || isSystemServer(editingServer)" @click="addHeaderRow">新增请求头</el-button>
              </div>
            </template>
          </el-form>
        </section>

        <section class="tools-panel">
          <div class="section-header">
            <strong>工具列表</strong>
            <span>{{ dialogTools.length }} 个</span>
          </div>
          <div v-if="dialogTools.length" class="tool-detail-list">
            <article v-for="tool in dialogTools" :key="tool.name" class="tool-detail-card">
              <div class="tool-detail-head">
                <code>{{ tool.name }}</code>
              </div>
              <p>{{ tool.description || '暂无描述' }}</p>
            </article>
          </div>
          <el-empty v-else description="还没有发现工具，可先保存后执行连通性测试或刷新工具列表。" />
        </section>
      </div>

      <template #footer>
        <el-button @click="closeDialog">
          {{ isSystemServer(editingServer) ? '关闭' : '取消' }}
        </el-button>
        <el-button v-if="!isSystemServer(editingServer)" type="primary" :loading="dialogLoading" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
