import dataPlatformRequest from '@/utils/data-platform-request';
import type {
  ObservabilityMetadata,
  PaginatedPayloadChunks,
  PaginatedTraces,
  TraceDetail,
  TracePayload,
  TraceQuery,
} from '../types/observability';

const OBSERVABILITY_API_PREFIX = '/api/v1/observability';

export function listTraces(query: TraceQuery): Promise<PaginatedTraces> {
  return dataPlatformRequest.get<PaginatedTraces>(
    `${OBSERVABILITY_API_PREFIX}/traces`,
    {
      params: {
        trace_id: query.traceId || undefined,
        started_from: query.startedFrom,
        started_to: query.startedTo,
        trigger: query.trigger || undefined,
        service: query.service || undefined,
        call_status: query.callStatus || undefined,
        keyword: query.keyword || undefined,
        page: query.page,
        page_size: query.pageSize,
      },
    },
  );
}

export function getTraceDetail(traceId: string): Promise<TraceDetail> {
  return dataPlatformRequest.get<TraceDetail>(
    `${OBSERVABILITY_API_PREFIX}/traces/${traceId}`,
  );
}

export function listSpanPayloads(spanId: string): Promise<TracePayload[]> {
  return dataPlatformRequest.get<TracePayload[]>(
    `${OBSERVABILITY_API_PREFIX}/spans/${spanId}/payloads`,
  );
}

export function listPayloadChunks(
  payloadId: string,
  chunkFrom: number,
  chunkLimit: number,
): Promise<PaginatedPayloadChunks> {
  return dataPlatformRequest.get<PaginatedPayloadChunks>(
    `${OBSERVABILITY_API_PREFIX}/payloads/${payloadId}/chunks`,
    { params: { chunk_from: chunkFrom, chunk_limit: chunkLimit } },
  );
}

export function getObservabilityMetadata(): Promise<ObservabilityMetadata> {
  return dataPlatformRequest.get<ObservabilityMetadata>(
    `${OBSERVABILITY_API_PREFIX}/metadata`,
  );
}
