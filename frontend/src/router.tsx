import { Suspense, useEffect } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import Layout from './components/Layout';
import RequireAuth from './components/require-auth/RequireAuth';
import Login from './pages/login/Login';
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
import { useUserStore } from './store/user-store';

// 懒加载页面统一 fallback
const LazyFallback = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
    <Spin size="large" />
  </div>
);

function withSuspense(element: React.ReactElement): React.ReactElement {
  return <Suspense fallback={LazyFallback}>{element}</Suspense>;
}

/**
 * 应用初始化组件：在路由渲染前触发登录态恢复。
 *
 * 页面刷新时 store 状态丢失，但 localStorage 中的 token 仍在。
 * 此组件在应用挂载时调用 restoreAuth，避免每个 RequireAuth 重复触发。
 */
function AppInitializer({ children }: { children: React.ReactElement }): React.ReactElement {
  const restoreAuth = useUserStore((state) => state.restoreAuth);

  useEffect(() => {
    void restoreAuth();
  }, [restoreAuth]);

  return children;
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
        element: withSuspense(<DataPlatformDashboard />),
      },
      {
        path: 'data-platform/data-items',
        element: withSuspense(<DataPlatformDataItems />),
      },
      {
        path: 'data-platform/system-config',
        element: withSuspense(<DataPlatformSystemConfig />),
      },
      // 系统设置-用户：四个三级菜单对应路由
      {
        path: 'system/user/profile',
        element: withSuspense(<UserProfile />),
      },
      {
        path: 'system/user/register',
        element: withSuspense(<UserRegister />),
      },
      {
        path: 'system/user/permission',
        element: withSuspense(<UserPermission />),
      },
      {
        path: 'system/user/invite-code',
        element: withSuspense(<InviteCode />),
      },
      // 系统设置-系统-菜单管理
      {
        path: 'system/menu',
        element: withSuspense(<MenuManagement />),
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
