export interface UserManageQueryParams {
  keyword: string;
  status: 'all' | 'enabled' | 'disabled';
  pageNumber: number;
  pageSize: number;
}

export interface UserManageItem {
  id: string;
  username: string;
  roleName: string;
  status: 'enabled' | 'disabled';
  updatedAt: string;
}

export interface UserManageListResponse {
  list: UserManageItem[];
  total: number;
}

export interface UserManageSearchValues {
  keyword: string;
  status: 'all' | 'enabled' | 'disabled';
}
