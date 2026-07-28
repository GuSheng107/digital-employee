import type { InternalAxiosRequestConfig } from 'axios';
import { BaseRequest } from './request';
import { useUserStore } from '../store/user-store';

/** backend-auth 响应信封：{ success, message, data } */
export interface AuthApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

/** 类型守卫：判断响应体是否为 backend-auth 响应信封形状 */
function isAuthResponse(body: unknown): body is AuthApiResponse<unknown> {
  return (
    body != null &&
    typeof body === 'object' &&
    'success' in body &&
    'message' in body &&
    'data' in body &&
    typeof (body as { success: unknown }).success === 'boolean'
  );
}

/**
 * BackendAuthRequest — 对接 backend-auth (port 8020) 的请求类。
 *
 * 响应格式：{ success, message, data }，success === true 表示成功。
 * 带 Bearer access_token 认证，401/403 时清除用户状态并跳转登录页。
 *
 * 双 token 机制：
 * - access_token 存 localStorage，请求时注入 Authorization 头
 * - refresh_token 存 localStorage，access_token 过期时自动刷新
 * - 刷新失败或用户被禁用时清除登录态
 */
class BackendAuthRequest extends BaseRequest {
  private static instance: BackendAuthRequest;
  private isRefreshing = false;

  private constructor() {
    // 统一带 /api/v1 前缀，避免每个 api 文件重复写
    super(import.meta.env.VITE_BACKEND_AUTH_API_BASE_URL || '/backend-auth-api/api/v1');
  }

  /** 单例获取，避免多次创建拦截器 */
  static getInstance(): BackendAuthRequest {
    if (!BackendAuthRequest.instance) {
      BackendAuthRequest.instance = new BackendAuthRequest();
    }
    return BackendAuthRequest.instance;
  }

  protected isSuccess(body: unknown): boolean {
    return isAuthResponse(body) && body.success;
  }

  protected extractData(body: unknown): unknown {
    return isAuthResponse(body) ? body.data : undefined;
  }

  protected getErrorMessage(body: unknown): string {
    if (isAuthResponse(body) && typeof body.message === 'string') {
      return body.message;
    }
    return '认证请求失败';
  }

  /** 从响应体 data 字段提取业务错误码（ErrorResponse.code） */
  protected getErrorCode(body: unknown): string | undefined {
    if (isAuthResponse(body) && body.data != null && typeof body.data === 'object') {
      const data = body.data as { code?: unknown };
      if (typeof data.code === 'string') {
        return data.code;
      }
    }
    return undefined;
  }

  protected onRequest(config: InternalAxiosRequestConfig): void {
    const accessToken = localStorage.getItem('access_token');
    if (accessToken && config.headers) {
      config.headers['Authorization'] = `Bearer ${accessToken}`;
    }
  }

  protected onAuthError(): void {
    useUserStore.getState().clearAuth();
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    // 跳转登录页，保留原路径用于登录后回跳
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath !== '/login') {
      window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
    }
  }

  /** 读取存储的 refresh_token */
  getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  /** 读取存储的 access_token */
  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  /** 是否正在刷新 token，避免并发刷新 */
  getIsRefreshing(): boolean {
    return this.isRefreshing;
  }

  /** 标记刷新状态 */
  setRefreshing(value: boolean): void {
    this.isRefreshing = value;
  }
}

const backendAuthRequest = BackendAuthRequest.getInstance();

export default backendAuthRequest;
