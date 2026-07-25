<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatusCard from '../components/StatusCard.vue'
import { apiBaseUrl, getErrorMessage } from '../api/request'
import {
  getDependencies,
  getServiceInfo,
  type DependenciesStatus,
  type ServiceInfo,
} from '../api/system'

const loading = ref(false)
const service = ref<ServiceInfo | null>(null)
const dependencies = ref<DependenciesStatus | null>(null)

function cardStatus(ok?: boolean): 'ok' | 'error' | 'unknown' {
  if (ok === undefined) return 'unknown'
  return ok ? 'ok' : 'error'
}

async function refresh() {
  loading.value = true
  try {
    const [serviceInfo, dependencyResponse] = await Promise.all([
      getServiceInfo(),
      getDependencies(),
    ])
    service.value = serviceInfo
    dependencies.value = dependencyResponse.data
    ElMessage.success('状态已刷新')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Dashboard</h2>
        <p>当前 API 地址：{{ apiBaseUrl }}</p>
      </div>
      <el-button type="primary" :loading="loading" @click="refresh">刷新状态</el-button>
    </div>

    <div class="status-grid">
      <StatusCard
        title="后端服务"
        :status="service?.status === 'running' ? 'ok' : 'unknown'"
        :message="service ? `${service.name} ${service.version}` : '等待检测'"
      />
      <StatusCard
        title="普通 PostgreSQL"
        :status="cardStatus(dependencies?.core_db.ok)"
        :message="dependencies?.core_db.message"
        :latency="dependencies?.core_db.latency_ms"
      />
      <StatusCard
        title="向量 PostgreSQL"
        :status="cardStatus(dependencies?.vector_db.ok)"
        :message="dependencies?.vector_db.message"
        :latency="dependencies?.vector_db.latency_ms"
      />
      <StatusCard
        title="Redis"
        :status="cardStatus(dependencies?.redis.ok)"
        :message="dependencies?.redis.message"
        :latency="dependencies?.redis.latency_ms"
      />
      <StatusCard
        title="MinIO"
        :status="cardStatus(dependencies?.minio.ok)"
        :message="dependencies?.minio.message"
        :latency="dependencies?.minio.latency_ms"
      />
    </div>
  </div>
</template>
