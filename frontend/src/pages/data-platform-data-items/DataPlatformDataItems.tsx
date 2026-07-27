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

const DEFAULT_PAGE_SIZE = 10;

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
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [currentJson, setCurrentJson] = useState<string>('');
  const [formValues, setFormValues] = useState<DataItemFormValues>(DEFAULT_FORM_VALUE);

  async function loadItems(pageNum = page, pageSz = pageSize): Promise<void> {
    setLoading(true);
    try {
      let result = await listDataItems(namespaceFilter, pageSz, (pageNum - 1) * pageSz);
      // 删除最后一页的最后一条后，后端返回空数组 — 自动回退到最后一页
      if (result.items.length === 0 && result.total > 0 && pageNum > 1) {
        const lastPage = Math.max(1, Math.ceil(result.total / pageSz));
        pageNum = lastPage;
        setPage(lastPage);
        result = await listDataItems(namespaceFilter, pageSz, (pageNum - 1) * pageSz);
      }
      setItems(result.items);
      setTotal(result.total);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function handlePageChange(newPage: number, newPageSize: number): void {
    setPage(newPage);
    setPageSize(newPageSize);
    void loadItems(newPage, newPageSize);
  }

  function handleQuery(): void {
    setPage(1);
    void loadItems(1, pageSize);
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
        total={total}
        page={page}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        namespaceFilter={namespaceFilter}
        onNamespaceFilterChange={setNamespaceFilter}
        onQuery={handleQuery}
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
