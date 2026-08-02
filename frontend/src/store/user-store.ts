import { create } from 'zustand';
import me from '@/assets/images/avatar/me.svg';
import { resolveAvatarUrl } from '@/utils/avatar-url';
import {
  getCurrentUser,
  login,
  logout as logoutApi,
  register as registerApi,
  type MenuNode,
  type LoginPayload,
  type RegisterRequest,
  type TokenPair,
  type UserInfo,
} from '@/api/auth-api';
import {
  appendTraceId,
  getRequestErrorMessage,
  HttpError,
  isServiceUnavailableError,
} from '@/utils/request';

/** 认证服务暂时不可用时的统一基础文案（不含 traceId）。
 *
 * 实际展示时通过 appendTraceId 追加 traceId。组件判别场景请使用
 * profileErrorKind 而非字符串匹配，避免文案调整或追加 traceId 后分支失效。 */
export const AUTH_SERVICE_UNAVAILABLE_MESSAGE = '认证服务暂时不可用，请稍后重试';

/** 用户资料加载失败的错误种类，供 UI 按结构化标记分支展示。 */
export type ProfileErrorKind = 'service-unavailable' | 'business';

interface AuthState {
  /** 是否已登录 */
  isAuthenticated: boolean;
  /** 当前用户信息（登录后填充） */
  userInfo: UserInfo | null;
  /** 头像（默认头像或用户自定义头像） */
  avatar: string;
  /** 加载态（登录/获取用户信息时） */
  loading: boolean;
  /** 登录后异步加载用户资料、菜单和权限。 */
  profileLoading: boolean;
  /** 用户资料异步加载失败时的可恢复错误。 */
  profileError: string | null;
  /** 用户资料加载失败的错误种类，供 UI 按结构化标记分支展示（替代字符串匹配）。 */
  profileErrorKind: ProfileErrorKind | null;
  /** 登录态恢复中（页面刷新时 restoreAuth 执行期间为 true，完成后置 false） */
  restoring: boolean;
  /** 当前用户可见的菜单树；空数组表示尚未加载或未授权。 */
  menus: MenuNode[];

  /** 用户名密码登录，成功后立即返回 token，并异步加载用户信息。 */
  login: (payload: LoginPayload) => Promise<TokenPair>;
  /** 用户注册，成功后存储双 token 并拉取用户信息（自动登录） */
  register: (payload: RegisterRequest) => Promise<void>;
  /** 登出，撤销 token 并清除登录态 */
  logout: () => Promise<void>;
  /** 从 access_token 恢复登录态（页面刷新时调用） */
  restoreAuth: () => Promise<void>;
  /** 清除登录态（不调登出接口，用于 token 失效时的被动清理） */
  clearAuth: () => void;
  /** 重新拉取当前用户信息（含菜单树），用于菜单/权限变更后清除前端缓存 */
  reloadMenus: () => Promise<void>;
  /** 登录成功后异步加载用户资料、菜单和权限。 */
  hydrateCurrentUser: () => Promise<void>;
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

/** 读取用户头像；私有 MinIO 历史地址统一转换为 backend-data 公开代理。 */
function getUserAvatar(info: UserInfo): string {
  return resolveAvatarUrl(info.avatar_url) ?? me;
}

let currentUserRequest: Promise<UserInfo> | null = null;

/** 合并并发的 /auth/me 请求，避免初始化与菜单刷新重复加载同一上下文。 */
function fetchCurrentUserOnce(): Promise<UserInfo> {
  if (currentUserRequest) {
    return currentUserRequest;
  }
  currentUserRequest = getCurrentUser().finally(() => {
    currentUserRequest = null;
  });
  return currentUserRequest;
}

function isAuthenticationFailure(error: unknown): boolean {
  return (
    !localStorage.getItem('access_token')
    || (error instanceof HttpError && error.status === 401)
  );
}

export const useUserStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  userInfo: null,
  avatar: me,
  loading: false,
  profileLoading: false,
  profileError: null,
  profileErrorKind: null,
  // 初始 true：AppInitializer 的 restoreAuth 完成前，RequireAuth 显示加载动画而非立即跳转登录页
  restoring: true,
  menus: [],

