import type { TablePaginationConfig } from 'antd/es/table';

export const DEFAULT_TABLE_PAGE_SIZE = 20;
export const TABLE_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

interface TablePaginationOptions {
  current: number;
  pageSize: number;
  total: number;
  onChange: (page: number, pageSize: number) => void;
}

/** 构造系统设置列表统一的 Ant Design 分页配置。 */
export function createTablePagination({
  current,
  pageSize,
  total,
  onChange,
}: TablePaginationOptions): TablePaginationConfig {
  return {
    current,
    pageSize,
    total,
    pageSizeOptions: TABLE_PAGE_SIZE_OPTIONS,
    showQuickJumper: total > pageSize,
    showSizeChanger: true,
    showTotal: (totalCount) => `共 ${totalCount} 条`,
    onChange,
  };
}
