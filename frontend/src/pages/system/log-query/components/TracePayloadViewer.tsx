import { useEffect, useState } from 'react';
import { Empty, Spin, Tabs, message } from 'antd';
import { listPayloadChunks } from '../api/observability-api';
import type { TracePayload, TracePayloadChunk } from '../types/observability';
import { PAYLOAD_TYPE_LABELS } from '../constants/observability';
import { getDataPlatformErrorMessage } from '@/utils/data-platform-request';

const LOAD_ALL_BATCH_SIZE = 100;

interface TracePayloadViewerProps {
  payloads: TracePayload[];
  loading: boolean;
}

function renderContent(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

function PayloadContent({ payload }: { payload: TracePayload }): React.ReactElement {
  const [chunks, setChunks] = useState<TracePayloadChunk[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadCompletePayload(): Promise<void> {
      const collected: TracePayloadChunk[] = [];
      try {
        while (collected.length < payload.chunk_count) {
          const result = await listPayloadChunks(
            payload.payload_id,
            collected.length,
            LOAD_ALL_BATCH_SIZE,
          );
          if (result.items.length === 0) break;
          collected.push(...result.items);
        }
        if (active) setChunks(collected);
      } catch (error) {
        if (active) message.error(getDataPlatformErrorMessage(error));
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadCompletePayload();
    return () => {
      active = false;
    };
  }, [payload.chunk_count, payload.payload_id]);

  const content = chunks.map((chunk) => chunk.content).join('');
  return (
    <div className="trace-payload">
      <Spin spinning={loading}>
        <pre>{renderContent(content || payload.content_preview)}</pre>
      </Spin>
    </div>
  );
}

export default function TracePayloadViewer({
  payloads,
  loading,
}: TracePayloadViewerProps): React.ReactElement {
  const visiblePayloads = payloads.filter(
    (payload) => !(
      payload.payload_type === 'http_request_body'
      && payload.content_preview === 'null'
    ),
  );

  if (!loading && visiblePayloads.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该节点没有载荷" />;
  }
  return (
    <Tabs
      items={visiblePayloads.map((payload) => ({
        key: payload.payload_id,
        label: PAYLOAD_TYPE_LABELS[payload.payload_type] ?? payload.payload_type,
        children: <PayloadContent payload={payload} />,
      }))}
    />
  );
}
