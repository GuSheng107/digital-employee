import request, { fetchWithAuth } from '@/utils/request';

// --- Project Logs ---

export interface LogListParams {
  category?: string;
  level?: string;
  trace_id?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export function getProjectLogs(params: LogListParams = {}) {
  const search = new URLSearchParams();
  if (params.category) search.set('category', params.category);
  if (params.level) search.set('level', params.level);
  if (params.trace_id) search.set('trace_id', params.trace_id);
  if (params.start_time) search.set('start_time', params.start_time);
  if (params.end_time) search.set('end_time', params.end_time);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  const query = search.toString();
  return request.get(`/project-logs${query ? `?${query}` : ''}`);
}

// --- Data Management ---

export function getDataOverview() {
  return request.get('/data/overview');
}

export function getTokenUsage() {
  return request.get('/data/token-usage');
}

export function optimizeDatabase() {
  return request.post('/data/optimize');
}

// --- Tasks ---

export interface TaskListParams {
  scope?: string;
  keyword?: string;
  status?: string;
  task_type?: string;
  page?: number;
  page_size?: number;
}

export function getPeriodicTasks(params: TaskListParams = {}) {
  const search = new URLSearchParams();
  if (params.scope) search.set('scope', params.scope);
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.status) search.set('status', params.status);
  if (params.task_type) search.set('task_type', params.task_type);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  const query = search.toString();
  return request.get(`/tasks/periodic${query ? `?${query}` : ''}`);
}

export function getTasks(params: TaskListParams = {}) {
  const search = new URLSearchParams();
  if (params.scope) search.set('scope', params.scope);
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.status) search.set('status', params.status);
  if (params.task_type) search.set('task_type', params.task_type);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  const query = search.toString();
  return request.get(`/tasks${query ? `?${query}` : ''}`);
}

export function getOneTimeTasks(params: TaskListParams = {}) {
  const search = new URLSearchParams();
  if (params.scope) search.set('scope', params.scope);
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.status) search.set('status', params.status);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  const query = search.toString();
  return request.get(`/tasks/one-time${query ? `?${query}` : ''}`);
}

export function getTaskExecutors() {
  return request.get('/tasks/executors');
}

export function getTaskDetail(taskKey: string) {
  return request.get(`/tasks/${encodeURIComponent(taskKey)}`);
}

export function enableTask(taskKey: string) {
  return request.post(`/tasks/${encodeURIComponent(taskKey)}/enable`);
}

export function disableTask(taskKey: string) {
  return request.post(`/tasks/${encodeURIComponent(taskKey)}/disable`);
}

export function updateTask(taskKey: string, data: Record<string, unknown>) {
  return request.put(`/tasks/${encodeURIComponent(taskKey)}`, data);
}

export function deleteTask(taskKey: string) {
  return request.delete(`/tasks/${encodeURIComponent(taskKey)}`);
}

export function createTask(data: Record<string, unknown>) {
  return request.post('/tasks', data);
}

export function triggerTask(taskKey: string) {
  return request.post(`/tasks/${encodeURIComponent(taskKey)}/trigger`);
}

// --- Platform Settings ---

export function getPlatformSettings(): Promise<Record<string, unknown>> {
  return request.get('/platform-settings') as Promise<Record<string, unknown>>;
}

export function savePlatformSettings(settings: Record<string, unknown>) {
  return request.post('/platform-settings', settings);
}

// --- Documents ---

export function getDocuments() {
  return request.get('/documents');
}

export function getDocumentsConfig() {
  return request.get('/documents/config');
}

export function uploadDocuments(files: File[]) {
  const body = new FormData();
  for (const file of files) {
    body.append('files', file);
  }
  return request.post('/documents/upload', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function deleteDocument(docId: string) {
  return request.delete(`/documents/${encodeURIComponent(docId)}?confirm=true`);
}

export async function downloadDocumentBlob(docId: string) {
  const response = await fetchWithAuth(`/documents/${encodeURIComponent(docId)}/download`);
  if (!response.ok) {
    throw new Error(response.statusText || '下载失败');
  }
  return response.blob();
}

// --- System ---

export async function exitSystem() {
  return request.post('/exit');
}

// --- Memory ---

export function getMemoryFiles() {
  return request.get('/memory/files');
}

export function getMemoryItems(fileKey: string) {
  return request.get(`/memory/items/${encodeURIComponent(fileKey)}`);
}

export function getMemoryItem(fileKey: string, itemId: string) {
  const search = new URLSearchParams();
  search.set('file_key', fileKey);
  search.set('item_id', itemId);
  return request.get(`/memory/item?${search.toString()}`);
}

export function addMemoryItem(fileKey: string, data: Record<string, unknown>) {
  return request.post(`/memory/items/${encodeURIComponent(fileKey)}`, data);
}

export function updateMemoryItem(fileKey: string, itemId: string, data: Record<string, unknown>) {
  return request.put('/memory/item', { file_key: fileKey, item_id: itemId, ...data });
}

export function deleteMemoryItem(fileKey: string, itemId: string) {
  const search = new URLSearchParams();
  search.set('file_key', fileKey);
  search.set('item_id', itemId);
  return request.delete(`/memory/item?${search.toString()}`);
}

export function searchMemory(query: string, fileKey?: string) {
  const search = new URLSearchParams();
  search.set('q', query);
  if (fileKey) search.set('file_key', fileKey);
  return request.get(`/memory/search?${search.toString()}`);
}

export interface MemoryAuditParams {
  days?: number;
  limit?: number;
}

export function getMemoryAudits(params: MemoryAuditParams = {}) {
  const search = new URLSearchParams();
  if (params.days) search.set('days', String(params.days));
  if (params.limit) search.set('limit', String(params.limit));
  const query = search.toString();
  return request.get(`/memory/audits${query ? `?${query}` : ''}`);
}

export function getMemoryReviews() {
  return request.get('/memory/reviews');
}

export function getMemoryReviewContent(filename: string) {
  return request.get(`/memory/reviews/${encodeURIComponent(filename)}`);
}

export function deleteMemoryReview(filename: string) {
  return request.delete(`/memory/reviews/${encodeURIComponent(filename)}`);
}
