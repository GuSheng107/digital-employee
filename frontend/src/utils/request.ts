import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { message } from 'antd';
import { useUserStore } from '../store/user';
import { clearAuthSession, getAccessToken, getRefreshToken, saveTokenPair } from './authSession';

interface ApiEnvelope<T = unknown> {
  ok?: boolean;
  code?: number;
  message?: string;
  data?: T;
  trace_id?: string;
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
}

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

const refreshClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

let refreshPromise: Promise<boolean> | null = null;

function unwrapResponse<T>(data: ApiEnvelope<T>): T | ApiEnvelope<T> {
  if (Object.prototype.hasOwnProperty.call(data, 'data')) {
    return data.data as T;
  }
  return data;
}

function getErrorMessage(data: ApiEnvelope | undefined, fallback: string): string {
  return data?.message || fallback;
}

async function refreshTokens(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post<ApiEnvelope>('/auth/refresh', { refresh_token: refreshToken })
      .then((response) => {
        if (response.data.ok === false || !response.data.access_token) {
          return false;
        }
        saveTokenPair(response.data);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

request.interceptors.response.use(
  (response: AxiosResponse) => {
    const data = response.data as ApiEnvelope;
    if (data.ok === false || (typeof data.code === 'number' && data.code !== 200)) {
      const errorMessage = getErrorMessage(data, '业务请求失败');
      message.error(errorMessage);
      return Promise.reject(new Error(errorMessage));
    }
    return unwrapResponse(data) as AxiosResponse;
  },
  async (error: AxiosError<ApiEnvelope>) => {
    if (error.response) {
      const { status, data } = error.response;
      switch (status) {
        case 401:
          {
            const config = error.config as RetryableRequestConfig | undefined;
            const isRefreshRequest = config?.url?.includes('/auth/refresh');
            if (config && !config._retry && !isRefreshRequest && await refreshTokens()) {
              config._retry = true;
              const token = getAccessToken();
              if (token) {
                config.headers.Authorization = `Bearer ${token}`;
              }
              return request(config);
            }
            message.error('登录状态已过期，请重新登录');
            clearAuthSession();
            useUserStore.getState().clearUserInfo();
          }
          break;
        case 403:
          message.error(getErrorMessage(data, '您没有权限访问该资源'));
          break;
        case 500:
          message.error(getErrorMessage(data, '服务器内部错误，请稍后再试'));
          break;
        default:
          message.error(data?.message || '网络请求异常');
          break;
      }
    } else if (error.message.includes('timeout')) {
      message.error('请求超时，请检查网络连接');
    } else {
      message.error('无法连接到服务器');
    }
    return Promise.reject(error);
  }
);

/**
 * Fetch with auth headers for streaming/SSE responses and blob downloads.
 * Uses native fetch (not axios) to support ReadableStream and blob responses.
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
  const fullUrl = url.startsWith('http') ? url : `${baseUrl}${url}`;

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  const token = getAccessToken();
  if (token && !headers.Authorization && !headers.authorization) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(fullUrl, { ...options, headers });

  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const newToken = getAccessToken();
      if (newToken) {
        headers.Authorization = `Bearer ${newToken}`;
      }
      return fetch(fullUrl, { ...options, headers });
    }
    clearAuthSession();
    useUserStore.getState().clearUserInfo();
  }

  return response;
}

export default request;
