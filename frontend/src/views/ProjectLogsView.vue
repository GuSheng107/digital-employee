<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { getProjectLogs } from '../api/runtime'
import { formatTime } from '../utils/format'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { CopyDocument } from '@element-plus/icons-vue'

const loading = ref(false)
const logs = ref([])
const pagination = ref({
  total: 0,
  page: 1,
  page_size: 20,
  total_pages: 1,
})

const filters = ref({
  category: '',
  level: '',
  trace_id: '',
  start_time: '',
  end_time: '',
})

const detailDialogVisible = ref(false)
const currentDetail = ref(null)

async function loadLogs() {
  loading.value = true
  try {
    const result = await getProjectLogs({
      category: filters.value.category,
      level: filters.value.level,
      trace_id: filters.value.trace_id,
      start_time: filters.value.start_time,
      end_time: filters.value.end_time,
      page: pagination.value.page,
      page_size: pagination.value.page_size,
    })
    logs.value = result.logs || []
    pagination.value = {
      total: result.total || 0,
      page: result.page || 1,
      page_size: result.page_size || 20,
      total_pages: result.total_pages || 1,
    }
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.value.page = 1
  loadLogs()
}

function handlePageChange(page) {
  pagination.value.page = page
  loadLogs()
}

function handleSizeChange(size) {
  pagination.value.page_size = size
  pagination.value.page = 1
  loadLogs()
}

function showDetail(log) {
  currentDetail.value = log
  detailDialogVisible.value = true
}

function getLevelType(level) {
  const map = {
    'ERROR': 'danger',
    'WARNING': 'warning',
    'INFO': 'info',
    'DEBUG': '',
  }
  return map[level] || ''
}

function getCategoryType(category) {
  const map = {
    system: 'info',
    network: 'warning',
    ai: 'success',
    task: 'primary',
    data: '',
    bot: 'danger',
    media: 'warning',
    message: 'info',
  }
  return map[category] || 'info'
}

function getCategoryLabel(category) {
  const map = {
    system: '系统',
    network: '网络',
    ai: 'AI',
    task: '任务',
    data: '数据',
    bot: 'Bot',
    media: '媒体',
    message: '消息',
  }
  return map[category] || category || '系统'
}

async function copyDetail() {
  if (!currentDetail.value?.detail) {
    ElMessage.warning('没有可复制的内容')
    return
  }
  try {
    // 优先使用现代剪贴板 API
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(currentDetail.value.detail)
      ElMessage.success('复制成功')
      return
    }
    // 回退到传统方法
    const textArea = document.createElement('textarea')
    textArea.value = currentDetail.value.detail
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    textArea.style.top = '-9999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    if (successful) {
      ElMessage.success('复制成功')
    } else {
      ElMessage.error('复制失败，请手动选择内容复制')
    }
  } catch (error) {
    console.error('复制失败:', error)
    ElMessage.error('复制失败，请手动选择内容复制')
  }
}

onMounted(() => {
  loadLogs()
})

onActivated(() => {
  loadLogs()
})
</script>

<template>
  <section class="console-view console-view--single">
    <el-card class="panel console-panel project-log-panel" shadow="never">
      <template #header>
        <div class="panel-title">
          <span>日志查询</span>
        </div>
      </template>

      <!-- 查询条件 -->
      <el-form :inline="true" class="search-form" @submit.prevent="handleSearch">
        <div class="search-form-row">
          <el-form-item label="日志类型">
            <el-select v-model="filters.category" placeholder="请选择" clearable style="width: 160px">
              <el-option label="系统" value="system" />
              <el-option label="网络" value="network" />
              <el-option label="AI" value="ai" />
              <el-option label="任务" value="task" />
              <el-option label="数据" value="data" />
              <el-option label="Bot" value="bot" />
              <el-option label="媒体" value="media" />
              <el-option label="消息" value="message" />
            </el-select>
          </el-form-item>
          <el-form-item label="TraceId">
            <el-input v-model="filters.trace_id" placeholder="请输入 TraceId" clearable style="width: 200px" />
          </el-form-item>
          <el-form-item label="日志级别">
            <el-select v-model="filters.level" placeholder="请选择" clearable style="width: 180px">
              <el-option label="ERROR" value="ERROR" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="INFO" value="INFO" />
            </el-select>
          </el-form-item>
          <el-form-item label="创建时间">
            <el-date-picker
              v-model="filters.start_time"
              type="datetime"
              placeholder="开始时间"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              clearable
            />
            <span style="margin: 0 8px">至</span>
            <el-date-picker
              v-model="filters.end_time"
              type="datetime"
              placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              clearable
            />
          </el-form-item>
          <el-form-item class="search-btn-item">
            <el-button type="primary" @click="handleSearch">查询</el-button>
          </el-form-item>
        </div>
      </el-form>

      <!-- 日志表格 -->
      <div class="table-wrapper">
        <el-table
          :data="logs"
          v-loading="loading"
          stripe
          style="width: 100%"
          height="100%"
        >
          <el-table-column type="index" label="行号" width="80" align="center" />
          <el-table-column prop="level" label="级别" width="100">
            <template #default="{ row }">
              <el-tag :type="getLevelType(row.level)" size="small">
                {{ row.level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="类型" width="110">
            <template #default="{ row }">
              <el-tag :type="getCategoryType(row.category)" size="small" effect="plain">
                {{ getCategoryLabel(row.category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="trace_id" label="TraceId" min-width="240" show-overflow-tooltip />
          <el-table-column prop="source" label="来源" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="row.error_code">
                {{ row.source }}
                <el-tag type="danger" size="small" style="margin-left: 8px">
                  {{ row.error_code }}
                </el-tag>
              </template>
              <template v-else>
                {{ row.source }}
              </template>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="200">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="message" label="信息" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showDetail(row)">
                查看详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="日志详情"
      width="1200px"
      top="10%"
      class="log-detail-dialog"
    >
      <el-descriptions v-if="currentDetail" :column="1" border class="log-detail-descriptions">
        <el-descriptions-item label="级别">
          <el-tag :type="getLevelType(currentDetail.level)" size="small">
            {{ currentDetail.level }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="类型">
          <el-tag :type="getCategoryType(currentDetail.category)" size="small" effect="plain">
            {{ getCategoryLabel(currentDetail.category) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="TraceId">
          {{ currentDetail.trace_id }}
        </el-descriptions-item>
        <el-descriptions-item label="来源">
          <template v-if="currentDetail.error_code">
            {{ currentDetail.source }} (错误码: {{ currentDetail.error_code }})
          </template>
          <template v-else>
            {{ currentDetail.source }}
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatTime(currentDetail.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="信息">
          {{ currentDetail.message }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentDetail.detail" label="详情">
          <div class="detail-wrapper">
            <el-button
              type="primary"
              link
              size="small"
              @click.stop="copyDetail"
              class="copy-icon-btn"
            >
              <el-icon><CopyDocument /></el-icon>
            </el-button>
            <pre class="log-detail">{{ currentDetail.detail }}</pre>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>
