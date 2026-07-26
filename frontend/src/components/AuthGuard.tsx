import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useUserStore } from '@/store/user';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const authChecked = useUserStore((s) => s.authChecked);
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const initializeSession = useUserStore((s) => s.initializeSession);

  useEffect(() => {
    initializeSession();
  }, [initializeSession]);

  if (!authChecked) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: '#f5f7fa',
      }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export function GuestGuard({ children }: { children: React.ReactNode }) {
  const authChecked = useUserStore((s) => s.authChecked);
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const initializeSession = useUserStore((s) => s.initializeSession);

  useEffect(() => {
    initializeSession();
  }, [initializeSession]);

  if (!authChecked) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
      }}>
        <Spin size="large" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
