import { useEffect } from 'react';
import { useUserStore } from '@/store/user-store';

interface AppInitializerProps {
  children: React.ReactElement;
}

/**
 * 在受保护路由渲染前恢复本地登录态。
 *
 * 页面刷新会清空内存 store，但 token 仍可能保存在 localStorage 中；
 * 统一在应用入口恢复，避免每个路由守卫各自发起重复请求。
 */
export default function AppInitializer({
  children,
}: AppInitializerProps): React.ReactElement {
  const restoreAuth = useUserStore((state) => state.restoreAuth);

  useEffect(() => {
    void restoreAuth();
  }, [restoreAuth]);

  return children;
}
