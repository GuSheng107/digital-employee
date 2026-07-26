import { request, type ApiResponse } from './request'

export interface DataItem {
  id: string
  namespace: string
  item_key: string
  item_value: Record<string, unknown>
  description: string
  created_at: string
  updated_at: string
  deleted_at?: string | null
}

export interface DataItemPayload {
  namespace: string
  item_key: string
  item_value: Record<string, unknown>
  description: string
}

export async function listDataItems(namespace?: string) {
  const { data } = await request.get<ApiResponse<DataItem[]>>('/api/v1/data-items', {
    params: { namespace: namespace || undefined },
  })
  return data
}

export async function createDataItem(payload: DataItemPayload) {
  const { data } = await request.post<ApiResponse<DataItem>>('/api/v1/data-items', payload)
  return data
}

export async function updateDataItem(id: string, payload: Partial<DataItemPayload>) {
  const { data } = await request.put<ApiResponse<DataItem>>(
    `/api/v1/data-items/${id}`,
    payload,
  )
  return data
}

export async function deleteDataItem(id: string) {
  const { data } = await request.delete<ApiResponse<{ id: string }>>(
    `/api/v1/data-items/${id}`,
  )
  return data
}
