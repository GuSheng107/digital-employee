import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { createTraceHeaders, TRACE_ID_HEADER } from './trace-context';

/** HTTP 错误：保留 status/data/config/code/traceId 等结构化字段，便于调用方按状态码分支处理 */
export class HttpError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly data?: unknown;
  readonly config?: unknown;
  /** 本次请求的 traceId，便于联调 debug 与日志查询页定位 */
  readonly traceId?: string;

  constructor(
    message: string,
    opts: {
      status?: number;
      code?: string;
      data?: unknown;
      config?: unknown;
      traceId?: string;
    } = {},
  ) {
    super(message);
    this.name = 'HttpError';
    this.status = opts.status;
    this.code = opts.code;
    this.data = opts.data;
    this.config = opts.config;
    this.traceId = opts.traceId;
  }
}

/** 响应体形状探测：是否包含指定字段 */
function hasField<T extends string>(body: unknown, field: T): body is Record<T, unknown> {
  return body != null && typeof body === 'object' && field in body;
}

/** 从 AxiosHeaders（支持 .get()）或普通对象中读取指定头，大小写不敏感。 */
function readHeader(headers: unknown, name: string): string | undefined {
  if (headers == null || typeof headers !== 'object') {
    return undefined;
  }
  // AxiosHeaders 实例：.get() 内部已做大小写归一
  if ('get' in headers && typeof (headers as { get: unknown }).get === 'function') {
    const value = (headers as { get: (n: string) => unknown }).get(name);
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    return undefined;
  }
  // 普通对象：按小写 key 读取
  const lower = (headers as Record<string, unknown>)[name.toLowerCase()];
  if (typeof lower === 'string' && lower.trim()) {
    return lower.trim();
  }
  return undefined;
}

/** 从 axios 错误中提取 traceId。
 *
 * 优先读响应头（后端 TraceMiddleware 回写的 X-Trace-Id）；
 * 网络层失败无响应时回退读请求头（前端 createTraceHeaders 生成的值），
 * 保证即使后端不可达也能拿到 traceId 供日志排查。
 */
function extractTraceId(error: unknown): string | undefined {
  if (!(error instanceof Error)) {
    return undefined;
  }
  if (hasField(error, 'response')) {
    const response = error.response as { headers?: unknown } | undefined;
    const responseTraceId = readHeader(response?.headers, TRACE_ID_HEADER);
    if (responseTraceId) {
      return responseTraceId;
    }
  }
  if (hasField(error, 'config')) {
    const config = error.config as { headers?: unknown } | undefined;
    return readHeader(config?.headers, TRACE_ID_HEADER);
  }
  return undefined;
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
  protected onAuthError(
    _status: number,
    _config?: unknown,
    _code?: string,
  ): void {
    // default: no-op
  }

  /**
   * HTTP 错误恢复 hook。
   *
   * 子类可在错误标准化前尝试恢复请求（例如 access token 过期后刷新 token
   * 并重放原请求）。返回 AxiosResponse 表示恢复成功；返回 undefined
   * 则继续走统一 HttpError 构造流程。
   */
  protected recoverFromHttpError(_error: unknown): Promise<AxiosResponse | undefined> {
    return Promise.resolve(undefined);
  }

  /** 从响应体提取错误消息，子类可覆写 */
  protected getErrorMessage(body: unknown): string {
    return readMessageField(body, '请求失败');
  }

  /** 从响应体提取业务错误码（如 INVALID_CREDENTIALS / RATE_LIMIT_EXCEEDED），子类可覆写 */
  protected getErrorCode(_body: unknown): string | undefined {
    return undefined;
  }

  // ── 公共固定实现 ────────────────────────────────

  protected setupInterceptors(): void {
    // 请求拦截：调用 hook
    this.instance.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (!config.headers.has(TRACE_ID_HEADER)) {
          const traceHeaders = createTraceHeaders();
          Object.entries(traceHeaders).forEach(([key, value]) => {
            config.headers.set(key, value);
          });
        }
        this.onRequest(config);
        return config;
      },
      (error) => Promise.reject(error),
    );

    // 响应拦截：normalize HTTP 错误为 HttpError（保留 status/code/data/config/traceId），
    // 不展示错误（不耦合 UI 库），调用方在 catch 中自行展示
    this.instance.interceptors.response.use(
      (response: AxiosResponse) => response,
      async (error) => {
        const recoveredResponse = await this.recoverFromHttpError(error);
        if (recoveredResponse) {
          return recoveredResponse;
        }
        const { message, status, code, data, config } = this.buildHttpError(error);
        const traceId = extractTraceId(error);
        return Promise.reject(
          new HttpError(message, { status, code, data, config, traceId }),
        );
      },
    );
  }

  /** 将原始 axios 错误转换为 { message, status, code, data, config }，保留结构化字段 */
  protected buildHttpError(error: unknown): {
    message: string;
    status?: number;
    code?: string;
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
        const code = this.getErrorCode(data);
        // 优先使用后端返回的业务文案（统一信封中的 message），兜底用状态码默认文案。
        // 这样 401 登录失败时能显示"用户名或密码错误"而非"登录状态已过期"。
        const backendMessage = this.getErrorMessage(data);
        let message: string;
        switch (status) {
          case 401:
            // 登录接口 401（INVALID_CREDENTIALS）与 token 过期 401（TOKEN_INVALID）
            // 都走这里：onAuthError 内部判断当前路径，登录页不跳转。
            this.onAuthError(status, config, code);
            message = backendMessage || '登录状态已过期，请重新登录';
            break;
          case 403:
            message = backendMessage || '您没有权限访问该资源';
            break;
          case 404:
            message = backendMessage || '请求的资源不存在';
            break;
          case 408:
            message = backendMessage || '请求超时，请稍后再试';
            break;
          case 422:
            message = backendMessage || '请求参数校验失败';
            break;
          case 429:
            // 限流场景：前端可结合 error.code === 'RATE_LIMIT_EXCEEDED' 做退避提示
            message = backendMessage || '请求过于频繁，请稍后再试';
            break;
          case 500:
            message = backendMessage || '服务器内部错误，请稍后再试';
            break;
          case 502:
          case 503:
            message = backendMessage || '服务暂不可用，请稍后再试';
            break;
          case 504:
            message = backendMessage || '网关超时，请稍后再试';
            break;
          default:
            message = backendMessage || '网络请求异常';
        }
        return { message, status, code, data, config };
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
   * 业务失败时抛 HttpError（携带 code/message/data/traceId），调用方可在
   * catch 中通过 error.code 做差异化处理（如 RATE_LIMIT_EXCEEDED 显示倒计时）。
   */
  protected unwrapResponse<T>(body: unknown, responseHeaders?: unknown): T {
    if (!this.isSuccess(body)) {
      throw new HttpError(this.getErrorMessage(body), {
        code: this.getErrorCode(body),
        data: body,
        traceId: readHeader(responseHeaders, TRACE_ID_HEADER),
      });
    }
    return this.extractData(body) as T;
  }

  // ── 类型化包装方法 ──────────────────────────────

  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.get(url, config).then((res) => this.unwrapResponse<T>(res.data, res.headers));
  }

  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.post(url, data, config).then((res) => this.unwrapResponse<T>(res.data, res.headers));
  }

  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.delete(url, config).then((res) => this.unwrapResponse<T>(res.data, res.headers));
  }
}

