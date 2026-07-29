import { create } from 'zustand';

interface SystemNavigationState {
  visitedPaths: string[];
  visitPath: (path: string) => void;
  closePath: (path: string) => void;
  clearVisitedPaths: () => void;
}

/** 系统设置访问页签状态；仅记录本次登录期间实际访问过的页面。 */
export const useSystemNavigationStore = create<SystemNavigationState>((set) => ({
  visitedPaths: [],
  visitPath: (path) => set((state) => (
    state.visitedPaths.includes(path)
      ? state
      : { visitedPaths: [...state.visitedPaths, path] }
  )),
  closePath: (path) => set((state) => ({
    visitedPaths: state.visitedPaths.filter((visitedPath) => (
      visitedPath !== path
    )),
  })),
  clearVisitedPaths: () => set({ visitedPaths: [] }),
}));
