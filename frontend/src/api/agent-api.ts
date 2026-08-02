import backendAuthRequest from '@/utils/backend-auth-request';

export interface AgentItem {
  id: number;
  agent_id: string;
  name: string;
  status: number;
  created_by?: number | null;
  created_by_name?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentListResponse {
  total: number;
  page: number;
  page_size: number;
  items: AgentItem[];
}

export interface CreateAgentPayload {
  agent_id: string;
  name: string;
  status?: number;
}

export interface UpdateAgentPayload {
  name?: string;
  status?: number;
}

/** 分页查询 Agent 列表 */
export function fetchAgents(page: number = 1, pageSize: number = 20): Promise<AgentListResponse> {
  return backendAuthRequest.get<AgentListResponse>('/agents', {
    params: { page, page_size: pageSize },
  });
}

/** 创建 Agent */
export function createAgent(payload: CreateAgentPayload): Promise<AgentItem> {
  return backendAuthRequest.post<AgentItem>('/agents', payload);
}

/** 更新 Agent 配置 */
export function updateAgent(agentId: string, payload: UpdateAgentPayload): Promise<AgentItem> {
  return backendAuthRequest.post<AgentItem>(`/agents/${encodeURIComponent(agentId)}`, payload);
}

/** 软删除 Agent */
export function deleteAgent(agentId: string): Promise<{ agent_id: string; deleted: boolean }> {
  return backendAuthRequest.delete<{ agent_id: string; deleted: boolean }>(
    `/agents/${encodeURIComponent(agentId)}`,
  );
}
