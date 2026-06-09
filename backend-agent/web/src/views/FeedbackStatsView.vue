<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { getFeedbackStats, getFeedbackListByMessage, getFeedbackAlerts } from '../api/feedback'
import { formatTime } from '../utils/format'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { Search } from '@element-plus/icons-vue'

const loading = ref(false)
const alertLoading = ref(false)
const querying = ref(false)
const stats = ref({
  total: 0,
  useful: 0,
  useless: 0,
  satisfaction_rate: 0,
  days: 0,
})
const feedbacks = ref([])
const alerts = ref([])
const pagination = ref({
  total: 0,
  page: 1,
  page_size: 20,
})
const alertPagination = ref({
  total: 0,
  page: 1,
  page_size: 10,
})

const daysFilter = ref(0)
const resultFilter = ref('')

async function loadStats() {
  try {
    const result = await getFeedbackStats({ days: daysFilter.value })
    stats.value = result
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  }
}

async function loadFeedbacks() {
  loading.value = true
  try {
    const result = await getFeedbackListByMessage({
      result: resultFilter.value,
      days: daysFilter.value,
      page: pagination.value.page,
      page_size: pagination.value.page_size,
    })
    feedbacks.value = result.items || []
    pagination.value.total = result.total || 0
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loading.value = false
  }
}

async function loadAlerts() {
  alertLoading.value = true
  try {
    const result = await getFeedbackAlerts({
      days: daysFilter.value,
      page: alertPagination.value.page,
      page_size: alertPagination.value.page_size,
    })
    alerts.value = result.items || []
    alertPagination.value.total = result.total || 0
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    alertLoading.value = false
  }
}

async function loadAll() {
  querying.value = true
  try {
    await Promise.all([loadStats(), loadFeedbacks(), loadAlerts()])
  } finally {
    querying.value = false
  }
}

async function handleQuery() {
  pagination.value.page = 1
  alertPagination.value.page = 1
  await loadAll()
}

function handlePageChange(page) {
  pagination.value.page = page
  loadFeedbacks()
}

function handleSizeChange(size) {
  pagination.value.page_size = size
  pagination.value.page = 1
  loadFeedbacks()
}

function handleAlertPageChange(page) {
  alertPagination.value.page = page
  loadAlerts()
}

function handleAlertSizeChange(size) {
  alertPagination.value.page_size = size
  alertPagination.value.page = 1
  loadAlerts()
}

function getStatusType(status) {
  if (status === 'useful') return 'success'
  if (status === 'useless') return 'danger'
  if (status === 'mixed') return 'warning'
  return 'info'
}

function getStatusLabel(status) {
  if (status === 'useful') return '有效'
  if (status === 'useless') return '无效'
  if (status === 'mixed') return '有争议'
  return '未知'
}

function getConvertStatusType(status) {
  if (status === 'converted') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'unconverted') return 'info'
  return 'info'
}

function getConvertStatusLabel(status) {
  if (status === 'converted') return '已转换'
  if (status === 'failed') return '转换失败'
  if (status === 'unconverted') return '待转换'
  return '未知'
}

function getReviewStatusType(status) {
  if (status === 'reviewed') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'pending') return 'info'
  return 'info'
}

function getReviewStatusLabel(status) {
  if (status === 'reviewed') return '已审核'
  if (status === 'partial') return '部分审核'
  if (status === 'pending') return '待审核'
  return '未知'
}

function feedbackReviewText(row) {
  const reviewed = Number(row?.reviewed_count || 0)
  const total = Number(row?.review_feedback_count ?? row?.useless_count ?? 0)
  if (!total) return ''
  return `${reviewed}/${total}`
}

function shouldShowConvertStatus(row) {
  const status = String(row?.feedback_status || '').trim().toLowerCase()
  return status === 'useful' || status === 'mixed'
}

function shouldShowReviewStatus(row) {
  const status = String(row?.feedback_status || '').trim().toLowerCase()
  return status === 'useless' || status === 'mixed'
}

function getChatTypeLabel(chat_type) {
  if (chat_type === 'group') return '群聊'
  if (chat_type === 'single') return '用户'
  if (chat_type === 'user') return '用户'
  if (chat_type === 'room') return '群聊'
  return chat_type || '未知'
}

function alertContextItems(row) {
  return row?.metadata?.context?.items || []
}

function feedbackReason(row) {
  return String(row?.useless_reasons || '').trim()
}

onMounted(() => {
  loadAll()
})

