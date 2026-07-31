import type { ReactNode } from 'react';
import { Navigate, useSearchParams } from 'react-router';
import { PageLoading } from '@/components/page-loading/PageLoading';
import { useUserStore } from '@/store/user-store';
import { getSafeRedirectPath } from '@/utils/auth-session';

interface RequireGuestProps {
  children: ReactNode;
}

/**
 * 访客页守卫：已登录用户访问 /login、/register 时跳回站内安全路径。
 * 登录态恢复由外层 AppInitializer 处理。
 */
export default function RequireGuest({
  children,
}: RequireGuestProps): React.ReactElement {
  const [searchParams] = useSearchParams();
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const restoring = useUserStore((state) => state.restoring);

  if (restoring && !isAuthenticated) {
    return <PageLoading fullScreen label="正在恢复登录状态" />;
  }

  if (isAuthenticated) {
    return (
      <Navigate
        to={getSafeRedirectPath(searchParams.get('redirect'))}
        replace
      />
    );
  }

  return <>{children}</>;
}
