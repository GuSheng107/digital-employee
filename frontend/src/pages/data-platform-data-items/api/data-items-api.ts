import dataPlatformRequest from '@/utils/data-platform-request';
import type { DataItem, DataItemPayload } from '../types/data-items';

// 列表查询，namespace 可选过滤
export async function listDataItems(namespace?: string): Promise<DataItem[]> {
  const data = await dataPlatformRequest.get<DataItem[]>('/api/v1/data-items', {
    params: { namespace: namespace || undefined },
  });
  return data as unknown as DataItem[];
}

// 新增数据项
export async function createDataItem(payload: DataItemPayload): Promise<DataItem> {
  const data = await dataPlatformRequest.post<DataItem>('/api/v1/data-items', payload);
  return data as unknown as DataItem;
}

// 更新数据项
export async function updateDataItem(id: string, payload: Partial<DataItemPayload>): Promise<DataItem> {
  const data = await dataPlatformRequest.put<DataItem>(`/api/v1/data-items/${id}`, payload);
  return data as unknown as DataItem;
}

// 删除数据项
export async function deleteDataItem(id: string): Promise<{ id: string }> {
  const data = await dataPlatformRequest.delete<{ id: string }>(`/api/v1/data-items/${id}`);
  return data as unknown as { id: string };
}
