import { api, fetchWithAuth } from './http'

export function getChats(params = {}) {
  const search = new URLSearchParams()
  if (params.bot_key) search.set('bot_key', params.bot_key)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  const query = search.toString()
  return api(`/api/chats${query ? `?${query}` : ''}`)
}

export function getChatDetail(chatId, params = {}) {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return api(`/api/chats/${encodeURIComponent(chatId)}${query ? `?${query}` : ''}`)
}

export function deleteChats(chatIds) {
  return api('/api/chats', {
    method: 'DELETE',
    body: JSON.stringify({ chat_ids: chatIds }),
  })
}

export function updateChatDisplayName(chatId, displayName) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/display-name`, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  })
}

export function setChatReplyMode(chatId, payload) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/reply-mode`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function markChatRead(chatId) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/read`, { method: 'POST' })
}

export function pinChat(chatId, pinned) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/pin`, {
    method: 'POST',
    body: JSON.stringify({ pinned }),
  })
}

export function compressChatContext(chatId) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/context/compress`, { method: 'POST' })
}

export function generateAiDraftStream(chatId, payload, signal) {
  return fetchWithAuth(`/api/chats/${encodeURIComponent(chatId)}/ai-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function sendManualReply(chatId, payload) {
  const body = payload instanceof FormData ? payload : JSON.stringify(payload)
  return api(`/api/chats/${encodeURIComponent(chatId)}/reply`, {
    method: 'POST',
    body,
  })
}

export function getManualReplyStatus(commandId) {
  return api(`/api/manual-replies/${encodeURIComponent(commandId)}`)
}

export function archiveChat(chatId) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/archive`, { method: 'POST' })
}

export function unarchiveChat(chatId) {
  return api(`/api/chats/${encodeURIComponent(chatId)}/unarchive`, { method: 'POST' })
}

export function updateUserDisplayName(userId, displayName) {
  return api(`/api/users/${encodeURIComponent(userId)}/display-name`, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  })
}
