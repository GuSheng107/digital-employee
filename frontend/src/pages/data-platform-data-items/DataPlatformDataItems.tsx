import { useEffect, useState } from 'react';
import { Button, Modal, Typography, message } from 'antd';
import {
  createDataItem,
  deleteDataItem,
  listDataItems,
  updateDataItem,
} from './api/data-items-api';
import DataItemsFormDialog from './components/DataItemsFormDialog';
import DataItemsJsonDialog from './components/DataItemsJsonDialog';
import DataItemsTable from './components/DataItemsTable';
import {
  DEFAULT_FORM_VALUE,
  type DataItem,
  type DataItemFormValues,
  type DataItemPayload,
} from './types/data-items';
import { getDataPlatformErrorMessage } from '@/utils/data-platform-request';
import styles from './index.module.css';

const { Title, Text } = Typography;

function parsePayload(values: DataItemFormValues): DataItemPayload {
  return {
    namespace: values.namespace,
    item_key: values.itemKey,
    description: values.description,
    item_value: JSON.parse(values.itemValueText || '{}'),
  };
}

export default function DataPlatformDataItems() {
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);
  const [jsonDialogOpen, setJsonDialogOpen] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<string>('');
  const [namespaceFilter, setNamespaceFilter] = useState<string>('');
  const [items, setItems] = useState<DataItem[]>([]);
  const [currentJson, setCurrentJson] = useState<string>('');
  const [formValues, setFormValues] = useState<DataItemFormValues>(DEFAULT_FORM_VALUE);

  async function loadItems(): Promise<void> {
    setLoading(true);
    try {
      const list = await listDataItems(namespaceFilter);
      setItems(list);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function openCreate(): void {
    setEditingId('');
    setFormValues(DEFAULT_FORM_VALUE);
    setDialogOpen(true);
  }

  function openEdit(item: DataItem): void {
    setEditingId(item.id);
    setFormValues({
      namespace: item.namespace,
      itemKey: item.item_key,
      description: item.description,
      itemValueText: JSON.stringify(item.item_value, null, 2),
    });
    setDialogOpen(true);
  }

  async function saveItem(values: DataItemFormValues): Promise<void> {
    setSaving(true);
    try {
      const payload = parsePayload(values);
      if (editingId) {
        await updateDataItem(editingId, payload);
        message.success('数据项已更新');
      } else {
        await createDataItem(payload);
        message.success('数据项已创建');
      }
      setDialogOpen(false);
      await loadItems();
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  function removeItem(item: DataItem): void {
    Modal.confirm({
      title: '删除确认',
      content: `确认删除 ${item.item_key}？`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteDataItem(item.id);
          message.success('数据项已删除');
          await loadItems();
        } catch (error) {
          message.error(getDataPlatformErrorMessage(error));
        }
      },
    });
  }

  function showJson(item: DataItem): void {
    setCurrentJson(JSON.stringify(item.item_value, null, 2));
    setJsonDialogOpen(true);
  }

  useEffect(() => {
    // 初始数据加载场景：异步函数内部 setState 不会同步触发级联渲染
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <Title level={3}>Data Items</Title>
          <Text type="secondary">验证 PostgreSQL 数据读写链路</Text>
        </div>
        <Button type="primary" onClick={openCreate}>
          新增数据项
        </Button>
      </div>

      <DataItemsTable
        loading={loading}
        dataSource={items}
        namespaceFilter={namespaceFilter}
        onNamespaceFilterChange={setNamespaceFilter}
        onQuery={() => void loadItems()}
        onShowJson={showJson}
        onEdit={openEdit}
        onDelete={removeItem}
      />

      <DataItemsFormDialog
        open={dialogOpen}
        saving={saving}
        editingId={editingId}
        initialValues={formValues}
        onCancel={() => setDialogOpen(false)}
        onSave={saveItem}
      />

      <DataItemsJsonDialog
        open={jsonDialogOpen}
        jsonText={currentJson}
        onCancel={() => setJsonDialogOpen(false)}
      />
    </div>
  );
}
