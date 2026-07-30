import backendAuthRequest from '@/utils/backend-auth-request';

export interface RoleItem {
  id: number;
  code: string;
  name: string;
  description: string;
  is_builtin: boolean;
  menu_ids: number[];
}

export interface CreateRolePayload {
  code: string;
  name: string;
  description?: string;
  menu_ids?: number[];
}

export interface UpdateRolePayload {
  name?: string;
  description?: string;
  menu_ids?: number[];
}

export function fetchRoles(): Promise<RoleItem[]> {
  return backendAuthRequest.get<RoleItem[]>('/roles');
}

export function createRole(payload: CreateRolePayload): Promise<RoleItem> {
  return backendAuthRequest.post<RoleItem>('/roles', payload);
}

export function updateRole(roleId: number, payload: UpdateRolePayload): Promise<RoleItem> {
  return backendAuthRequest.post<RoleItem>(`/roles/${roleId}`, payload);
}

export function deleteRole(roleId: number): Promise<{ role_id: number; deleted: boolean }> {
  return backendAuthRequest.delete(`/roles/${roleId}`);
}

export function fetchRoleMenus(roleId: number): Promise<unknown[]> {
  return backendAuthRequest.get(`/roles/${roleId}/menus`);
}

export function assignRoleMenus(roleId: number, menuIds: number[]): Promise<{ role_id: number; menu_ids: number[] }> {
  return backendAuthRequest.post(`/roles/${roleId}/menus`, { menu_ids: menuIds });
}
