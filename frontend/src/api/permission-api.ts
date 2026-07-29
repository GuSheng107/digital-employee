import backendAuthRequest from '@/utils/backend-auth-request';

export interface PermissionItem {
  id: number;
  code: string;
  name: string;
  description: string;
  module: string | null;
}

/** 获取服务端定义的规范权限码目录。 */
export function fetchPermissions(): Promise<PermissionItem[]> {
  return backendAuthRequest.get<PermissionItem[]>('/permissions');
}
