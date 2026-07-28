import { Suspense, useEffect } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import Layout from './components/Layout';
import RequireAuth from './components/require-auth/RequireAuth';
import Login from './pages/login/Login';
import PageA from './pages/PageA';
import PageB from './pages/PageB';
import {
  DataPlatformDashboard,
  DataPlatformDataItems,
  DataPlatformSystemConfig,
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
    path: '/',
    element: (
      <AppInitializer>
        <RequireAuth>
          <Layout />
        </RequireAuth>
      </AppInitializer>
    ),
    children: [
      {
        index: true,
        element: <PageA />,
      },
      {
        path: 'page-b',
        element: <PageB />,
      },
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
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
