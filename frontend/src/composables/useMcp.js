import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getMcpTools, refreshMcpTools as refreshMcpToolsApi } from '../api/runtime'

export function useMcp() {
  const mcpTools = ref([])

  async function loadMcpTools() {
    try {
      const result = await getMcpTools()
      mcpTools.value = result.tools || []
    } catch (error) {
      mcpTools.value = []
      ElMessage.error(`加载 MCP 工具失败：${error?.message || error}`)
    }
  }

  async function refreshMcpToolList() {
    try {
      const result = await refreshMcpToolsApi()
      mcpTools.value = result.tools || []
    } catch (error) {
      ElMessage.error(`刷新 MCP 工具失败：${error?.message || error}`)
    }
  }

  return {
    mcpTools,
    loadMcpTools,
    refreshMcpToolList,
  }
}
