import { lazy } from 'react';

// 路由级懒加载：数据中台三个页面分离到独立 chunk，减小首屏 JS 体积
// 独立文件以避免 router.tsx 同时 export 组件与非组件触发 react-refresh 警告
export const DataPlatformDashboard = lazy(
  () => import('@/pages/data-platform-dashboard/DataPlatformDashboard'),
);
export const DataPlatformDataItems = lazy(
  () => import('@/pages/data-platform-data-items/DataPlatformDataItems'),
);
export const DataPlatformSystemConfig = lazy(
  () => import('@/pages/data-platform-system-config/DataPlatformSystemConfig'),
);
