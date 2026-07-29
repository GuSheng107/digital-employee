import { ApartmentOutlined } from '@ant-design/icons';
import { Tag, Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import type { TraceEvent, TraceSpan } from '../types/observability';
import {
  CALL_STATUS_COLORS,
  CALL_STATUS_LABELS,
  TRACE_SERVICE_LABELS,
  resolveSpanCallStatus,
} from '../constants/observability';

interface TraceTreeProps {
  spans: TraceSpan[];
  events: TraceEvent[];
  selectedSpanId?: string;
  onSelect: (span: TraceSpan) => void;
}

function buildTree(spans: TraceSpan[], events: TraceEvent[]): DataNode[] {
  const spanMap = new Map(spans.map((span) => [span.span_id, span]));
  const childrenMap = new Map<string, TraceSpan[]>();
  const roots: TraceSpan[] = [];

  spans.forEach((span) => {
    if (span.parent_span_id && spanMap.has(span.parent_span_id)) {
      const siblings = childrenMap.get(span.parent_span_id) ?? [];
      siblings.push(span);
      childrenMap.set(span.parent_span_id, siblings);
    } else {
      roots.push(span);
    }
  });

  const toNode = (span: TraceSpan): DataNode => {
    const callStatus = resolveSpanCallStatus(span, events);
    return {
    key: span.span_id,
    icon: <ApartmentOutlined />,
    title: (
      <span className="trace-tree-title">
        <strong>{TRACE_SERVICE_LABELS[span.service] ?? span.service}</strong>
        <span>{span.operation}</span>
        <Tag color={CALL_STATUS_COLORS[callStatus]}>
          {CALL_STATUS_LABELS[callStatus]}
        </Tag>
        <small>{span.duration_ms} ms</small>
      </span>
    ),
    children: (childrenMap.get(span.span_id) ?? []).map(toNode),
    };
  };
  return roots.map(toNode);
}

export default function TraceTree({
  spans,
  events,
  selectedSpanId,
  onSelect,
}: TraceTreeProps): React.ReactElement {
  const spanMap = new Map(spans.map((span) => [span.span_id, span]));
  return (
    <Tree
      showIcon
      blockNode
      defaultExpandAll
      treeData={buildTree(spans, events)}
      selectedKeys={selectedSpanId ? [selectedSpanId] : []}
      onSelect={(keys) => {
        const span = spanMap.get(String(keys[0] ?? ''));
        if (span) onSelect(span);
      }}
    />
  );
}
