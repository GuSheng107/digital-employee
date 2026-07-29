import axios from 'axios';
import { message } from 'antd';
import { BACKEND_AUTH_API_BASE_URL } from '@/config/api-config';
import { useUserStore } from '@/store/user-store';
import { createTraceHeaders } from './trace-context';

interface AuthApiEnvelope<T> {
  success: boolean;
  data: T;
}

interface RefreshTokenPair {
  access_token: string;
  refresh_token: string;
}

let refreshPromise: Promise<boolean> | null = null;

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

async function requestTokenRefresh(refreshToken: string): Promise<boolean> {
  try {
    const response = await axios.post<AuthApiEnvelope<unknown>>(
      `${BACKEND_AUTH_API_BASE_URL}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 10000, headers: createTraceHeaders() },
    );
    if (
      response.data.success !== true
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

/** 合并并发 401，只使用 refresh_token 发起一次恢复请求。 */
export async function refreshAuthenticatedSession(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) {
    return false;
  }
  if (refreshPromise) {
    return refreshPromise;
  }

  const pending = requestTokenRefresh(refreshToken);
  refreshPromise = pending;
  try {
    return await pending;
  } finally {
    if (refreshPromise === pending) {
      refreshPromise = null;
    }
  }
}

/** 清理本地会话并带原访问地址跳转登录页。 */
export function invalidateSessionAndRedirect(errorCode?: string): void {
  const hadStoredSession =
    localStorage.getItem('access_token') != null
    || localStorage.getItem('refresh_token') != null;
  useUserStore.getState().clearAuth();
  const currentPath = window.location.pathname + window.location.search;
  if (window.location.pathname !== '/login') {
    if (hadStoredSession && errorCode === 'SESSION_REPLACED') {
      void message.warning('您的账号已在其他设备登录，请重新登录');
    }
    window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
  }
}
