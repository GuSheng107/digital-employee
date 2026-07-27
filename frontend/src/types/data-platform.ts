// 数据中台公共类型：跨页面共享的稳定接口契约
// 仅放确实被两个及以上页面复用的类型，页面私有类型留在页面目录

export interface DependencyStatus {
  ok: boolean;
  message: string;
  latency_ms?: number | null;
}

export interface DependenciesStatus {
  core_db: DependencyStatus;
  vector_db: DependencyStatus;
  redis: DependencyStatus;
  minio: DependencyStatus;
}
