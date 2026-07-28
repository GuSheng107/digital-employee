import backendAuthRequest from '@/utils/backend-auth-request';

/** 登录请求参数 */
export interface LoginPayload {
  username: string;
  password: string;
}

/** 双 token 响应数据 */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  access_expires_in: number;
  refresh_expires_in: number;
  token_type: string;
  user_id: number;
}

/** 当前登录用户信息 */
export interface UserInfo {
  id: number;
  username: string;
  nickname: string | null;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
  is_vip: boolean;
  vip_level: number;
  status: number;
  roles: string[];
  permissions: string[];
}

/** 登出请求参数 */
export interface LogoutPayload {
  refresh_token?: string;
}

/**
 * 用户名密码登录，返回双 token。
 * POST /api/v1/auth/login
 */
export function login(payload: LoginPayload): Promise<TokenPair> {
  return backendAuthRequest.post<TokenPair>('/api/v1/auth/login', payload);
}

/**
 * 用 refresh_token 换取新的双 token。
 * POST /api/v1/auth/refresh
 */
export function refreshToken(refreshToken: string): Promise<TokenPair> {
  return backendAuthRequest.post<TokenPair>('/api/v1/auth/refresh', {
    refresh_token: refreshToken,
  });
}

/**
 * 登出，撤销当前 token。
 * POST /api/v1/auth/logout
 * access_token 从 Authorization 头读取，refresh_token 通过请求体传递。
 */
export function logout(refreshToken?: string): Promise<void> {
  return backendAuthRequest.post<void>('/api/v1/auth/logout', {
    refresh_token: refreshToken,
  });
}

/**
 * 获取当前登录用户信息（含角色与权限码）。
 * GET /api/v1/auth/me
 */
export function getCurrentUser(): Promise<UserInfo> {
  return backendAuthRequest.get<UserInfo>('/api/v1/auth/me');
}
