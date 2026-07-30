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

// 路由级懒加载：注册页分离到独立 chunk，减小登录页首屏 JS 体积
export const Register = lazy(() => import('@/pages/register/Register'));

// 系统设置-用户 四个子页面，按菜单 path 注册路由
export const UserProfile = lazy(() => import('@/pages/system/user/profile/Profile'));
export const UserRegister = lazy(() => import('@/pages/system/user/register/UserRegister'));
export const UserPermission = lazy(() => import('@/pages/system/user/permission/UserPermission'));
export const InviteCode = lazy(() => import('@/pages/system/user/invite-code/InviteCode'));

// 系统设置-系统-菜单管理/日志查询/Bot管理
export const MenuManagement = lazy(() => import('@/pages/system/menu/MenuManagement'));
export const LogQuery = lazy(() => import('@/pages/system/log-query/LogQuery'));
export const BotManagement = lazy(() => import('@/pages/system/bot/BotManagement'));
