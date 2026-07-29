import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  DatePicker,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import {
  assignUserRoles,
  createUser,
  deleteUser,
  fetchVipLevels,
  fetchUsers,
  resetUserPassword,
  updateUserStatus,
  updateUserVip,
  type CreateUserPayload,
  type UserListItem,
  type VipLevelOption,
} from '@/api/user-api';
import { fetchRoles, type RoleItem } from '@/api/role-api';
import {
  getVipDisplayFallback,
  ROLE_CODE,
  VIP_LEVEL,
} from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';
import { getRequestErrorMessage } from '@/utils/request';
import { PHONE_DIAL_PREFIX } from '@/config/identity-config';
import {
  EMAIL_PATTERN,
  PASSWORD_COMPLEXITY_MESSAGE,
  PASSWORD_COMPLEXITY_PATTERN,
  normalizePhoneNumber,
} from '@/utils/identity-validation';
import SystemPage from '@/components/system-page/SystemPage';
import {
  createTablePagination,
  DEFAULT_TABLE_PAGE_SIZE,
} from '@/utils/table-pagination';
import styles from './index.module.css';

interface CreateUserFormValues {
  username: string;
  password: string;
  nickname?: string;
  email?: string;
  phone?: string;
  roleCodes: string[];
  isVip: boolean;
  vipLevel?: number;
  vipExpiresAt?: Dayjs;
}

