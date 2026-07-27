import { BaseRequest, getRequestErrorMessage } from './request';

/** 数据中台响应信封：{ success, message, data } */
export interface DataPlatformApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

/**
 * DataPlatformRequest — 对接 backend-data (port 8010) 的请求类。
 *
 * 响应格式：{ success, message, data }，success === true 表示成功。
 * 无 token 认证，无 401/403 处理。
 */
class DataPlatformRequest extends BaseRequest {
  constructor() {
    super(import.meta.env.VITE_DATA_PLATFORM_API_BASE_URL || '/data-platform-api');
  }

  protected isSuccess(body: unknown): boolean {
    return (
      body != null &&
      typeof body === 'object' &&
      'success' in body &&
      (body as DataPlatformApiResponse<unknown>).success === true
    );
  }

  protected extractData(body: unknown): unknown {
    return (body as DataPlatformApiResponse<unknown>).data;
  }

  protected getErrorMessage(body: unknown): string {
    if (body && typeof body === 'object' && 'message' in body) {
      const msg = (body as { message?: unknown }).message;
      if (typeof msg === 'string') return msg;
    }
    return '数据中台请求失败';
  }
}

const dataPlatformRequest = new DataPlatformRequest();

export default dataPlatformRequest;

/** 提取错误信息（向后兼容导出） */
export function getDataPlatformErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '数据中台请求失败');
}
