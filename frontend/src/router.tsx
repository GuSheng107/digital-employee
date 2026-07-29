import { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import Layout from './components/Layout';
import AppInitializer from './components/app-initializer/AppInitializer';
import RequireAuth from './components/require-auth/RequireAuth';
import RequirePermission from './components/require-permission/RequirePermission';
import Login from './pages/login/Login';
import { PERMISSION_CODE } from './constants/access-control';
import {
  DataPlatformDashboard,
  DataPlatformDataItems,
  DataPlatformSystemConfig,
  InviteCode,
  MenuManagement,
  Register,
  UserPermission,
  UserProfile,
  UserRegister,
} from './router/lazy-pages';

// 懒加载页面统一 fallback
const LazyFallback = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
    <Spin size="large" />
  </div>
);

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

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/register',
    element: withSuspense(<Register />),
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
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
