import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Space,
  Spin,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TreeDataNode, TreeProps } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
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
import type { MenuNode } from '@/api/auth-api';
import { ROLE_CODE } from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';
import { getRequestErrorMessage } from '@/utils/request';
import styles from './index.module.css';

const { Text } = Typography;

const DEFAULT_PAGE_SIZE = 20;

/** 从请求错误中提取用户可读的提示文案 */
function getErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '操作失败，请稍后重试');
}

/** 把后端菜单树（MenuNode[]）转换为 antd Tree 的 treeData 格式 */
function convertMenusToTreeData(menus: MenuNode[]): TreeDataNode[] {
  return menus.map((menu) => {
    const node: TreeDataNode = {
      key: menu.id,
      title: menu.title,
    };
    if (menu.children && menu.children.length > 0) {
      node.children = convertMenusToTreeData(menu.children);
    }
    return node;
  });
}

/** 超级管理员是平台保护角色，不进入通用角色维护列表。 */
function getManageableRoles(roles: RoleItem[]): RoleItem[] {
  return roles.filter((role) => role.code !== ROLE_CODE.SUPER_ADMIN);
}

interface RoleFormValues {
  code: string;
  name: string;
  description: string;
}

export default function UserPermission(): React.ReactElement {
  // ── 左栏：用户角色分配 ──
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [usersLoading, setUsersLoading] = useState<boolean>(true);
  const [usersTotal, setUsersTotal] = useState<number>(0);
  const [usersPage, setUsersPage] = useState<number>(1);
  const [usersPageSize, setUsersPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);
  const [userRoleCodes, setUserRoleCodes] = useState<string[]>([]);
  const [userRolesSaving, setUserRolesSaving] = useState<boolean>(false);

  // ── 用户独立菜单（选中用户后加载，可个性化调整） ──
  const [userMenuIds, setUserMenuIds] = useState<number[]>([]);
  const [userMenusLoading, setUserMenusLoading] = useState<boolean>(false);
  const [userMenusSaving, setUserMenusSaving] = useState<boolean>(false);

  // ── 右栏：角色管理 + 菜单分配 ──
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [rolesLoading, setRolesLoading] = useState<boolean>(true);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [checkedMenuIds, setCheckedMenuIds] = useState<number[]>([]);
  const [roleMenusSaving, setRoleMenusSaving] = useState<boolean>(false);

  // ── 角色创建/编辑弹窗 ──
  const [roleModalOpen, setRoleModalOpen] = useState<boolean>(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [roleForm] = Form.useForm<RoleFormValues>();
  const [roleSubmitting, setRoleSubmitting] = useState<boolean>(false);

  const menus = useUserStore((state) => state.menus);
  const menuTreeData = useMemo<TreeDataNode[]>(() => convertMenusToTreeData(menus), [menus]);

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
      const manageableRoles = getManageableRoles(response);
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

  /** 加载用户独立菜单（选中用户后调用） */
  async function loadUserMenus(userId: number): Promise<void> {
    setUserMenusLoading(true);
    try {
      const menusResp = await fetchUserMenus(userId);
      setUserMenuIds(menusResp.map((m) => m.id));
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
      fetchUsers(1, DEFAULT_PAGE_SIZE),
      fetchRoles(),
    ])
      .then(([userResponse, roleResponse]) => {
        if (!active) return;
        setUsers(userResponse.items);
        setUsersTotal(userResponse.total);
        setUsersPage(userResponse.page);
        setUsersPageSize(userResponse.page_size);
        setRoles(getManageableRoles(roleResponse));
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
  }, []);

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
        message.success('用户角色保存成功，角色菜单已复制到该用户');
        const updatedRoles = [...userRoleCodes];
        setUsers((prev) =>
          prev.map((u) => (u.id === selectedUser.id ? { ...u, roles: updatedRoles } : u)),
        );
        setSelectedUser((prev) => (prev ? { ...prev, roles: updatedRoles } : prev));
        // 角色变更后，重新加载用户独立菜单（后端已 union 角色菜单）
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
        message.success('用户菜单保存成功');
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
                {code}
              </Tag>
            ))
          )}
        </Space>
      ),
    },
  ];

  return (
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
            pagination={{
              current: usersPage,
              pageSize: usersPageSize,
              total: usersTotal,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => void loadUsers(page, pageSize),
            }}
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
                <Button
                  type="primary"
                  size="small"
                  loading={userRolesSaving}
                  onClick={() => void handleSaveUserRoles()}
                >
                  保存角色
                </Button>
              </div>
              {rolesLoading ? (
                <Spin />
              ) : roles.length === 0 ? (
                <Empty description="暂无角色" />
              ) : (
                <Checkbox.Group
                  value={userRoleCodes}
                  onChange={(values) => {
                    setUserRoleCodes(
                      values.filter((v): v is string => typeof v === 'string'),
                    );
                  }}
                >
                  <Space orientation="vertical">
                    {roles.map((role) => (
                      <Checkbox key={role.code} value={role.code}>
                        {role.name}（{role.code}）
                      </Checkbox>
                    ))}
                  </Space>
                </Checkbox.Group>
              )}
            </div>

            <Alert
              type="info"
              showIcon
              className={styles.hintAlert}
              message="分配角色后，角色的权限和菜单会自动复制到该用户。之后可在下方独立调整，不影响其他用户。"
            />

            {/* 用户独立菜单 */}
            <div className={styles.userPermSection}>
              <div className={styles.sectionHeader}>
                <Text strong>用户独立菜单</Text>
                <Button
                  type="primary"
                  size="small"
                  loading={userMenusSaving}
                  disabled={userMenusLoading}
                  onClick={() => void handleSaveUserMenus()}
                >
                  保存菜单
                </Button>
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
          <Button
            type="primary"
            icon={<PlusOutlined />}
            size="small"
            onClick={openCreateRoleModal}
          >
            新建角色
          </Button>
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
                </div>
              ))}
            </Space>
          </Radio.Group>
        )}

        {selectedRole ? (
          <div className={styles.menuTree}>
            <div className={styles.sectionHeader}>
              <Text strong>为 {selectedRole.name} 分配菜单</Text>
              <Button
                type="primary"
                size="small"
                loading={roleMenusSaving}
                onClick={() => void handleSaveRoleMenus()}
              >
                保存
              </Button>
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
    </div>
  );
}
