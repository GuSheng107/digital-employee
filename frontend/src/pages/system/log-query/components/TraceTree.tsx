import { ApartmentOutlined } from '@ant-design/icons';
import { Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import type { TraceSpan } from '../types/observability';
import { TRACE_SERVICE_LABELS } from '../constants/observability';

interface TraceTreeProps {
  spans: TraceSpan[];
  selectedSpanId?: string;
  onSelect: (span: TraceSpan) => void;
}

function buildTree(spans: TraceSpan[]): DataNode[] {
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

  const toNode = (span: TraceSpan): DataNode => ({
    key: span.span_id,
    icon: <ApartmentOutlined />,
    title: (
      <span className="trace-tree-title">
        {TRACE_SERVICE_LABELS[span.service] ?? span.service}
      </span>
    ),
    children: (childrenMap.get(span.span_id) ?? []).map(toNode),
  });
  return roots.map(toNode);
}

export default function TraceTree({
  spans,
  selectedSpanId,
  onSelect,
}: TraceTreeProps): React.ReactElement {
  const spanMap = new Map(spans.map((span) => [span.span_id, span]));
  return (
    <Tree
      showIcon
      blockNode
      defaultExpandAll
      treeData={buildTree(spans)}
      selectedKeys={selectedSpanId ? [selectedSpanId] : []}
      onSelect={(keys) => {
        const span = spanMap.get(String(keys[0] ?? ''));
        if (span) onSelect(span);
      }}
    />
  );
}
