import { api, fetchWithAuth } from './http'

export function getProjectLogs(params = {}) {
  const search = new URLSearchParams()
  if (params.category) search.set('category', params.category)
  if (params.level) search.set('level', params.level)
  if (params.trace_id) search.set('trace_id', params.trace_id)
  if (params.start_time) search.set('start_time', params.start_time)
  if (params.end_time) search.set('end_time', params.end_time)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  const query = search.toString()
  return api(`/api/project-logs${query ? `?${query}` : ''}`)
}

export function getDataOverview() {
  return api('/api/data/overview')
}

export function getTokenUsage() {
  return api('/api/data/token-usage')
}

export function optimizeDatabase() {
  return api('/api/data/optimize', {
    method: 'POST',
  })
}

export function getPeriodicTasks(params = {}) {
  const search = new URLSearchParams()
  if (params.scope) search.set('scope', params.scope)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.status) search.set('status', params.status)
  if (params.task_type) search.set('task_type', params.task_type)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  const query = search.toString()
  return api(`/api/tasks/periodic${query ? `?${query}` : ''}`)
}

export function getTasks(params = {}) {
  const search = new URLSearchParams()
  if (params.scope) search.set('scope', params.scope)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.status) search.set('status', params.status)
  if (params.task_type) search.set('task_type', params.task_type)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  const query = search.toString()
  return api(`/api/tasks${query ? `?${query}` : ''}`)
}

export function getOneTimeTasks(params = {}) {
  const search = new URLSearchParams()
  if (params.scope) search.set('scope', params.scope)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.status) search.set('status', params.status)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  const query = search.toString()
  return api(`/api/tasks/one-time${query ? `?${query}` : ''}`)
}

export function getTaskExecutors() {
  return api('/api/tasks/executors')
}

export function getTaskDetail(taskKey) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}`)
}

export function enableTask(taskKey) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}/enable`, { method: 'POST' })
}

export function disableTask(taskKey) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}/disable`, { method: 'POST' })
}

export function updateTask(taskKey, data) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteTask(taskKey) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}`, { method: 'DELETE' })
}

export function createTask(data) {
  return api('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function triggerTask(taskKey) {
  return api(`/api/tasks/${encodeURIComponent(taskKey)}/trigger`, {
    method: 'POST',
  })
}

export function getPlatformSettings() {
  return api('/api/platform-settings')
}

export function savePlatformSettings(settings) {
  return api('/api/platform-settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
}

export function getDocuments() {
  return api('/api/documents')
}

export function getDocumentsConfig() {
  return api('/api/documents/config')
}

export function uploadDocuments(files) {
  const body = new FormData()
  for (const file of files) {
    body.append('files', file)
  }
  return api('/api/documents/upload', { method: 'POST', body })
}

export function deleteDocument(docId) {
  return api(`/api/documents/${encodeURIComponent(docId)}?confirm=true`, { method: 'DELETE' })
}

export async function downloadDocumentBlob(docId) {
  const response = await fetchWithAuth(`/api/documents/${encodeURIComponent(docId)}/download`)
  if (!response.ok) {
    throw new Error(response.statusText || '下载失败')
  }
  return response.blob()
}

export async function exitSystem() {
  return api('/api/exit', { method: 'POST' })
}

export function getMemoryFiles() {
  return api('/api/memory/files')
}

export function getMemoryItems(fileKey) {
  return api(`/api/memory/items/${encodeURIComponent(fileKey)}`)
}

export function getMemoryItem(fileKey, itemId) {
  const search = new URLSearchParams()
  search.set('file_key', fileKey)
  search.set('item_id', itemId)
  return api(`/api/memory/item?${search.toString()}`)
}

export function addMemoryItem(fileKey, data) {
  return api(`/api/memory/items/${encodeURIComponent(fileKey)}`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateMemoryItem(fileKey, itemId, data) {
  return api('/api/memory/item', {
    method: 'PUT',
    body: JSON.stringify({ file_key: fileKey, item_id: itemId, ...data }),
  })
}

export function deleteMemoryItem(fileKey, itemId) {
  const search = new URLSearchParams()
  search.set('file_key', fileKey)
  search.set('item_id', itemId)
  return api(`/api/memory/item?${search.toString()}`, { method: 'DELETE' })
}

export function searchMemory(query, fileKey) {
  const search = new URLSearchParams()
  search.set('q', query)
  if (fileKey) search.set('file_key', fileKey)
  return api(`/api/memory/search?${search.toString()}`)
}

export function getMemoryAudits(params = {}) {
  const search = new URLSearchParams()
  if (params.days) search.set('days', String(params.days))
  if (params.limit) search.set('limit', String(params.limit))
  const query = search.toString()
  return api(`/api/memory/audits${query ? `?${query}` : ''}`)
}

export function getMemoryReviews() {
  return api('/api/memory/reviews')
}

export function getMemoryReviewContent(filename) {
  return api(`/api/memory/reviews/${encodeURIComponent(filename)}`)
}

export function deleteMemoryReview(filename) {
  return api(`/api/memory/reviews/${encodeURIComponent(filename)}`, { method: 'DELETE' })
}
