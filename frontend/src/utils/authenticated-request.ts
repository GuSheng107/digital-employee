import axios, {
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import {
  invalidateSessionAndRedirect,
  refreshAuthenticatedSession,
} from './auth-session';
import { BaseRequest } from './request';

interface AuthRetryConfig extends InternalAxiosRequestConfig {
  _authRetryAttempted?: boolean;
}

function getRequestUrl(config: unknown): string {
  if (config != null && typeof config === 'object' && 'url' in config) {
    return typeof config.url === 'string' ? config.url : '';
  }
  return '';
}

/** 带 Bearer token、单次刷新和统一失效跳转的请求基类。 */
export abstract class AuthenticatedRequest extends BaseRequest {
  protected onRequest(config: InternalAxiosRequestConfig): void {
    const accessToken = localStorage.getItem('access_token');
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
  }

  protected async recoverFromHttpError(
    error: unknown,
  ): Promise<AxiosResponse | undefined> {
    if (
      !axios.isAxiosError(error)
      || error.response?.status !== 401
      || !error.config
      || this.shouldSkipSessionRecovery(error.config.url ?? '')
      || (error.config as AuthRetryConfig)._authRetryAttempted === true
    ) {
      return undefined;
    }

    const retryConfig = error.config as AuthRetryConfig;
    retryConfig._authRetryAttempted = true;
    const refreshed = await refreshAuthenticatedSession();
    if (!refreshed) {
      return undefined;
    }
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      return undefined;
    }
    retryConfig.headers.Authorization = `Bearer ${accessToken}`;
    return this.instance.request(retryConfig);
  }

  protected onAuthError(
    _status: number,
    config?: unknown,
    code?: string,
  ): void {
    if (this.shouldSkipSessionRecovery(getRequestUrl(config))) {
      return;
    }
    invalidateSessionAndRedirect(code);
  }

  /** 登录、注册和刷新接口可覆写为 true，避免递归恢复。 */
  protected shouldSkipSessionRecovery(_requestUrl: string): boolean {
    return false;
  }
}