/** 判断是否为服务不可用类错误。
 *
 * 覆盖两种场景：
 *   - 网络层失败（连接被拒绝/DNS 失败/超时无响应）：HttpError.status 为
 *     undefined，axios 错误未携带 HTTP 响应；
 *   - 网关类 5xx（502/503/504）：上游服务或网关自身不可用。
 *
 * 调用方据此区分“服务暂时不可用（可重试）”与“业务返回的错误（如 403）”，
 * 避免在后端短暂不可用时把已登录用户重定向回登录页。
 */
export function isServiceUnavailableError(error: unknown): boolean {
  if (!(error instanceof HttpError)) {
    return false;
  }
  return (
    error.status === undefined
    || error.status === 502
    || error.status === 503
    || error.status === 504
  );
}

/** 通用错误信息提取。
 *
 * 如果是 HttpError 且携带业务码，返回 `[CODE] message` 格式；
 * 否则返回纯 message。这样前端 message.error 能直接显示业务码+原因，
 * 便于用户定位问题（如 [PERMISSION_DENIED] 无权限访问）。
 *
 * 当 HttpError 携带 traceId 时，统一在末尾追加 `（traceId: xxx）`，
 * 方便用户把提示反馈给开发人员后，在日志查询页按 traceId 精确定位链路。
 */
export function getRequestErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (error instanceof HttpError) {
    const nestedCode = readNestedErrorCode(error.data);
    const errorCode = error.code ?? nestedCode;
    const baseMessage = errorCode
      ? `[${errorCode}] ${error.message}`
      : error.message;
    return appendTraceId(baseMessage, error.traceId);
  }
  return error instanceof Error ? error.message : fallback;
}

/** 在错误文案末尾追加 traceId；无 traceId 时原样返回。 */
function appendTraceId(message: string, traceId: string | undefined): string {
  if (!traceId) {
    return message;
  }
  return `${message}（traceId: ${traceId}）`;
}

/** 从统一 429 响应的 data.detail 中读取服务端限流剩余秒数。 */
export function getRateLimitRetryAfter(error: unknown): number | undefined {
  if (!(error instanceof HttpError) || error.status !== 429) {
    return undefined;
  }
  const detail = readNestedDetail(error.data);
  if (
    detail != null
    && typeof detail === 'object'
    && 'retry_after_seconds' in detail
    && typeof detail.retry_after_seconds === 'number'
  ) {
    return Math.max(1, Math.ceil(detail.retry_after_seconds));
  }
  return undefined;
}

/** 兼容直接错误详情与统一响应信封两种 data 结构。 */
function readNestedErrorCode(value: unknown): string | undefined {
  if (value == null || typeof value !== 'object') {
    return undefined;
  }
  if ('code' in value && typeof value.code === 'string') {
    return value.code;
  }
  if ('data' in value) {
    return readNestedErrorCode(value.data);
  }
  return undefined;
}

function readNestedDetail(value: unknown): unknown {
  if (value == null || typeof value !== 'object') {
    return undefined;
  }
  if ('detail' in value) {
    return value.detail;
  }
  if ('data' in value) {
    return readNestedDetail(value.data);
  }
  return undefined;
}
