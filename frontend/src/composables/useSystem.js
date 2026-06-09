import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { ElNotification } from 'element-plus/es/components/notification/index.mjs'
import { AbortableApi } from '../api/http'
import { api } from '../api/http'
import { getPlatformSettings } from '../api/runtime'
import { useRuntimeCore } from './useRuntimeCore'
import { useChats } from './useChats'
import { useAgents } from './useAgents'
import { useMcp } from './useMcp'
import { useData } from './useData'

const loading = ref(false)
const shutdownOverlay = ref(false)
const platformSettings = ref({})
let timer = null
let pollingInFlight = false
const pollAbortable = new AbortableApi()
const shownCrashIds = new Set()
const shownSystemAlertIds = new Set()

export function useSystem() {
  const { activeBotKey, activeView, status, bots, botStatuses, crashEvents, ensureActiveBot } = useRuntimeCore()
  const { loadChats } = useChats()
  const { loadAgents } = useAgents()
  const { loadMcpTools } = useMcp()
  const { loadDataOverview } = useData()

  async function loadStatus() {
    try {
      const result = await api('/api/status')
      status.value = result
      bots.value = result.bots || []
      botStatuses.value = result.bot_statuses || {}
      processCrashEvents(result.crash_events || [])
      processSystemAlerts(result.system_alerts || [])
      ensureActiveBot()
    } catch (error) {
      if (error.name === 'AbortError') return
      console.error('Failed to load status:', error)
    }
  }

  async function loadPlatformSettings() {
    try {
      const res = await getPlatformSettings()
      platformSettings.value = res.settings || {}
    } catch (error) {
      console.error('Failed to load platform settings:', error)
    }
  }

  async function refreshAll() {
    loading.value = true
    try {
      await Promise.all([loadStatus(), loadDataOverview(), loadMcpTools(), loadAgents(), loadPlatformSettings()])
      await loadChats()
    } catch (error) {
      console.error('Failed to refresh all:', error)
    } finally {
      loading.value = false
    }
  }

  async function pollRuntime() {
    if (pollingInFlight) return
    pollingInFlight = true
    try {
      const result = await pollAbortable.api('/api/status')
      status.value = result
      bots.value = result.bots || []
      botStatuses.value = result.bot_statuses || {}
      processCrashEvents(result.crash_events || [])
      processSystemAlerts(result.system_alerts || [])
      ensureActiveBot()
      
      if (activeView.value === 'chats') {
        await loadChats()
      }
    } catch (error) {
      if (error.name === 'AbortError') return
      console.error('Polling error:', error)
    } finally {
      pollingInFlight = false
    }
  }

  function processCrashEvents(events) {
    crashEvents.value = events
    for (const event of events) {
      if (shownCrashIds.has(event.id)) continue
      shownCrashIds.add(event.id)
      const botName = bots.value.find(b => b.bot_key === event.bot_key)?.name || event.bot_key
      ElNotification({
        title: 'Bot 进程异常退出',
        message: `${botName} 已意外停止（退出码: ${event.exit_code ?? '未知'}），请检查日志。`,
        type: 'error',
        duration: 0,
        position: 'bottom-right',
        onClose: () => acknowledgeCrash(event.id),
      })
    }
  }

  function processSystemAlerts(alerts) {
    for (const alert of alerts) {
      if (shownSystemAlertIds.has(alert.id)) continue
      shownSystemAlertIds.add(alert.id)
      if (alert.type === 'memory_update_review_required') {
        ElNotification({
          title: '记忆更新待处理',
          message: `${alert.message} 请前往“任务管理”处理“${alert.task_name || '记忆更新'}”。`,
          type: 'warning',
          duration: 0,
          position: 'bottom-right',
        })
      }
    }
  }

  async function acknowledgeCrash(eventId) {
    try {
      await api('/api/crash-events/ack', {
        method: 'POST',
        body: JSON.stringify({ event_id: eventId }),
      })
    } catch {
      // ignore
    }
  }

  async function exitSystem() {
    try {
      await ElMessageBox.confirm('确定要退出系统吗？退出后所有 Bot 将停止运行。', '确认退出', {
        type: 'warning',
        confirmButtonText: '退出',
        cancelButtonText: '取消',
      })
      shutdownOverlay.value = true
      await api('/api/exit', { method: 'POST' })
      ElMessage.success('系统正在退出')
      // 尝试关闭当前标签页
      window.close()
    } catch (error) {
      if (error !== 'cancel') {
        ElMessage.error(String(error))
      }
    }
  }

  function startPolling(intervalMs = 3000) {
    stopPolling()
    timer = window.setInterval(pollRuntime, intervalMs)
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }

  function stopPolling() {
    pollAbortable.abort()
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }

  function handleVisibilityChange() {
    if (document.visibilityState === 'visible' && timer !== null) {
      pollRuntime()
    }
  }

  async function initialize() {
    await refreshAll()
    startPolling()
  }

  return {
    loading,
    shutdownOverlay,
    platformSettings,
    loadStatus,
    loadPlatformSettings,
    refreshAll,
    pollRuntime,
    exitSystem,
    startPolling,
    stopPolling,
    initialize,
  }
}
