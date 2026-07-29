import { Descriptions, Divider, Tag } from 'antd';
import type { TraceEvent, TracePayload, TraceSpan } from '../types/observability';
import TracePayloadViewer from './TracePayloadViewer';
import {
  CALL_STATUS_COLORS,
  CALL_STATUS_LABELS,
  TRACE_SERVICE_LABELS,
  resolveSpanCallStatus,
} from '../constants/observability';

interface TraceNodeDetailProps {
  span?: TraceSpan;
  events: TraceEvent[];
  payloads: TracePayload[];
  payloadLoading: boolean;
}

export default function TraceNodeDetail({
  span,
  events,
  payloads,
  payloadLoading,
}: TraceNodeDetailProps): React.ReactElement | null {
  if (!span) return null;
  const spanEvents = events.filter((event) => event.span_id === span.span_id);
  const callStatus = resolveSpanCallStatus(span, events);
  return (
    <div>
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="服务">
          {TRACE_SERVICE_LABELS[span.service] ?? span.service}
        </Descriptions.Item>
        <Descriptions.Item label="调用状态">
          <Tag color={CALL_STATUS_COLORS[callStatus]}>
            {CALL_STATUS_LABELS[callStatus]}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Span ID" span={2}>
          {span.span_id}
        </Descriptions.Item>
        <Descriptions.Item label="操作">{span.operation}</Descriptions.Item>
        <Descriptions.Item label="耗时">{span.duration_ms} ms</Descriptions.Item>
        <Descriptions.Item label="类型">{span.kind}</Descriptions.Item>
        <Descriptions.Item label="事件">
          {spanEvents.map((event) => event.name).join('、') || '-'}
        </Descriptions.Item>
        {span.error_message && (
          <Descriptions.Item label="异常" span={2}>
            {span.error_message}
          </Descriptions.Item>
        )}
      </Descriptions>
      <Divider>完整业务载荷</Divider>
      <TracePayloadViewer payloads={payloads} loading={payloadLoading} />
    </div>
  );
}
