import { getRequestErrorMessage } from './request';
import { AuthenticatedRequest } from './authenticated-request';
import { DATA_PLATFORM_API_BASE_URL } from '@/config/api-config';

/** 数据中台响应信封：{ success, message, data } */
export interface DataPlatformApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

/** 类型守卫：判断响应体是否为数据中台响应信封形状 */
function isDataPlatformResponse(body: unknown): body is DataPlatformApiResponse<unknown> {
  return (
    body != null &&
    typeof body === 'object' &&
    'success' in body &&
    'message' in body &&
    'data' in body &&
    typeof (body as { success: unknown }).success === 'boolean'
  );
}

/** 从 data 字段中提取业务错误码（data.code），不存在则返回 undefined */
function extractDataPlatformErrorCode(body: unknown): string | undefined {
  if (isDataPlatformResponse(body)) {
    const data = body.data;
    if (data != null && typeof data === 'object' && 'code' in data) {
      const code = (data as { code: unknown }).code;
      if (typeof code === 'string' && code) return code;
    }
  }
  return undefined;
}

/**
 * DataPlatformRequest — 对接 backend-data (port 8010) 的请求类。
 *
 * 响应格式：{ success, message, data }，success === true 表示成功。
 * 统一携带 Bearer token；401 时尝试刷新一次，失败后清理会话并回登录页。
 */
class DataPlatformRequest extends AuthenticatedRequest {
  constructor() {
    super(DATA_PLATFORM_API_BASE_URL);
  }

  protected isSuccess(body: unknown): boolean {
    return isDataPlatformResponse(body) && body.success === true;
  }

  protected extractData(body: unknown): unknown {
    return isDataPlatformResponse(body) ? body.data : undefined;
  }

  protected getErrorMessage(body: unknown): string {
    if (isDataPlatformResponse(body) && typeof body.message === 'string') {
      return body.message;
    }
    return '数据中台请求失败';
  }

  /** 从 data.code 提取业务错误码（如 DEPENDENCY_UNAVAILABLE） */
  protected getErrorCode(body: unknown): string | undefined {
    return extractDataPlatformErrorCode(body);
  }
}

const dataPlatformRequest = new DataPlatformRequest();

export default dataPlatformRequest;

/** 提取错误信息（向后兼容导出） */
export function getDataPlatformErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '数据中台请求失败');
}
