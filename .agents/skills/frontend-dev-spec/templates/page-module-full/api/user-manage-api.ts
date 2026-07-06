import request from '@/utils/request';
import type { UserManageListResponse, UserManageQueryParams } from '../types/user-manage';

export function getUserManageList(params: UserManageQueryParams): Promise<UserManageListResponse> {
  return request.get('/user-manage/list', { params });
}
