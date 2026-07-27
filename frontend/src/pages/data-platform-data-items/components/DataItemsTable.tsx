import { Button, Input, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import styles from '../index.module.css';
import type { DataItem } from '../types/data-items';

export interface DataItemsTableProps {
  loading: boolean;
  dataSource: DataItem[];
  namespaceFilter: string;
  onNamespaceFilterChange: (value: string) => void;
  onQuery: () => void;
  onShowJson: (item: DataItem) => void;
  onEdit: (item: DataItem) => void;
  onDelete: (item: DataItem) => void;
}

export default function DataItemsTable({
  loading,
  dataSource,
  namespaceFilter,
  onNamespaceFilterChange,
  onQuery,
  onShowJson,
  onEdit,
  onDelete,
}: DataItemsTableProps) {
  const columns: ColumnsType<DataItem> = [
    { title: 'Namespace', dataIndex: 'namespace', width: 150 },
    { title: 'Key', dataIndex: 'item_key', minWidth: 180 },
    { title: '描述', dataIndex: 'description', minWidth: 180 },
    { title: '创建时间', dataIndex: 'created_at', width: 220 },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => onShowJson(record)}>
            JSON
          </Button>
          <Button size="small" type="primary" onClick={() => onEdit(record)}>
            编辑
          </Button>
          <Button size="small" danger onClick={() => onDelete(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className={styles.toolbar}>
        <Input
          value={namespaceFilter}
          onChange={(e) => onNamespaceFilterChange(e.target.value)}
          allowClear
          placeholder="按 namespace 过滤"
          className={styles.filterInput}
          onPressEnter={onQuery}
        />
        <Button loading={loading} onClick={onQuery}>
          查询列表
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={dataSource}
        pagination={false}
        bordered
      />
    </>
  );
}
