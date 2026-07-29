/** 浏览器端分布式追踪头生成。 */

export const TRACE_ID_HEADER = 'X-Trace-Id';
export const TRACEPARENT_HEADER = 'traceparent';

function compactUuid(value: string): string {
  return value.replaceAll('-', '').toLowerCase();
}

function createSpanId(): string {
  return compactUuid(crypto.randomUUID()).slice(-16);
}

/** 每个新的业务 HTTP 请求创建 traceId；Axios 重试会复用原请求头。 */
export function createTraceHeaders(): Record<string, string> {
  const traceId = crypto.randomUUID();
  return {
    [TRACE_ID_HEADER]: traceId,
    [TRACEPARENT_HEADER]: `00-${compactUuid(traceId)}-${createSpanId()}-01`,
  };
}