  login: async (payload: LoginPayload) => {
    set({ loading: true });
    try {
      const tokenPair = await login(payload);
      persistAccessToken(tokenPair.access_token);
      persistRefreshToken(tokenPair.refresh_token);
      set({
        isAuthenticated: true,
        loading: false,
        restoring: false,
        profileError: null,
        profileErrorKind: null,
      });
      void useUserStore.getState().hydrateCurrentUser();
      return tokenPair;
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  register: async (payload: RegisterRequest) => {
    set({ loading: true });
    try {
      const tokenPair = await registerApi(payload);
      persistAccessToken(tokenPair.access_token);
      persistRefreshToken(tokenPair.refresh_token);

      // 注册成功后自动登录：拉取用户信息
      const info = await fetchCurrentUserOnce();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: getUserAvatar(info),
        menus: info.menus ?? [],
        loading: false,
        profileLoading: false,
        profileError: null,
        profileErrorKind: null,
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
        profileLoading: false,
        profileError: null,
        profileErrorKind: null,
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
    set({
      isAuthenticated: true,
      restoring: false,
      profileLoading: true,
      profileError: null,
      profileErrorKind: null,
    });
    try {
      const info = await fetchCurrentUserOnce();
      set({
        isAuthenticated: true,
        userInfo: info,
        avatar: getUserAvatar(info),
        menus: info.menus ?? [],
        restoring: false,
        profileLoading: false,
        profileError: null,
        profileErrorKind: null,
      });
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        clearStoredTokens();
        set({
          restoring: false,
          isAuthenticated: false,
          userInfo: null,
          avatar: me,
          menus: [],
          profileLoading: false,
          profileError: null,
          profileErrorKind: null,
        });
        return;
      }
      // 服务不可用（连接被拒绝/超时/5xx 网关错误）：保留登录态，提示重试，
      // 避免后端短暂不可用时把已登录用户踢回登录页。
      const serviceDown = isServiceUnavailableError(error);
      const traceId = error instanceof HttpError ? error.traceId : undefined;
      set({
        restoring: false,
        isAuthenticated: true,
        profileLoading: false,
        profileErrorKind: serviceDown ? 'service-unavailable' : 'business',
        profileError: serviceDown
          ? appendTraceId(AUTH_SERVICE_UNAVAILABLE_MESSAGE, traceId)
          : getRequestErrorMessage(error, '用户信息加载失败，请稍后重试'),
      });
    }
  },

  clearAuth: () => {
    clearStoredTokens();
    set({
      isAuthenticated: false,
      userInfo: null,
      avatar: me,
      menus: [],
      profileLoading: false,
      profileError: null,
      profileErrorKind: null,
    });
  },

  reloadMenus: async () => {
    // 菜单/权限变更后，重新拉取 /auth/me 刷新本地缓存的菜单树与权限码
    set({ profileLoading: true, profileError: null, profileErrorKind: null });
    try {
      const info = await fetchCurrentUserOnce();
      set({
        userInfo: info,
        avatar: getUserAvatar(info),
        menus: info.menus ?? [],
        profileLoading: false,
        profileError: null,
        profileErrorKind: null,
      });
    } catch (error) {
      set({ profileLoading: false });
      throw error;
    }
  },

  hydrateCurrentUser: async () => {
    const currentState = useUserStore.getState();
    if (currentState.profileLoading || currentState.userInfo) {
      return;
    }
    set({ profileLoading: true, profileError: null, profileErrorKind: null });
    try {
      const info = await fetchCurrentUserOnce();
      set({
        userInfo: info,
        avatar: getUserAvatar(info),
        menus: info.menus ?? [],
        profileLoading: false,
        profileError: null,
        profileErrorKind: null,
      });
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        clearStoredTokens();
        set({
          isAuthenticated: false,
          userInfo: null,
          avatar: me,
          menus: [],
          profileLoading: false,
          profileError: null,
          profileErrorKind: null,
        });
        return;
      }
      const serviceDown = isServiceUnavailableError(error);
      const traceId = error instanceof HttpError ? error.traceId : undefined;
      set({
        profileLoading: false,
        profileErrorKind: serviceDown ? 'service-unavailable' : 'business',
        profileError: serviceDown
          ? appendTraceId(AUTH_SERVICE_UNAVAILABLE_MESSAGE, traceId)
          : getRequestErrorMessage(error, '用户信息加载失败，请稍后重试'),
      });
    }
  },
}));

/** 获取用户友好的登录错误提示文案 */
export function getLoginErrorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    // 后端登录失败文案本身不区分“账号不存在”和“密码错误”，既避免
    // 账号枚举，也可以安全展示统一错误码，便于用户和运维定位。
    return getRequestErrorMessage(error, '账号或密码有误');
  }
  return '账号或密码有误';
}

/** 获取用户友好的注册错误提示文案 */
export function getRegisterErrorMessage(error: unknown): string {
  if (error instanceof HttpError) {
    if (error.status === 429) {
      return getRequestErrorMessage(error, '请求过于频繁，请稍后再试');
    }
  }
  return getRequestErrorMessage(error, '注册失败，请检查网络连接');
}
