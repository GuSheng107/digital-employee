import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import {
  getAgents,
  saveAgent as saveAgentApi,
  toggleAgent,
  testAgent,
} from '../api/runtime'

const agents = ref([])
const loadingAgents = ref(false)
const savingAgent = ref(false)
const testingAgent = ref(null)
const agentKeyword = ref('')
const pagination = ref({
  total: 0,
  page: 1,
  page_size: 10,
  total_pages: 1,
})

export function useAgents() {
  async function loadAgents(page = 1, pageSize = 10, keyword = agentKeyword.value) {
    loadingAgents.value = true
    try {
      agentKeyword.value = keyword || ''
      const response = await getAgents({ page, page_size: pageSize, keyword: agentKeyword.value })
      if (response && response.agents) {
        agents.value = response.agents
        pagination.value = {
          total: response.total || 0,
          page: response.page || 1,
          page_size: response.page_size || 10,
          total_pages: response.total_pages || 1,
        }
      }
    } catch (error) {
      ElMessage.error(String(error))
    } finally {
      loadingAgents.value = false
    }
  }

  async function handleSaveAgent(agent, mode = 'add') {
    savingAgent.value = true
    try {
      await saveAgentApi(agent, mode)
      await loadAgents(pagination.value.page, pagination.value.page_size)
      ElMessage.success('Agent 已保存')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      savingAgent.value = false
    }
  }

  async function handleToggleAgent(providerKey, isActive) {
    try {
      await toggleAgent(providerKey, isActive)
      await loadAgents(pagination.value.page, pagination.value.page_size)
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function handleTestAgent(providerKey) {
    testingAgent.value = providerKey
    try {
      const result = await testAgent(providerKey)
      if (result.ok) {
        ElMessage.success('连通性测试成功')
      } else {
        ElMessage.error(result.message || '连通性测试失败')
      }
      await loadAgents(pagination.value.page, pagination.value.page_size)
      return result
    } catch (error) {
      ElMessage.error(String(error))
      return { ok: false, message: String(error) }
    } finally {
      testingAgent.value = null
    }
  }

  return {
    agents,
    loadingAgents,
    savingAgent,
    testingAgent,
    agentKeyword,
    pagination,
    loadAgents,
    handleSaveAgent,
    handleToggleAgent,
    handleTestAgent,
  }
}
