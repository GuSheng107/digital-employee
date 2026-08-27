import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Tree,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TreeDataNode, TreeProps } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import {
  assignUserMenus,
  assignUserRoles,
  fetchUserMenus,
  fetchUsers,
  type UserListItem,
} from '@/api/user-api';
import {
  assignRoleMenus,
  createRole,
  deleteRole,
  fetchRoles,
  updateRole,
  type CreateRolePayload,
  type RoleItem,
  type UpdateRolePayload,
} from '@/api/role-api';
import { fetchMenus, type MenuItem } from '@/api/menu-api';
import {
  createPermission,
  deletePermission,
  fetchPermissions,
  type CreatePermissionPayload,
  type PermissionItem,
} from '@/api/permission-api';
import {
  hasManagePermission,
  PERMISSION_CODE,
  RESERVED_ROLE_CODES,
  ROLE_CODE,
} from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';
import { getRequestErrorMessage } from '@/utils/request';
import { normalizeRoleCodes } from '@/utils/role-validation';
import SystemPage from '@/components/system-page/SystemPage';
import {
  createTablePagination,
  DEFAULT_TABLE_PAGE_SIZE,
} from '@/utils/table-pagination';
import styles from './index.module.css';

const { Text } = Typography;

/** 从请求错误中提取用户可读的提示文案 */
function getErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '操作失败，请稍后重试');
}

/** 把菜单管理接口的扁平目录转换为权限配置树。有权限码要求的菜单会附带提示图标。 */
function convertMenusToTreeData(menus: MenuItem[]): TreeDataNode[] {
  const nodes = new Map<number, TreeDataNode>();
  menus.forEach((menu) => {
    nodes.set(menu.id, {
      key: menu.id,
      title: menu.permission ? (
        <Tooltip title={`需权限码：${menu.permission}`}>
          <Space size={4}>
            <SafetyCertificateOutlined style={{ color: '#1677ff', fontSize: 13 }} />
            <span>{menu.title}</span>
          </Space>
        </Tooltip>
      ) : (
        menu.title
      ),
    });
  });

  const roots: TreeDataNode[] = [];
  menus.forEach((menu) => {
    const node = nodes.get(menu.id);
    if (!node) return;
    const parent = nodes.get(menu.parent_id);
    if (menu.parent_id === 0 || !parent) {
      roots.push(node);
      return;
    }
    parent.children = [...(parent.children ?? []), node];
  });
  return roots;
}

/** 返回当前操作者可维护的角色；超级管理员角色始终由系统保护。 */
function getManageableRoles(
  roles: RoleItem[],
  canManageManager: boolean,
): RoleItem[] {
  return roles.filter(
    (role) =>
      role.code !== ROLE_CODE.SUPER_ADMIN
      && (role.code !== ROLE_CODE.MANAGER || canManageManager),
  );
}

interface RoleFormValues {
  code: string;
  name: string;
  description: string;
}

interface PermissionFormValues {
  code: string;
  name: string;
  description: string;
  module: string;
}

