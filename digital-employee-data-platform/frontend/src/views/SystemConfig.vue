<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatusCard from '../components/StatusCard.vue'
import { getErrorMessage } from '../api/request'
import {
  ensureBucket,
  getSystemConfig,
  listBuckets,
  readRedisTest,
  readTestObject,
  testConnections,
  writeRedisTest,
  writeTestObject,
  type DependenciesStatus,
  type SystemConfig,
  type TestTarget,
} from '../api/system'

const loading = ref(false)
const actionLoading = ref('')
const config = ref<SystemConfig | null>(null)
const dependencies = ref<DependenciesStatus | null>(null)
const lastResult = ref('')

const configRows = computed(() => {
  if (!config.value) return []
  return [
    { group: '普通 PostgreSQL', values: config.value.core_db },
    { group: '向量 PostgreSQL', values: config.value.vector_db },
    { group: 'Redis', values: config.value.redis },
    { group: 'MinIO', values: config.value.minio },
  ]
})

function statusOf(ok?: boolean): 'ok' | 'error' | 'unknown' {
  if (ok === undefined) return 'unknown'
  return ok ? 'ok' : 'error'
}

async function loadConfig() {
  loading.value = true
  try {
    const response = await getSystemConfig()
    config.value = response.data
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function runTest(target: TestTarget, label: string) {
  actionLoading.value = label
  try {
    const response = await testConnections(target)
    dependencies.value = response.data
    lastResult.value = JSON.stringify(response.data, null, 2)
    ElMessage.success(`${label}完成`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    actionLoading.value = ''
  }
}

async function runAction(label: string, action: () => Promise<unknown>) {
  actionLoading.value = label
  try {
    const response = await action()
    lastResult.value = JSON.stringify(response, null, 2)
    ElMessage.success(`${label}完成`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    actionLoading.value = ''
  }
}

onMounted(loadConfig)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>System Config</h2>
        <p>查看脱敏配置并测试外部依赖连接</p>
      </div>
      <el-button :loading="loading" @click="loadConfig">刷新配置</el-button>
    </div>

    <div class="toolbar">
      <el-button
        type="primary"
        :loading="actionLoading === '测试全部连接'"
        @click="runTest('all', '测试全部连接')"
      >
        测试全部连接
      </el-button>
      <el-button
        :loading="actionLoading === '测试 PostgreSQL'"
        @click="runTest('postgres', '测试 PostgreSQL')"
      >
        测试 PostgreSQL
      </el-button>
      <el-button
        :loading="actionLoading === '测试 Redis'"
        @click="runTest('redis', '测试 Redis')"
      >
        测试 Redis
      </el-button>
      <el-button
        :loading="actionLoading === '测试 MinIO'"
        @click="runTest('minio', '测试 MinIO')"
      >
        测试 MinIO
      </el-button>
    </div>

    <div class="status-grid compact">
      <StatusCard
        title="普通 PostgreSQL"
        :status="statusOf(dependencies?.core_db.ok)"
        :message="dependencies?.core_db.message"
        :latency="dependencies?.core_db.latency_ms"
      />
      <StatusCard
        title="向量 PostgreSQL"
        :status="statusOf(dependencies?.vector_db.ok)"
        :message="dependencies?.vector_db.message"
        :latency="dependencies?.vector_db.latency_ms"
      />
      <StatusCard
        title="Redis"
        :status="statusOf(dependencies?.redis.ok)"
        :message="dependencies?.redis.message"
        :latency="dependencies?.redis.latency_ms"
      />
      <StatusCard
        title="MinIO"
        :status="statusOf(dependencies?.minio.ok)"
        :message="dependencies?.minio.message"
        :latency="dependencies?.minio.latency_ms"
      />
    </div>

    <el-table v-if="configRows.length" :data="configRows" border class="config-table">
      <el-table-column prop="group" label="配置分组" width="180" />
      <el-table-column label="脱敏配置">
        <template #default="{ row }">
          <el-descriptions :column="3" size="small" border>
            <el-descriptions-item
              v-for="(value, key) in row.values"
              :key="key"
              :label="String(key)"
            >
              {{ value }}
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </el-table-column>
    </el-table>

    <div class="toolbar secondary">
      <el-button
        :loading="actionLoading === 'Redis 写入测试'"
        @click="runAction('Redis 写入测试', writeRedisTest)"
      >
        Redis 写入测试
      </el-button>
      <el-button
        :loading="actionLoading === 'Redis 读取测试'"
        @click="runAction('Redis 读取测试', readRedisTest)"
      >
        Redis 读取测试
      </el-button>
      <el-button
        :loading="actionLoading === '确保 Bucket'"
        @click="runAction('确保 Bucket', ensureBucket)"
      >
        确保 Bucket
      </el-button>
      <el-button
        :loading="actionLoading === 'MinIO 写入对象'"
        @click="runAction('MinIO 写入对象', writeTestObject)"
      >
        MinIO 写入对象
      </el-button>
      <el-button
        :loading="actionLoading === 'MinIO 读取对象'"
        @click="runAction('MinIO 读取对象', readTestObject)"
      >
        MinIO 读取对象
      </el-button>
      <el-button
        :loading="actionLoading === 'Bucket 列表'"
        @click="runAction('Bucket 列表', listBuckets)"
      >
        Bucket 列表
      </el-button>
    </div>

    <pre v-if="lastResult" class="result-box">{{ lastResult }}</pre>
  </div>
</template>
