import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { message } from 'antd';

// 数据中台响应信封：{ success, message, data }
export interface DataPlatformApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

const instance: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_DATA_PLATFORM_API_BASE_URL || '/data-platform-api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => config,
  (error) => Promise.reject(error),
);

// 响应拦截器：解包 data.data，业务层直接拿到 T 而非 AxiosResponse<T>
// 注意：axios 类型要求 fulfilled 返回 AxiosResponse，这里运行时返回的是 body.data，
// 通过 as unknown as AxiosResponse 在类型层兼容，下方包装层会再次断言为 Promise<T>
instance.interceptors.response.use(
  (response) => {
    const body = response.data as DataPlatformApiResponse<unknown>;
    if (!body.success) {
      message.error(body.message || '数据中台请求失败');
      return Promise.reject(new Error(body.message || 'Error'));
    }
    return body.data as unknown as AxiosResponse;
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

// 类型化包装：响应拦截器已解包 data.data，此处把 AxiosPromise 断言为 Promise<T>
// 强转仅存在于封装层一处，调用方直接返回 Promise<T>，无需二次断言
export const dataPlatformRequest = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config) as unknown as Promise<T>;
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config) as unknown as Promise<T>;
  },
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config) as unknown as Promise<T>;
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config) as unknown as Promise<T>;
  },
};

export default dataPlatformRequest;

// 提取错误信息
export function getDataPlatformErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '数据中台请求失败';
}
