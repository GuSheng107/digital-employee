import { create } from 'zustand';
import me from '@/assets/images/avatar/me.svg';
import { clearAuthSession, getAccessToken, saveTokenPair, type TokenPairPayload } from '@/utils/authSession';
import { getCurrentSession, logoutConsole, type SessionUser } from '@/api/auth';

interface UserState {
  username: string;
  displayName: string;
  avatar: string;
  permission: string;
  userType: string;
  authChecked: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isGuest: boolean;

  setUserInfo: (info: { username: string; avatar?: string; permission?: string; userType?: string }) => void;
  setLoginSession: (payload: TokenPairPayload & {
    user?: SessionUser | null;
    user_type?: string;
  }) => void;
  initializeSession: () => Promise<void>;
  clearUserInfo: () => void;
  logout: () => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  username: '',
  displayName: '',
  avatar: me,
  permission: '',
  userType: '',
  authChecked: false,
  isAuthenticated: false,
  isAdmin: false,
  isGuest: false,

  setUserInfo: (info) => set({
    username: info.username,
    displayName: info.username,
    avatar: info.avatar || me,
    permission: info.permission || '',
    userType: info.userType || 'registered',
    isAuthenticated: true,
    isAdmin: info.permission === 'admin',
    isGuest: info.permission === 'guest' || info.userType === 'guest',
  }),

  setLoginSession: (payload) => {
    saveTokenPair(payload);
    const user = payload.user;
    const role = user?.role || '';
    const userType = user?.user_type || payload.user_type || 'registered';
    set({
      username: user?.display_name || user?.username || '',
      displayName: user?.display_name || user?.username || '',
      avatar: me,
      permission: role,
      userType,
      isAuthenticated: true,
      authChecked: true,
      isAdmin: role === 'admin',
      isGuest: role === 'guest' || userType === 'guest',
    });
  },

  initializeSession: async () => {
    const { authChecked } = get();
    if (authChecked) return;

    const token = getAccessToken();
    if (!token) {
      set({ authChecked: true });
      return;
    }

    try {
      const response = await getCurrentSession();
      const user = response.user;
      if (user) {
        const role = user.role || '';
        const userType = user.user_type || '';
        set({
          username: user.display_name || user.username || '',
          displayName: user.display_name || user.username || '',
          avatar: me,
          permission: role,
          userType,
          isAuthenticated: true,
          authChecked: true,
          isAdmin: role === 'admin',
          isGuest: role === 'guest' || userType === 'guest',
        });
        return;
      }
    } catch {
      // Server session invalid — clear local state
    }

    clearAuthSession();
    set({
      username: '',
      displayName: '',
      permission: '',
      userType: '',
      isAuthenticated: false,
      authChecked: true,
      isAdmin: false,
      isGuest: false,
    });
  },

  clearUserInfo: () => {
    clearAuthSession();
    set({
      username: '',
      displayName: '',
      avatar: '',
      permission: '',
      userType: '',
      isAuthenticated: false,
      isAdmin: false,
      isGuest: false,
    });
  },

  logout: async () => {
    const { isAuthenticated } = get();
    if (!isAuthenticated) return;

    try {
      await logoutConsole();
    } catch {
      // Client-side session removal is authoritative
    }

    clearAuthSession();
    set({
      username: '',
      displayName: '',
      permission: '',
      userType: '',
      isAuthenticated: false,
      authChecked: true,
      isAdmin: false,
      isGuest: false,
    });
  },
}));
