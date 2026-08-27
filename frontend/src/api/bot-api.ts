import backendAuthRequest from '@/utils/backend-auth-request';

export type BotPlatform = 'feishu' | 'wechat';
export type BotMode = 'test' | 'prod';

export interface BotItem {
  id: number;
  bot_id: string;
  name: string;
  platform: BotPlatform;
  app_id: string;
  app_secret: string;
  mode: BotMode;
  status: number;
  agent_id?: string | null;
  agent_name?: string | null;
  parent_bot_id?: number | null;
  parent_bot_name?: string | null;
  created_by?: number | null;
  created_by_name?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BotListResponse {
  total: number;
  page: number;
  page_size: number;
  items: BotItem[];
}

export interface CreateBotPayload {
  bot_id: string;
  name: string;
  platform: BotPlatform;
  app_id: string;
  app_secret: string;
  mode?: BotMode;
  agent_id?: string | null;
  parent_bot_id?: number | null;
}

export interface UpdateBotPayload {
  name?: string;
  platform?: BotPlatform;
  app_id?: string;
  app_secret?: string;
  mode?: BotMode;
  agent_id?: string | null;
  parent_bot_id?: number | null;
}

/** 分页查询 Bot 列表 */
export function fetchBots(page: number = 1, pageSize: number = 20): Promise<BotListResponse> {
  return backendAuthRequest.get<BotListResponse>('/bots', {
    params: { page, page_size: pageSize },
  });
}

/** 创建 Bot */
export function createBot(payload: CreateBotPayload): Promise<BotItem> {
  return backendAuthRequest.post<BotItem>('/bots', payload);
}

/** 更新 Bot 配置 */
export function updateBot(botId: string, payload: UpdateBotPayload): Promise<BotItem> {
  return backendAuthRequest.post<BotItem>(`/bots/${encodeURIComponent(botId)}`, payload);
}

/** 软删除 Bot */
export function deleteBot(botId: string): Promise<{ bot_id: string; deleted: boolean }> {
  return backendAuthRequest.delete(`/bots/${encodeURIComponent(botId)}`);
}
