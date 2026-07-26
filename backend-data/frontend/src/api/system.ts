import { request, type ApiResponse } from './request'

export interface ServiceInfo {
  name: string
  version: string
  environment: string
  status: string
}

export interface DependencyStatus {
  ok: boolean
  message: string
  latency_ms?: number | null
}

export interface DependenciesStatus {
  core_db: DependencyStatus
  vector_db: DependencyStatus
  redis: DependencyStatus
  minio: DependencyStatus
}

export type TestTarget = 'all' | 'postgres' | 'core_db' | 'vector_db' | 'redis' | 'minio'

export interface SystemConfig {
  app: Record<string, unknown>
  core_db: Record<string, unknown>
  vector_db: Record<string, unknown>
  redis: Record<string, unknown>
  minio: Record<string, unknown>
  cors_origins: string[]
}

export async function getServiceInfo() {
  const { data } = await request.get<ServiceInfo>('/')
  return data
}

export async function getDependencies() {
  const { data } = await request.get<ApiResponse<DependenciesStatus>>(
    '/api/v1/health/dependencies',
  )
  return data
}

export async function getSystemConfig() {
  const { data } = await request.get<ApiResponse<SystemConfig>>('/api/v1/system/config')
  return data
}

export async function testConnections(target: TestTarget = 'all') {
  const { data } = await request.post<ApiResponse<DependenciesStatus>>(
    '/api/v1/system/test-connections',
    { target },
  )
  return data
}

export async function writeRedisTest() {
  const { data } = await request.post<ApiResponse<Record<string, unknown>>>(
    '/api/v1/cache/test',
  )
  return data
}

export async function readRedisTest() {
  const { data } = await request.get<ApiResponse<Record<string, unknown>>>(
    '/api/v1/cache/test',
  )
  return data
}

export async function ensureBucket() {
  const { data } = await request.post<ApiResponse<Record<string, unknown>>>(
    '/api/v1/storage/buckets/ensure',
  )
  return data
}

export async function listBuckets() {
  const { data } = await request.get<ApiResponse<Record<string, unknown>[]>>(
    '/api/v1/storage/buckets',
  )
  return data
}

export async function writeTestObject() {
  const { data } = await request.post<ApiResponse<Record<string, unknown>>>(
    '/api/v1/storage/test-object',
  )
  return data
}

export async function readTestObject() {
  const { data } = await request.get<ApiResponse<Record<string, unknown>>>(
    '/api/v1/storage/test-object',
  )
  return data
}
