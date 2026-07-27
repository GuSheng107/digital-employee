import backendAgentRequest from '@/utils/backend-agent-request';

/** 登录请求参数 */
export interface LoginPayload {
  username: string;
  password: string;
}

/** 登录响应数据 */
export interface LoginResult {
  token: string;
  username: string;
  permission: string;
}

/** 调用 backend-agent 登录接口，返回 token 与用户信息 */
export function loginConsole(payload: LoginPayload): Promise<LoginResult> {
  return backendAgentRequest.post<LoginResult>('/api/auth/login', payload);
}

/** 调用 backend-agent 登出接口 */
export function logoutConsole(): Promise<void> {
  return backendAgentRequest.post<void>('/api/auth/logout');
}
