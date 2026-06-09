import { api } from './http'

export async function getAgents(params = {}) {
  const search = new URLSearchParams()
  if (params.provider_key) search.set('provider_key', params.provider_key)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.keyword) search.set('keyword', params.keyword)
  const query = search.toString()
  const response = await api(`/api/agents${query ? `?${query}` : ''}`)
  if (params.provider_key) {
    return response.agent
  }
  return response
}

export async function getAgent(providerKey) {
  const response = await api(`/api/agents?provider_key=${encodeURIComponent(providerKey)}`)
  return response.agent
}

export async function saveAgent(agent, mode = 'add') {
  const response = await api('/api/agents', {
    method: 'POST',
    body: JSON.stringify({ ...agent, mode }),
  })
  return response.agent
}

export async function toggleAgent(providerKey, isActive) {
  return api(`/api/agents/${encodeURIComponent(providerKey)}/toggle`, {
    method: 'POST',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export async function testAgent(providerKey) {
  return api(`/api/agents/${encodeURIComponent(providerKey)}/test`, { method: 'POST' })
}

export async function getAgentCapabilities(model, providerType) {
  const search = new URLSearchParams()
  search.set('model', model)
  search.set('provider_type', providerType)
  return api(`/api/agents/capabilities?${search.toString()}`)
}

export async function getAgentProviderSchemas() {
  const response = await api('/api/agents/provider-schemas')
  return response.providers || {}
}

export async function batchDeleteAgents(providerKeys) {
  return api('/api/agents/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ provider_keys: providerKeys }),
  })
}

export function getAiStatus() {
  return api('/api/ai/status')
}

export function cancelAiWork(traceId) {
  return api(`/api/ai/status/${encodeURIComponent(traceId)}/cancel`, { method: 'POST' })
}

export function clearAiWork(traceId) {
  return api(`/api/ai/status/${encodeURIComponent(traceId)}`, { method: 'DELETE' })
}
