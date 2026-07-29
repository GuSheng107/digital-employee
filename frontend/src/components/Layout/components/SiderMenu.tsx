import { useEffect, useMemo, useState } from 'react';
import { Layout, Menu } from 'antd';
import type { MenuProps } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUserStore } from '@/store/user-store';
import type { MenuNode } from '@/api/auth-api';
import logo from '@/assets/images/avatar/logo.svg';
import { getMenuIcon } from '@/constants/menu-icons';
import styles from '../index.module.css';

const { Sider } = Layout;

type MenuItem = NonNullable<MenuProps['items']>[number];

/** 生成菜单 key：优先 path，回退到 menu-${id} */
function menuKey(menu: MenuNode): string {
  return menu.path || `menu-${menu.id}`;
}

/** 把后端菜单树转换为 antd Menu items（仅渲染 visible=true 的节点） */
function convertMenusToItems(menus: MenuNode[]): MenuItem[] {
  return menus
    .filter((m) => m.visible)
    .map((menu) => {
      const icon = getMenuIcon(menu.icon, null);
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
function collectParentKeys(menus: MenuNode[]): string[] {
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

  // 空菜单代表未授权，不使用本地兜底菜单绕过服务端授权结果。
  const items = useMemo<MenuItem[]>(() => convertMenusToItems(menus), [menus]);
  const parentKeys = useMemo(() => collectParentKeys(menus), [menus]);
  const parentKeySet = useMemo(() => new Set(parentKeys), [parentKeys]);
  const [openKeys, setOpenKeys] = useState<string[]>([]);

  useEffect(() => {
    setOpenKeys((currentKeys) => {
      const retainedKeys = currentKeys.filter((key) => parentKeySet.has(key));
      return retainedKeys.length > 0 ? retainedKeys : parentKeys;
    });
  }, [parentKeys, parentKeySet]);

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
        openKeys={openKeys}
        onOpenChange={(keys) => setOpenKeys(keys)}
        onClick={({ key }) => {
          // 父菜单（含 children）仅负责展开/折叠，不触发路由跳转
          if (parentKeySet.has(key)) return;
          navigate(key);
        }}
        items={items}
      />
    </Sider>
  );
}
