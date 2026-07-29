import { AuthenticatedRequest } from './authenticated-request';
import { BACKEND_AUTH_API_BASE_URL } from '@/config/api-config';

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

const SESSION_NEUTRAL_AUTH_PATHS = Object.freeze([
  '/auth/login',
  '/auth/register',
  '/auth/captcha',
  '/auth/refresh',
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
class BackendAuthRequest extends AuthenticatedRequest {
  private static instance: BackendAuthRequest;

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

  protected shouldSkipSessionRecovery(requestUrl: string): boolean {
    return isSessionNeutralAuthRequest(requestUrl);
  }
}

const backendAuthRequest = BackendAuthRequest.getInstance();

export default backendAuthRequest;
