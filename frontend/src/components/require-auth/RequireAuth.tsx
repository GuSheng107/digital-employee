import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useUserStore } from '@/store/user-store';

interface RequireAuthProps {
  children: ReactNode;
}

/**
 * 路由守卫：未登录时重定向到 /login，保留原路径用于登录后回跳。
 *
 * 登录态恢复由 AppInitializer 统一处理，本组件只负责检查 isAuthenticated。
 * 恢复过程中（loading=true）显示全屏加载动画。
 */
export default function RequireAuth({ children }: RequireAuthProps): React.ReactElement {
  const location = useLocation();
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const loading = useUserStore((state) => state.loading);

  // 正在恢复登录态时显示加载动画
  if (loading && !isAuthenticated) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          background: '#0a0e1a',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (!isAuthenticated) {
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }

  return <>{children}</>;
}
