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

/** 菜单节点（后端返回的菜单树节点） */
export interface MenuNode {
  id: number;
  parent_id: number;
  /** 1=目录 2=菜单 3=按钮 */
  menu_type: number;
  title: string;
  path: string | null;
  component: string | null;
  icon: string | null;
  permission: string | null;
  sort: number;
  visible: boolean;
  children: MenuNode[];
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
  vip_level_display: string;
  status: number;
  roles: string[];
  permissions: string[];
  /** 用户可见的菜单树（已按 sort 排序、按 parent_id 组织为树形） */
  menus: MenuNode[];
}

/** 登出请求参数 */
export interface LogoutPayload {
  refresh_token?: string;
}

/** 注册请求参数 */
export interface RegisterRequest {
  username: string;
  password: string;
  invite_code: string;
}

/**
 * 用户名密码登录，返回双 token。
 * POST /auth/login
 */
export function login(payload: LoginPayload): Promise<TokenPair> {
  return backendAuthRequest.post<TokenPair>('/auth/login', payload);
}

/**
 * 用户注册，成功后返回双 token（与登录一致，前端自动登录）。
 * POST /auth/register
 */
export function register(payload: RegisterRequest): Promise<TokenPair> {
  return backendAuthRequest.post<TokenPair>('/auth/register', payload);
}

/**
 * 用 refresh_token 换取新的双 token。
 * POST /auth/refresh
 */
export function refreshToken(refreshToken: string): Promise<TokenPair> {
  return backendAuthRequest.post<TokenPair>('/auth/refresh', {
    refresh_token: refreshToken,
  });
}

/**
 * 登出，撤销当前 token。
 * POST /auth/logout
 * access_token 从 Authorization 头读取，refresh_token 通过请求体传递。
 */
export function logout(refreshToken?: string): Promise<void> {
  return backendAuthRequest.post<void>('/auth/logout', {
    refresh_token: refreshToken,
  });
}

/**
 * 获取当前登录用户信息（含角色与权限码）。
 * GET /auth/me
 */
export function getCurrentUser(): Promise<UserInfo> {
  return backendAuthRequest.get<UserInfo>('/auth/me');
}
