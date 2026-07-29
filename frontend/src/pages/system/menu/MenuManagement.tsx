import { useEffect, useMemo, useState } from 'react';
import type { Key, ReactNode } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  TreeSelect,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AppstoreOutlined,
  ControlOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {
  createMenu,
  deleteMenu,
  fetchMenus,
  updateMenu,
  type CreateMenuPayload,
  type MenuItem,
  type UpdateMenuPayload,
} from '@/api/menu-api';
import {
  fetchPermissions,
  type PermissionItem,
} from '@/api/permission-api';
import { useUserStore } from '@/store/user-store';
import { getMenuIcon } from '@/constants/menu-icons';
import { getRequestErrorMessage } from '@/utils/request';
import styles from './index.module.css';

const { Title } = Typography;

/** 菜单类型文案与颜色 */
const MENU_TYPE_META: Record<number, { label: string; color: string }> = {
  1: { label: '目录', color: 'blue' },
  2: { label: '菜单', color: 'green' },
  3: { label: '按钮', color: 'orange' },
};

/** 菜单表单值 */
interface MenuFormValues {
  parent_id: number;
  menu_type: number;
  title: string;
  path?: string;
  component?: string;
  icon?: string;
  permission?: string;
  sort: number;
  visible: boolean;
}

/** 树节点（用于父菜单选择器） */
interface TreeNode {
  value: number;
  title: string;
  children?: TreeNode[];
}

/** 表格树节点：MenuItem 扩展可选 children（用于层级展示与"有子节点禁止删除"判断） */
type MenuTreeNode = MenuItem & { children?: MenuTreeNode[] };

/** 从请求错误中提取用户可读的提示文案 */
function getErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '操作失败，请稍后重试');
}

/** 把扁平菜单列表构建为树形（用于父菜单 TreeSelect） */
function buildTree(menus: MenuItem[]): TreeNode[] {
  const map = new Map<number, TreeNode>();
  menus.forEach((m) => {
    if (!map.has(m.id)) {
      map.set(m.id, { value: m.id, title: m.title });
    }
  });
  const roots: TreeNode[] = [];
  menus.forEach((m) => {
    const node = map.get(m.id);
    if (!node) return;
    if (m.parent_id === 0 || !map.has(m.parent_id)) {
      roots.push(node);
    } else {
      const parent = map.get(m.parent_id);
      if (!parent) return;
      if (!parent.children) {
        parent.children = [];
      }
      parent.children.push(node);
    }
  });
  return roots;
}

/**
 * 把扁平菜单列表构建为 Antd Table 树数据。
 *
 * dataSource 只返回根节点，子节点仅存在于父节点 ``children`` 中，避免同一
 * 菜单被顶层与子层重复渲染。叶子节点不写空 children，因此不会出现无效的
 * 展开按钮。重复 ID 只保留首次出现的数据，避免异常响应污染表格。
 */
function buildTableData(menus: MenuItem[]): MenuTreeNode[] {
  const map = new Map<number, MenuTreeNode>();
  menus.forEach((m) => {
    if (!map.has(m.id)) {
      map.set(m.id, { ...m });
    }
  });
  const roots: MenuTreeNode[] = [];
  menus.forEach((menu) => {
    const node = map.get(menu.id);
    if (!node) return;
    if (node.parent_id === 0 || !map.has(node.parent_id)) {
      if (!roots.some((root) => root.id === node.id)) {
        roots.push(node);
      }
    } else {
      const parent = map.get(node.parent_id);
      if (!parent) return;
      if (!parent.children) {
        parent.children = [];
      }
      if (!parent.children.some((child) => child.id === node.id)) {
        parent.children.push(node);
      }
    }
  });
  return roots;
}

/** 返回实际拥有子节点的目录 ID，用于受控展开状态。 */
function getExpandableDirectoryIds(menus: MenuItem[]): Key[] {
  const parentIds = new Set(menus.map((menu) => menu.parent_id));
  return menus
    .filter((menu) => menu.menu_type === 1 && parentIds.has(menu.id))
    .map((menu) => menu.id);
}

/** 未配置或无法识别图标时，按菜单类型提供稳定的语义化图标。 */
function getFallbackIcon(menuType: number): ReactNode {
  if (menuType === 1) {
    return <FolderOpenOutlined />;
  }
  if (menuType === 3) {
    return <ControlOutlined />;
  }
  return <AppstoreOutlined />;
}

