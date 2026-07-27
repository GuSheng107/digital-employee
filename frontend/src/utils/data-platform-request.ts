import { BaseRequest, getRequestErrorMessage } from './request';

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
}

const dataPlatformRequest = new DataPlatformRequest();

export default dataPlatformRequest;

/** 提取错误信息（向后兼容导出） */
export function getDataPlatformErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '数据中台请求失败');
}
