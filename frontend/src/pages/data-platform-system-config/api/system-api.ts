import dataPlatformRequest from '@/utils/data-platform-request';
import type { DependenciesStatus } from '@/types/data-platform';
import type { SystemConfigData, TestTarget } from '../types/system';

// 获取脱敏系统配置
export async function getSystemConfig(): Promise<SystemConfigData> {
  const data = await dataPlatformRequest.get<SystemConfigData>('/api/v1/system/config');
  return data as unknown as SystemConfigData;
}

// 测试外部依赖连接
export async function testConnections(target: TestTarget): Promise<DependenciesStatus> {
  const data = await dataPlatformRequest.post<DependenciesStatus>(
    '/api/v1/system/test-connections',
    { target },
  );
  return data as unknown as DependenciesStatus;
}

// Redis 写入测试
export async function writeRedisTest(): Promise<Record<string, unknown>> {
  const data = await dataPlatformRequest.post<Record<string, unknown>>('/api/v1/cache/test');
  return data as unknown as Record<string, unknown>;
}

// Redis 读取测试
export async function readRedisTest(): Promise<Record<string, unknown>> {
  const data = await dataPlatformRequest.get<Record<string, unknown>>('/api/v1/cache/test');
  return data as unknown as Record<string, unknown>;
}

// 确保 MinIO Bucket 存在
export async function ensureBucket(): Promise<Record<string, unknown>> {
  const data = await dataPlatformRequest.post<Record<string, unknown>>(
    '/api/v1/storage/buckets/ensure',
  );
  return data as unknown as Record<string, unknown>;
}

// 列出 MinIO Bucket
export async function listBuckets(): Promise<Record<string, unknown>[]> {
  const data = await dataPlatformRequest.get<Record<string, unknown>[]>(
    '/api/v1/storage/buckets',
  );
  return data as unknown as Record<string, unknown>[];
}

// MinIO 写入测试对象
export async function writeTestObject(): Promise<Record<string, unknown>> {
  const data = await dataPlatformRequest.post<Record<string, unknown>>(
    '/api/v1/storage/test-object',
  );
  return data as unknown as Record<string, unknown>;
}

// MinIO 读取测试对象
export async function readTestObject(): Promise<Record<string, unknown>> {
  const data = await dataPlatformRequest.get<Record<string, unknown>>(
    '/api/v1/storage/test-object',
  );
  return data as unknown as Record<string, unknown>;
}
