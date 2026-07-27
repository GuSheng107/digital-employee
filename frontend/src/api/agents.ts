import request from '@/utils/request';

export interface Agent {
  provider_key: string;
  provider_type?: string;
  provider_name?: string;
  model?: string;
  display_name?: string;
  label?: string;
  base_url?: string;
  api_key?: string;
  is_active?: boolean;
  is_bound_to_bot?: boolean;
  system_prompt?: string;
  temperature?: number;
  timeout_seconds?: number;
  max_retries?: number;
  reasoning_effort?: string;
  mounted_bot_names?: string[];
  last_test_status?: string;
  last_test_time?: string;
  last_test_trace_id?: string;
  max_tokens?: number;
  [key: string]: unknown;
}

export interface AgentListParams {
  provider_key?: string;
  page?: number;
  page_size?: number;
  keyword?: string;
}

export interface AgentListResponse {
  agents: Agent[];
}

interface AgentItemResponse {
  agent: Agent;
}

interface AgentProviderSchemasResponse {
  providers?: Record<string, unknown>;
}

export interface AiTask {
  trace_id: string;
  status: string;
  stage?: string;
  question?: string;
  reasoning?: string;
  error?: string;
  chat_name?: string;
  chat_id?: string;
  conv_display_name?: string;
  conv_chat_type?: string;
  conv_sender_name?: string;
  started_at?: string;
}

export interface AiStatus {
  busy: boolean;
  active: AiTask[];
  recent: AiTask[];
}

export function getAgents(params: AgentListParams & { provider_key: string }): Promise<Agent>;
export function getAgents(params?: AgentListParams): Promise<AgentListResponse>;
export async function getAgents(params: AgentListParams = {}): Promise<Agent | AgentListResponse> {
  const search = new URLSearchParams();
  if (params.provider_key) search.set('provider_key', params.provider_key);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  if (params.keyword) search.set('keyword', params.keyword);
  const query = search.toString();
  if (params.provider_key) {
    const response = await request.get(`/agents${query ? `?${query}` : ''}`) as AgentItemResponse;
    return response.agent;
  }
  return request.get(`/agents${query ? `?${query}` : ''}`) as Promise<AgentListResponse>;
}

export async function getAgent(providerKey: string): Promise<Agent> {
  const response = await request.get(`/agents?provider_key=${encodeURIComponent(providerKey)}`) as AgentItemResponse;
  return response.agent;
}

export async function saveAgent(agent: Agent, mode: 'add' | 'edit' = 'add'): Promise<Agent> {
  const response = await request.post('/agents', { ...agent, mode }) as AgentItemResponse;
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
  const response = await request.get('/agents/provider-schemas') as AgentProviderSchemasResponse;
  return response.providers || {};
}

export async function batchDeleteAgents(providerKeys: string[]) {
  return request.post('/agents/batch-delete', { provider_keys: providerKeys });
}

export function getAiStatus(): Promise<AiStatus> {
  return request.get('/ai/status') as Promise<AiStatus>;
}

export function cancelAiWork(traceId: string) {
  return request.post(`/ai/status/${encodeURIComponent(traceId)}/cancel`);
}

export function clearAiWork(traceId: string) {
  return request.delete(`/ai/status/${encodeURIComponent(traceId)}`);
}
