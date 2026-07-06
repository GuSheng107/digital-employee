import { Table } from 'antd';
import type { TablePaginationConfig } from 'antd';
import type { Key } from 'react';
import { useUserManageColumns } from '../hooks/use-user-manage-columns';
import type { UserManageItem } from '../types/user-manage';

interface UserManageTableProps {
  loading: boolean;
  total: number;
  pageNumber: number;
  pageSize: number;
  dataSource: UserManageItem[];
  selectedRowKeys: string[];
  onPageChange: (pageNumber: number, pageSize: number) => void;
  onSelectChange: (selectedRowKeys: string[]) => void;
}

export default function UserManageTable({
  loading,
  total,
  pageNumber,
  pageSize,
  dataSource,
  selectedRowKeys,
  onPageChange,
  onSelectChange,
}: UserManageTableProps) {
  const columns = useUserManageColumns();

  const handleTableChange = (pagination: TablePaginationConfig): void => {
    const nextPageNumber = pagination.current ?? pageNumber;
    const nextPageSize = pagination.pageSize ?? pageSize;
    onPageChange(nextPageNumber, nextPageSize);
  };

  return (
    <Table
      rowKey="id"
      columns={columns}
      dataSource={dataSource}
      loading={loading}
      pagination={{
        current: pageNumber,
        pageSize,
        total,
        showSizeChanger: true,
      }}
      rowSelection={{
        selectedRowKeys,
        onChange: (keys: Key[]): void => {
          onSelectChange(keys.map((item: Key) => String(item)));
        },
      }}
      onChange={handleTableChange}
    />
  );
}
