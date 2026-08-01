import { create } from 'zustand';
import {
  DEFAULT_USER_MANAGE_PAGE_NUMBER,
  DEFAULT_USER_MANAGE_PAGE_SIZE,
} from '../constants/user-manage-constants';

interface UserManageStore {
  keyword: string;
  status: 'all' | 'enabled' | 'disabled';
  pageNumber: number;
  pageSize: number;
  selectedRowKeys: string[];
  setKeyword: (keyword: string) => void;
  setStatus: (status: 'all' | 'enabled' | 'disabled') => void;
  setPagination: (pageNumber: number, pageSize: number) => void;
  setSelectedRowKeys: (selectedRowKeys: string[]) => void;
  resetFilters: () => void;
}

export const useUserManageStore = create<UserManageStore>((set) => ({
  keyword: '',
  status: 'all',
  pageNumber: DEFAULT_USER_MANAGE_PAGE_NUMBER,
  pageSize: DEFAULT_USER_MANAGE_PAGE_SIZE,
  selectedRowKeys: [],
  setKeyword: (keyword): void => set({ keyword }),
  setStatus: (status): void => set({ status }),
  setPagination: (pageNumber, pageSize): void => set({ pageNumber, pageSize }),
  setSelectedRowKeys: (selectedRowKeys): void => set({ selectedRowKeys }),
  resetFilters: (): void => set({
    keyword: '',
    status: 'all',
    pageNumber: DEFAULT_USER_MANAGE_PAGE_NUMBER,
    pageSize: DEFAULT_USER_MANAGE_PAGE_SIZE,
    selectedRowKeys: [],
  }),
}));
