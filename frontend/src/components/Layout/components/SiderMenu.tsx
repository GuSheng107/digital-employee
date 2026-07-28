import { Layout, Menu } from 'antd';
import type { MenuProps } from 'antd';
import {
  AppstoreOutlined,
  BuildOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  MenuOutlined,
  SettingOutlined,
  TableOutlined,
  UserOutlined,
  ProfileOutlined,
  UserAddOutlined,
  SafetyOutlined,
  GiftOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUserStore } from '@/store/user-store';
import type { MenuNode } from '@/api/auth-api';
import logo from '@/assets/images/avatar/logo.svg';
import styles from '../index.module.css';

const { Sider } = Layout;

const DATA_PLATFORM_KEY = 'data-platform';

type MenuItem = NonNullable<MenuProps['items']>[number];

/** 后端 icon 字符串到 antd 图标组件的映射 */
const iconMap: Record<string, React.ReactNode> = {
  AppstoreOutlined: <AppstoreOutlined />,
  BuildOutlined: <BuildOutlined />,
  DatabaseOutlined: <DatabaseOutlined />,
  DashboardOutlined: <DashboardOutlined />,
  MenuOutlined: <MenuOutlined />,
  SettingOutlined: <SettingOutlined />,
  TableOutlined: <TableOutlined />,
  UserOutlined: <UserOutlined />,
  ProfileOutlined: <ProfileOutlined />,
  UserAddOutlined: <UserAddOutlined />,
  SafetyOutlined: <SafetyOutlined />,
  GiftOutlined: <GiftOutlined />,
};

/** 生成菜单 key：优先 path，回退到 menu-${id} */
function menuKey(menu: MenuNode): string {
  return menu.path || `menu-${menu.id}`;
}

/** 把后端菜单树转换为 antd Menu items（仅渲染 visible=true 的节点） */
function convertMenusToItems(menus: MenuNode[]): MenuItem[] {
  return menus
    .filter((m) => m.visible)
    .map((menu) => {
      const icon = menu.icon ? iconMap[menu.icon] : null;
      const key = menuKey(menu);
      if (menu.children && menu.children.length > 0) {
        return {
          key,
          icon,
          label: menu.title,
          children: convertMenusToItems(menu.children),
        } as MenuItem;
      }
      return {
        key,
        icon,
        label: menu.title,
      } as MenuItem;
    });
}

/** 收集所有含 children 的菜单 key（父菜单），用于 onClick 时判断不跳转 */
function collectParentKeys(menus: MenuNode[]): Set<string> {
  const keys = new Set<string>();
  const walk = (list: MenuNode[]) => {
    list.forEach((m) => {
      if (m.children && m.children.length > 0) {
        keys.add(menuKey(m));
        walk(m.children);
      }
    });
  };
  walk(menus);
  return keys;
}

/** 默认菜单（fallback：后端未返回菜单数据时使用，兼容旧数据） */
const defaultMenuItems: MenuItem[] = [
  {
    key: DATA_PLATFORM_KEY,
    icon: <DatabaseOutlined />,
    label: '数据中台',
    children: [
      { key: '/data-platform/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
      { key: '/data-platform/data-items', icon: <TableOutlined />, label: 'Data Items' },
      { key: '/data-platform/system-config', icon: <SettingOutlined />, label: 'System Config' },
    ],
  } as MenuItem,
];

/** 递归收集所有含 children 的菜单 key（含多层），用于默认全展开 */
function collectAllParentKeys(menus: MenuNode[]): string[] {
  const keys: string[] = [];
  const walk = (list: MenuNode[]) => {
    list.forEach((m) => {
      if (m.children && m.children.length > 0) {
        keys.push(menuKey(m));
        walk(m.children);
      }
    });
  };
  walk(menus);
  return keys;
}

export default function SiderMenu(): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const menus = useUserStore((s) => s.menus);

  // 后端未返回菜单数据时使用默认菜单，保证数据库菜单未插入时也能正常使用
  const useDynamic = menus.length > 0;
  const items: MenuItem[] = useDynamic ? convertMenusToItems(menus) : defaultMenuItems;
  const parentKeys = useDynamic
    ? collectParentKeys(menus)
    : new Set<string>([DATA_PLATFORM_KEY]);

  // 默认全展开：递归收集所有层级含 children 的菜单 key
  const defaultOpenKeys = useDynamic
    ? collectAllParentKeys(menus)
    : [DATA_PLATFORM_KEY];

  const selectedKeys = [location.pathname];

  return (
    <Sider theme="dark" width={220}>
      <div className={styles.logo}>
        <img src={logo} alt="logo" />
        <span>工作台</span>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={selectedKeys}
        defaultOpenKeys={defaultOpenKeys}
        onClick={({ key }) => {
          // 父菜单（含 children）仅负责展开/折叠，不触发路由跳转
          if (parentKeys.has(key)) return;
          navigate(key);
        }}
        items={items}
      />
    </Sider>
  );
}
