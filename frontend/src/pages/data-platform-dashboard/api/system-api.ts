import dataPlatformRequest from '@/utils/data-platform-request';
import type { ServiceInfo } from '../types/system';
import type { DependenciesStatus } from '@/types/data-platform';

// 获取后端服务基本信息
export async function getServiceInfo(): Promise<ServiceInfo> {
  return dataPlatformRequest.get<ServiceInfo>('/');
}

// 获取所有外部依赖状态
export async function getDependencies(): Promise<DependenciesStatus> {
  return dataPlatformRequest.get<DependenciesStatus>('/api/v1/health/dependencies');
}
