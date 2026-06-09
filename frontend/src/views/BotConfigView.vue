<script setup>
import { computed, onBeforeUnmount, onMounted, onActivated, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { QuestionFilled } from '@element-plus/icons-vue'
import { useRuntimeConsole } from '../composables/useRuntimeConsole'
import { getBots, rebindBot, startNamedBot, stopNamedBot } from '../api/runtime'
import { formatTime, getAgentLabel as getAgentLabelUtil, escapeHtml, renderInlineMarkdown } from '../utils/format'
import BotMappingModal from '../components/bot/BotMappingModal.vue'

const {
  bots,
  loadingBots,
  savingBot,
  botPagination,
  loadBotsConfig,
  handleSaveBot,
  handleToggleBot,
  handleDeleteBots,
  handleUnbindBot,
  agents,
  loadAgents,
  botStatuses,
} = useRuntimeConsole()

const dialogVisible = ref(false)
const isEdit = ref(false)
const editingBot = ref(null)
const keyword = ref('')
const selectedBotKeys = ref([])
const loadingEditDialog = ref(false)
const loadingSearch = ref(false)
const pageLoading = ref(false)
const secretInputRef = ref(null)
const originalSecretCipher = ref('')

const bindDialogVisible = ref(false)
const bindingBot = ref(null)
const bindingActionLoading = ref(false)
const bindDialogBusy = ref(false)
const bindDialogCloseReason = ref('')
const BIND_COUNTDOWN_SECONDS = 180
const bindCountdown = ref(BIND_COUNTDOWN_SECONDS)

const activeAgents = computed(() => agents.value.filter((agent) => agent.is_active))
const promptText = computed(() => String(editingBot.value?.system_prompt || ''))
const promptIsMarkdown = computed(() => isMarkdownLike(promptText.value))
const promptPreviewLabel = computed(() => (promptIsMarkdown.value ? 'Markdown' : '文本'))
const promptPreviewHtml = computed(() => (
  promptIsMarkdown.value ? renderMarkdownPreview(promptText.value) : ''
))
const promptPlainPreview = computed(() => promptText.value || ' ')

let bindPollingTimer = null
let bindCountdownTimer = null

const mappingModalVisible = ref(false)
const mappingModalBot = ref(null)
const mappingModalType = ref('skills')

const activeBots = computed(() => bots.value)
const selectableAgents = computed(() => {
  const active = agents.value.filter((agent) => agent.is_active)
  const selectedProviderKey = String(editingBot.value?.agent_provider || '').trim()
  if (!selectedProviderKey) {
    return active
  }
  const current = agents.value.find((agent) => agent.provider_key === selectedProviderKey)
  if (!current || active.some((agent) => agent.provider_key === selectedProviderKey)) {
    return active
  }
  return [current, ...active]
})

function isBotBound(bot) {
  return Boolean(bot?.is_bound)
}

function isBotRunning(bot) {
  if (!bot?.bot_key) return false
  return Boolean(botStatuses.value[bot.bot_key]?.running)
}

function getAgentLabel(providerKey) {
  return getAgentLabelUtil(providerKey, agents.value)
}

function getBindStatusLabel(bot) {
  return isBotBound(bot) ? '已绑定' : '未绑定'
}

function isMarkdownLike(text) {
  const value = String(text || '').trim()
  if (!value) return false
  const lines = value.split(/\r?\n/)
  return lines.some((line, index) => {
    if (/^\s{0,3}#{1,6}\s+\S/.test(line)) return true
    if (/^\s{0,3}(```|~~~)/.test(line)) return true
    if (/^\s{0,3}>\s+\S/.test(line)) return true
    if (/^\s{0,3}[-*+]\s+\S/.test(line)) return true
    if (/^\s{0,3}\d+\.\s+\S/.test(line)) return true
    if (/^\s{0,3}---+\s*$/.test(line)) return true
    if (/\*\*[^*\n]+\*\*/.test(line) || /`[^`\n]+`/.test(line)) return true
    const next = lines[index + 1] || ''
    return line.includes('|') && /^\s*\|?[\s:|-]+\|[\s:|-]+\|?\s*$/.test(next)
  })
}

function parseTableCells(line) {
  const trimmed = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

function isTableSeparator(line) {
  return /^\s*\|?[\s:|-]+\|[\s:|-]+\|?\s*$/.test(String(line || ''))
}

function isBlockStart(line, nextLine = '') {
  return (
    /^\s{0,3}#{1,6}\s+\S/.test(line)
    || /^\s{0,3}(```|~~~)/.test(line)
    || /^\s{0,3}>\s+\S/.test(line)
    || /^\s{0,3}[-*+]\s+\S/.test(line)
    || /^\s{0,3}\d+\.\s+\S/.test(line)
    || /^\s{0,3}---+\s*$/.test(line)
    || (line.includes('|') && isTableSeparator(nextLine))
  )
}

function renderMarkdownPreview(text) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n')
  const html = []
  let index = 0
  let listType = ''
  let inCode = false
  let codeLines = []

  const closeList = () => {
    if (!listType) return
    html.push(`</${listType}>`)
    listType = ''
  }

  while (index < lines.length) {
    const line = lines[index]

    if (/^\s{0,3}(```|~~~)/.test(line)) {
      closeList()
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        inCode = false
      } else {
        inCode = true
      }
      index += 1
      continue
    }

    if (inCode) {
      codeLines.push(line)
      index += 1
      continue
    }

    if (!line.trim()) {
      closeList()
      index += 1
      continue
    }

    const tableNext = lines[index + 1] || ''
    if (line.includes('|') && isTableSeparator(tableNext)) {
      closeList()
      const headers = parseTableCells(line)
      const rows = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(parseTableCells(lines[index]))
        index += 1
      }
      html.push(
        '<table><thead><tr>'
        + headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join('')
        + '</tr></thead><tbody>'
        + rows.map((row) => (
          '<tr>'
          + row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join('')
          + '</tr>'
        )).join('')
        + '</tbody></table>',
      )
      continue
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    if (/^\s{0,3}---+\s*$/.test(line)) {
      closeList()
      html.push('<hr>')
      index += 1
      continue
    }

    const quote = line.match(/^\s{0,3}>\s+(.+)$/)
    if (quote) {
      closeList()
      html.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`)
      index += 1
      continue
    }

    const unordered = line.match(/^\s{0,3}[-*+]\s+(.+)$/)
    if (unordered) {
      if (listType !== 'ul') {
        closeList()
        listType = 'ul'
        html.push('<ul>')
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`)
      index += 1
      continue
    }

    const ordered = line.match(/^\s{0,3}\d+\.\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') {
        closeList()
        listType = 'ol'
        html.push('<ol>')
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`)
      index += 1
      continue
    }

    closeList()
    const paragraph = [line.trim()]
    while (
      index + 1 < lines.length
      && lines[index + 1].trim()
      && !isBlockStart(lines[index + 1], lines[index + 2] || '')
    ) {
      index += 1
      paragraph.push(lines[index].trim())
    }
    html.push(`<p>${paragraph.map(renderInlineMarkdown).join('<br>')}</p>`)
    index += 1
  }

  closeList()
  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  return html.join('')
}

function resetPasswordInput() {
  window.setTimeout(() => {
    const input =
      secretInputRef.value?.$el?.querySelector('input[type="text"], input[type="password"]') || null
    if (input) {
      input.setAttribute('type', 'password')
    }
  }, 0)
}

async function loadPageData() {
  await loadBotsConfig()
  await loadAgents()
}

onMounted(loadPageData)

onActivated(loadPageData)

function openCreateDialog() {
  isEdit.value = false
  originalSecretCipher.value = ''
  editingBot.value = {
    name: '',
    bot_id: '',
    secret: '',
    agent_provider: '',
    system_prompt: '',
    startup_text: '',
    shutdown_text: '',
  }
  dialogVisible.value = true
  resetPasswordInput()
}

async function openEditDialog(bot) {
  if (loadingEditDialog.value) return
  if (isBotRunning(bot)) {
    ElMessage.warning('Bot正在运行中，无法编辑，请先停用')
    return
  }
  isEdit.value = true
  originalSecretCipher.value = ''
  editingBot.value = {
    bot_key: bot.bot_key,
    name: '',
    bot_id: '',
    secret: '',
    agent_provider: '',
    system_prompt: '',
    startup_text: '',
    shutdown_text: '',
  }
  dialogVisible.value = true

  await new Promise((resolve) => window.setTimeout(resolve, 0))
  loadingEditDialog.value = true

  try {
    const freshBot = await getBots({ bot_key: bot.bot_key })
    if (freshBot) {
      originalSecretCipher.value = freshBot.secret || ''
      editingBot.value = {
        ...editingBot.value,
        ...freshBot,
        name: freshBot.name ?? '',
        bot_id: freshBot.bot_id ?? '',
        secret: freshBot.secret ?? '',
        agent_provider: freshBot.agent_provider ?? '',
        system_prompt: freshBot.system_prompt ?? '',
        startup_text: freshBot.startup_text ?? '',
        shutdown_text: freshBot.shutdown_text ?? '',
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300))
    }
  } catch (error) {
    ElMessage.error(`获取 Bot 数据失败：${error.message || error}`)
  } finally {
    loadingEditDialog.value = false
    resetPasswordInput()
  }
}

function closeDialog() {
  dialogVisible.value = false
  loadingEditDialog.value = false
  originalSecretCipher.value = ''
  window.setTimeout(() => {
    editingBot.value = null
    resetPasswordInput()
  }, 100)
}

async function saveBot() {
    if (!editingBot.value) return
    if (!editingBot.value.name) {
      ElMessage.error('请输入 Bot 名称')
      return
    }
    if (!editingBot.value.bot_id) {
      ElMessage.error('请输入 Bot ID')
      return
    }
    if (!editingBot.value.secret) {
      ElMessage.error('请输入 Secret')
      return
    }

    const botToSave = { ...editingBot.value }
    // 确保 agent_provider 为空时是正确的空字符串而不是 null
    if (botToSave.agent_provider === null || botToSave.agent_provider === undefined) {
      botToSave.agent_provider = ''
    }
    if (isEdit.value && botToSave.secret === originalSecretCipher.value) {
      delete botToSave.secret
    }

    const success = await handleSaveBot(botToSave, isEdit.value ? 'edit' : 'new')
    if (success) {
      closeDialog()
    }
  }

async function handlePageChange(page) {
  await loadBotsConfig(page, botPagination.page_size, keyword.value)
}

async function handleSizeChange(size) {
  await loadBotsConfig(1, size, keyword.value)
}

function handleSelectionChange(selection) {
  selectedBotKeys.value = selection.map((bot) => bot.bot_key)
}

async function handleSearch() {
  loadingSearch.value = true
  try {
    await loadBotsConfig(1, botPagination.page_size, keyword.value)
  } catch {
    ElMessage.error('搜索失败')
  } finally {
    loadingSearch.value = false
  }
}

async function batchDelete() {
  if (!selectedBotKeys.value.length) {
    ElMessage.warning('请先选择要删除的 Bot')
    return
  }

  // 检查是否有正在运行的Bot
  const hasRunningBot = selectedBotKeys.value.some((key) => {
    const bot = bots.value.find((b) => b.bot_key === key)
    return bot && isBotRunning(bot)
  })
  if (hasRunningBot) {
    ElMessage.warning('选中的Bot中有正在运行的，无法删除，请先停用')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedBotKeys.value.length} 个 Bot 吗？`,
      '确认删除',
      {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )

    await handleDeleteBots(selectedBotKeys.value)
    selectedBotKeys.value = []
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function toggleBot(bot) {
  pageLoading.value = true
  try {
    const success = await handleToggleBot(bot.bot_key, !bot.is_active)
    if (success) {
      ElMessage.success(!bot.is_active ? 'Bot 已启用' : 'Bot 已禁用')
    }
  } catch (error) {
    ElMessage.error(`操作失败：${error.message || error}`)
  } finally {
    pageLoading.value = false
  }
}

async function doUnbindBot(bot) {
  if (isBotRunning(bot)) {
    ElMessage.warning('Bot正在运行中，无法解绑，请先停用')
    return
  }
  await handleUnbindBot(bot.bot_key)
}

async function refreshSingleBot(botKey) {
  const freshBot = await getBots({ bot_key: botKey })
  const index = bots.value.findIndex((item) => item.bot_key === botKey)
  if (index >= 0) {
    bots.value.splice(index, 1, freshBot)
  }
  return freshBot
}

function stopBindPolling() {
    if (bindPollingTimer) {
        window.clearInterval(bindPollingTimer)
        bindPollingTimer = null
    }
}

function stopBindCountdown() {
    if (bindCountdownTimer) {
        window.clearInterval(bindCountdownTimer)
        bindCountdownTimer = null
    }
}

function startBindCountdown() {
    stopBindCountdown()
    bindCountdown.value = BIND_COUNTDOWN_SECONDS
    bindCountdownTimer = window.setInterval(() => {
        bindCountdown.value--
        if (bindCountdown.value <= 0) {
            stopBindCountdown()
        }
    }, 1000)
}

function formatCountdown(seconds) {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

async function stopBindRuntime(botKey) {
  if (!botKey) return
  try {
    await stopNamedBot(botKey)
  } catch {
    // 忽略关闭绑定长连接时的停止异常
  }
}

async function finishBindSuccess(botKey) {
    bindDialogCloseReason.value = 'success'
    stopBindPolling()
    stopBindCountdown()
    // 停止用于绑定的 Bot 服务
    await stopBindRuntime(botKey)
    bindDialogVisible.value = false
    bindingBot.value = null
    await loadBotsConfig(botPagination.page, botPagination.page_size, keyword.value)
    ElMessage.success('绑定成功')
    bindDialogCloseReason.value = ''
}

function startBindPolling(botKey) {
  stopBindPolling()
  bindPollingTimer = window.setInterval(async () => {
    try {
      // 检查倒计时是否已结束
      if (bindCountdown.value <= 0) {
        bindDialogCloseReason.value = 'failed'
        stopBindPolling()
        stopBindCountdown()
        await stopBindRuntime(botKey)
        bindDialogVisible.value = false
        bindingBot.value = null
        await loadBotsConfig(botPagination.page, botPagination.page_size, keyword.value)
        ElMessage.error('绑定超时，请重试')
        bindDialogCloseReason.value = ''
        return
      }
      
      const bot = await refreshSingleBot(botKey)
      if (isBotBound(bot)) {
        await finishBindSuccess(botKey)
        return
      }
      if (bot?.runtime_status && !bot.runtime_status.running) {
        bindDialogCloseReason.value = 'failed'
        stopBindPolling()
        stopBindCountdown()
        bindDialogVisible.value = false
        bindingBot.value = null
        await loadBotsConfig(botPagination.page, botPagination.page_size, keyword.value)
        ElMessage.error('绑定流程已终止，请仅在个人会话发送 connect mycom')
        bindDialogCloseReason.value = ''
      }
    } catch {
      // 轮询期间忽略瞬时错误，等待下一次刷新
    }
  }, 1500)
}

async function openBindDialog(bot) {
  if (isBotBound(bot) || bindingActionLoading.value) {
    return
  }

  bindingActionLoading.value = true
  try {
    await rebindBot(bot.bot_key)
    await startNamedBot(bot.bot_key, { purpose: 'bind' })
    bindingBot.value = { ...bot }
    bindDialogCloseReason.value = ''
    bindDialogVisible.value = true
    startBindCountdown()
    await refreshSingleBot(bot.bot_key)
    startBindPolling(bot.bot_key)
  } catch (error) {
    await stopBindRuntime(bot.bot_key)
    bindingBot.value = null
    ElMessage.error(`开启绑定流程失败：${error.message || error}`)
  } finally {
    bindingActionLoading.value = false
  }
}

async function closeBindDialogByUser() {
  if (bindDialogBusy.value || !bindingBot.value?.bot_key) {
    return
  }

  bindDialogBusy.value = true
  const botKey = bindingBot.value.bot_key
  try {
    const freshBot = await refreshSingleBot(botKey).catch(() => null)
    if (freshBot && isBotBound(freshBot)) {
      await finishBindSuccess(botKey)
      return
    }

    bindDialogCloseReason.value = 'cancel'
    stopBindPolling()
    stopBindCountdown()
    await stopBindRuntime(botKey)
    bindDialogVisible.value = false
    bindingBot.value = null
    await loadBotsConfig(botPagination.page, botPagination.page_size, keyword.value)
    ElMessage.info('用户已取消')
    bindDialogCloseReason.value = ''
  } finally {
    bindDialogBusy.value = false
  }
}

function handleBindDialogClose() {
  if (
    bindDialogCloseReason.value === 'success'
    || bindDialogCloseReason.value === 'cancel'
    || bindDialogCloseReason.value === 'failed'
  ) {
    return
  }
  closeBindDialogByUser().catch(() => undefined)
}

function openMappingDialog(bot, type) {
  if (isBotRunning(bot)) {
    ElMessage.warning('Bot 运行中时不允许修改 MCP/Skill 映射')
    return
  }
  mappingModalBot.value = bot
  mappingModalType.value = type
  mappingModalVisible.value = true
}

async function handleMappingSaved() {
  await loadBotsConfig(botPagination.page, botPagination.page_size, keyword.value)
}

onBeforeUnmount(() => {
  stopBindPolling()
  stopBindCountdown()
  if (bindingBot.value?.bot_key) {
    stopBindRuntime(bindingBot.value.bot_key).catch(() => undefined)
  }
})
</script>

<template>
  <div class="bot-config" v-loading="pageLoading">
    <div class="header">
      <h2>Bot 配置</h2>
      <div class="actions">
        <el-input v-model="keyword" class="bot-search-input" placeholder="搜索机器人名称" clearable />
        <el-button type="default" @click="handleSearch" :loading="loadingSearch">查询</el-button>
        <el-button type="primary" @click="openCreateDialog">新增</el-button>
        <el-button type="danger" @click="batchDelete" :disabled="selectedBotKeys.length === 0">
          删除
        </el-button>
      </div>
    </div>

    <div class="content">
      <div class="left-panel">
        <div v-if="loadingBots" class="loading">加载中...</div>
        <div v-else class="table-container">
          <div class="table-scroll">
            <el-table :data="bots" class="bot-table" stripe @selection-change="handleSelectionChange">
              <el-table-column type="selection" width="55" />
              <el-table-column prop="name" label="Bot 名称" min-width="140" />
              <el-table-column label="关联 Agent" min-width="120">
                <template #default="{ row }">
                  <span>{{ getAgentLabel(row.agent_provider) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="绑定状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="isBotBound(row) ? 'success' : 'info'" size="small">
                    {{ getBindStatusLabel(row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="启用状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                    {{ row.is_active ? '已启用' : '已禁用' }}
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
              <el-table-column label="操作" fixed="right" width="320">
                <template #header>
                  <div class="operation-header">
                    <span>操作</span>
                    <el-tooltip content="被BOT搭载的组件都无法被编辑/删除。" placement="top">
                      <el-icon class="operation-header__icon">
                        <QuestionFilled />
                      </el-icon>
                    </el-tooltip>
                  </div>
                </template>
                <template #default="{ row }">
                  <el-button type="primary" size="small" link :disabled="loadingEditDialog || isBotRunning(row)" @click="openEditDialog(row)">
                    编辑
                  </el-button>
                  <el-button type="success" size="small" link :disabled="isBotBound(row) || bindingActionLoading || isBotRunning(row)"
                    @click="openBindDialog(row)">
                    绑定
                  </el-button>
                  <el-button type="warning" size="small" link :disabled="!isBotBound(row) || isBotRunning(row)"
                    @click="doUnbindBot(row)">
                    解绑
                  </el-button>
                  <template v-if="row.is_active">
                    <el-button type="primary" size="small" link disabled>启用</el-button>
                    <el-button type="danger" size="small" link :disabled="isBotRunning(row)" @click="toggleBot(row)">停用</el-button>
                  </template>
                  <template v-else>
                    <el-button type="primary" size="small" link :disabled="isBotRunning(row)" @click="toggleBot(row)">
                      启用
                    </el-button>
                    <el-button type="danger" size="small" link disabled>停用</el-button>
                  </template>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div v-if="!bots.length" class="empty">暂无 Bot 配置，点击"新增"添加</div>

          <div class="pagination-container">
            <el-pagination v-model:current-page="botPagination.page" v-model:page-size="botPagination.page_size"
              :page-sizes="[10, 20, 50, 100]" :total="botPagination.total"
              layout="total, sizes, prev, pager, next, jumper" @size-change="handleSizeChange"
              @current-change="handlePageChange" />
          </div>
        </div>
      </div>

      <div class="right-panel">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>全部 Bot</span>
            </div>
          </template>
          <div class="active-bots-container">
            <div v-if="activeBots.length === 0" class="empty-bots">
              <p>暂无 Bot</p>
            </div>
            <div v-else class="bot-list">
              <div v-for="bot in activeBots" :key="bot.bot_key" class="bot-item" :class="{ 'bot-item-disabled': !bot.is_active }">
                <div class="bot-name">
                  {{ bot.name }}
                  <el-tag :type="bot.is_active ? 'success' : 'info'" size="small" class="bot-status-tag">
                    {{ bot.is_active ? '已启用' : '未启用' }}
                  </el-tag>
                </div>
                <div class="bot-buttons">
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="isBotRunning(bot)"
                    @click="openMappingDialog(bot, 'mcp')"
                  >
                    已启用 MCP ({{ bot.enabled_mcp_count || 0 }})
                  </el-button>
                  <el-button
                    type="success"
                    size="small"
                    :disabled="isBotRunning(bot)"
                    @click="openMappingDialog(bot, 'skills')"
                  >
                    已启用 Skills ({{ bot.enabled_skill_count || 0 }})
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" class="bot-edit-dialog" :title="isEdit ? '编辑 Bot' : '新增 Bot'" width="1040px"
      :close-on-click-modal="false">
      <el-form
        v-if="editingBot"
        v-loading="loadingEditDialog"
        class="bot-edit-form"
        element-loading-text="正在加载数据..."
        :model="editingBot"
        label-width="120px"
      >
        <div class="bot-edit-layout">
          <div class="bot-edit-fields">
            <el-form-item label="Bot 名称" required>
              <el-input v-model="editingBot.name" placeholder="请输入唯一的 Bot 名称" />
            </el-form-item>
            <el-form-item label="Bot ID" required>
              <el-input v-model="editingBot.bot_id" placeholder="请输入 Bot ID" />
            </el-form-item>
            <el-form-item label="Secret" required>
              <el-input ref="secretInputRef" v-model="editingBot.secret" type="password" show-password
                placeholder="请输入 Secret" />
            </el-form-item>
            <el-form-item label="关联 Agent">
              <el-select v-model="editingBot.agent_provider" placeholder="选择已启用的 Agent" style="width: 100%" clearable>
                <el-option v-for="agent in selectableAgents" :key="agent.provider_key"
                  :label="agent.label || agent.provider_name" :value="agent.provider_key" />
              </el-select>
            </el-form-item>
            <el-form-item label="提示词" class="prompt-editor-form-item">
              <el-input
                v-model="editingBot.system_prompt"
                class="prompt-editor-textarea"
                type="textarea"
                :rows="20"
                placeholder="请输入系统提示词，支持 Markdown 或普通文本"
              />
            </el-form-item>
            <el-form-item label="欢迎语">
              <el-input v-model="editingBot.startup_text" type="textarea" :rows="2" placeholder="请输入欢迎语" />
            </el-form-item>
            <el-form-item label="结束语">
              <el-input v-model="editingBot.shutdown_text" type="textarea" :rows="2" placeholder="请输入结束语" />
            </el-form-item>
          </div>
          <aside class="bot-edit-preview">
            <div class="prompt-preview-panel">
              <div class="prompt-preview-panel__header">
                <span>回显预览</span>
                <el-tag size="small" type="info">{{ promptPreviewLabel }}</el-tag>
              </div>
              <div
                v-if="promptIsMarkdown"
                class="prompt-preview-panel__body prompt-preview-panel__body--markdown"
                v-html="promptPreviewHtml"
              />
              <pre v-else class="prompt-preview-panel__body prompt-preview-panel__body--text">{{ promptPlainPreview }}</pre>
            </div>
          </aside>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="closeDialog">取消</el-button>
        <el-button type="primary" :loading="savingBot" :disabled="savingBot" @click="saveBot">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bindDialogVisible" title="绑定 Bot" width="520px" :close-on-click-modal="false" :show-close="true"
      @close="handleBindDialogClose">
      <div class="bind-dialog-body">
        <p>请对 {{ bindingBot?.name || '-' }} 发送命令 `connect mycom`</p>
        <p class="bind-countdown" :class="{ 'bind-countdown-danger': bindCountdown <= 30 }">
          剩余时间: {{ formatCountdown(bindCountdown) }}
        </p>
      </div>
      <template #footer>
        <el-button :disabled="bindDialogBusy" @click="closeBindDialogByUser">取消</el-button>
      </template>
    </el-dialog>

    <BotMappingModal v-model="mappingModalVisible" :bot="mappingModalBot" :type="mappingModalType"
      @saved="handleMappingSaved" />
  </div>
</template>
