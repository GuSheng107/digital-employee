import { useEffect, useRef, useState } from 'react';
import { Drawer, Empty, Skeleton, message } from 'antd';
import {
  getObservabilityMetadata,
  getTraceDetail,
  listSpanPayloads,
  listTraces,
} from './api/observability-api';
import LogSearchForm, { type LogSearchValues } from './components/LogSearchForm';
import TraceNodeDetail from './components/TraceNodeDetail';
import TraceSummaryTable from './components/TraceSummaryTable';
import TraceTree from './components/TraceTree';
import type {
  ObservabilityMetadata,
  TraceDetail,
  TracePayload,
  TraceQuery,
  TraceRecord,
  TraceSpan,
} from './types/observability';
import { getDataPlatformErrorMessage } from '@/utils/data-platform-request';
import SystemPage from '@/components/system-page/SystemPage';
import styles from './index.module.css';

const DEFAULT_PAGE_SIZE = 20;
const EMPTY_METADATA: ObservabilityMetadata = {
  triggers: [],
  services: [],
  span_kinds: [],
  statuses: [],
  levels: [],
  event_types: [],
  payload_types: [],
  call_statuses: [],
};

export default function LogQuery(): React.ReactElement {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<TraceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [metadata, setMetadata] = useState(EMPTY_METADATA);
  const [query, setQuery] = useState<TraceQuery>({
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<TraceDetail>();
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan>();
  const [payloads, setPayloads] = useState<TracePayload[]>([]);
  const [payloadLoading, setPayloadLoading] = useState(false);
  const initializedRef = useRef(false);

  async function loadTraces(nextQuery: TraceQuery): Promise<void> {
    setLoading(true);
    try {
      const result = await listTraces(nextQuery);
      setItems(result.items);
      setTotal(result.total);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(values: LogSearchValues): void {
    const nextQuery: TraceQuery = {
      traceId: values.traceId?.trim(),
      startedFrom: values.timeRange?.[0].toISOString(),
      startedTo: values.timeRange?.[1].toISOString(),
      trigger: values.trigger,
      service: values.service,
      callStatus: values.callStatus,
      keyword: values.keyword?.trim(),
      page: 1,
      pageSize: query.pageSize,
    };
    setQuery(nextQuery);
    void loadTraces(nextQuery);
  }

  async function openTrace(trace: TraceRecord): Promise<void> {
    setDrawerOpen(true);
    setDetail(undefined);
    setSelectedSpan(undefined);
    setPayloads([]);
    setDetailLoading(true);
    try {
      const result = await getTraceDetail(trace.trace_id);
      setDetail(result);
      const firstSpan = result.spans[0];
      if (firstSpan) {
        await selectSpan(firstSpan);
      }
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setDetailLoading(false);
    }
  }

  async function selectSpan(span: TraceSpan): Promise<void> {
    setSelectedSpan(span);
    setPayloads([]);
    setPayloadLoading(true);
    try {
      setPayloads(await listSpanPayloads(span.span_id));
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setPayloadLoading(false);
    }
  }

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    void Promise.all([
      getObservabilityMetadata().then(setMetadata),
      loadTraces(query),
    ]).catch((error: unknown) => {
      message.error(getDataPlatformErrorMessage(error));
    });
  }, [query]);

  return (
    <SystemPage title="日志查询">
      <div className={styles.contentStack}>
        <section className={styles.searchPanel}>
          <LogSearchForm metadata={metadata} loading={loading} onSearch={handleSearch} />
        </section>
        <section className={styles.tablePanel}>
          <TraceSummaryTable
            items={items}
            loading={loading}
            total={total}
            page={query.page}
            pageSize={query.pageSize}
            onPageChange={(page, pageSize) => {
              const nextQuery = { ...query, page, pageSize };
              setQuery(nextQuery);
              void loadTraces(nextQuery);
            }}
            onOpen={openTrace}
          />
        </section>
      </div>

      <Drawer
        title={detail ? `链路详情 · ${detail.trace.trace_id}` : '链路详情'}
        width="min(1400px, 96vw)"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {detailLoading ? (
          <Skeleton active />
        ) : detail ? (
          <div className={styles.traceLayout}>
            <aside className={styles.traceTree}>
              <TraceTree
                spans={detail.spans}
                selectedSpanId={selectedSpan?.span_id}
                onSelect={(span) => void selectSpan(span)}
              />
            </aside>
            <main className={styles.traceDetail}>
              <TraceNodeDetail
                span={selectedSpan}
                events={detail.events}
                payloads={payloads}
                payloadLoading={payloadLoading}
              />
            </main>
          </div>
        ) : (
          <Empty description="未找到链路详情" />
        )}
      </Drawer>
    </SystemPage>
  );
}
