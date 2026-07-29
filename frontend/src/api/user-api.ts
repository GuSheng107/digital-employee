import backendAuthRequest from '@/utils/backend-auth-request';

export interface UserListItem {
  id: number;
  username: string;
  nickname: string | null;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
  status: number;
  is_vip: boolean;
  vip_level: number | null;
  vip_level_display: string;
  vip_expires_at: string | null;
  roles: string[];
  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserListResponse {
  total: number;
  page: number;
  page_size: number;
  items: UserListItem[];
}

export interface CreateUserPayload {
  username: string;
  password: string;
  nickname?: string;
  email?: string;
  phone?: string;
  role_codes: string[];
  is_vip: boolean;
  vip_level?: number;
  vip_expires_at?: string;
}

export interface UpdateProfilePayload {
  nickname?: string;
  email?: string;
  phone?: string;
  /** 修改密码时传入，不传或为空表示不修改 */
  password?: string;
}

export function fetchUsers(page: number, pageSize: number): Promise<UserListResponse> {
  return backendAuthRequest.get<UserListResponse>('/users', { params: { page, page_size: pageSize } });
}

export function createUser(payload: CreateUserPayload): Promise<{ id: number; username: string }> {
  return backendAuthRequest.post('/users', payload);
}

export function assignUserRoles(userId: number, roleCodes: string[]): Promise<{ user_id: number; roles: string[] }> {
  return backendAuthRequest.put(`/users/${userId}/roles`, { role_codes: roleCodes });
}

/** 管理员重置指定用户密码（覆盖式，不校验旧密码） */
export function resetUserPassword(userId: number, newPassword: string): Promise<{ user_id: number; username: string }> {
  return backendAuthRequest.put(`/users/${userId}/password`, { new_password: newPassword });
}

export interface VipLevelOption {
  value: number;
  label: string;
}

export interface UpdateVipPayload {
  is_vip: boolean;
  vip_level?: number;
  vip_expires_at?: string;
}

export function fetchVipLevels(): Promise<VipLevelOption[]> {
  return backendAuthRequest.get<VipLevelOption[]>('/users/vip-levels');
}

export function updateUserVip(
  userId: number,
  payload: UpdateVipPayload,
): Promise<{
  user_id: number;
  is_vip: boolean;
  vip_level: number;
  vip_level_display: string;
  vip_expires_at: string | null;
}> {
  return backendAuthRequest.put(`/users/${userId}/vip`, payload);
}

export function updateUserStatus(
  userId: number,
  status: number,
): Promise<{ user_id: number; status: number }> {
  return backendAuthRequest.put(`/users/${userId}/status`, { status });
}

export function deleteUser(
  userId: number,
): Promise<{ user_id: number; deleted: boolean }> {
  return backendAuthRequest.delete(`/users/${userId}`);
}

/** 用户独立菜单项（与角色菜单解耦） */
export interface UserMenuItem {
  id: number;
  parent_id: number;
  menu_type: number;
  title: string;
  path: string | null;
  icon: string | null;
  permission: string | null;
  sort: number;
  visible: boolean;
}

/** 获取用户独立菜单列表 */
export function fetchUserMenus(userId: number): Promise<UserMenuItem[]> {
  return backendAuthRequest.get<UserMenuItem[]>(`/users/${userId}/menus`);
}

/** 分配用户独立菜单（覆盖式） */
export function assignUserMenus(userId: number, menuIds: number[]): Promise<{ user_id: number; menu_ids: number[] }> {
  return backendAuthRequest.put(`/users/${userId}/menus`, { menu_ids: menuIds });
}

/** 用户独立权限项 */
export interface UserPermissionItem {
  id: number;
  code: string;
  name: string;
  description: string;
  module: string | null;
}

/** 获取用户独立权限列表 */
export function fetchUserPermissions(userId: number): Promise<UserPermissionItem[]> {
  return backendAuthRequest.get<UserPermissionItem[]>(`/users/${userId}/permissions`);
}

/** 分配用户独立权限（覆盖式） */
export function assignUserPermissions(userId: number, permissionIds: number[]): Promise<{ user_id: number; permission_ids: number[] }> {
  return backendAuthRequest.put(`/users/${userId}/permissions`, { permission_ids: permissionIds });
}

export function updateProfile(payload: UpdateProfilePayload): Promise<{ id: number; username: string; nickname: string | null; email: string | null; phone: string | null; avatar_url: string | null; must_change_password: boolean }> {
  return backendAuthRequest.put('/users/me', payload);
}

export function uploadAvatar(file: File | Blob): Promise<{ avatar_url: string }> {
  const formData = new FormData();
  formData.append('file', file);
  // 关键：删除默认的 Content-Type: application/json，让浏览器自动设置
  // multipart/form-data; boundary=... 否则后端无法解析 multipart body
  return backendAuthRequest.post('/users/avatar', formData, {
    headers: { 'Content-Type': null },
  });
}
