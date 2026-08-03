import type { TableColumnsType } from 'antd';
import type { UserManageItem } from '../types/user-manage';

function getStatusText(status: UserManageItem['status']): string {
  return status === 'enabled' ? '启用' : '停用';
}

export function useUserManageColumns(): TableColumnsType<UserManageItem> {
  return [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '角色',
      dataIndex: 'roleName',
      key: 'roleName',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (_value: unknown, record: UserManageItem): string => getStatusText(record.status),
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
    },
  ];
}
