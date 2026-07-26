import dataPlatformRequest from '@/utils/data-platform-request';
import type { DependenciesStatus } from '@/types/data-platform';
import type { SystemConfigData, TestTarget } from '../types/system';

// 获取脱敏系统配置
export async function getSystemConfig(): Promise<SystemConfigData> {
  return dataPlatformRequest.get<SystemConfigData>('/api/v1/system/config');
}

// 测试外部依赖连接
export async function testConnections(target: TestTarget): Promise<DependenciesStatus> {
  return dataPlatformRequest.post<DependenciesStatus>('/api/v1/system/test-connections', {
    target,
  });
}

// Redis 写入测试
export async function writeRedisTest(): Promise<Record<string, unknown>> {
  return dataPlatformRequest.post<Record<string, unknown>>('/api/v1/cache/test');
}

// Redis 读取测试
export async function readRedisTest(): Promise<Record<string, unknown>> {
  return dataPlatformRequest.get<Record<string, unknown>>('/api/v1/cache/test');
}

// 确保 MinIO Bucket 存在
export async function ensureBucket(): Promise<Record<string, unknown>> {
  return dataPlatformRequest.post<Record<string, unknown>>('/api/v1/storage/buckets/ensure');
}

// 列出 MinIO Bucket
export async function listBuckets(): Promise<Record<string, unknown>[]> {
  return dataPlatformRequest.get<Record<string, unknown>[]>('/api/v1/storage/buckets');
}

// MinIO 写入测试对象
export async function writeTestObject(): Promise<Record<string, unknown>> {
  return dataPlatformRequest.post<Record<string, unknown>>('/api/v1/storage/test-object');
}

// MinIO 读取测试对象
export async function readTestObject(): Promise<Record<string, unknown>> {
  return dataPlatformRequest.get<Record<string, unknown>>('/api/v1/storage/test-object');
}
