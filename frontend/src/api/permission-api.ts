import backendAuthRequest from '@/utils/backend-auth-request';

export interface PermissionItem {
  id: number;
  code: string;
  name: string;
  description: string;
  module: string | null;
}

export interface CreatePermissionPayload {
  code: string;
  name: string;
  description?: string;
  module?: string;
}

/** 获取服务端定义的规范权限码目录。 */
export function fetchPermissions(): Promise<PermissionItem[]> {
  return backendAuthRequest.get<PermissionItem[]>('/permissions');
}

/** 动态创建权限码（仅用于菜单可见性与角色授权）。 */
export function createPermission(payload: CreatePermissionPayload): Promise<PermissionItem> {
  return backendAuthRequest.post<PermissionItem>('/permissions', payload);
}

/** 物理删除权限码（无角色/用户引用时）。 */
export function deletePermission(
  permissionId: number,
): Promise<{ permission_id: number; deleted: boolean }> {
  return backendAuthRequest.delete(`/permissions/${permissionId}`);
}
