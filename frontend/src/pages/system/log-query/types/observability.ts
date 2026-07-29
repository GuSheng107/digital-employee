export type CallStatus = 'success' | 'warning' | 'failure';

export interface TraceRecord {
  trace_id: string;
  trigger: string;
  name: string;
  status: string;
  call_status: CallStatus;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  root_service: string;
  http_method?: string | null;
  http_path?: string | null;
  http_status?: number | null;
  error_message?: string | null;
}

export interface TraceSpan {
  span_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  service: string;
  kind: string;
  operation: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
  error_message?: string | null;
}

export interface TraceEvent {
  event_id: string;
  trace_id: string;
  span_id: string;
  service: string;
  event_type: string;
  level: string;
  name: string;
  occurred_at: string;
  attributes: Record<string, unknown>;
}

export interface TracePayload {
  payload_id: string;
  trace_id: string;
  span_id: string;
  service: string;
  payload_type: string;
  content_type: string;
  content_preview: string;
  content_sha256: string;
  chunk_count: number;
  size_bytes: number;
  created_at: string;
}

export interface TracePayloadChunk {
  payload_id: string;
  chunk_index: number;
  content: string;
  size_bytes: number;
}

export interface PaginatedPayloadChunks {
  items: TracePayloadChunk[];
  total: number;
  chunk_from: number;
  chunk_limit: number;
}

export interface PaginatedTraces {
  items: TraceRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface TraceDetail {
  trace: TraceRecord;
  spans: TraceSpan[];
  events: TraceEvent[];
}

export interface ObservabilityMetadata {
  triggers: string[];
  services: string[];
  span_kinds: string[];
  statuses: string[];
  levels: string[];
  event_types: string[];
  payload_types: string[];
  call_statuses: CallStatus[];
}

export interface TraceQuery {
  traceId?: string;
  startedFrom?: string;
  startedTo?: string;
  trigger?: string;
  service?: string;
  callStatus?: CallStatus;
  keyword?: string;
  page: number;
  pageSize: number;
}
