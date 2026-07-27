import { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import Layout from './components/Layout';
import PageA from './pages/PageA';
import PageB from './pages/PageB';
import {
  DataPlatformDashboard,
  DataPlatformDataItems,
  DataPlatformSystemConfig,
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

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
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