interface VipFormValues {
  isVip: boolean;
  vipLevel?: number;
  vipExpiresAt?: Dayjs;
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
  const currentUserRoles = useUserStore((state) => state.userInfo?.roles ?? []);
  const canAssignManager = currentUserRoles.includes(ROLE_CODE.SUPER_ADMIN);
  const [loading, setLoading] = useState<boolean>(false);
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_TABLE_PAGE_SIZE);

  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [rolesLoading, setRolesLoading] = useState<boolean>(false);

  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createForm] = Form.useForm<CreateUserFormValues>();
  const createIsVip = Form.useWatch('isVip', createForm) ?? false;
  const createRoleCodes = Form.useWatch('roleCodes', createForm) ?? [];
  const createIsManager = createRoleCodes.includes(ROLE_CODE.MANAGER);
  const createBusinessVipEnabled = createIsVip && !createIsManager;

  const [assignTarget, setAssignTarget] = useState<UserListItem | null>(null);
  const [assignOpen, setAssignOpen] = useState<boolean>(false);
  const [assignSubmitting, setAssignSubmitting] = useState<boolean>(false);
  const [assignRoleCodes, setAssignRoleCodes] = useState<string[]>([]);

  const [pwdTarget, setPwdTarget] = useState<UserListItem | null>(null);
  const [pwdOpen, setPwdOpen] = useState<boolean>(false);
  const [pwdSubmitting, setPwdSubmitting] = useState<boolean>(false);
  const [pwdForm] = Form.useForm<{ new_password: string; confirm_password: string }>();

  const [vipLevels, setVipLevels] = useState<VipLevelOption[]>([]);
  const [vipLevelsLoading, setVipLevelsLoading] = useState<boolean>(false);
  const [vipTarget, setVipTarget] = useState<UserListItem | null>(null);
  const [vipOpen, setVipOpen] = useState<boolean>(false);
  const [vipSubmitting, setVipSubmitting] = useState<boolean>(false);
  const [vipForm] = Form.useForm<VipFormValues>();
  const vipEnabled = Form.useWatch('isVip', vipForm) ?? false;

  const roleOptions = useMemo(
    () => roles
      .filter((role) => role.code !== ROLE_CODE.MANAGER || canAssignManager)
      .map((role) => ({ label: role.name, value: role.code })),
    [canAssignManager, roles],
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

  async function loadVipLevels(): Promise<void> {
    setVipLevelsLoading(true);
    try {
      setVipLevels(await fetchVipLevels());
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setVipLevelsLoading(false);
    }
  }

  // 初始数据加载：effect 仅在挂载时执行一次，loadUsers 内部 setState 为异步流程，
  // 不会在 effect 同步阶段触发级联渲染，符合 react-hooks 规范例外。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadUsers(1, DEFAULT_TABLE_PAGE_SIZE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleTableChange(nextPage: number, nextPageSize: number): void {
    void loadUsers(nextPage, nextPageSize);
  }

  function openCreateModal(): void {
    createForm.resetFields();
    createForm.setFieldsValue({ isVip: false, roleCodes: [] });
    setCreateOpen(true);
    if (roles.length === 0) {
      void loadRoles();
    }
    if (vipLevels.length === 0) {
      void loadVipLevels();
    }
  }

  async function handleCreateSubmit(values: CreateUserFormValues): Promise<void> {
    const parsedPhone = values.phone
      ? normalizePhoneNumber(values.phone)
      : null;
    if (values.phone && !parsedPhone) {
      message.error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`);
      return;
    }
    const normalizedPhone = parsedPhone ?? undefined;
    setCreateSubmitting(true);
    try {
      const payload: CreateUserPayload = {
        username: values.username,
        password: values.password,
        nickname: values.nickname || undefined,
        email: values.email?.trim().toLowerCase() || undefined,
        phone: normalizedPhone,
        role_codes: values.roleCodes ?? [],
        is_vip:
          values.isVip
          && !(values.roleCodes ?? []).includes(ROLE_CODE.MANAGER),
        vip_level: createBusinessVipEnabled ? values.vipLevel : undefined,
        vip_expires_at:
          createBusinessVipEnabled && values.vipExpiresAt
            ? values.vipExpiresAt.toISOString()
            : undefined,
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
      message.success(
        `已重置用户 ${pwdTarget.username} 的密码，下次登录将强制修改`,
      );
      closePwdModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setPwdSubmitting(false);
    }
  }

  function openVipModal(user: UserListItem): void {
    if (user.roles.includes(ROLE_CODE.MANAGER)) {
      message.warning('管理员身份不能配置业务 VIP');
      return;
    }
    setVipTarget(user);
    vipForm.setFieldsValue({
      isVip: user.is_vip,
      vipLevel: user.is_vip ? user.vip_level ?? undefined : undefined,
      vipExpiresAt:
        user.is_vip && user.vip_expires_at
          ? dayjs(user.vip_expires_at)
          : undefined,
    });
    setVipOpen(true);
    if (vipLevels.length === 0) {
      void loadVipLevels();
    }
  }

  function closeVipModal(): void {
    setVipOpen(false);
    setVipTarget(null);
    vipForm.resetFields();
  }

  async function handleVipSubmit(values: VipFormValues): Promise<void> {
    if (!vipTarget) return;
    setVipSubmitting(true);
    try {
      await updateUserVip(vipTarget.id, {
        is_vip: values.isVip,
        vip_level: values.isVip ? values.vipLevel : undefined,
        vip_expires_at:
          values.isVip && values.vipExpiresAt
            ? values.vipExpiresAt.toISOString()
            : undefined,
      });
      message.success(`已更新用户 ${vipTarget.username} 的 VIP 设置`);
      closeVipModal();
      await loadUsers();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setVipSubmitting(false);
    }
  }

  async function handleStatusChange(user: UserListItem): Promise<void> {
    const nextStatus = user.status === 1 ? 0 : 1;
    try {
      await updateUserStatus(user.id, nextStatus);
      message.success(
        `${nextStatus === 1 ? '已启用' : '已停用'}用户 ${user.username}`,
      );
      await loadUsers();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function handleDeleteUser(user: UserListItem): Promise<void> {
    try {
      await deleteUser(user.id);
      message.success(`已删除用户 ${user.username}`);
      await loadUsers(page, pageSize);
    } catch (error) {
      message.error(getErrorMessage(error));
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
      title: '联系方式',
      key: 'contact',
      width: 220,
      render: (_, record) => (
        <div className={styles.contactCell}>
          <span>{record.email || '未填写邮箱'}</span>
          <span>{record.phone || '未填写手机号'}</span>
        </div>
      ),
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
      width: 150,
      render: (display: string, record) => {
        const vipDisplay = display
          || getVipDisplayFallback(record.vip_level, record.is_vip);
        const isExpired = Boolean(
          record.vip_expires_at
          && dayjs(record.vip_expires_at).isBefore(dayjs()),
        );
        if (record.vip_level === VIP_LEVEL.SUPER_ADMIN) {
          return <Tag color="purple">{vipDisplay}</Tag>;
        }
        if (record.vip_level === VIP_LEVEL.MANAGER) {
          return <Tag color="blue">{vipDisplay}</Tag>;
        }
        if (!record.is_vip) {
          return <Tag>{vipDisplay}</Tag>;
        }
        return (
          <Space direction="vertical" size={2}>
            <Tag color={isExpired ? 'default' : 'gold'}>
              {isExpired ? `${vipDisplay}（已过期）` : vipDisplay}
            </Tag>
            <span className={styles.cellMeta}>
              至 {formatDateTime(record.vip_expires_at)}
            </span>
          </Space>
        );
      },
    },
    {
      title: '最近登录',
      key: 'lastLogin',
      width: 190,
      render: (_, record) => (
        <div className={styles.contactCell}>
          <span>{formatDateTime(record.last_login_at)}</span>
          <span>{record.last_login_ip || '无 IP 记录'}</span>
        </div>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '最近更新',
      dataIndex: 'updated_at',
      width: 180,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 330,
      align: 'center',
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openAssignModal(record)}>
            分配角色
          </Button>
          <Button type="link" size="small" onClick={() => openPwdModal(record)}>
            重置密码
          </Button>
          <Button
            type="link"
            size="small"
            disabled={record.roles.includes(ROLE_CODE.MANAGER)}
            title={
              record.roles.includes(ROLE_CODE.MANAGER)
                ? '管理员身份不能配置业务 VIP'
                : undefined
            }
            onClick={() => openVipModal(record)}
          >
            VIP 设置
          </Button>
          <Popconfirm
            title={`${record.status === 1 ? '停用' : '启用'}用户`}
            description={
              record.status === 1
                ? '停用后当前会话会立即失效，是否继续？'
                : '确认恢复该用户登录权限？'
            }
            onConfirm={() => void handleStatusChange(record)}
            okText="确认"
            cancelText="取消"
          >
            <Button
              type="link"
              size="small"
              danger={record.status === 1}
            >
              {record.status === 1 ? '停用' : '启用'}
            </Button>
          </Popconfirm>
          <Popconfirm
            title="删除用户"
            description="该操作会软删除用户并撤销全部会话，是否继续？"
            onConfirm={() => void handleDeleteUser(record)}
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <SystemPage
      title="用户管理"
      actions={(
        <Button type="primary" onClick={openCreateModal}>
          新建用户
        </Button>
      )}
    >
      <div className={styles.container}>

        <div className={styles.tableWrapper}>
          <Table<UserListItem>
            rowKey="id"
            columns={columns}
            dataSource={users}
            loading={loading}
            sticky
            scroll={{ x: 1780, y: 'calc(100vh - 250px)' }}
            pagination={createTablePagination({
              current: page,
              pageSize,
              total,
              onChange: handleTableChange,
            })}
          />
        </div>
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
              {
                pattern: PASSWORD_COMPLEXITY_PATTERN,
                message: PASSWORD_COMPLEXITY_MESSAGE,
              },
            ]}
          >
            <Input.Password autoComplete="new-password" placeholder="请输入密码" />
          </Form.Item>
          <Form.Item label="昵称" name="nickname">
            <Input placeholder="请输入昵称" />
          </Form.Item>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { pattern: EMAIL_PATTERN, message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input autoComplete="email" placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item
            label="手机号"
            name="phone"
            rules={[
              {
                validator: (_, value: string | undefined) => {
                  if (!value || normalizePhoneNumber(value)) {
                    return Promise.resolve();
                  }
                  return Promise.reject(
                    new Error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`),
                  );
                },
              },
            ]}
          >
            <Input
              prefix={PHONE_DIAL_PREFIX}
              autoComplete="tel"
              placeholder="请输入手机号"
            />
          </Form.Item>
          <Form.Item label="角色" name="roleCodes">
            <Select
              mode="multiple"
              options={roleOptions}
              loading={rolesLoading}
              placeholder="请选择角色"
              allowClear
              onChange={(nextRoleCodes: string[]) => {
                if (nextRoleCodes.includes(ROLE_CODE.MANAGER)) {
                  createForm.setFieldsValue({
                    isVip: false,
                    vipLevel: undefined,
                    vipExpiresAt: undefined,
                  });
                }
              }}
            />
          </Form.Item>
          <Form.Item
            label="是否 VIP"
            name="isVip"
            valuePropName="checked"
            extra={
              createIsManager
                ? '管理员使用 VIP66 身份，不能同时配置业务 VIP'
                : undefined
            }
          >
            <Switch
              disabled={createIsManager}
              checkedChildren="开启"
              unCheckedChildren="关闭"
            />
          </Form.Item>
          {createBusinessVipEnabled ? (
            <>
              <Form.Item
                label="VIP 等级"
                name="vipLevel"
                rules={[{ required: true, message: '请选择 VIP 等级' }]}
              >
                <Select
                  options={vipLevels}
                  loading={vipLevelsLoading}
                  placeholder="请选择 VIP1-VIP9"
                />
              </Form.Item>
              <Form.Item
                label="VIP 过期时间"
                name="vipExpiresAt"
                rules={[
                  { required: true, message: '请选择 VIP 过期时间' },
                  {
                    validator: (_, value: Dayjs | undefined) => {
                      if (!value || value.isAfter(dayjs())) {
                        return Promise.resolve();
                      }
                      return Promise.reject(
                        new Error('VIP 过期时间必须晚于当前时间'),
                      );
                    },
                  },
                ]}
              >
                <DatePicker
                  showTime
                  format="YYYY-MM-DD HH:mm"
                  style={{ width: '100%' }}
                  placeholder="请选择 VIP 过期时间"
                />
              </Form.Item>
            </>
          ) : null}
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
              { max: 128, message: '重置密码不能超过 128 位' },
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
        <div className={styles.resetHint}>
          管理员重置密码不受复杂度规则限制；重置后会撤销该用户现有会话，
          并在下次登录时强制其设置符合规则的新密码。
        </div>
      </Modal>

      <Modal
        open={vipOpen}
        title={`VIP 设置 - ${vipTarget?.username ?? ''}`}
        width={480}
        onCancel={closeVipModal}
        onOk={() => vipForm.submit()}
        confirmLoading={vipSubmitting}
        okText="保存"
        cancelText="取消"
      >
        <Form<VipFormValues>
          form={vipForm}
          layout="vertical"
          onFinish={handleVipSubmit}
        >
          <Form.Item
            label="是否 VIP"
            name="isVip"
            valuePropName="checked"
          >
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          {vipEnabled ? (
            <>
              <Form.Item
                label="VIP 等级"
                name="vipLevel"
                rules={[{ required: true, message: '请选择 VIP 等级' }]}
              >
                <Select
                  options={vipLevels}
                  loading={vipLevelsLoading}
                  placeholder="请选择 VIP1-VIP9"
                />
              </Form.Item>
              <Form.Item
                label="VIP 过期时间"
                name="vipExpiresAt"
                rules={[
                  { required: true, message: '请选择 VIP 过期时间' },
                  {
                    validator: (_, value: Dayjs | undefined) => {
                      if (!value || value.isAfter(dayjs())) {
                        return Promise.resolve();
                      }
                      return Promise.reject(
                        new Error('VIP 过期时间必须晚于当前时间'),
                      );
                    },
                  },
                ]}
              >
                <DatePicker
                  showTime
                  format="YYYY-MM-DD HH:mm"
                  style={{ width: '100%' }}
                  placeholder="请选择 VIP 过期时间"
                />
              </Form.Item>
            </>
          ) : null}
        </Form>
      </Modal>
    </SystemPage>
  );
}
