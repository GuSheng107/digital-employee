// SystemConfig 页面私有类型
// DependenciesStatus 跨页面共享，从全局 types 引入
import type { DependenciesStatus } from '@/types/data-platform';

export type TestTarget = 'all' | 'postgres' | 'core_db' | 'vector_db' | 'redis' | 'minio';

export interface SystemConfigData {
  app: Record<string, unknown>;
  core_db: Record<string, unknown>;
  vector_db: Record<string, unknown>;
  redis: Record<string, unknown>;
  minio: Record<string, unknown>;
  cors_origins: string[];
}

// 配置表格按分组展示
export interface SystemConfigRow {
  group: string;
  values: Record<string, unknown>;
}

export type SystemConfigDependencies = DependenciesStatus;
