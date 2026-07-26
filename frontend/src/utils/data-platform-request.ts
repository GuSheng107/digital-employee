import axios, { type AxiosInstance, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

// 数据中台响应信封：{ success, message, data }
export interface DataPlatformApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

// 数据中台独立 baseURL，端口 8010 与主项目后端不同
const dataPlatformRequest: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_DATA_PLATFORM_API_BASE_URL || '/data-platform-api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

dataPlatformRequest.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => config,
  (error) => Promise.reject(error),
);

dataPlatformRequest.interceptors.response.use(
  (response: AxiosResponse<DataPlatformApiResponse<unknown>>) => {
    const { data } = response;
    if (!data.success) {
      message.error(data.message || '数据中台请求失败');
      return Promise.reject(new Error(data.message || 'Error'));
    }
    // 直接返回 data.data，便于业务层按需透传
    return data.data as unknown as AxiosResponse;
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response;
      switch (status) {
        case 500:
          message.error('数据中台内部错误，请稍后再试');
          break;
        default:
          message.error(data?.message || '数据中台请求异常');
          break;
      }
    } else if (error.message.includes('timeout')) {
      message.error('数据中台请求超时，请检查网络连接');
    } else {
      message.error('无法连接到数据中台');
    }
    return Promise.reject(error);
  },
);

export default dataPlatformRequest;

// 提取错误信息
export function getDataPlatformErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '数据中台请求失败';
}
