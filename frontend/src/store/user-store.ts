import { create } from 'zustand';
import me from '@/assets/images/avatar/me.svg';
import { getCurrentUser, login, logout as logoutApi, type UserInfo } from '@/api/auth-api';
import { getRequestErrorMessage, HttpError } from '@/utils/request';

interface AuthState {
  /** 是否已登录 */
  isAuthenticated: boolean;
  /** 当前用户信息（登录后填充） */
  userInfo: UserInfo | null;
  /** 头像（默认头像或用户自定义头像） */
  avatar: string;
  /** 加载态（登录/获取用户信息时） */
  loading: boolean;

  /** 用户名密码登录，成功后存储双 token 并拉取用户信息 */
  login: (username: string, password: string) => Promise<void>;
  /** 登出，撤销 token 并清除登录态 */
  logout: () => Promise<void>;
  /** 从 access_token 恢复登录态（页面刷新时调用） */
  restoreAuth: () => Promise<void>;
  /** 清除登录态（不调登出接口，用于 token 失效时的被动清理） */
  clearAuth: () => void;
}

/** 存储 access_token 到 localStorage */
function persistAccessToken(token: string): void {
  localStorage.setItem('access_token', token);
}

/** 存储 refresh_token 到 localStorage */
function persistRefreshToken(token: string): void {
  localStorage.setItem('refresh_token', token);
}

/** 清除 localStorage 中的双 token */
function clearStoredTokens(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

export const useUserStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  userInfo: null,
  avatar: me,
  loading: false,

  login: async (username: string, password: string) => {
    set({ loading: true });
    try {
      const tokenPair = await login({ username, password });
      persistAccessToken(tokenPair.access_token);
      persistRefreshToken(tokenPair.refresh_token);

      // 登录成功后拉取用户信息
      const info = await getCurrentUser();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: info.avatar_url || me,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  logout: async () => {
    const refreshToken = localStorage.getItem('refresh_token');
    try {
      await logoutApi(refreshToken ?? undefined);
    } catch {
      // 即使登出接口失败也清除本地登录态，避免卡在已登录状态
    } finally {
      clearStoredTokens();
      set({
        isAuthenticated: false,
        userInfo: null,
        avatar: me,
      });
    }
  },

  restoreAuth: async () => {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      return;
    }
    set({ loading: true });
    try {
      const info = await getCurrentUser();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: info.avatar_url || me,
        loading: false,
      });
    } catch (error) {
      // access_token 已失效，尝试用 refresh_token 恢复
      if (error instanceof HttpError && error.status === 401) {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          try {
            const { refreshToken: refreshFn } = await import('@/api/auth-api');
            const newTokenPair = await refreshFn(refreshToken);
            persistAccessToken(newTokenPair.access_token);
            persistRefreshToken(newTokenPair.refresh_token);
            const info = await getCurrentUser();
            set({
              isAuthenticated: true,
              userInfo: info,
              avatar: info.avatar_url || me,
              loading: false,
            });
            return;
          } catch {
            // refresh 也失败，清除登录态
          }
        }
      }
      clearStoredTokens();
      set({ loading: false, isAuthenticated: false, userInfo: null, avatar: me });
    }
  },

  clearAuth: () => {
    clearStoredTokens();
    set({
      isAuthenticated: false,
      userInfo: null,
      avatar: me,
    });
  },
}));

/** 获取用户友好的登录错误提示文案 */
export function getLoginErrorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    // 优先使用后端返回的 message
    if (error.message) {
      return error.message;
    }
    if (error.status === 429) {
      return '请求过于频繁，请稍后再试';
    }
  }
  return getRequestErrorMessage(error, '登录失败，请检查网络连接');
}