export default function UserPermission(): React.ReactElement {
  const currentUser = useUserStore((state) => state.userInfo);
  const currentUserRoles = currentUser?.roles ?? [];
  const currentUserId = currentUser?.id ?? null;
  const canManageManager = currentUserRoles.includes(ROLE_CODE.SUPER_ADMIN);
  /** 是否可管理权限（拥有 manage 权限；仅 readonly 时隐藏写操作入口） */
  const canManage = currentUser !== null
    && hasManagePermission(
      currentUser.roles,
      currentUser.permissions,
      PERMISSION_CODE.PERMISSION_MANAGE,
    );

  // ── 左栏：用户角色分配 ──
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [usersLoading, setUsersLoading] = useState<boolean>(true);
  const [usersTotal, setUsersTotal] = useState<number>(0);
  const [usersPage, setUsersPage] = useState<number>(1);
  const [usersPageSize, setUsersPageSize] = useState<number>(
    DEFAULT_TABLE_PAGE_SIZE,
  );
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);
  const [userRoleCodes, setUserRoleCodes] = useState<string[]>([]);
  const [userRolesSaving, setUserRolesSaving] = useState<boolean>(false);

  // ── 用户菜单权限 ──
  const [userMenuIds, setUserMenuIds] = useState<number[]>([]);
  const [userMenusLoading, setUserMenusLoading] = useState<boolean>(false);
  const [userMenusSaving, setUserMenusSaving] = useState<boolean>(false);

  // ── 右栏：角色管理 + 菜单分配 ──
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [roleCatalog, setRoleCatalog] = useState<RoleItem[]>([]);
  const [rolesLoading, setRolesLoading] = useState<boolean>(true);
  const [allMenus, setAllMenus] = useState<MenuItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [checkedMenuIds, setCheckedMenuIds] = useState<number[]>([]);
  const [roleMenusSaving, setRoleMenusSaving] = useState<boolean>(false);

  // ── 角色创建/编辑弹窗 ──
  const [roleModalOpen, setRoleModalOpen] = useState<boolean>(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [roleForm] = Form.useForm<RoleFormValues>();
  const [roleSubmitting, setRoleSubmitting] = useState<boolean>(false);

  // ── 权限码管理弹窗 ──
  const [permissionModalOpen, setPermissionModalOpen] = useState<boolean>(false);
  const [permissions, setPermissions] = useState<PermissionItem[]>([]);
  const [permissionsLoading, setPermissionsLoading] = useState<boolean>(false);
  const [permissionSubmitting, setPermissionSubmitting] = useState<boolean>(false);
  const [permissionForm] = Form.useForm<PermissionFormValues>();

  const menuTreeData = useMemo<TreeDataNode[]>(
    () => convertMenusToTreeData(allMenus),
    [allMenus],
  );

  const roleNameByCode = useMemo(
    () => new Map(roleCatalog.map((role) => [role.code, role.name])),
    [roleCatalog],
  );

  const selectedRole = useMemo<RoleItem | null>(
    () => roles.find((r) => r.id === selectedRoleId) ?? null,
    [roles, selectedRoleId],
  );

  async function loadUsers(pageNum: number, pageSz: number): Promise<void> {
    setUsersLoading(true);
    try {
      const response = await fetchUsers(pageNum, pageSz);
      setUsers(response.items);
      setUsersTotal(response.total);
      setUsersPage(response.page);
      setUsersPageSize(response.page_size);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setUsersLoading(false);
    }
  }

  async function loadRoles(): Promise<void> {
    setRolesLoading(true);
    try {
      const response = await fetchRoles();
      const manageableRoles = getManageableRoles(response, canManageManager);
      setRoleCatalog(response);
      setRoles(manageableRoles);
      setSelectedRoleId((currentRoleId) => {
        if (
          currentRoleId !== null
          && !manageableRoles.some((role) => role.id === currentRoleId)
        ) {
          setCheckedMenuIds([]);
          return null;
        }
        return currentRoleId;
      });
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setRolesLoading(false);
    }
  }

  /** 加载用户菜单权限。 */
  async function loadUserMenus(userId: number): Promise<void> {
    setUserMenusLoading(true);
    try {
      const menusResp = await fetchUserMenus(userId);
      setUserMenuIds(menusResp.map((menu) => menu.id));
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setUserMenusLoading(false);
    }
  }

  // 初始数据加载：effect 仅在挂载时执行一次
  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchUsers(1, DEFAULT_TABLE_PAGE_SIZE),
      fetchRoles(),
      fetchMenus(),
    ])
      .then(([userResponse, roleResponse, menuResponse]) => {
        if (!active) return;
        setUsers(userResponse.items);
        setUsersTotal(userResponse.total);
        setUsersPage(userResponse.page);
        setUsersPageSize(userResponse.page_size);
        setRoleCatalog(roleResponse);
        setRoles(getManageableRoles(roleResponse, canManageManager));
        setAllMenus(menuResponse);
      })
      .catch((error: unknown) => {
        if (active) {
          message.error(getErrorMessage(error));
        }
      })
      .finally(() => {
        if (active) {
          setUsersLoading(false);
          setRolesLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [canManageManager]);

  function handleSelectUser(user: UserListItem): void {
    setSelectedUser(user);
    setUserRoleCodes(user.roles);
    void loadUserMenus(user.id);
  }

  function handleSaveUserRoles(): Promise<void> {
    if (!selectedUser) return Promise.resolve();
    setUserRolesSaving(true);
    return assignUserRoles(selectedUser.id, userRoleCodes)
      .then(() => {
        message.success('用户角色已保存');
        const updatedRoles = [...userRoleCodes];
        setUsers((prev) =>
          prev.map((u) => (u.id === selectedUser.id ? { ...u, roles: updatedRoles } : u)),
        );
        setSelectedUser((prev) => (prev ? { ...prev, roles: updatedRoles } : prev));
        // 角色变更会重新生成用户权限快照，因此同步刷新菜单权限。
        return loadUserMenus(selectedUser.id);
      })
      .catch((error: unknown) => {
        message.error(getErrorMessage(error));
      })
      .finally(() => {
        setUserRolesSaving(false);
      });
  }

  function handleSelectRole(roleId: number): void {
    const role = roles.find((r) => r.id === roleId);
    if (!role) return;
    setSelectedRoleId(roleId);
    setCheckedMenuIds(role.menu_ids);
  }

  const handleMenuCheck: TreeProps['onCheck'] = (checkedKeys) => {
    const checked = Array.isArray(checkedKeys) ? checkedKeys : checkedKeys.checked;
    setCheckedMenuIds(checked.map((key) => Number(key)));
  };

  function handleSaveRoleMenus(): Promise<void> {
    if (!selectedRole) return Promise.resolve();
    setRoleMenusSaving(true);
    return assignRoleMenus(selectedRole.id, checkedMenuIds)
      .then(() => {
        message.success('角色菜单保存成功');
        const updatedMenuIds = [...checkedMenuIds];
        setRoles((prev) =>
          prev.map((r) => (r.id === selectedRole.id ? { ...r, menu_ids: updatedMenuIds } : r)),
        );
      })
      .catch((error: unknown) => {
        message.error(getErrorMessage(error));
      })
      .finally(() => {
        setRoleMenusSaving(false);
      });
  }

  // ── 用户独立菜单/权限保存 ──
  const handleUserMenuCheck: TreeProps['onCheck'] = (checkedKeys) => {
    const checked = Array.isArray(checkedKeys) ? checkedKeys : checkedKeys.checked;
    setUserMenuIds(checked.map((key) => Number(key)));
  };

  function handleSaveUserMenus(): Promise<void> {
    if (!selectedUser) return Promise.resolve();
    setUserMenusSaving(true);
    return assignUserMenus(selectedUser.id, userMenuIds)
      .then(() => {
        message.success('用户菜单权限已保存');
      })
      .catch((error: unknown) => {
        message.error(getErrorMessage(error));
      })
      .finally(() => {
        setUserMenusSaving(false);
      });
  }

  // ── 角色创建/编辑 ──
  function openCreateRoleModal(): void {
    setEditingRole(null);
    roleForm.resetFields();
    setRoleModalOpen(true);
  }

  function openEditRoleModal(role: RoleItem): void {
    setEditingRole(role);
    roleForm.setFieldsValue({
      code: role.code,
      name: role.name,
      description: role.description,
    });
    setRoleModalOpen(true);
  }

  function closeRoleModal(): void {
    setRoleModalOpen(false);
    setEditingRole(null);
    roleForm.resetFields();
  }

  async function handleRoleSubmit(values: RoleFormValues): Promise<void> {
    setRoleSubmitting(true);
    try {
      if (editingRole) {
        const payload: UpdateRolePayload = {
          name: values.name,
          description: values.description,
        };
        await updateRole(editingRole.id, payload);
        message.success('角色更新成功');
      } else {
        const payload: CreateRolePayload = {
          code: values.code,
          name: values.name,
          description: values.description,
        };
        await createRole(payload);
        message.success('角色创建成功');
      }
      closeRoleModal();
      await loadRoles();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setRoleSubmitting(false);
    }
  }

  async function handleDeleteRole(role: RoleItem): Promise<void> {
    try {
      await deleteRole(role.id);
      message.success(`角色 ${role.name} 已删除`);
      if (selectedRoleId === role.id) {
        setSelectedRoleId(null);
        setCheckedMenuIds([]);
      }
      await loadRoles();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  // ── 权限码管理 ──
  async function loadPermissions(): Promise<void> {
    setPermissionsLoading(true);
    try {
      const response = await fetchPermissions();
      setPermissions(response);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setPermissionsLoading(false);
    }
  }

  function openPermissionModal(): void {
    permissionForm.resetFields();
    setPermissionModalOpen(true);
    void loadPermissions();
  }

  function closePermissionModal(): void {
    setPermissionModalOpen(false);
    permissionForm.resetFields();
  }

  async function handlePermissionSubmit(values: PermissionFormValues): Promise<void> {
    setPermissionSubmitting(true);
    try {
      const payload: CreatePermissionPayload = {
        code: values.code.trim(),
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        module: values.module?.trim() || undefined,
      };
      await createPermission(payload);
      message.success(`权限码创建成功：${payload.code}`);
      permissionForm.resetFields();
      await loadPermissions();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setPermissionSubmitting(false);
    }
  }

  async function handleDeletePermission(record: PermissionItem): Promise<void> {
    try {
      await deletePermission(record.id);
      message.success(`权限码 ${record.code} 已删除`);
      await loadPermissions();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  const permissionColumns: ColumnsType<PermissionItem> = [
    { title: '权限码', dataIndex: 'code', width: 220 },
    { title: '名称', dataIndex: 'name', width: 140 },
    { title: '模块', dataIndex: 'module', width: 120, render: (value: string | null) => value || '-' },
    { title: '描述', dataIndex: 'description', render: (value: string) => value || '-' },
    {
      title: '操作',
      key: 'action',
      width: 80,
      align: 'center',
      render: (_, record) => (
        <Popconfirm
          title="确认删除该权限码？"
          description="删除后不可恢复，请确保已解除角色/用户关联。"
          onConfirm={() => void handleDeletePermission(record)}
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
        >
          <Button type="link" size="small" danger>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ];

  const userColumns: ColumnsType<UserListItem> = [
    { title: '用户名', dataIndex: 'username', width: 140 },
    {
      title: '昵称',
      dataIndex: 'nickname',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '当前角色',
      dataIndex: 'roles',
      render: (value: string[]) => (
        <Space size={[4, 4]} wrap>
          {value.length === 0 ? (
            <Tag>无</Tag>
          ) : (
            value.map((code) => (
              <Tag key={code} color="blue">
                {roleNameByCode.get(code) ?? code}
              </Tag>
            ))
          )}
        </Space>
      ),
    },
  ];

  return (
    <SystemPage title="用户权限">
      <div className={styles.container}>
      {/* 左栏：用户角色 + 用户独立权限/菜单分配 */}
      <Card className={styles.panel}>
        <div className={styles.panelTitle}>用户角色分配</div>
        <div className={styles.userTable}>
          <Table<UserListItem>
            rowKey="id"
            columns={userColumns}
            dataSource={users}
            loading={usersLoading}
            size="small"
            pagination={createTablePagination({
              current: usersPage,
              pageSize: usersPageSize,
              total: usersTotal,
              onChange: (page, pageSize) => void loadUsers(page, pageSize),
            })}
            rowSelection={{
              type: 'radio',
              selectedRowKeys: selectedUser ? [selectedUser.id] : [],
              onChange: (_, rows) => {
                if (rows.length > 0) {
                  handleSelectUser(rows[0]);
                }
              },
            }}
            onRow={(record) => ({
              onClick: () => handleSelectUser(record),
            })}
          />
        </div>

        {selectedUser ? (
          <>
            <div className={styles.roleSection}>
              <div className={styles.sectionHeader}>
                <Text strong>为 {selectedUser.username} 分配角色</Text>
                {canManage && (
                  <Button
                    type="primary"
                    size="small"
                    loading={userRolesSaving}
                    disabled={selectedUser.id === currentUserId}
                    onClick={() => void handleSaveUserRoles()}
                  >
                    保存角色
                  </Button>
                )}
              </div>
              {rolesLoading ? (
                <Spin />
              ) : roles.length === 0 ? (
                <Empty description="暂无角色" />
              ) : (
                <Select
                  mode="multiple"
                  value={userRoleCodes}
                  disabled={!canManage || selectedUser.id === currentUserId}
                  onChange={(values: string[]) => {
                    setUserRoleCodes(normalizeRoleCodes(values));
                  }}
                  options={roles.map((role) => ({
                    label: `${role.name}（${role.code}）`,
                    value: role.code,
                  }))}
                  placeholder="请选择角色"
                  style={{ width: '100%' }}
                  allowClear
                />
              )}
            </div>

            {/* 用户菜单权限 */}
            <div className={styles.userPermSection}>
              <div className={styles.sectionHeader}>
                <Text strong>用户菜单权限</Text>
                {canManage && (
                  <Button
                    type="primary"
                    size="small"
                    loading={userMenusSaving}
                    disabled={userMenusLoading}
                    onClick={() => void handleSaveUserMenus()}
                  >
                    保存菜单
                  </Button>
                )}
              </div>
              {userMenusLoading ? (
                <Spin />
              ) : menuTreeData.length === 0 ? (
                <Empty description="暂无菜单数据" />
              ) : (
                <Tree
                  checkable
                  defaultExpandAll
                  treeData={menuTreeData}
                  checkedKeys={userMenuIds}
                  onCheck={handleUserMenuCheck}
                  disabled={!canManage}
                />
              )}
            </div>
          </>
        ) : (
          <Empty description="请选择用户进行角色分配" className={styles.emptyHint} />
        )}
      </Card>

      {/* 右栏：角色管理 + 菜单分配 */}
      <Card className={styles.panel}>
        <div className={styles.roleToolbar}>
          <div className={styles.panelTitle}>角色管理</div>
          {canManage && (
            <Space size="small">
              <Button
                type="primary"
                icon={<PlusOutlined />}
                size="small"
                onClick={openCreateRoleModal}
              >
                新建角色
              </Button>
              <Button
                size="small"
                icon={<SafetyCertificateOutlined />}
                onClick={openPermissionModal}
              >
                权限码管理
              </Button>
            </Space>
          )}
        </div>

        {rolesLoading ? (
          <Spin />
        ) : roles.length === 0 ? (
          <Empty description="暂无角色，请点击「新建角色」创建" />
        ) : (
          <Radio.Group
            value={selectedRoleId}
            onChange={(e) => {
              const value = e.target.value;
              if (typeof value === 'number') {
                handleSelectRole(value);
              }
            }}
            className={styles.roleList}
          >
            <Space orientation="vertical" style={{ width: '100%' }}>
              {roles.map((role) => (
                <div key={role.id} className={styles.roleRow}>
                  <Radio value={role.id}>
                    <span className={styles.roleName}>{role.name}</span>
                    <span className={styles.roleCode}>（{role.code}）</span>
                    {role.is_builtin && <Tag color="orange" className={styles.builtinTag}>内置</Tag>}
                  </Radio>
                  {canManage && (
                    <Space size={4} className={styles.roleActions}>
                      <Button
                        type="link"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          openEditRoleModal(role);
                        }}
                      />
                      {!role.is_builtin && (
                        <Popconfirm
                          title="确认删除该角色？"
                          description="删除后不可恢复，请确保已解除用户关联。"
                          onConfirm={() => void handleDeleteRole(role)}
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                        >
                          <Button
                            type="link"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                          />
                        </Popconfirm>
                      )}
                    </Space>
                  )}
                </div>
              ))}
            </Space>
          </Radio.Group>
        )}

        {selectedRole ? (
          <div className={styles.menuTree}>
            <div className={styles.sectionHeader}>
              <Text strong>为 {selectedRole.name} 分配菜单</Text>
              {canManage && (
                <Button
                  type="primary"
                  size="small"
                  loading={roleMenusSaving}
                  onClick={() => void handleSaveRoleMenus()}
                >
                  保存
                </Button>
              )}
            </div>
            {menuTreeData.length === 0 ? (
              <Empty description="暂无菜单数据" />
            ) : (
              <Tree
                checkable
                defaultExpandAll
                treeData={menuTreeData}
                checkedKeys={checkedMenuIds}
                onCheck={handleMenuCheck}
                disabled={!canManage}
              />
            )}
          </div>
        ) : (
          <Empty description="请选择角色进行菜单分配" className={styles.emptyHint} />
        )}
      </Card>

      {/* 角色创建/编辑弹窗 */}
      <Modal
        open={roleModalOpen}
        title={editingRole ? `编辑角色 - ${editingRole.name}` : '新建角色'}
        width={480}
        onCancel={closeRoleModal}
        onOk={() => roleForm.submit()}
        confirmLoading={roleSubmitting}
        okText={editingRole ? '保存' : '创建'}
        cancelText="取消"
      >
        <Form<RoleFormValues>
          form={roleForm}
          layout="vertical"
          onFinish={handleRoleSubmit}
        >
          <Form.Item
            label="角色代码"
            name="code"
            extra={editingRole ? '角色代码创建后不可修改' : '唯一标识，如 editor、auditor 等'}
            rules={[
              { required: true, message: '请输入角色代码' },
              { min: 2, max: 64, message: '角色代码长度需在 2-64 之间' },
              { pattern: /^[a-zA-Z][a-zA-Z0-9_]*$/, message: '仅支持字母开头，字母/数字/下划线' },
              {
                validator: (_, value: string | undefined) => {
                  if (
                    editingRole !== null
                    || !value
                    || !RESERVED_ROLE_CODES.has(value)
                  ) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('该角色代码由系统保留'));
                },
              },
            ]}
          >
            <Input placeholder="如 editor" disabled={editingRole !== null} />
          </Form.Item>
          <Form.Item
            label="角色名称"
            name="name"
            rules={[
              { required: true, message: '请输入角色名称' },
              { max: 64, message: '角色名称不超过 64 字符' },
            ]}
          >
            <Input placeholder="如 内容编辑员" />
          </Form.Item>
          <Form.Item
            label="角色描述"
            name="description"
            rules={[{ max: 255, message: '描述不超过 255 字符' }]}
          >
            <Input.TextArea placeholder="可选，描述该角色的职责" rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 权限码管理弹窗 */}
      <Modal
        open={permissionModalOpen}
        title="权限码管理"
        width={720}
        onCancel={closePermissionModal}
        footer={null}
      >
        <Form<PermissionFormValues>
          form={permissionForm}
          layout="inline"
          onFinish={handlePermissionSubmit}
          className={styles.permissionForm}
        >
          <Form.Item
            label="权限码"
            name="code"
            rules={[
              { required: true, message: '请输入权限码' },
              { min: 3, max: 128, message: '权限码长度需在 3-128 之间' },
              { pattern: /^[a-z][a-z0-9_]*:[a-z0-9_:]+$/, message: '格式如 admin:report:manage' },
            ]}
          >
            <Input placeholder="如 admin:report:manage" style={{ width: 200 }} />
          </Form.Item>
          <Form.Item
            label="名称"
            name="name"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如 报表管理" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item label="模块" name="module">
            <Input placeholder="如 report" style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input placeholder="可选" style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={permissionSubmitting}>
              新建
            </Button>
          </Form.Item>
        </Form>

        <Table<PermissionItem>
          rowKey="id"
          columns={permissionColumns}
          dataSource={permissions}
          loading={permissionsLoading}
          size="small"
          style={{ marginTop: 16 }}
          pagination={false}
          scroll={{ y: 360 }}
        />
      </Modal>
      </div>
    </SystemPage>
  );
}
