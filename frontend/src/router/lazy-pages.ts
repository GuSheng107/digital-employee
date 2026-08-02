import { lazy } from 'react';

// 路由级懒加载：数据中台三个页面分离到独立 chunk，减小首屏 JS 体积
// 独立文件以避免 router.tsx 同时 export 组件与非组件触发 react-refresh 警告
export const DataPlatformDashboard = lazy(
  () => import('@/pages/data-platform/dashboard'),
);
export const DataPlatformDataItems = lazy(
  () => import('@/pages/data-platform/data-items'),
);
export const DataPlatformSystemConfig = lazy(
  () => import('@/pages/data-platform/system-config'),
);

// 路由级懒加载：注册页分离到独立 chunk，减小登录页首屏 JS 体积
export const Register = lazy(() => import('@/pages/register/Register'));

// 系统设置-用户 四个子页面，按菜单 path 注册路由
export const UserProfile = lazy(() => import('@/pages/system/user/profile/Profile'));
export const UserRegister = lazy(() => import('@/pages/system/user/register/UserRegister'));
export const UserPermission = lazy(() => import('@/pages/system/user/permission/UserPermission'));
export const InviteCode = lazy(() => import('@/pages/system/user/invite-code/InviteCode'));

// 系统设置-系统-菜单管理/日志查询
export const MenuManagement = lazy(() => import('@/pages/system/menu/MenuManagement'));
export const LogQuery = lazy(() => import('@/pages/system/log-query/LogQuery'));

// 数字员工-Bot管理
export const BotManagement = lazy(
  () => import('@/pages/digital-employee/bot/BotManagement'),
);

// 数字员工-Agent管理
export const AgentManagement = lazy(
  () => import('@/pages/digital-employee/agent/AgentManagement'),
);

// 动态路由兜底：将所有未匹配静态路由的路径交给 DynamicPage，
// 后者根据 /auth/me 菜单树中的 component 字段 + 组件注册表解析页面。
export const DynamicPage = lazy(() => import('@/pages/dynamic-page/DynamicPage'));
