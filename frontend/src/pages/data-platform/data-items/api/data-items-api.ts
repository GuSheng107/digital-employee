import dataPlatformRequest from '@/utils/data-platform-request';
import type { DataItem, DataItemPayload, PaginatedDataItems } from '../types/data-items';

// 列表查询，namespace 可选过滤，支持分页
export async function listDataItems(
  namespace?: string,
  limit?: number,
  offset?: number,
): Promise<PaginatedDataItems> {
  return dataPlatformRequest.get<PaginatedDataItems>('/api/v1/data-items', {
    params: {
      namespace: namespace || undefined,
      limit,
      offset,
    },
  });
}

// 新增数据项
export async function createDataItem(payload: DataItemPayload): Promise<DataItem> {
  return dataPlatformRequest.post<DataItem>('/api/v1/data-items', payload);
}

// 更新数据项
export async function updateDataItem(id: string, payload: Partial<DataItemPayload>): Promise<DataItem> {
  return dataPlatformRequest.post<DataItem>(`/api/v1/data-items/${id}`, payload);
}

// 删除数据项
export async function deleteDataItem(id: string): Promise<{ id: string }> {
  return dataPlatformRequest.delete<{ id: string }>(`/api/v1/data-items/${id}`);
}
