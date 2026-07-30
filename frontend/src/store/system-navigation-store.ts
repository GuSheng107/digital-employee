import { create } from 'zustand';
import { MAX_SYSTEM_TAB_COUNT } from '@/constants/navigation';

interface SystemNavigationState {
  visitedPaths: string[];
  visitPath: (path: string) => void;
  closePath: (path: string) => void;
  closeOtherPaths: (path: string) => void;
  clearVisitedPaths: () => void;
}

/** 系统设置访问页签状态；仅记录本次登录期间实际访问过的页面。 */
export const useSystemNavigationStore = create<SystemNavigationState>((set) => ({
  visitedPaths: [],
  visitPath: (path) => set((state) => (
    state.visitedPaths.includes(path)
      ? state
      : {
        visitedPaths: [...state.visitedPaths, path].slice(
          -MAX_SYSTEM_TAB_COUNT,
        ),
      }
  )),
  closePath: (path) => set((state) => ({
    visitedPaths: state.visitedPaths.filter((visitedPath) => (
      visitedPath !== path
    )),
  })),
  closeOtherPaths: (path) => set({ visitedPaths: [path] }),
  clearVisitedPaths: () => set({ visitedPaths: [] }),
}));
