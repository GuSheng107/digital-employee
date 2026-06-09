import { computed, ref } from 'vue'

let runtimeCoreInstance = null

export function createRuntimeCore() {
  const activeBotKey = ref('')
  const activeView = ref('control')
  const status = ref(null)
  const bots = ref([])
  const botStatuses = ref({})
  const crashEvents = ref([])

  const activeBot = computed(() => bots.value.find((bot) => bot.bot_key === activeBotKey.value) || bots.value[0] || null)
  const activeBotStatus = computed(() => botStatuses.value[activeBot.value?.bot_key] || { running: false, pid: null })

  function ensureActiveBot() {
    if (!bots.value.length) {
      activeBotKey.value = ''
      return
    }
    if (!bots.value.some((bot) => bot.bot_key === activeBotKey.value)) {
      activeBotKey.value = bots.value[0].bot_key
    }
  }

  runtimeCoreInstance = {
    activeBotKey,
    activeView,
    status,
    bots,
    botStatuses,
    crashEvents,
    activeBot,
    activeBotStatus,
    ensureActiveBot,
  }
  return runtimeCoreInstance
}

export function useRuntimeCore() {
  if (!runtimeCoreInstance) {
    return createRuntimeCore()
  }
  return runtimeCoreInstance
}

export function disposeRuntimeCore() {
  if (runtimeCoreInstance) {
    runtimeCoreInstance.activeBotKey.value = ''
    runtimeCoreInstance.activeView.value = 'control'
    runtimeCoreInstance.status.value = null
    runtimeCoreInstance.bots.value = []
    runtimeCoreInstance.botStatuses.value = {}
    runtimeCoreInstance.crashEvents.value = []
    runtimeCoreInstance = null
  }
}