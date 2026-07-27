import request from '@/utils/request';

export interface Bot {
  bot_key: string;
  name?: string;
  display_name?: string;
  agent_key?: string;
  agent_provider?: string;
  is_active?: boolean;
  is_deleted?: boolean;
  is_bound?: boolean;
  enabled_mcp_count?: number;
  enabled_skill_count?: number;
  unread_total?: number;
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

export interface BotStatus {
  running: boolean;
  pid: number | null;
}

export interface BotListResponse {
  bots: Bot[];
  statuses?: Record<string, BotStatus>;
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

interface BotItemResponse {
  bot: Bot;
  status?: BotStatus;
}

export interface BotSkillsResponse {
  skill_names: string[];
}

export interface BotMcpServersResponse {
  server_ids: string[];
}

export interface StartBotResponse {
  warnings?: string[];
}

export function getStatus(): Promise<Record<string, unknown>> {
  return request.get('/status') as Promise<Record<string, unknown>>;
}

export function getBots(params: BotListParams & { bot_key: string }): Promise<Bot>;
export function getBots(params?: BotListParams): Promise<BotListResponse>;
export async function getBots(params: BotListParams = {}): Promise<Bot | BotListResponse> {
  const search = new URLSearchParams();
  if (params.bot_key) search.set('bot_key', params.bot_key);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.include_deleted) search.set('include_deleted', 'true');
  const query = search.toString();
  if (params.bot_key) {
    const response = await request.get(`/bots${query ? `?${query}` : ''}`) as BotItemResponse;
    return { ...response.bot, runtime_status: response.status || { running: false, pid: null } };
  }
  return request.get(`/bots${query ? `?${query}` : ''}`) as Promise<BotListResponse>;
}

export interface SaveBotPayload extends Record<string, unknown> {
  bot_key?: string;
  name?: string;
  agent_provider?: string;
  is_active?: boolean;
  mode?: unknown;
}

export function saveBot(bot: SaveBotPayload, mode: 'add' | 'edit' = 'add'): Promise<Bot> {
  const { mode: _botMode, ...botWithoutMode } = bot;
  void _botMode;
  return request.post('/bots', { ...botWithoutMode, operation: mode }) as Promise<Bot>;
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

export function startNamedBot(botKey: string, payload: Record<string, unknown> = {}): Promise<StartBotResponse> {
  return request.post(`/bots/${encodeURIComponent(botKey)}/start`, payload) as Promise<StartBotResponse>;
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

export async function getBotSkills(botKey: string): Promise<BotSkillsResponse> {
  return request.get(`/bots/${encodeURIComponent(botKey)}/skills`) as Promise<BotSkillsResponse>;
}

export async function saveBotSkills(botKey: string, skillNames: string[]) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/skills`, { skill_names: skillNames });
}

export async function getBotMcpServers(botKey: string): Promise<BotMcpServersResponse> {
  return request.get(`/bots/${encodeURIComponent(botKey)}/mcp`) as Promise<BotMcpServersResponse>;
}

export async function saveBotMcpServers(botKey: string, serverIds: string[]) {
  return request.post(`/bots/${encodeURIComponent(botKey)}/mcp`, { server_ids: serverIds });
}