onActivated(() => {
  loadAll()
})
</script>

<template>
  <section class="console-view console-view--single feedback-stats-view">
    <el-card class="panel console-panel" shadow="never">
      <template #header>
        <div class="panel-title">
          <span>反馈分析</span>
        </div>
      </template>

      <div class="stats-cards">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总反馈数</div>
        </el-card>
        <el-card class="stat-card stat-card--success" shadow="hover">
          <div class="stat-value">{{ stats.useful }}</div>
          <div class="stat-label">有效</div>
        </el-card>
        <el-card class="stat-card stat-card--danger" shadow="hover">
          <div class="stat-value">{{ stats.useless }}</div>
          <div class="stat-label">无效</div>
        </el-card>
        <el-card class="stat-card stat-card--primary" shadow="hover">
          <div class="stat-value">{{ stats.satisfaction_rate }}%</div>
          <div class="stat-label">满意度</div>
        </el-card>
      </div>

      <div class="filter-bar">
        <el-form :inline="true">
          <el-form-item label="时间范围">
            <el-select v-model="daysFilter" style="width: 140px">
              <el-option label="今日" :value="0" />
              <el-option label="过去一周" :value="7" />
              <el-option label="15天前" :value="15" />
              <el-option label="30天前" :value="30" />
            </el-select>
          </el-form-item>
          <el-form-item label="反馈状态">
            <el-select v-model="resultFilter" clearable placeholder="全部" style="width: 120px">
              <el-option label="有效" value="useful" />
              <el-option label="无效" value="useless" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :icon="Search" :loading="querying" @click="handleQuery">
              查询
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="feedback-content">
        <div class="feedback-detail-panel">
          <div class="panel-section-title">反馈详情（按消息）</div>
          <div class="table-wrapper">
            <el-table
              :data="feedbacks"
              v-loading="loading"
              stripe
              style="width: 100%"
              height="100%"
            >
              <el-table-column type="expand" width="44">
                <template #default="{ row }">
                  <div class="feedback-detail">
                    <div class="feedback-detail__grid">
                      <div>
                        <div class="detail-label">用户问题</div>
                        <div class="detail-text">{{ row.question || '-' }}</div>
                      </div>
                      <div>
                        <div class="detail-label">Bot 回复</div>
                        <div class="detail-text">{{ row.answer || '-' }}</div>
                      </div>
                      <div v-if="shouldShowConvertStatus(row)">
                        <div class="detail-label">记忆转换状态</div>
                        <div class="detail-tags">
                          <el-tag :type="getConvertStatusType(row.memory_convert_status)" size="small">
                            {{ getConvertStatusLabel(row.memory_convert_status) }}
                          </el-tag>
                          <span v-if="row.memory_convert_at" class="detail-meta">{{ formatTime(row.memory_convert_at) }}</span>
                        </div>
                      </div>
                      <div v-if="shouldShowReviewStatus(row)">
                        <div class="detail-label">反馈审核状态</div>
                        <div class="detail-tags">
                          <el-tag :type="getReviewStatusType(row.review_status)" size="small">
                            {{ getReviewStatusLabel(row.review_status) }}
                          </el-tag>
                          <span class="detail-meta">{{ feedbackReviewText(row) || '-' }}</span>
                          <span v-if="row.latest_reviewed_at" class="detail-meta">{{ formatTime(row.latest_reviewed_at) }}</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="row.feedbacks && row.feedbacks.length > 0" class="feedback-list-box">
                      <div class="detail-label">反馈明细（{{ row.feedbacks.length }} 条）</div>
                      <div class="feedback-list">
                        <div
                          v-for="(fb, idx) in row.feedbacks"
                          :key="fb.id || idx"
                          class="feedback-list__item"
                        >
                          <el-tag :type="fb.result === 'useful' ? 'success' : 'danger'" size="small">
                            {{ fb.result === 'useful' ? '有效' : '无效' }}
                          </el-tag>
                          <el-tag
                            v-if="shouldShowReviewStatus(row) && fb.result === 'useless'"
                            :type="fb.reviewed_at ? 'success' : 'info'"
                            size="small"
                          >
                            {{ fb.reviewed_at ? '已审核' : '待审核' }}
                          </el-tag>
                          <span v-if="fb.reason" class="feedback-list__reason">{{ fb.reason }}</span>
                          <span class="feedback-list__meta">{{ fb.user_display_name || '' }}{{ fb.user_display_name ? ' · ' : '' }}{{ formatTime(fb.created_at) }}</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="feedbackReason(row)" class="feedback-reason-box">
                      <div class="detail-label">无效原因汇总</div>
                      <div class="detail-text">{{ feedbackReason(row) }}</div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column type="index" label="序号" width="60" align="center" />
              <el-table-column prop="feedback_status" label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.feedback_status)" size="small">
                    {{ getStatusLabel(row.feedback_status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="记忆/审核" width="150">
                <template #default="{ row }">
                  <div class="status-tags">
                    <el-tag
                      v-if="shouldShowConvertStatus(row)"
                      :type="getConvertStatusType(row.memory_convert_status)"
                      size="small"
                    >
                      {{ getConvertStatusLabel(row.memory_convert_status) }}
                    </el-tag>
                    <el-tag
                      v-if="shouldShowReviewStatus(row)"
                      :type="getReviewStatusType(row.review_status)"
                      size="small"
                    >
                      {{ getReviewStatusLabel(row.review_status) }}
                    </el-tag>
                    <span
                      v-if="!shouldShowConvertStatus(row) && !shouldShowReviewStatus(row)"
                      class="empty-inline"
                    >
                      -
                    </span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="反馈数" width="70" align="center">
                <template #default="{ row }">
                  <span v-if="row.feedback_count > 1" class="feedback-count-badge">
                    {{ row.useful_count }}<span class="feedback-count-sep">/</span>{{ row.useless_count }}
                  </span>
                  <span v-else>{{ row.feedback_count }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" width="80">
                <template #default="{ row }">
                  {{ getChatTypeLabel(row.chat_type) }}
                </template>
              </el-table-column>
              <el-table-column prop="chat_display_name" label="群聊/用户" min-width="140" show-overflow-tooltip />
              <el-table-column label="无效原因" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="feedbackReason(row)" class="reason-text">{{ feedbackReason(row) }}</span>
                  <span v-else class="empty-inline">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="bot_name" label="Bot" width="120" show-overflow-tooltip />
              <el-table-column prop="latest_feedback_at" label="时间" width="150">
                <template #default="{ row }">
                  {{ formatTime(row.latest_feedback_at) }}
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="pagination-wrapper">
            <span class="pagination-label">反馈详情分页</span>
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
        </div>

        <div class="alert-card-panel">
          <div class="panel-section-title">告警记录</div>
          <div class="alert-list" v-loading="alertLoading">
            <div v-if="alerts.length === 0" class="alert-empty">暂无告警记录</div>
            <div
              v-for="alert in alerts"
              :key="alert.id || alert.notified_at"
              class="alert-card"
            >
              <div class="alert-card__head">
                <span class="alert-card__name">{{ alert.chat_display_name || '-' }}</span>
                <el-tag size="small" type="danger">{{ alert.feedback_count }} / {{ alert.threshold }}</el-tag>
              </div>
              <div class="alert-card__meta">
                <span>{{ getChatTypeLabel(alert.chat_type) }}</span>
                <span v-if="alert.bot_name">· {{ alert.bot_name }}</span>
                <span>· {{ alert.window_minutes }}分钟窗口</span>
              </div>
              <div class="alert-card__time">{{ formatTime(alert.notified_at) }}</div>
              <el-collapse class="alert-card__collapse">
                <el-collapse-item title="展开上下文">
                  <div class="alert-context">
                    <div
                      v-for="(item, index) in alertContextItems(alert)"
                      :key="item.id || index"
                      class="alert-context__item"
                    >
                      <div class="alert-context__meta">{{ formatTime(item.created_at) }} · {{ item.user_id || '-' }}</div>
                      <div v-if="item.question" class="qa-line qa-q">Q: {{ item.question }}</div>
                      <div v-if="item.answer" class="qa-line qa-a">A: {{ item.answer }}</div>
                      <div v-if="item.reason" class="qa-line qa-reason">原因: {{ item.reason }}</div>
                    </div>
                    <div v-if="alertContextItems(alert).length === 0" class="empty-inline">暂无上下文</div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
          <div class="pagination-wrapper">
            <span class="pagination-label">告警记录分页</span>
            <el-pagination
              v-model:current-page="alertPagination.page"
              v-model:page-size="alertPagination.page_size"
              :page-sizes="[5, 10, 20]"
              :total="alertPagination.total"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="handleAlertPageChange"
              @size-change="handleAlertSizeChange"
            />
          </div>
        </div>
      </div>
    </el-card>
  </section>
</template>
