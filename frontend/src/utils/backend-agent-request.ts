import type { InternalAxiosRequestConfig } from 'axios';
import { BaseRequest } from './request';
import { useUserStore } from '../store/user';

/** backend-agent 响应信封：{ code, message, data } */
export interface AgentApiResponse<T> {
  code: number;
  message: string;
  data: T;
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
    return (
      body != null &&
      typeof body === 'object' &&
      'code' in body &&
      (body as AgentApiResponse<unknown>).code === 200
    );
  }

  protected extractData(body: unknown): unknown {
    return (body as AgentApiResponse<unknown>).data;
  }

  protected getErrorMessage(body: unknown): string {
    if (body && typeof body === 'object' && 'message' in body) {
      const msg = (body as { message?: unknown }).message;
      if (typeof msg === 'string') return msg;
    }
    return '业务请求失败';
  }

  protected onRequest(config: InternalAxiosRequestConfig): void {
    const token = localStorage.getItem('token');
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
  }

  protected onAuthError(): void {
    useUserStore.getState().clearUserInfo();
    localStorage.removeItem('token');
  }
}

const backendAgentRequest = new BackendAgentRequest();

export default backendAgentRequest;
