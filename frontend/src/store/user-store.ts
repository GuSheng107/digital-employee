import { create } from 'zustand';
import me from '@/assets/images/avatar/me.svg';
import {
  getCurrentUser,
  login,
  logout as logoutApi,
  register as registerApi,
  refreshToken,
  type MenuNode,
  type UserInfo,
} from '@/api/auth-api';
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
  /** 登录态恢复中（页面刷新时 restoreAuth 执行期间为 true，完成后置 false） */
  restoring: boolean;
  /** 当前用户可见的菜单树（后端返回，登录后填充；空数组表示使用默认菜单） */
  menus: MenuNode[];

  /** 用户名密码登录，成功后存储双 token 并拉取用户信息 */
  login: (username: string, password: string) => Promise<void>;
  /** 用户注册，成功后存储双 token 并拉取用户信息（自动登录） */
  register: (username: string, password: string, inviteCode: string) => Promise<void>;
  /** 登出，撤销 token 并清除登录态 */
  logout: () => Promise<void>;
  /** 从 access_token 恢复登录态（页面刷新时调用） */
  restoreAuth: () => Promise<void>;
  /** 清除登录态（不调登出接口，用于 token 失效时的被动清理） */
  clearAuth: () => void;
  /** 重新拉取当前用户信息（含菜单树），用于菜单/权限变更后清除前端缓存 */
  reloadMenus: () => Promise<void>;
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
  // 初始 true：AppInitializer 的 restoreAuth 完成前，RequireAuth 显示加载动画而非立即跳转登录页
  restoring: true,
  menus: [],

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
        menus: info.menus ?? [],
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  register: async (username: string, password: string, inviteCode: string) => {
    set({ loading: true });
    try {
      const tokenPair = await registerApi({ username, password, invite_code: inviteCode });
      persistAccessToken(tokenPair.access_token);
      persistRefreshToken(tokenPair.refresh_token);

      // 注册成功后自动登录：拉取用户信息
      const info = await getCurrentUser();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: info.avatar_url || me,
        menus: info.menus ?? [],
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
        menus: [],
      });
    }
  },

  restoreAuth: async () => {
    // 已登录（如刚从登录页跳转过来），跳过重复请求
    if (useUserStore.getState().isAuthenticated) {
      set({ restoring: false });
      return;
    }
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      // 无 token：结束恢复，让 RequireAuth 走未登录分支
      set({ restoring: false });
      return;
    }
    try {
      const info = await getCurrentUser();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: info.avatar_url || me,
        menus: info.menus ?? [],
        restoring: false,
      });
    } catch (error) {
      // access_token 已失效，尝试用 refresh_token 恢复
      if (error instanceof HttpError && error.status === 401) {
        const storedRefreshToken = localStorage.getItem('refresh_token');
        if (storedRefreshToken) {
          try {
            const newTokenPair = await refreshToken(storedRefreshToken);
            persistAccessToken(newTokenPair.access_token);
            persistRefreshToken(newTokenPair.refresh_token);
            const info = await getCurrentUser();
            set({
              isAuthenticated: true,
              userInfo: info,
              avatar: info.avatar_url || me,
              menus: info.menus ?? [],
              restoring: false,
            });
            return;
          } catch {
            // refresh 也失败，清除登录态
          }
        }
      }
      clearStoredTokens();
      set({ restoring: false, isAuthenticated: false, userInfo: null, avatar: me, menus: [] });
    }
  },

  clearAuth: () => {
    clearStoredTokens();
    set({
      isAuthenticated: false,
      userInfo: null,
      avatar: me,
      menus: [],
    });
  },

  reloadMenus: async () => {
    // 菜单/权限变更后，重新拉取 /auth/me 刷新本地缓存的菜单树与权限码
    const info = await getCurrentUser();
    set({
      userInfo: info,
      avatar: info.avatar_url || me,
      menus: info.menus ?? [],
    });
  },
}));

/** 获取用户友好的登录错误提示文案 */
export function getLoginErrorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    // 限流单独提示
    if (error.status === 429) {
      return '请求过于频繁，请稍后再试';
    }
    // 其他所有登录错误（密码错误、用户不存在、网络异常、认证失败等）
    // 统一提示"账号或密码有误"，避免泄露用户是否存在，提升安全性
    return '账号或密码有误';
  }
  return '账号或密码有误';
}

/** 获取用户友好的注册错误提示文案 */
export function getRegisterErrorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    // 优先使用后端返回的 message
    if (error.message) {
      return error.message;
    }
    if (error.status === 429) {
      return '请求过于频繁，请稍后再试';
    }
  }
  return getRequestErrorMessage(error, '注册失败，请检查网络连接');
}
