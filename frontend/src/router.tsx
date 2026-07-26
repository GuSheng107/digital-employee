import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import PageA from './pages/PageA';
import PageB from './pages/PageB';
import DataPlatformDashboard from './pages/data-platform-dashboard/DataPlatformDashboard';
import DataPlatformDataItems from './pages/data-platform-data-items/DataPlatformDataItems';
import DataPlatformSystemConfig from './pages/data-platform-system-config/DataPlatformSystemConfig';

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
        element: <DataPlatformDashboard />,
      },
      {
        path: 'data-platform/data-items',
        element: <DataPlatformDataItems />,
      },
      {
        path: 'data-platform/system-config',
        element: <DataPlatformSystemConfig />,
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
