import dataPlatformRequest from '@/utils/data-platform-request';
import type { ServiceInfo } from '../types/system';
import type { DependenciesStatus } from '@/types/data-platform';

// 获取后端服务基本信息
export async function getServiceInfo(): Promise<ServiceInfo> {
  const data = await dataPlatformRequest.get<ServiceInfo>('/');
  return data as unknown as ServiceInfo;
}

// 获取所有外部依赖状态
export async function getDependencies(): Promise<DependenciesStatus> {
  const data = await dataPlatformRequest.get<DependenciesStatus>('/api/v1/health/dependencies');
  return data as unknown as DependenciesStatus;
}
