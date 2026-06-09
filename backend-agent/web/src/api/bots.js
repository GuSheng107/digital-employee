import { api } from './http'

export function getStatus() {
  return api('/api/status')
}

export async function getBots(params = {}) {
  const search = new URLSearchParams()
  if (params.bot_key) search.set('bot_key', params.bot_key)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.include_deleted) search.set('include_deleted', 'true')
  const query = search.toString()
  const response = await api(`/api/bots${query ? `?${query}` : ''}`)
  if (params.bot_key) {
    return { ...response.bot, runtime_status: response.status || { running: false, pid: null } }
  }
  return response
}

export function saveBot(bot, mode = 'add') {
  const payload = { ...bot, operation: mode }
  delete payload.mode
  return api('/api/bots', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function batchDeleteBots(botKeys) {
  return api('/api/bots/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ bot_keys: botKeys }),
  })
}

export function restoreDeletedBots(botKeys) {
  return api('/api/bots/restore', {
    method: 'POST',
    body: JSON.stringify({ bot_keys: botKeys }),
  })
}

export function toggleBot(botKey, isActive) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/toggle`, {
    method: 'POST',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export function startNamedBot(botKey, payload = {}) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/start`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function stopNamedBot(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/stop`, { method: 'POST' })
}

export function rebindBot(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/rebind`, { method: 'POST' })
}

export function unbindBot(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/unbind`, { method: 'POST' })
}

export function markAllBotChatsRead(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/read-all`, { method: 'POST' })
}

export async function getBotSkills(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/skills`)
}

export async function saveBotSkills(botKey, skillNames) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/skills`, {
    method: 'POST',
    body: JSON.stringify({ skill_names: skillNames }),
  })
}

export async function getBotMcpServers(botKey) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/mcp`)
}

export async function saveBotMcpServers(botKey, serverIds) {
  return api(`/api/bots/${encodeURIComponent(botKey)}/mcp`, {
    method: 'POST',
    body: JSON.stringify({ server_ids: serverIds }),
  })
}
