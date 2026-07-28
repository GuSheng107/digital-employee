import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  assignUserRoles,
  createUser,
  fetchUsers,
  resetUserPassword,
  type CreateUserPayload,
  type UserListItem,
} from '@/api/user-api';
import { fetchRoles, type RoleItem } from '@/api/role-api';
import {
  getVipDisplayFallback,
  ROLE_CODE,
  VIP_LEVEL,
} from '@/constants/access-control';
import { getRequestErrorMessage } from '@/utils/request';
import styles from './index.module.css';

const { Title } = Typography;

const DEFAULT_PAGE_SIZE = 20;

interface CreateUserFormValues {
  username: string;
  password: string;
  nickname?: string;
  email?: string;
  phone?: string;
  roleCodes: string[];
}

/** 格式化后端返回的时间字符串为本地可读格式 */
function formatDateTime(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

/** 从请求错误中提取用户可读的提示文案 */
function getErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '操作失败，请稍后重试');
}

export default function UserRegister(): React.ReactElement {
  const [loading, setLoading] = useState<boolean>(false);
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);

  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [rolesLoading, setRolesLoading] = useState<boolean>(false);

  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createForm] = Form.useForm<CreateUserFormValues>();

  const [assignTarget, setAssignTarget] = useState<UserListItem | null>(null);
  const [assignOpen, setAssignOpen] = useState<boolean>(false);
  const [assignSubmitting, setAssignSubmitting] = useState<boolean>(false);
  const [assignRoleCodes, setAssignRoleCodes] = useState<string[]>([]);

  const [pwdTarget, setPwdTarget] = useState<UserListItem | null>(null);
  const [pwdOpen, setPwdOpen] = useState<boolean>(false);
  const [pwdSubmitting, setPwdSubmitting] = useState<boolean>(false);
  const [pwdForm] = Form.useForm<{ new_password: string; confirm_password: string }>();

  const roleOptions = useMemo(
    () => roles.map((role) => ({ label: role.name, value: role.code })),
    [roles],
  );

  async function loadUsers(pageNum = page, pageSz = pageSize): Promise<void> {
    setLoading(true);
    try {
      const response = await fetchUsers(pageNum, pageSz);
      setUsers(response.items);
      setTotal(response.total);
      setPage(response.page);
      setPageSize(response.page_size);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadRoles(): Promise<void> {
    setRolesLoading(true);
    try {
      const response = await fetchRoles();
      setRoles(response.filter((role) => role.code !== ROLE_CODE.SUPER_ADMIN));
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setRolesLoading(false);
    }
  }

  // 初始数据加载：effect 仅在挂载时执行一次，loadUsers 内部 setState 为异步流程，
  // 不会在 effect 同步阶段触发级联渲染，符合 react-hooks 规范例外。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadUsers(1, DEFAULT_PAGE_SIZE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleTableChange(nextPage: number, nextPageSize: number): void {
    void loadUsers(nextPage, nextPageSize);
  }

  function openCreateModal(): void {
    createForm.resetFields();
    setCreateOpen(true);
    if (roles.length === 0) {
      void loadRoles();
    }
  }

  async function handleCreateSubmit(values: CreateUserFormValues): Promise<void> {
    setCreateSubmitting(true);
    try {
      const payload: CreateUserPayload = {
        username: values.username,
        password: values.password,
        nickname: values.nickname || undefined,
        email: values.email || undefined,
        phone: values.phone || undefined,
        role_codes: values.roleCodes ?? [],
      };
      await createUser(payload);
      message.success('用户创建成功');
      setCreateOpen(false);
      await loadUsers();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setCreateSubmitting(false);
    }
  }

  function openAssignModal(user: UserListItem): void {
    setAssignTarget(user);
    setAssignRoleCodes(user.roles);
    setAssignOpen(true);
    if (roles.length === 0) {
      void loadRoles();
    }
  }

  function closeAssignModal(): void {
    setAssignOpen(false);
    setAssignTarget(null);
    setAssignRoleCodes([]);
  }

  async function handleAssignSubmit(): Promise<void> {
    if (!assignTarget) return;
    setAssignSubmitting(true);
    try {
      await assignUserRoles(assignTarget.id, assignRoleCodes);
      message.success('角色分配成功');
      closeAssignModal();
      await loadUsers();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setAssignSubmitting(false);
    }
  }

  function openPwdModal(user: UserListItem): void {
    setPwdTarget(user);
    pwdForm.resetFields();
    setPwdOpen(true);
  }

  function closePwdModal(): void {
    setPwdOpen(false);
    setPwdTarget(null);
    pwdForm.resetFields();
  }

  async function handlePwdSubmit(values: { new_password: string; confirm_password: string }): Promise<void> {
    if (!pwdTarget) return;
    setPwdSubmitting(true);
    try {
      await resetUserPassword(pwdTarget.id, values.new_password);
      message.success(`已重置用户 ${pwdTarget.username} 的密码`);
      closePwdModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setPwdSubmitting(false);
    }
  }

  const columns: ColumnsType<UserListItem> = [
    { title: '用户名', dataIndex: 'username', width: 140 },
    {
      title: '昵称',
      dataIndex: 'nickname',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '角色',
      dataIndex: 'roles',
      render: (value: string[]) => (
        <Space size={[4, 4]} wrap>
          {value.length === 0 ? (
            <Tag>无</Tag>
          ) : (
            value.map((code) => (
              <Tag key={code} color="blue">
                {code}
              </Tag>
            ))
          )}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: number) =>
        value === 1 ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>,
    },
    {
      title: 'VIP',
      dataIndex: 'vip_level_display',
      width: 100,
      render: (display: string, record) => {
        const vipDisplay = display
          || getVipDisplayFallback(record.vip_level, record.is_vip);
        if (record.vip_level === VIP_LEVEL.SUPER_ADMIN) {
          return <Tag color="purple">{vipDisplay}</Tag>;
        }
        if (record.vip_level === VIP_LEVEL.MANAGER) {
          return <Tag color="blue">{vipDisplay}</Tag>;
        }
        return record.is_vip
          ? <Tag color="gold">{vipDisplay}</Tag>
          : <Tag>{vipDisplay}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openAssignModal(record)}>
            分配角色
          </Button>
          <Button type="link" size="small" onClick={() => openPwdModal(record)}>
            重置密码
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <Title level={3} style={{ margin: 0 }}>
          用户注册管理
        </Title>
        <Button type="primary" onClick={openCreateModal}>
          新建用户
        </Button>
      </div>

      <div className={styles.tableWrapper}>
        <Table<UserListItem>
          rowKey="id"
          columns={columns}
          dataSource={users}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (totalCount) => `共 ${totalCount} 条`,
            onChange: handleTableChange,
          }}
        />
      </div>

      <Modal
        open={createOpen}
        title="新建用户"
        width={560}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createSubmitting}
        okText="创建"
        cancelText="取消"
      >
        <Form<CreateUserFormValues>
          form={createForm}
          layout="vertical"
          onFinish={handleCreateSubmit}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 4, max: 64, message: '用户名长度需在 4-64 之间' },
            ]}
          >
            <Input autoComplete="username" placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, max: 128, message: '密码长度需在 8-128 之间' },
            ]}
          >
            <Input.Password autoComplete="new-password" placeholder="请输入密码" />
          </Form.Item>
          <Form.Item label="昵称" name="nickname">
            <Input placeholder="请输入昵称" />
          </Form.Item>
          <Form.Item label="邮箱" name="email">
            <Input autoComplete="email" placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item label="手机号" name="phone">
            <Input autoComplete="tel" placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item label="角色" name="roleCodes">
            <Select
              mode="multiple"
              options={roleOptions}
              loading={rolesLoading}
              placeholder="请选择角色"
              allowClear
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={assignOpen}
        title={`分配角色 - ${assignTarget?.username ?? ''}`}
        width={480}
        onCancel={closeAssignModal}
        onOk={() => void handleAssignSubmit()}
        confirmLoading={assignSubmitting}
        okText="保存"
        cancelText="取消"
      >
        <Select
          mode="multiple"
          value={assignRoleCodes}
          onChange={setAssignRoleCodes}
          options={roleOptions}
          loading={rolesLoading}
          placeholder="请选择角色"
          style={{ width: '100%' }}
          allowClear
        />
      </Modal>

      <Modal
        open={pwdOpen}
        title={`重置密码 - ${pwdTarget?.username ?? ''}`}
        width={480}
        onCancel={closePwdModal}
        onOk={() => pwdForm.submit()}
        confirmLoading={pwdSubmitting}
        okText="重置"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <Form<{ new_password: string; confirm_password: string }>
          form={pwdForm}
          layout="vertical"
          onFinish={handlePwdSubmit}
        >
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, max: 128, message: '密码长度需在 8-128 之间' },
            ]}
          >
            <Input.Password placeholder="请输入新密码" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认新密码"
            name="confirm_password"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
