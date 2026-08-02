import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import Layout from './components/Layout';
import AppInitializer from './components/app-initializer/AppInitializer';
import RequireAuth from './components/require-auth/RequireAuth';
import RequireGuest from './components/require-guest/RequireGuest';
import RequirePermission from './components/require-permission/RequirePermission';
import Login from './pages/login/Login';
import { PageLoading } from './components/page-loading/PageLoading';
import { PERMISSION_CODE } from './constants/access-control';
import {
  AgentManagement,
  BotManagement,
  DataPlatformDashboard,
  DataPlatformDataItems,
  DataPlatformSystemConfig,
  InviteCode,
  LogQuery,
  MenuManagement,
  Register,
  UserPermission,
  UserProfile,
  UserRegister,
} from './router/lazy-pages';

// 动态路由兜底：将所有未匹配静态路由的路径交给 DynamicPage，
// 后者根据 /auth/me 菜单树中的 component 字段 + 组件注册表解析页面。
const DynamicPage = lazy(() => import('@/pages/dynamic-page/DynamicPage'));

// 懒加载页面统一 fallback
const LazyFallback = <PageLoading />;

function withSuspense(element: React.ReactElement): React.ReactElement {
  return <Suspense fallback={LazyFallback}>{element}</Suspense>;
}

function withPermission(
  element: React.ReactElement,
  required: readonly string[],
): React.ReactElement {
  return (
    <RequirePermission required={required}>
      {withSuspense(element)}
    </RequirePermission>
  );
}

function withGuestPage(element: React.ReactElement): React.ReactElement {
  return (
    <AppInitializer>
      <RequireGuest>{element}</RequireGuest>
    </AppInitializer>
  );
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: withGuestPage(<Login />),
  },
  {
    path: '/register',
    element: withGuestPage(withSuspense(<Register />)),
  },
  {
    path: '/',
    element: (
      <AppInitializer>
        <RequireAuth>
          <Layout />
        </RequireAuth>
      </AppInitializer>
    ),
    children: [
      // 首页直接跳转到个人信息（原 PageA/PageB 占位页已移除）
      { index: true, element: <Navigate to="/system/user/profile" replace /> },
      {
        path: 'data-platform/dashboard',
        element: withPermission(
          <DataPlatformDashboard />,
          [PERMISSION_CODE.DATA_PLATFORM_DASHBOARD],
        ),
      },
      {
        path: 'data-platform/data-items',
        element: withPermission(
          <DataPlatformDataItems />,
          [PERMISSION_CODE.DATA_PLATFORM_DATA_ITEMS],
        ),
      },
      {
        path: 'data-platform/system-config',
        element: withPermission(
          <DataPlatformSystemConfig />,
          [PERMISSION_CODE.DATA_PLATFORM_CONFIG],
        ),
      },
      // 系统设置-用户：个人信息、用户管理、权限与邀请码路由
      {
        path: 'system/user/profile',
        element: withSuspense(<UserProfile />),
      },
      {
        path: 'system/user/register',
        element: withPermission(
          <UserRegister />,
          [PERMISSION_CODE.USER_MANAGE],
        ),
      },
      {
        path: 'system/user/permission',
        element: withPermission(
          <UserPermission />,
          [PERMISSION_CODE.USER_PERMISSION],
        ),
      },
      {
        path: 'system/user/invite-code',
        element: withPermission(
          <InviteCode />,
          [PERMISSION_CODE.INVITE_CODE_MANAGE],
        ),
      },
      // 系统设置-系统-菜单管理
      {
        path: 'system/menu',
        element: withPermission(
          <MenuManagement />,
          [PERMISSION_CODE.MENU_MANAGE],
        ),
      },
      {
        path: 'system/log-query',
        element: withPermission(
          <LogQuery />,
          [PERMISSION_CODE.OBSERVABILITY_LOG_VIEW],
        ),
      },
      // 数字员工-Bot管理
      {
        path: 'digital-employee/bots',
        element: withPermission(
          <BotManagement />,
          [PERMISSION_CODE.BOT_MANAGE],
        ),
      },
      // 数字员工-Agent管理
      {
        path: 'digital-employee/agents',
        element: withPermission(
          <AgentManagement />,
          [PERMISSION_CODE.AGENT_MANAGE],
        ),
      },
      // ★ 动态路由兜底：菜单管理页面新增的菜单项若未在静态路由中注册，
      // 则走 DynamicPage —— 根据 /auth/me 菜单树 + component 注册表渲染。
      {
        path: '*',
        element: withSuspense(<DynamicPage />),
      },
    ],
  },
]);
