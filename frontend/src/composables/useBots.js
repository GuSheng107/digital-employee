import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import {
  getBots,
  saveBot as saveBotApi,
  batchDeleteBots,
  toggleBot,
  rebindBot,
  startNamedBot,
  stopNamedBot,
  unbindBot,
} from '../api/runtime'
import { useRuntimeCore } from './useRuntimeCore'
import { useChats } from './useChats'

const loadingBots = ref(false)
const savingBot = ref(false)
const startingBots = ref(new Set())
const stoppingBots = ref(new Set())
const botKeyword = ref('')
const botPagination = ref({
  total: 0,
  page: 1,
  page_size: 10,
  total_pages: 1,
})

export function useBots() {
  const { bots, botStatuses, activeBotKey, ensureActiveBot } = useRuntimeCore()

  async function loadBots() {
    const result = await getBots({ include_deleted: true })
    bots.value = result.bots || []
    botStatuses.value = result.statuses || {}
    ensureActiveBot()
  }

  async function loadBotsConfig(page = 1, pageSize = 10, keyword = botKeyword.value) {
    loadingBots.value = true
    try {
      botKeyword.value = keyword || ''
      const response = await getBots({ page, page_size: pageSize, keyword: botKeyword.value })
      if (response && response.bots) {
        bots.value = response.bots
        botStatuses.value = response.statuses || {}
        botPagination.value = {
          total: response.total || 0,
          page: response.page || 1,
          page_size: response.page_size || 10,
          total_pages: response.total_pages || 1,
        }
      }
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      loadingBots.value = false
    }
  }

  async function handleSaveBot(bot, mode = 'add') {
    savingBot.value = true
    try {
      await saveBotApi(bot, mode)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      ElMessage.success('Bot 已保存')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      savingBot.value = false
    }
  }

  async function handleToggleBot(botKey, isActive) {
    try {
      await toggleBot(botKey, isActive)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function handleDeleteBots(botKeys) {
    try {
      await batchDeleteBots(botKeys)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      ElMessage.success('Bot 已删除')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function handleUnbindBot(botKey) {
    try {
      await stopNamedBot(botKey)
      await unbindBot(botKey)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      ElMessage.success('Bot 已解绑')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function handleStartBot(botKey) {
    startingBots.value.add(botKey)
    try {
      const result = await startNamedBot(botKey)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      const warnings = Array.isArray(result?.warnings) ? result.warnings.filter(Boolean) : []
      warnings.forEach(message => ElMessage.warning(message))
      ElMessage.success('Bot 已启动')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      startingBots.value.delete(botKey)
    }
  }

  async function handleStopBot(botKey) {
    stoppingBots.value.add(botKey)
    try {
      await stopNamedBot(botKey)
      await loadBotsConfig(botPagination.value.page, botPagination.value.page_size)
      ElMessage.success('Bot 已停止')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      stoppingBots.value.delete(botKey)
    }
  }

  async function selectBot(botKey) {
    activeBotKey.value = botKey
    const { loadChats } = useChats()
    await loadChats(true)
  }

  return {
    loadingBots,
    savingBot,
    startingBots,
    stoppingBots,
    botKeyword,
    botPagination,
    loadBots,
    loadBotsConfig,
    handleSaveBot,
    handleToggleBot,
    handleDeleteBots,
    handleUnbindBot,
    handleStartBot,
    handleStopBot,
    selectBot,
  }
}
