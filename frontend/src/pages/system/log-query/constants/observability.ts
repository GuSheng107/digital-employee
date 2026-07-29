export const TRACE_STATUS_LABELS: Readonly<Record<string, string>> = {
  success: '成功',
  error: '异常',
  denied: '拒绝',
  timeout: '超时',
  cancelled: '已取消',
};

export const TRACE_STATUS_COLORS: Readonly<Record<string, string>> = {
  success: 'success',
  error: 'error',
  denied: 'warning',
  timeout: 'orange',
  cancelled: 'default',
};

export const TRACE_TRIGGER_LABELS: Readonly<Record<string, string>> = {
  frontend_http: '前端请求',
  internal_http: '内部服务',
  platform_callback: '平台回调',
  message_queue: '消息队列',
  scheduled_task: '定时任务',
  system_lifecycle: '系统生命周期',
};

export const TRACE_SERVICE_LABELS: Readonly<Record<string, string>> = {
  frontend: '前端',
  backend_auth: '认证服务',
  backend_data: '数据服务',
  backend_gateway: '网关服务',
  backend_agent: 'Agent 服务',
};

export const TRACE_LEVEL_LABELS: Readonly<Record<string, string>> = {
  info: '信息',
  warning: '警告',
  error: '错误',
};

export const CALL_STATUS_LABELS: Readonly<Record<CallStatus, string>> = {
  success: '成功',
  warning: '警告',
  failure: '失败',
};

export const CALL_STATUS_COLORS: Readonly<Record<CallStatus, string>> = {
  success: 'success',
  warning: 'orange',
  failure: 'error',
};

/** 按 Span 状态与其事件级别计算互斥的调用状态。 */
export function resolveSpanCallStatus(
  span: TraceSpan,
  events: TraceEvent[],
): CallStatus {
  const spanEvents = events.filter((event) => event.span_id === span.span_id);
  if (
    span.status !== 'success'
    || spanEvents.some((event) => event.level === 'error')
  ) {
    return 'failure';
  }
  if (spanEvents.some((event) => event.level === 'warning')) {
    return 'warning';
  }
  return 'success';
}

export const PAYLOAD_TYPE_LABELS: Readonly<Record<string, string>> = {
  http_request_body: 'HTTP 请求体',
  http_response_body: 'HTTP 响应体',
  im_message: 'IM 消息正文',
  mq_message: 'MQ 消息正文',
  model_input: '模型输入',
  model_output: '模型输出',
  external_request: '外部平台请求',
  external_response: '外部平台响应',
  file_metadata: '文件元数据',
};
import type {
  CallStatus,
  TraceEvent,
  TraceSpan,
} from '../types/observability';
