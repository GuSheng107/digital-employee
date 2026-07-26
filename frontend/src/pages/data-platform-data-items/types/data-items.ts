// DataItems 页面私有类型
export interface DataItem {
  id: string;
  namespace: string;
  item_key: string;
  item_value: Record<string, unknown>;
  description: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export interface DataItemPayload {
  namespace: string;
  item_key: string;
  item_value: Record<string, unknown>;
  description: string;
}

// 表单初始值
export const DEFAULT_FORM_VALUE: DataItemFormValues = {
  namespace: 'default',
  itemKey: '',
  description: '',
  itemValueText: '{\n  "hello": "world"\n}',
};

export interface DataItemFormValues {
  namespace: string;
  itemKey: string;
  description: string;
  itemValueText: string;
}
