import backendAuthRequest from '@/utils/backend-auth-request';

/** 菜单项（扁平结构，含 parent_id 用于前端构建树） */
export interface MenuItem {
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
}

export interface CreateMenuPayload {
  parent_id: number;
  menu_type: number;
  title: string;
  path?: string;
  component?: string;
  icon?: string;
  permission?: string;
  sort?: number;
  visible?: boolean;
}

export interface UpdateMenuPayload {
  parent_id?: number;
  menu_type?: number;
  title?: string;
  path?: string;
  component?: string;
  icon?: string;
  permission?: string;
  sort?: number;
  visible?: boolean;
}

/** 列出所有菜单（扁平列表） */
export function fetchMenus(): Promise<MenuItem[]> {
  return backendAuthRequest.get<MenuItem[]>('/menus');
}

/** 创建菜单 */
export function createMenu(payload: CreateMenuPayload): Promise<MenuItem> {
  return backendAuthRequest.post<MenuItem>('/menus', payload);
}

/** 更新菜单（字段未传则不修改） */
export function updateMenu(menuId: number, payload: UpdateMenuPayload): Promise<MenuItem> {
  return backendAuthRequest.put<MenuItem>(`/menus/${menuId}`, payload);
}

/** 删除菜单（软删除） */
export function deleteMenu(menuId: number): Promise<{ menu_id: number; deleted: boolean }> {
  return backendAuthRequest.delete(`/menus/${menuId}`);
}
