// Dashboard 页面私有类型
// DependenciesStatus 跨页面共享，从全局 types 引入
import type { DependenciesStatus } from '@/types/data-platform';

export interface ServiceInfo {
  name: string;
  version: string;
  environment: string;
  status: string;
}

export type DashboardDependencies = DependenciesStatus;
