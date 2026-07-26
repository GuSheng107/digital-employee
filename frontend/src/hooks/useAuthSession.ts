import { useEffect } from 'react';
import { useUserStore } from '@/store/user';

/**
 * Initializes the auth session on app mount.
 * Call once in the root component.
 */
export function useAuthSession() {
  const authChecked = useUserStore((s) => s.authChecked);
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const isAdmin = useUserStore((s) => s.isAdmin);
  const isGuest = useUserStore((s) => s.isGuest);
  const username = useUserStore((s) => s.username);
  const displayName = useUserStore((s) => s.displayName);
  const permission = useUserStore((s) => s.permission);
  const userType = useUserStore((s) => s.userType);
  const initializeSession = useUserStore((s) => s.initializeSession);
  const logout = useUserStore((s) => s.logout);

  useEffect(() => {
    initializeSession();
  }, [initializeSession]);

  return {
    authChecked,
    isAuthenticated,
    isAdmin,
    isGuest,
    username,
    displayName,
    permission,
    userType,
    logout,
  };
}
