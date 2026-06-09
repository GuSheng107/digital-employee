import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getDataOverview, getTokenUsage, optimizeDatabase as optimizeDataApi } from '../api/runtime'

const dataOverview = ref(null)
const tokenUsage = ref(null)
const optimizingData = ref(false)

export function useData() {
  async function loadDataOverview() {
    try {
      dataOverview.value = await getDataOverview()
    } catch (error) {
      dataOverview.value = null
    }
  }

  async function loadTokenUsage() {
    try {
      tokenUsage.value = await getTokenUsage()
    } catch (error) {
      tokenUsage.value = null
    }
  }

  async function optimizeData() {
    optimizingData.value = true
    try {
      const response = await optimizeDataApi()
      await loadDataOverview()
      await loadTokenUsage()
      const result = response?.result || {}
      ElMessage.success(
        `数据库优化完成：会话 ${result.removed_conversations || 0}，消息 ${result.removed_messages || 0}，手动回复 ${result.removed_manual_reply_commands || 0}，日志 ${result.removed_logs || 0}，AI 任务 ${result.removed_ai_work_items || 0}，Token 消耗 ${result.removed_token_usage || 0}`,
      )
    } catch (error) {
      ElMessage.error(String(error))
    } finally {
      optimizingData.value = false
    }
  }

  return {
    dataOverview,
    tokenUsage,
    optimizingData,
    loadDataOverview,
    loadTokenUsage,
    optimizeData,
  }
}