export default function MenuManagement(): React.ReactElement {
  const [loading, setLoading] = useState<boolean>(true);
  const [menus, setMenus] = useState<MenuItem[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<Key[]>([]);
  const [permissions, setPermissions] = useState<PermissionItem[]>([]);
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [form] = Form.useForm<MenuFormValues>();

  const reloadMenus = useUserStore((state) => state.reloadMenus);

  /** 表格数据：仅根节点进入 dataSource，子节点通过 children 嵌套 */
  const tableData = useMemo(() => buildTableData(menus), [menus]);

  const menuSummary = useMemo(
    () => ({
      total: menus.length,
      directories: menus.filter((menu) => menu.menu_type === 1).length,
      pages: menus.filter((menu) => menu.menu_type === 2).length,
      permissions: menus.filter((menu) => Boolean(menu.permission)).length,
    }),
    [menus],
  );

  /** 父菜单树选项：包含「顶级」选项 */
  const parentTreeData = useMemo<TreeNode[]>(() => {
    const tree = buildTree(menus);
    return [{ value: 0, title: '顶级菜单', children: tree }];
  }, [menus]);

  async function loadMenus(): Promise<void> {
    setLoading(true);
    try {
      const [list, permissionList] = await Promise.all([
        fetchMenus(),
        fetchPermissions(),
      ]);
      setMenus(list);
      setExpandedRowKeys(getExpandableDirectoryIds(list));
      setPermissions(permissionList);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  // 初始数据加载：菜单与权限码目录并行读取
  useEffect(() => {
    let active = true;
    void Promise.all([fetchMenus(), fetchPermissions()])
      .then(([menuList, permissionList]) => {
        if (!active) return;
        setMenus(menuList);
        setExpandedRowKeys(getExpandableDirectoryIds(menuList));
        setPermissions(permissionList);
      })
      .catch((error: unknown) => {
        if (active) {
          message.error(getErrorMessage(error));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  /** 计算指定父菜单下的下一个排序值（同级最大 sort + 10，便于中间插入） */
  function calcNextSort(parentId: number): number {
    const siblings = menus.filter((m) => m.parent_id === parentId);
    const maxSort = siblings.reduce((max, m) => Math.max(max, m.sort), 0);
    return maxSort + 10;
  }

  function openCreateModal(): void {
    setEditingId(null);
    form.resetFields();
    // 新建时自动计算顶级菜单下一个 sort，用户可在表单中手动修改
    form.setFieldsValue({
      parent_id: 0,
      menu_type: 1,
      sort: calcNextSort(0),
      visible: true,
    });
    setModalOpen(true);
  }

  function openEditModal(menu: MenuItem): void {
    setEditingId(menu.id);
    form.setFieldsValue({
      parent_id: menu.parent_id,
      menu_type: menu.menu_type,
      title: menu.title,
      path: menu.path ?? undefined,
      component: menu.component ?? undefined,
      icon: menu.icon ?? undefined,
      permission: menu.permission ?? undefined,
      sort: menu.sort,
      visible: menu.visible,
    });
    setModalOpen(true);
  }

  function closeModal(): void {
    setModalOpen(false);
    setEditingId(null);
    form.resetFields();
  }

  /** 菜单变更后刷新列表与当前用户菜单缓存。 */
  async function refreshAfterChange(): Promise<void> {
    await loadMenus();
    try {
      // 重新拉取 /auth/me 刷新当前用户的菜单树缓存
      await reloadMenus();
      // 路由/侧边栏等部分依赖页面初始化时构建，提示用户手动刷新以确保完全生效
      message.success('菜单已更新，侧边栏已同步刷新');
    } catch {
      // 静默处理：菜单列表本身已刷新，缓存刷新失败不阻塞主流程
    }
  }

  async function handleSubmit(values: MenuFormValues): Promise<void> {
    setSubmitting(true);
    try {
      if (editingId !== null) {
        const payload: UpdateMenuPayload = {
          parent_id: values.parent_id,
          menu_type: values.menu_type,
          title: values.title,
          path: values.path?.trim() || null,
          component: values.component?.trim() || null,
          icon: values.icon?.trim() || null,
          permission: values.permission || null,
          sort: values.sort,
          visible: values.visible,
        };
        await updateMenu(editingId, payload);
        message.success('菜单更新成功');
      } else {
        const payload: CreateMenuPayload = {
          parent_id: values.parent_id,
          menu_type: values.menu_type,
          title: values.title,
          path: values.path || undefined,
          component: values.component || undefined,
          icon: values.icon || undefined,
          permission: values.permission || undefined,
          sort: values.sort,
          visible: values.visible,
        };
        await createMenu(payload);
        message.success('菜单创建成功');
      }
      closeModal();
      await refreshAfterChange();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(menu: MenuItem): Promise<void> {
    try {
      await deleteMenu(menu.id);
      message.success(`菜单 ${menu.title} 已删除`);
      await refreshAfterChange();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  const columns: ColumnsType<MenuTreeNode> = [
    {
      title: '标题',
      dataIndex: 'title',
      width: 236,
      render: (value: string, record: MenuTreeNode) => (
        <span className={styles.titleCell}>
          <Tooltip title={record.icon ? `图标：${record.icon}` : '未配置图标'}>
            <span
              className={`${styles.iconTile} ${
                record.menu_type === 1 ? styles.directoryIcon : styles.menuIcon
              }`}
            >
              {getMenuIcon(record.icon, getFallbackIcon(record.menu_type))}
            </span>
          </Tooltip>
          <span className={styles.titleText}>{value}</span>
        </span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'menu_type',
      width: 78,
      render: (value: number) => {
        const meta = MENU_TYPE_META[value] ?? { label: '未知', color: 'default' };
        return (
          <Tag
            color={meta.color}
            variant="filled"
            className={styles.menuTypeTag}
          >
            {meta.label}
          </Tag>
        );
      },
    },
    {
      title: '路由路径',
      dataIndex: 'path',
      width: 184,
      render: (value: string | null) =>
        value ? (
          <Tooltip title={value}>
            <code className={styles.pathText}>{value}</code>
          </Tooltip>
        ) : (
          <span className={styles.emptyValue}>—</span>
        ),
    },
    {
      title: '组件',
      dataIndex: 'component',
      width: 168,
      render: (value: string | null) =>
        value ? (
          <Tooltip title={value}>
            <code className={styles.pathText}>{value}</code>
          </Tooltip>
        ) : (
          <span className={styles.emptyValue}>—</span>
        ),
    },
    {
      title: '权限码',
      dataIndex: 'permission',
      width: 178,
      render: (value: string | null) =>
        value ? (
          <Tooltip title={value}>
            <span className={styles.permissionCode}>
              <SafetyCertificateOutlined />
              <code>{value}</code>
            </span>
          </Tooltip>
        ) : (
          <span className={styles.emptyValue}>—</span>
        ),
    },
    {
      title: '排序',
      dataIndex: 'sort',
      width: 64,
      align: 'center',
      render: (value: number) => (
        <span className={styles.sortValue}>{value}</span>
      ),
    },
    {
      title: '可见',
      dataIndex: 'visible',
      width: 74,
      align: 'center',
      render: (value: boolean) =>
        value ? (
          <span className={`${styles.visibilityBadge} ${styles.isVisible}`}>
            <EyeOutlined />
            显示
          </span>
        ) : (
          <span className={`${styles.visibilityBadge} ${styles.isHidden}`}>
            <EyeInvisibleOutlined />
            隐藏
          </span>
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 154,
      render: (_, record) => {
        // 根目录（顶级）不允许删除，避免误删顶层导航结构
        const isRoot = record.parent_id === 0;
        // 有子菜单的节点不允许删除，需先删除子菜单
        const hasChildren = menus.some((m) => m.parent_id === record.id);
        if (isRoot) {
          // 根目录：不显示删除按钮
          return (
            <Button
              type="link"
              size="small"
              className={styles.actionButton}
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            >
              编辑
            </Button>
          );
        }
        if (hasChildren) {
          // 有子节点：可点击但直接弹 message 提示，不进入删除流程
          return (
            <Space size={4}>
              <Button
                type="link"
                size="small"
                className={styles.actionButton}
                icon={<EditOutlined />}
                onClick={() => openEditModal(record)}
              >
                编辑
              </Button>
              <Button
                type="link"
                size="small"
                danger
                className={styles.actionButton}
                icon={<DeleteOutlined />}
                onClick={() =>
                  message.warning('该菜单下仍有子菜单，请先删除子菜单')
                }
              >
                删除
              </Button>
            </Space>
          );
        }
        // 叶子菜单：正常删除流程
        return (
          <Space size={4}>
            <Button
              type="link"
              size="small"
              className={styles.actionButton}
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            >
              编辑
            </Button>
            <Popconfirm
              title="确认删除该菜单？"
              description="删除后需手动重新分配角色。"
              onConfirm={() => void handleDelete(record)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button
                type="link"
                size="small"
                danger
                className={styles.actionButton}
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <div className={styles.headingBlock}>
          <span className={styles.eyebrow}>ACCESS CONTROL · NAVIGATION</span>
          <Title level={3} className={styles.pageTitle}>
            菜单管理
          </Title>
          <p className={styles.pageDescription}>
            维护系统导航层级、页面路由与权限标识
          </p>
        </div>
        <Space className={styles.toolbarActions}>
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void loadMenus()}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新建菜单
          </Button>
        </Space>
      </div>

      <div className={styles.summaryGrid}>
        <div className={styles.summaryItem}>
          <span className={styles.summaryLabel}>全部节点</span>
          <strong className={styles.summaryValue}>{menuSummary.total}</strong>
        </div>
        <div className={styles.summaryItem}>
          <span className={styles.summaryLabel}>目录层级</span>
          <strong className={styles.summaryValue}>
            {menuSummary.directories}
          </strong>
        </div>
        <div className={styles.summaryItem}>
          <span className={styles.summaryLabel}>页面菜单</span>
          <strong className={styles.summaryValue}>{menuSummary.pages}</strong>
        </div>
        <div className={styles.summaryItem}>
          <span className={styles.summaryLabel}>权限绑定</span>
          <strong className={styles.summaryValue}>
            {menuSummary.permissions}
          </strong>
        </div>
      </div>

      <div className={styles.tableWrapper}>
        <div className={styles.tableHeader}>
          <div>
            <span className={styles.tableTitle}>菜单结构</span>
            <span className={styles.tableHint}>
              目录节点支持展开，页面节点直接关联业务路由
            </span>
          </div>
          <span className={styles.recordCount}>{menus.length} 条配置</span>
        </div>
        <Table<MenuTreeNode>
          rowKey="id"
          columns={columns}
          dataSource={tableData}
          loading={loading}
          pagination={false}
          size="middle"
          tableLayout="fixed"
          scroll={{ x: 1136 }}
          rowClassName={(record) =>
            record.menu_type === 1 ? styles.directoryRow : styles.menuRow
          }
          expandable={{
            expandedRowKeys,
            onExpandedRowsChange: (keys) => setExpandedRowKeys([...keys]),
            rowExpandable: (record) =>
              record.menu_type === 1 && Boolean(record.children?.length),
          }}
        />
      </div>

      <Modal
        open={modalOpen}
        title={editingId !== null ? '编辑菜单' : '新建菜单'}
        width={600}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        okText={editingId !== null ? '保存' : '创建'}
        cancelText="取消"
        destroyOnHidden
      >
        <Form<MenuFormValues>
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          onValuesChange={(changed) => {
            // 仅新建时联动：父菜单变化后自动填入同级下一个 sort
            if (
              editingId === null
              && typeof changed.parent_id === 'number'
            ) {
              form.setFieldValue('sort', calcNextSort(changed.parent_id));
            }
          }}
        >
          <Form.Item
            label="父菜单"
            name="parent_id"
            rules={[{ required: true, message: '请选择父菜单' }]}
          >
            <TreeSelect
              treeData={parentTreeData}
              treeDefaultExpandAll
              placeholder="选择父菜单，顶级菜单选「顶级菜单」"
            />
          </Form.Item>

          <Form.Item
            label="菜单类型"
            name="menu_type"
            rules={[{ required: true, message: '请选择菜单类型' }]}
          >
            <Select
              options={[
                { value: 1, label: '目录（含子菜单的容器）' },
                { value: 2, label: '菜单（实际页面）' },
                { value: 3, label: '按钮（仅权限点，不显示）' },
              ]}
              placeholder="选择类型"
            />
          </Form.Item>

          <Form.Item
            label="标题"
            name="title"
            rules={[
              { required: true, message: '请输入菜单标题' },
              { max: 64, message: '标题不超过 64 字符' },
            ]}
          >
            <Input placeholder="如 数据中台、Dashboard" />
          </Form.Item>

          <Form.Item
            label="路由路径"
            name="path"
            rules={[{ max: 255, message: '路径不超过 255 字符' }]}
            extra="前端路由路径，如 /data-platform/dashboard；目录可留空"
          >
            <Input placeholder="/system/menu" />
          </Form.Item>

          <Form.Item
            label="组件路径"
            name="component"
            rules={[{ max: 255, message: '组件路径不超过 255 字符' }]}
            extra="前端组件相对路径，如 system/menu；目录与按钮可留空"
          >
            <Input placeholder="system/menu" />
          </Form.Item>

          <Form.Item
            label="图标名"
            name="icon"
            rules={[{ max: 64, message: '图标名不超过 64 字符' }]}
            extra="antd 图标组件名，如 DatabaseOutlined、SettingOutlined"
          >
            <Input placeholder="DatabaseOutlined" />
          </Form.Item>

          <Form.Item
            label="权限码"
            name="permission"
            extra="访问该菜单所需权限码；留空表示仅登录可见"
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="选择服务端已定义的权限码"
              options={permissions.map((permission) => ({
                value: permission.code,
                label: `${permission.name}（${permission.code}）`,
              }))}
            />
          </Form.Item>

          <Form.Item label="排序" name="sort" rules={[{ required: true }]}>
            <InputNumber min={0} max={9999} precision={0} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            label="是否可见"
            name="visible"
            valuePropName="checked"
            rules={[{ required: true }]}
          >
            <Switch checkedChildren="显示" unCheckedChildren="隐藏" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
