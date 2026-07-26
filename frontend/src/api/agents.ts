import request from '@/utils/request';

export interface Agent {
  provider_key: string;
  provider_type?: string;
  model?: string;
  display_name?: string;
  is_active?: boolean;
  system_prompt?: string;
  temperature?: number;
  max_tokens?: number;
  [key: string]: unknown;
}

export interface AgentListParams {
  provider_key?: string;
  page?: number;
  page_size?: number;
  keyword?: string;
}

export async function getAgents(params: AgentListParams = {}) {
  const search = new URLSearchParams();
  if (params.provider_key) search.set('provider_key', params.provider_key);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  if (params.keyword) search.set('keyword', params.keyword);
  const query = search.toString();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const response: any = await request.get(`/agents${query ? `?${query}` : ''}`);
  if (params.provider_key) {
    return response.agent as Agent;
  }
  return response;
}

export async function getAgent(providerKey: string): Promise<Agent> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const response: any = await request.get(`/agents?provider_key=${encodeURIComponent(providerKey)}`);
  return response.agent;
}

export async function saveAgent(agent: Agent, mode: 'add' | 'edit' = 'add'): Promise<Agent> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const response: any = await request.post('/agents', { ...agent, mode });
  return response.agent;
}

export async function toggleAgent(providerKey: string, isActive: boolean) {
  return request.post(`/agents/${encodeURIComponent(providerKey)}/toggle`, { is_active: isActive });
}

export async function testAgent(providerKey: string) {
  return request.post(`/agents/${encodeURIComponent(providerKey)}/test`);
}

export async function getAgentCapabilities(model: string, providerType: string) {
  const search = new URLSearchParams();
  search.set('model', model);
  search.set('provider_type', providerType);
  return request.get(`/agents/capabilities?${search.toString()}`);
}

export async function getAgentProviderSchemas(): Promise<Record<string, unknown>> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const response: any = await request.get('/agents/provider-schemas');
  return response.providers || {};
}

export async function batchDeleteAgents(providerKeys: string[]) {
  return request.post('/agents/batch-delete', { provider_keys: providerKeys });
}

export function getAiStatus() {
  return request.get('/ai/status');
}

export function cancelAiWork(traceId: string) {
  return request.post(`/ai/status/${encodeURIComponent(traceId)}/cancel`);
}

export function clearAiWork(traceId: string) {
  return request.delete(`/ai/status/${encodeURIComponent(traceId)}`);
}
