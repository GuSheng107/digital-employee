import { create } from 'zustand';
import me from '@/assets/images/avatar/me.svg';

interface UserState {
  username: string;
  avatar: string;
  permission: string;

  setUserInfo: (info: { username: string; avatar: string; permission: string }) => void;
  clearUserInfo: () => void;
}

export const useUserStore = create<UserState>((set) => ({
  username: '管理员-小张',
  avatar: me,
  permission: 'admin',

  setUserInfo: (info) => set({
    username: info.username,
    avatar: info.avatar,
    permission: info.permission,
  }),

  clearUserInfo: () => set({
    username: '',
    avatar: '',
    permission: '',
  }),
}));
