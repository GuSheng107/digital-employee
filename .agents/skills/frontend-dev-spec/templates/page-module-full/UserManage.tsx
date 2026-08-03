import { Card, Flex, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { getUserManageList } from './api/user-manage-api';
import UserManageSearchForm from './components/UserManageSearchForm';
import UserManageTable from './components/UserManageTable';
import styles from './index.module.css';
import { useUserManageStore } from './store/use-user-manage-store';
import type {
  UserManageItem,
  UserManageListResponse,
  UserManageQueryParams,
  UserManageSearchValues,
} from './types/user-manage';

const { Title, Text } = Typography;

function buildUserManageParams(
  keyword: string,
  status: 'all' | 'enabled' | 'disabled',
  pageNumber: number,
  pageSize: number,
): UserManageQueryParams {
  return {
    keyword,
    status,
    pageNumber,
    pageSize,
  };
}

export default function UserManage() {
  const keyword = useUserManageStore((state) => state.keyword);
  const status = useUserManageStore((state) => state.status);
  const pageNumber = useUserManageStore((state) => state.pageNumber);
  const pageSize = useUserManageStore((state) => state.pageSize);
  const selectedRowKeys = useUserManageStore((state) => state.selectedRowKeys);
  const setKeyword = useUserManageStore((state) => state.setKeyword);
  const setStatus = useUserManageStore((state) => state.setStatus);
  const setPagination = useUserManageStore((state) => state.setPagination);
  const setSelectedRowKeys = useUserManageStore((state) => state.setSelectedRowKeys);
  const resetFilters = useUserManageStore((state) => state.resetFilters);

  const [loading, setLoading] = useState<boolean>(false);
  const [dataSource, setDataSource] = useState<UserManageItem[]>([]);
  const [total, setTotal] = useState<number>(0);

  useEffect(() => {
    async function fetchList(): Promise<void> {
      setLoading(true);
      try {
        const params = buildUserManageParams(keyword, status, pageNumber, pageSize);
        const response: UserManageListResponse = await getUserManageList(params);
        setDataSource(response.list);
        setTotal(response.total);
      } finally {
        setLoading(false);
      }
    }

    void fetchList();
  }, [keyword, status, pageNumber, pageSize]);

  const handleSearch = (values: UserManageSearchValues): void => {
    setKeyword(values.keyword);
    setStatus(values.status);
    setPagination(1, pageSize);
  };

  const handleReset = (): void => {
    resetFilters();
  };

  const handlePageChange = (nextPageNumber: number, nextPageSize: number): void => {
    setPagination(nextPageNumber, nextPageSize);
  };

  const handleSelectChange = (nextSelectedRowKeys: string[]): void => {
    setSelectedRowKeys(nextSelectedRowKeys);
  };

  return (
    <div className={styles.container}>
      <Flex vertical gap={16}>
        <div className={styles.header}>
          <Title level={3}>
            用户管理
          </Title>
          <Text type="secondary">
            这是页面模块模板示例，可替换为实际业务字段和接口。
          </Text>
        </div>

        <Card>
          <UserManageSearchForm
            initialValues={{ keyword, status }}
            loading={loading}
            onSearch={handleSearch}
            onReset={handleReset}
          />
        </Card>

        <Card>
          <UserManageTable
            loading={loading}
            total={total}
            pageNumber={pageNumber}
            pageSize={pageSize}
            dataSource={dataSource}
            selectedRowKeys={selectedRowKeys}
            onPageChange={handlePageChange}
            onSelectChange={handleSelectChange}
          />
        </Card>
      </Flex>
    </div>
  );
}
