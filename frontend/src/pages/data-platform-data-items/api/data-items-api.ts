import dataPlatformRequest from '@/utils/data-platform-request';
import type { DataItem, DataItemPayload } from '../types/data-items';

// 列表查询，namespace 可选过滤
export async function listDataItems(namespace?: string): Promise<DataItem[]> {
  return dataPlatformRequest.get<DataItem[]>('/api/v1/data-items', {
    params: { namespace: namespace || undefined },
  });
}

// 新增数据项
export async function createDataItem(payload: DataItemPayload): Promise<DataItem> {
  return dataPlatformRequest.post<DataItem>('/api/v1/data-items', payload);
}

// 更新数据项
export async function updateDataItem(id: string, payload: Partial<DataItemPayload>): Promise<DataItem> {
  return dataPlatformRequest.put<DataItem>(`/api/v1/data-items/${id}`, payload);
}

// 删除数据项
export async function deleteDataItem(id: string): Promise<{ id: string }> {
  return dataPlatformRequest.delete<{ id: string }>(`/api/v1/data-items/${id}`);
}
