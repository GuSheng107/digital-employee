import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';

/** HTTP 错误：保留 status/data/config 等结构化字段，便于调用方按状态码分支处理 */
export class HttpError extends Error {
  readonly status?: number;
  readonly data?: unknown;
  readonly config?: unknown;

  constructor(message: string, opts: { status?: number; data?: unknown; config?: unknown } = {}) {
    super(message);
    this.name = 'HttpError';
    this.status = opts.status;
    this.data = opts.data;
    this.config = opts.config;
  }
}

/** 响应体形状探测：是否包含指定字段 */
function hasField<T extends string>(body: unknown, field: T): body is Record<T, unknown> {
  return body != null && typeof body === 'object' && field in body;
}

/** 从 unknown 响应体中安全读取 string 类型 message 字段 */
function readMessageField(body: unknown, fallback: string): string {
  if (hasField(body, 'message')) {
    const msg = body.message;
    if (typeof msg === 'string') return msg;
  }
  return fallback;
}

/**
 * BaseRequest — 所有平台请求类的抽象基类。
 *
 * 子类需实现：
 *   - isSuccess(body) 业务成功判断
 *   - extractData(body) 从响应体提取业务数据
 *
 * 可选覆写：
 *   - onRequest(config)  请求拦截（如加 token）
 *   - onAuthError()      401/403 处理（如清用户态）
 *   - getErrorMessage(body) 自定义错误文案
 *
 * 错误处理策略：基类不展示错误（不耦合 UI 库），仅将错误 normalize 为
 * HttpError 抛出（携带 status/data/config 与 friendly message）。
 * 调用方在 catch 中自行展示，也可通过 error.status 按状态码分支处理。
 */
export abstract class BaseRequest {
  protected instance: AxiosInstance;

  constructor(baseURL: string) {
    this.instance = axios.create({
      baseURL,
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
    return readMessageField(body, '请求失败');
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

    // 响应拦截：normalize HTTP 错误为 HttpError（保留 status/data/config），
    // 不展示错误（不耦合 UI 库），调用方在 catch 中自行展示
    this.instance.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error) => {
        const { message, status, data, config } = this.buildHttpError(error);
        return Promise.reject(new HttpError(message, { status, data, config }));
      },
    );
  }

  /** 将原始 axios 错误转换为 { message, status, data, config }，保留结构化字段 */
  protected buildHttpError(error: unknown): {
    message: string;
    status?: number;
    data?: unknown;
    config?: unknown;
  } {
    if (!(error instanceof Error)) {
      return { message: '请求失败' };
    }

    if (hasField(error, 'response')) {
      const response = error.response as
        | { status: number; data?: unknown; config?: unknown }
        | undefined;
      if (response) {
        const { status, data, config } = response;
        let message: string;
        switch (status) {
          case 401:
            this.onAuthError(status);
            message = '登录状态已过期，请重新登录';
            break;
          case 403:
            message = '您没有权限访问该资源';
            break;
          case 500:
            message = '服务器内部错误，请稍后再试';
            break;
          default:
            message = this.getErrorMessage(data) || '网络请求异常';
        }
        return { message, status, data, config };
      }
    }

    if (hasField(error, 'message') && typeof error.message === 'string') {
      if (error.message.includes('timeout')) {
        return { message: '请求超时，请检查网络连接' };
      }
    }
    return { message: '无法连接到服务器' };
  }

  /** 将 HTTP 错误 normalize 为用户友好的消息字符串 */
  protected getHttpErrorMessage(error: unknown): string {
    return this.buildHttpError(error).message;
  }

  /**
   * 业务响应解包：校验 isSuccess，提取 data。
   * 消除审核报告 #7 的双重 as unknown as 断言。
   * 业务失败时 throw Error，不展示（调用方 catch 展示）。
   */
  protected unwrapResponse<T>(body: unknown): T {
    if (!this.isSuccess(body)) {
      throw new Error(this.getErrorMessage(body));
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
