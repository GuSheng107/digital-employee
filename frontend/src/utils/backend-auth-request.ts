import axios, {
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { BACKEND_AUTH_API_BASE_URL } from '@/config/api-config';
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

interface RefreshTokenPair {
  access_token: string;
  refresh_token: string;
}

function isRefreshTokenPair(value: unknown): value is RefreshTokenPair {
  return (
    value != null
    && typeof value === 'object'
    && 'access_token' in value
    && typeof value.access_token === 'string'
    && 'refresh_token' in value
    && typeof value.refresh_token === 'string'
  );
}

function getRequestUrl(config: unknown): string {
  if (config != null && typeof config === 'object' && 'url' in config) {
    return typeof config.url === 'string' ? config.url : '';
  }
  return '';
}

const SESSION_NEUTRAL_AUTH_PATHS = Object.freeze([
  '/auth/login',
  '/auth/register',
]);

function isSessionNeutralAuthRequest(url: string): boolean {
  return SESSION_NEUTRAL_AUTH_PATHS.some((path) => url.endsWith(path));
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
  private refreshPromise: Promise<boolean> | null = null;
  private readonly retriedConfigs = new WeakSet<object>();

  private constructor() {
    // 统一带 /api/v1 前缀，避免每个 api 文件重复写
    super(BACKEND_AUTH_API_BASE_URL);
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

  protected async recoverFromHttpError(
    error: unknown,
  ): Promise<AxiosResponse | undefined> {
    if (
      !axios.isAxiosError(error)
      || error.response?.status !== 401
      || !error.config
    ) {
      return undefined;
    }

    const requestUrl = error.config.url ?? '';
    if (
      isSessionNeutralAuthRequest(requestUrl)
      || requestUrl.endsWith('/auth/refresh')
      || this.retriedConfigs.has(error.config)
    ) {
      return undefined;
    }

    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      return undefined;
    }

    this.retriedConfigs.add(error.config);
    const refreshed = await this.refreshSession(refreshToken);
    if (!refreshed) {
      return undefined;
    }

    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      return undefined;
    }
    error.config.headers.Authorization = `Bearer ${accessToken}`;
    return this.instance.request(error.config);
  }

  protected onAuthError(_status: number, config?: unknown): void {
    if (isSessionNeutralAuthRequest(getRequestUrl(config))) {
      return;
    }
    useUserStore.getState().clearAuth();
    // 跳转登录页，保留原路径用于登录后回跳
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath !== '/login') {
      window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
    }
  }

  /** 合并并发 401，只发起一次 refresh 请求。 */
  private async refreshSession(refreshToken: string): Promise<boolean> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    const refreshPromise = this.requestTokenRefresh(refreshToken);
    this.refreshPromise = refreshPromise;
    try {
      return await refreshPromise;
    } finally {
      if (this.refreshPromise === refreshPromise) {
        this.refreshPromise = null;
      }
    }
  }

  /** 使用独立 Axios 实例刷新 token，避免刷新请求进入当前拦截器造成递归。 */
  private async requestTokenRefresh(refreshToken: string): Promise<boolean> {
    try {
      const response = await axios.post<AuthApiResponse<unknown>>(
        `${BACKEND_AUTH_API_BASE_URL}/auth/refresh`,
        { refresh_token: refreshToken },
        { timeout: 10000 },
      );
      if (
        !isAuthResponse(response.data)
        || !response.data.success
        || !isRefreshTokenPair(response.data.data)
      ) {
        return false;
      }
      localStorage.setItem('access_token', response.data.data.access_token);
      localStorage.setItem('refresh_token', response.data.data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }
}

const backendAuthRequest = BackendAuthRequest.getInstance();

export default backendAuthRequest;
