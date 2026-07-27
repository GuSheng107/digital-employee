import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { message } from 'antd';

/**
 * BaseRequest — 所有平台请求类的抽象基类。
 *
 * 子类需实现：
 *   - baseURL         目标后端地址
 *   - isSuccess(body) 业务成功判断
 *   - extractData(body) 从响应体提取业务数据
 *
 * 可选覆写：
 *   - onRequest(config)  请求拦截（如加 token）
 *   - onAuthError()      401/403 处理（如清用户态）
 *   - getErrorMessage(body) 自定义错误文案
 */
export abstract class BaseRequest {
  protected instance: AxiosInstance;
  protected baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.instance = axios.create({
      baseURL: this.baseURL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    this.setupInterceptors();
  }

  // ── 子类必须实现 ────────────────────────────────

  protected abstract isSuccess(body: unknown): boolean;

  protected abstract extractData(body: unknown): unknown;

  // ── 子类可选覆写 ────────────────────────────────

  /** 请求拦截 hook，默认空实现。子类可覆写以加 token 等 */
  protected onRequest(_config: InternalAxiosRequestConfig): void {
    // default: no-op
  }

  /** 401/403 认证失败 hook，默认空实现。子类可覆写以清用户态 */
  protected onAuthError(_status: number): void {
    // default: no-op
  }

  /** 从响应体提取错误消息，子类可覆写 */
  protected getErrorMessage(body: unknown): string {
    if (body && typeof body === 'object' && 'message' in body) {
      const msg = (body as { message?: unknown }).message;
      if (typeof msg === 'string') return msg;
    }
    return '请求失败';
  }

  // ── 公共固定实现 ────────────────────────────────

  protected setupInterceptors(): void {
    // 请求拦截：调用 hook
    this.instance.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        this.onRequest(config);
        return config;
      },
      (error) => Promise.reject(error),
    );

    // 响应拦截：只处理 HTTP 错误，业务解包在 wrapper 中做
    this.instance.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error) => {
        this.handleHttpError(error);
        return Promise.reject(error);
      },
    );
  }

  /** HTTP 层错误处理（timeout / 网络错误 / 4xx / 5xx） */
  protected handleHttpError(error: unknown): void {
    if (!(error instanceof Error)) return;

    // axios error with response
    const axiosError = error as { response?: { status: number; data?: unknown }; message?: string };
    if (axiosError.response) {
      const { status, data } = axiosError.response;
      switch (status) {
        case 401:
        case 403:
          this.onAuthError(status);
          message.error(status === 401 ? '登录状态已过期，请重新登录' : '您没有权限访问该资源');
          break;
        case 500:
          message.error('服务器内部错误，请稍后再试');
          break;
        default:
          message.error(this.getErrorMessage(data) || '网络请求异常');
          break;
      }
    } else if (axiosError.message?.includes('timeout')) {
      message.error('请求超时，请检查网络连接');
    } else {
      message.error('无法连接到服务器');
    }
  }

  /**
   * 业务响应解包：校验 isSuccess，提取 data。
   * 消除审核报告 #7 的双重 as unknown as 断言。
   */
  protected unwrapResponse<T>(body: unknown): T {
    if (!this.isSuccess(body)) {
      const msg = this.getErrorMessage(body);
      message.error(msg);
      throw new Error(msg);
    }
    return this.extractData(body) as T;
  }

  // ── 类型化包装方法 ──────────────────────────────

  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.get(url, config).then((res) => this.unwrapResponse<T>(res.data));
  }

  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.post(url, data, config).then((res) => this.unwrapResponse<T>(res.data));
  }

  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.put(url, data, config).then((res) => this.unwrapResponse<T>(res.data));
  }

  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.delete(url, config).then((res) => this.unwrapResponse<T>(res.data));
  }
}

/** 通用错误信息提取 */
export function getRequestErrorMessage(error: unknown, fallback = '请求失败'): string {
  return error instanceof Error ? error.message : fallback;
}
