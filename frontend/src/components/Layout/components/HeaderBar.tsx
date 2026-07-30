import { useEffect, useMemo } from 'react';
import {
  Avatar,
  Breadcrumb,
  Button,
  Dropdown,
  Flex,
  Layout,
  Tabs,
  message,
} from 'antd';
import type { TabsProps } from 'antd';
import {
  DownOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MoreOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import styles from '../index.module.css';
import { useUserStore } from '@/store/user-store';
import type { MenuNode } from '@/api/auth-api';
import {
  SYSTEM_ROUTE_PREFIX,
  WORKBENCH_HOME_PATH,
} from '@/constants/navigation';
import { useSystemNavigationStore } from '@/store/system-navigation-store';

const { Header } = Layout;

function findMenuTrail(
  menus: MenuNode[],
  pathname: string,
  parents: string[] = [],
): string[] | undefined {
  for (const menu of menus) {
    const currentTrail = [...parents, menu.title];
    if (menu.path === pathname) return currentTrail;
    const childTrail = findMenuTrail(menu.children ?? [], pathname, currentTrail);
    if (childTrail) return childTrail;
  }
  return undefined;
}

function collectSystemPages(
  menus: MenuNode[],
  pages: Map<string, MenuNode> = new Map(),
): Map<string, MenuNode> {
  for (const menu of menus) {
    if (
      menu.path?.startsWith(SYSTEM_ROUTE_PREFIX)
      && menu.menu_type === 2
      && menu.visible
    ) {
      pages.set(menu.path, menu);
    }
    collectSystemPages(menu.children ?? [], pages);
  }
  return pages;
}

export default function HeaderBar(): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const userInfo = useUserStore((state) => state.userInfo);
  const profileLoading = useUserStore((state) => state.profileLoading);
  const avatar = useUserStore((state) => state.avatar);
  const logout = useUserStore((state) => state.logout);
  const menus = useUserStore((state) => state.menus);
  const visitedSystemPaths = useSystemNavigationStore(
    (state) => state.visitedPaths,
  );
  const visitSystemPath = useSystemNavigationStore((state) => state.visitPath);
  const closeSystemPath = useSystemNavigationStore((state) => state.closePath);
  const closeOtherSystemPaths = useSystemNavigationStore(
    (state) => state.closeOtherPaths,
  );
  const clearVisitedSystemPaths = useSystemNavigationStore(
    (state) => state.clearVisitedPaths,
  );

  const displayName = userInfo?.nickname
    || userInfo?.username
    || (profileLoading ? '加载中' : '未登录');
  const breadcrumbItems = useMemo(
    () => [
      { title: '数字员工' },
      ...(findMenuTrail(menus, location.pathname) ?? []).map((title) => ({ title })),
    ],
    [location.pathname, menus],
  );
  const systemPageByPath = useMemo(
    () => collectSystemPages(menus),
    [menus],
  );
  const currentSystemPage = systemPageByPath.get(location.pathname);
  const visitedSystemPages = useMemo(
    () => visitedSystemPaths
      .map((path) => systemPageByPath.get(path))
      .filter(
        (page): page is MenuNode & { path: string } => (
          page !== undefined && page.path !== null
        ),
      ),
    [systemPageByPath, visitedSystemPaths],
  );
  const systemTabItems = useMemo<TabsProps['items']>(
    () => visitedSystemPages.map((page) => ({
      key: page.path,
      label: (
        <span className={styles.systemTabLabel}>
          <FileTextOutlined />
          <span>{page.title}</span>
        </span>
      ),
      closable: true,
    })),
    [visitedSystemPages],
  );

  useEffect(() => {
    const path = currentSystemPage?.path;
    if (path) visitSystemPath(path);
  }, [currentSystemPage?.path, visitSystemPath]);

  const userActionItems = [
    { key: 'profile', icon: <UserOutlined />, label: '个人信息' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserClick = async ({ key }: { key: string }): Promise<void> => {
    if (key === 'profile') {
      navigate('/system/user/profile');
    } else if (key === 'logout') {
      await logout();
      clearVisitedSystemPaths();
      message.success('已退出登录');
      navigate('/login', { replace: true });
    }
  };

  const handleCloseSystemPage = (path: string): void => {
    const remainingPaths = visitedSystemPaths.filter((item) => item !== path);
    closeSystemPath(path);
    if (path === location.pathname) {
      navigate(remainingPaths.at(-1) ?? WORKBENCH_HOME_PATH);
    }
  };
  const handleSystemTabEdit: NonNullable<TabsProps['onEdit']> = (
    targetKey,
    action,
  ): void => {
    if (action === 'remove' && typeof targetKey === 'string') {
      handleCloseSystemPage(targetKey);
    }
  };
  const handleSystemTabAction = ({ key }: { key: string }): void => {
    if (key === 'close-current') {
      handleCloseSystemPage(location.pathname);
      return;
    }
    if (key === 'close-others') {
      closeOtherSystemPaths(location.pathname);
      return;
    }
    if (key === 'close-all') {
      clearVisitedSystemPaths();
      navigate(WORKBENCH_HOME_PATH);
    }
  };
  const systemTabActionItems = [
    { key: 'close-current', label: '关闭当前' },
    { key: 'close-others', label: '关闭其他' },
    { type: 'divider' as const },
    { key: 'close-all', label: '关闭全部' },
  ];

  return (
    <>
      <Header className={styles.header}>
        <Flex justify="space-between" align="center" className={styles.headerFlex}>
          <div className={styles.navigation}>
            <span className={styles.navigationLabel}>WORKBENCH</span>
            <Breadcrumb items={breadcrumbItems} />
          </div>
          <Dropdown menu={{ items: userActionItems, onClick: handleUserClick }} placement="bottomRight">
            <span className={styles.userDropdown}>
              <Avatar src={avatar} icon={<UserOutlined />} size={32} className={styles.avatar} />
              <span className={styles.username}>{displayName}</span>
              <DownOutlined className={styles.downIcon} />
            </span>
          </Dropdown>
        </Flex>
      </Header>
      {location.pathname.startsWith(SYSTEM_ROUTE_PREFIX)
      && visitedSystemPages.length > 0 ? (
        <nav className={styles.systemTabs} aria-label="系统设置页面导航">
          <Tabs
            className={styles.systemTabsControl}
            activeKey={location.pathname}
            type="editable-card"
            hideAdd
            items={systemTabItems}
            onChange={(path) => navigate(path)}
            onEdit={handleSystemTabEdit}
            tabBarExtraContent={{
              right: (
                <Dropdown
                  menu={{
                    items: systemTabActionItems,
                    onClick: handleSystemTabAction,
                  }}
                  placement="bottomRight"
                >
                  <Button
                    type="text"
                    className={styles.systemTabActions}
                    icon={<MoreOutlined />}
                    aria-label="页签操作"
                  />
                </Dropdown>
              ),
            }}
          />
        </nav>
      ) : null}
    </>
  );
}
