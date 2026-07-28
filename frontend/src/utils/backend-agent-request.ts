import type { InternalAxiosRequestConfig } from 'axios';
import { BaseRequest } from './request';
import { useUserStore } from '../store/user-store';

/** backend-agent 响应信封：{ code, message, data } */
export interface AgentApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

/** 类型守卫：判断响应体是否为 backend-agent 响应信封形状 */
function isAgentResponse(body: unknown): body is AgentApiResponse<unknown> {
  return (
    body != null &&
    typeof body === 'object' &&
    'code' in body &&
    'message' in body &&
    'data' in body &&
    typeof (body as { code: unknown }).code === 'number'
  );
}

/**
 * BackendAgentRequest — 对接 backend-agent (port 8765) 的请求类。
 *
 * 响应格式：{ code, message, data }，code === 200 表示成功。
 * 带 Bearer token 认证，401/403 时清除用户状态。
 */
class BackendAgentRequest extends BaseRequest {
  constructor() {
    super(import.meta.env.VITE_API_BASE_URL || '/backend-agent-api');
  }

  protected isSuccess(body: unknown): boolean {
    return isAgentResponse(body) && body.code === 200;
  }

  protected extractData(body: unknown): unknown {
    return isAgentResponse(body) ? body.data : undefined;
  }

  protected getErrorMessage(body: unknown): string {
    if (isAgentResponse(body) && typeof body.message === 'string') {
      return body.message;
    }
    return '业务请求失败';
  }

  protected onRequest(config: InternalAxiosRequestConfig): void {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
  }

  protected onAuthError(): void {
    useUserStore.getState().clearAuth();
  }
}

const backendAgentRequest = new BackendAgentRequest();

export default backendAgentRequest;
