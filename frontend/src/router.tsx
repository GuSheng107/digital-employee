import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import PageA from './pages/PageA';
import PageB from './pages/PageB';

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
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
