import { useEffect, useMemo } from 'react';
import { Layout, Dropdown, Avatar, Breadcrumb, Flex, message } from 'antd';
import {
  DownOutlined,
  CloseOutlined,
  FileTextOutlined,
  LogoutOutlined,
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
  const avatar = useUserStore((state) => state.avatar);
  const logout = useUserStore((state) => state.logout);
  const menus = useUserStore((state) => state.menus);
  const visitedSystemPaths = useSystemNavigationStore(
    (state) => state.visitedPaths,
  );
  const visitSystemPath = useSystemNavigationStore((state) => state.visitPath);
  const closeSystemPath = useSystemNavigationStore((state) => state.closePath);
  const clearVisitedSystemPaths = useSystemNavigationStore(
    (state) => state.clearVisitedPaths,
  );

  const displayName = userInfo?.nickname || userInfo?.username || '未登录';
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
      .filter((page): page is MenuNode => page !== undefined),
    [systemPageByPath, visitedSystemPaths],
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
          {visitedSystemPages.map((page) => (
            <div
              key={page.path}
              className={
                page.path === location.pathname
                  ? `${styles.systemTab} ${styles.systemTabActive}`
                  : styles.systemTab
              }
            >
              <button
                type="button"
                className={styles.systemTabLink}
                onClick={() => navigate(page.path ?? WORKBENCH_HOME_PATH)}
              >
                <FileTextOutlined />
                <span>{page.title}</span>
              </button>
              {page.path ? (
                <button
                  type="button"
                  className={styles.systemTabClose}
                  aria-label={`关闭${page.title}`}
                  onClick={() => handleCloseSystemPage(page.path as string)}
                >
                  <CloseOutlined />
                </button>
              ) : null}
            </div>
          ))}
        </nav>
      ) : null}
    </>
  );
}
