import request from '@/utils/request';

export interface Bot {
  bot_key: string;
  display_name?: string;
  agent_key?: string;
  is_active?: boolean;
  runtime_status?: { running: boolean; pid: number | null };
  [key: string]: unknown;
}

export interface BotListParams {
  bot_key?: string;
  page?: number;
  page_size?: number;
  keyword?: string;
  include_deleted?: boolean;
}

export function getStatus() {
  return request.get('/status');
}

export async function getBots(params: BotListParams = {}) {
  const search = new URLSearchParams();
  if (params.bot_key) search.set('bot_key', params.bot_key);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.include_deleted) search.set('include_deleted', 'true');
  const query = search.toString();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const response: any = await request.get(`/bots${query ? `?${query}` : ''}`);
  if (params.bot_key) {
    return { ...response.bot, runtime_status: response.status || { running: false, pid: null } };
  }
  return response;
}

export function saveBot(bot: Record<string, unknown>, mode: 'add' | 'edit' = 'add') {
  // Remove 'mode' from bot if present, then add 'operation'
  const { mode: _botMode, ...botWithoutMode } = bot as Record<string, unknown> & { mode?: unknown };
  void _botMode;
  return request.post('/bots', { ...botWithoutMode, operation: mode });
}

export function batchDeleteBots(botKeys: string[]) {
  return request.post('/bots/batch-delete', { bot_keys: botKeys });
}

export function restoreDeletedBots(botKeys: string[]) {
  return request.post('/bots/restore', { bot_keys: botKeys });
}

export function toggleBot(botKey: string, isActive: boolean) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/toggle`, { is_active: isActive });
}

export function startNamedBot(botKey: string, payload: Record<string, unknown> = {}) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/start`, payload);
}

export function stopNamedBot(botKey: string) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/stop`);
}

export function rebindBot(botKey: string) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/rebind`);
}

export function unbindBot(botKey: string) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/unbind`);
}

export function markAllBotChatsRead(botKey: string) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/read-all`);
}

export async function getBotSkills(botKey: string) {
  return request.get(`/bots/${encodeURIComponent(botKey)}/skills`);
}

export async function saveBotSkills(botKey: string, skillNames: string[]) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/skills`, { skill_names: skillNames });
}

export async function getBotMcpServers(botKey: string) {
  return request.get(`/bots/${encodeURIComponent(botKey)}/mcp`);
}

export async function saveBotMcpServers(botKey: string, serverIds: string[]) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/mcp`, { server_ids: serverIds });
}
