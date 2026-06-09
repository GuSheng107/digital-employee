<script setup>
import { onActivated, onMounted, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { Search, Plus, Delete, Edit, View, Refresh } from '@element-plus/icons-vue'
import {
  getMemoryFiles,
  getMemoryItems,
  addMemoryItem,
  updateMemoryItem,
  deleteMemoryItem,
  searchMemory,
  getMemoryReviews,
  getMemoryReviewContent,
  deleteMemoryReview,
} from '../api/system'
import { formatTime, renderMarkdown } from '../utils/format'

const activeTab = ref('files')
const files = ref([])
const selectedFileKey = ref('')
const items = ref([])
const loadingFiles = ref(false)
const loadingItems = ref(false)
const searchQuery = ref('')
const searchResults = ref([])
const isSearchMode = ref(false)
const loadingSearch = ref(false)

const dialogVisible = ref(false)
const dialogMode = ref('view')
const dialogSaving = ref(false)
const dialogForm = ref({})

const expandedItemKey = ref(null)

const selectedFileLabel = computed(() => {
  const f = files.value.find(f => f.file_key === selectedFileKey.value)
  return f ? f.label : selectedFileKey.value
})

const fileGroups = computed(() => {
  const core = []
  const timeline = []
  const documents = []
  for (const f of files.value) {
    if (f.file_key.startsWith('documents/')) {
      documents.push(f)
    } else if (f.file_key.startsWith('timeline/')) {
      timeline.push(f)
    } else {
      core.push(f)
    }
  }
  const groups = []
  if (core.length) groups.push({ key: 'core', label: '核心记忆', files: core })
  if (timeline.length) groups.push({ key: 'timeline', label: '时间线', files: timeline })
  if (documents.length) groups.push({ key: 'documents', label: '文档记忆', files: documents })
  return groups
})

const displayItems = computed(() => {
  if (isSearchMode.value) {
    return searchResults.value.map(r => ({
      ...r.item,
      _file_key: r.file_key,
      _score: r.score,
      _isSearchResult: true,
    }))
  }
  return items.value
})

function contentTypeTagType(ct) {
  return {
    problem_solution: 'danger',
    qa: 'success',
    term_definition: 'primary',
    operation_guide: 'warning',
    configuration: 'info',
    process: 'danger',
    rule: 'warning',
    fact: 'primary',
    preference: 'success',
  }[ct] || 'info'
}

function priorityLabel(p) {
  if (p == null) return '-'
  const v = Number(p)
  if (v >= 10) return '紧急'
  if (v >= 6) return '高'
  if (v >= 3) return '中'
  return '低'
}

function priorityTagType(p) {
  if (p == null) return 'info'
  const v = Number(p)
  if (v >= 10) return 'danger'
  if (v >= 6) return 'warning'
  if (v >= 3) return ''
  return 'info'
}

function truncate(text, len = 120) {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

function fileLabel(fileKey) {
  const f = files.value.find(f => f.file_key === fileKey)
  return f?.label || ''
}

function displaySource(item) {
  const source = String(item?.source || '').toLowerCase()
  const sourceId = item?.source_id || ''
  const fileKey = item?._file_key || selectedFileKey.value || ''
  if (fileKey === 'explicit' || ['explicit', 'admin', 'admin_config', 'admin-config'].includes(source)) {
    return '管理员配置内容'
  }
  if (source === 'document' || fileKey.startsWith('documents/')) {
    const docKey = fileKey.startsWith('documents/') ? fileKey : sourceId ? `documents/${sourceId}` : ''
    const label = fileLabel(docKey)
    return label ? `文档《${label}》` : '文档'
  }
  return ''
}

function itemIdentity(item, fileKey = '') {
  const fk = item?._file_key || fileKey || selectedFileKey.value || ''
  return `${fk}:${item?.id || ''}`
}

async function loadFiles() {
  loadingFiles.value = true
  try {
    const result = await getMemoryFiles()
    files.value = result.files || []
    const hasSelectedFile = files.value.some(f => f.file_key === selectedFileKey.value)
    if ((!selectedFileKey.value || !hasSelectedFile) && files.value.length) {
      selectedFileKey.value = files.value[0].file_key
    } else if (!files.value.length) {
      selectedFileKey.value = ''
    }
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loadingFiles.value = false
  }
}

async function loadItems() {
  if (!selectedFileKey.value) {
    items.value = []
    return
  }
  loadingItems.value = true
  try {
    const result = await getMemoryItems(selectedFileKey.value)
    items.value = result.items || []
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loadingItems.value = false
  }
}

async function handleSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    isSearchMode.value = false
    searchResults.value = []
    return
  }
  loadingSearch.value = true
  isSearchMode.value = true
  try {
    const result = await searchMemory(q, selectedFileKey.value || '')
    searchResults.value = result.results || []
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loadingSearch.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  isSearchMode.value = false
  searchResults.value = []
  expandedItemKey.value = null
}

function selectFile(fileKey) {
  selectedFileKey.value = fileKey
  expandedItemKey.value = null
  if (isSearchMode.value) {
    void handleSearch()
  }
}

function toggleExpand(item) {
  const key = itemIdentity(item)
  expandedItemKey.value = expandedItemKey.value === key ? null : key
}

function openAddDialog() {
  dialogMode.value = 'add'
  dialogForm.value = {
    _file_key: selectedFileKey.value,
    content: '',
    content_type: 'fact',
    speed_lookup: '',
    priority: 4,
    source: '',
    source_id: '',
  }
  dialogVisible.value = true
}

function openViewDialog(item, fileKey) {
  dialogMode.value = 'view'
  dialogForm.value = {
    ...item,
    _file_key: fileKey || selectedFileKey.value,
  }
  dialogVisible.value = true
}

function openEditDialog(item, fileKey) {
  dialogMode.value = 'edit'
  dialogForm.value = {
    ...item,
    _file_key: fileKey || selectedFileKey.value,
  }
  dialogVisible.value = true
}

async function handleDialogSave() {
  const fk = dialogForm.value._file_key || selectedFileKey.value
  if (!fk) {
    ElMessage.warning('未选择记忆文件')
    return
  }
  if (!dialogForm.value.content?.trim()) {
    ElMessage.warning('记忆内容不能为空')
    return
  }
  dialogSaving.value = true
  try {
    if (dialogMode.value === 'add') {
      const data = {
        content: dialogForm.value.content.trim(),
        content_type: dialogForm.value.content_type || 'fact',
        speed_lookup: dialogForm.value.speed_lookup || '',
        priority: dialogForm.value.priority ?? 4,
      }
      if (dialogForm.value.source) data.source = dialogForm.value.source
      if (dialogForm.value.source_id) data.source_id = dialogForm.value.source_id
      await addMemoryItem(fk, data)
      ElMessage.success('记忆条目已添加')
    } else if (dialogMode.value === 'edit') {
      const data = {
        content: dialogForm.value.content.trim(),
        content_type: dialogForm.value.content_type || 'fact',
        speed_lookup: dialogForm.value.speed_lookup || '',
        priority: dialogForm.value.priority ?? 4,
      }
      await updateMemoryItem(fk, dialogForm.value.id, data)
      ElMessage.success('记忆条目已更新')
    }
    dialogVisible.value = false
    await loadFiles()
    if (isSearchMode.value) {
      await handleSearch()
    } else {
      await loadItems()
    }
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    dialogSaving.value = false
  }
}

async function handleDelete(item, fileKey) {
  const fk = fileKey || selectedFileKey.value
  try {
    await ElMessageBox.confirm(
      '确定要删除这条记忆吗？删除后不可恢复。',
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteMemoryItem(fk, item.id)
    ElMessage.success('记忆条目已删除')
    if (expandedItemKey.value === itemIdentity(item, fk)) {
      expandedItemKey.value = null
    }
    await loadFiles()
    if (isSearchMode.value) {
      await handleSearch()
    } else {
      await loadItems()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || String(error))
    }
  }
}

const reviewReports = ref([])
const loadingReviews = ref(false)
const selectedReport = ref(null)
const reportContent = ref('')
const loadingReportContent = ref(false)

const reportHtml = computed(() => {
  if (!reportContent.value) return ''
  return renderMarkdown(reportContent.value)
})

const reviewGroups = computed(() => {
  const chat = []
  const document = []
  const other = []
  for (const r of reviewReports.value) {
    const t = r.report_type || 'other'
    if (t === 'chat') chat.push(r)
    else if (t === 'document') document.push(r)
    else other.push(r)
  }
  const groups = []
  if (chat.length) groups.push({ key: 'chat', label: '会话审核', reports: chat })
  if (document.length) groups.push({ key: 'document', label: '文档审核', reports: document })
  if (other.length) groups.push({ key: 'other', label: '其他审核', reports: other })
  return groups
})

async function loadReviews() {
  loadingReviews.value = true
  try {
    const result = await getMemoryReviews()
    reviewReports.value = result.reports || []
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loadingReviews.value = false
  }
}

async function viewReport(report) {
  selectedReport.value = report
  loadingReportContent.value = true
  try {
    const result = await getMemoryReviewContent(report.filename)
    reportContent.value = result.content || ''
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    loadingReportContent.value = false
  }
}

async function deleteReport(report) {
  try {
    await ElMessageBox.confirm(
      '删除报告仅移除审核报告文件，不会删除已修改的记忆内容。此操作不可恢复。',
      '删除审核报告',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await deleteMemoryReview(report.filename)
    ElMessage.success('审核报告已删除')
    if (selectedReport.value?.filename === report.filename) {
      selectedReport.value = null
      reportContent.value = ''
    }
    await loadReviews()
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

watch(selectedFileKey, () => {
  if (!isSearchMode.value) {
    loadItems()
  }
})

onMounted(() => {
  loadFiles()
  loadReviews()
})
onActivated(() => {
  loadFiles()
  loadReviews()
  if (selectedFileKey.value) loadItems()
})
</script>

<template>
  <section class="memory-management">
    <div class="header">
      <h2>记忆管理</h2>
    </div>

    <div class="tab-bar">
      <div :class="['tab-item', { active: activeTab === 'files' }]" @click="activeTab = 'files'">记忆文件</div>
      <div :class="['tab-item', { active: activeTab === 'reviews' }]" @click="activeTab = 'reviews'">审核报告</div>
    </div>

    <div v-if="activeTab === 'files'" class="memory-layout">
      <aside class="sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">记忆文件</span>
          <el-button :icon="Refresh" circle size="small" @click="loadFiles" :loading="loadingFiles" />
        </div>
        <div class="file-list" v-loading="loadingFiles">
          <template v-for="group in fileGroups" :key="group.key">
            <div class="file-group-label">{{ group.label }}</div>
            <div
              v-for="file in group.files"
              :key="file.file_key"
              :class="['file-item', { active: selectedFileKey === file.file_key }]"
              @click="selectFile(file.file_key)"
            >
              <div class="file-info">
                <span class="file-label">{{ file.label }}</span>
                <span class="file-key">{{ file.file_key }}</span>
              </div>
              <el-badge :value="file.item_count || 0" :type="selectedFileKey === file.file_key ? 'primary' : 'info'" />
            </div>
          </template>
          <div v-if="!files.length && !loadingFiles" class="empty-sidebar">暂无记忆文件</div>
        </div>
      </aside>

      <main class="main-area">
        <div class="toolbar">
          <div class="search-bar">
            <el-input
              v-model="searchQuery"
              placeholder="搜索记忆内容..."
              clearable
              :prefix-icon="Search"
              @keyup.enter="handleSearch"
              @clear="clearSearch"
              style="max-width: 400px"
            />
            <el-button type="primary" :icon="Search" @click="handleSearch" :loading="loadingSearch">搜索</el-button>
            <el-button v-if="isSearchMode" @click="clearSearch">退出搜索</el-button>
          </div>
          <div class="toolbar-actions">
            <el-button type="primary" :icon="Plus" @click="openAddDialog" :disabled="!selectedFileKey">新增条目</el-button>
          </div>
        </div>

        <div v-if="isSearchMode" class="search-hint">
          <el-tag type="warning" size="large">搜索模式</el-tag>
          <span>共找到 {{ searchResults.length }} 条结果</span>
        </div>

        <div class="items-area" v-loading="loadingItems || loadingSearch">
          <div v-if="!displayItems.length && !(loadingItems || loadingSearch)" class="empty-items">
            {{ isSearchMode ? '未找到匹配的记忆条目' : '该文件暂无记忆条目' }}
          </div>

          <div
            v-for="item in displayItems"
            :key="itemIdentity(item)"
            :class="['item-card', { expanded: expandedItemKey === itemIdentity(item) }]"
          >
            <div class="item-header" @click="toggleExpand(item)">
              <div class="item-meta">
                <el-tag :type="contentTypeTagType(item.content_type)" size="small">{{ item.content_type || '未分类' }}</el-tag>
                <el-tag v-if="item.priority != null" :type="priorityTagType(item.priority)" size="small">P{{ item.priority }} {{ priorityLabel(item.priority) }}</el-tag>
                <el-tag v-if="item._isSearchResult" type="warning" size="small">{{ item._file_key }}</el-tag>
                <span v-if="item.speed_lookup" class="speed-lookup">{{ truncate(item.speed_lookup, 40) }}</span>
              </div>
              <div class="item-actions" @click.stop>
                <el-button :icon="View" size="small" text @click="openViewDialog(item, item._file_key)" />
                <el-button :icon="Edit" size="small" text @click="openEditDialog(item, item._file_key)" />
                <el-button :icon="Delete" size="small" text type="danger" @click="handleDelete(item, item._file_key)" />
              </div>
            </div>
            <div class="item-content">
              <span v-if="expandedItemKey !== itemIdentity(item)">{{ truncate(item.content, 200) }}</span>
              <pre v-else class="item-content-full">{{ item.content }}</pre>
            </div>
            <div class="item-footer">
              <span v-if="displaySource(item)" class="item-source">来源: {{ displaySource(item) }}</span>
              <span class="item-time">{{ formatTime(item.created_at) }}</span>
            </div>
          </div>
        </div>
      </main>
    </div>

    <div v-if="activeTab === 'reviews'" class="reviews-panel">
      <div class="reviews-list" v-loading="loadingReviews">
        <div v-if="!reviewReports.length && !loadingReviews" class="empty-items">暂无审核报告</div>
        <template v-for="group in reviewGroups" :key="group.key">
          <div class="review-group-label">{{ group.label }}</div>
          <div
            v-for="report in group.reports"
            :key="report.filename"
            :class="['review-card', { active: selectedReport?.filename === report.filename }]"
            @click="viewReport(report)"
          >
            <div class="review-card-info">
              <span class="review-card-name">{{ report.filename }}</span>
              <span class="review-card-meta">{{ formatFileSize(report.size) }} · {{ formatTime(report.modified_at) }}</span>
            </div>
          </div>
        </template>
      </div>
      <div class="review-content" v-loading="loadingReportContent">
        <div v-if="!selectedReport" class="empty-items">选择左侧报告查看内容</div>
        <template v-else>
          <div class="review-content-header">
            <span class="review-content-filename">{{ selectedReport.filename }}</span>
            <el-button :icon="Delete" size="small" text type="danger" @click="deleteReport(selectedReport)">删除</el-button>
          </div>
          <div class="review-content-text markdown-body" v-html="reportHtml"></div>
        </template>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogMode === 'add' ? '新增记忆条目' : dialogMode === 'edit' ? '编辑记忆条目' : '记忆条目详情'" width="700px" :close-on-click-modal="false">
      <el-form :model="dialogForm" label-width="100px">
        <el-form-item label="记忆文件">
          <template v-if="dialogMode === 'add'">
            <el-select v-model="dialogForm._file_key" placeholder="选择记忆文件" style="width: 100%">
              <el-option v-for="f in files" :key="f.file_key" :label="f.label" :value="f.file_key" />
            </el-select>
          </template>
          <template v-else>
            <el-tag>{{ dialogForm._file_key }}</el-tag>
          </template>
        </el-form-item>
        <el-form-item label="内容">
          <template v-if="dialogMode !== 'view'">
            <el-input v-model="dialogForm.content" type="textarea" :rows="8" placeholder="输入记忆内容" />
          </template>
          <template v-else>
            <pre class="dialog-content-view">{{ dialogForm.content }}</pre>
          </template>
        </el-form-item>
        <el-form-item label="内容类型">
          <template v-if="dialogMode !== 'view'">
            <el-select v-model="dialogForm.content_type" style="width: 200px">
              <el-option label="事实 (fact)" value="fact" />
              <el-option label="偏好 (preference)" value="preference" />
              <el-option label="问题方案 (problem_solution)" value="problem_solution" />
              <el-option label="问答 (qa)" value="qa" />
              <el-option label="术语定义 (term_definition)" value="term_definition" />
              <el-option label="操作指南 (operation_guide)" value="operation_guide" />
              <el-option label="配置 (configuration)" value="configuration" />
              <el-option label="流程 (process)" value="process" />
              <el-option label="规则 (rule)" value="rule" />
            </el-select>
          </template>
          <template v-else>
            <el-tag :type="contentTypeTagType(dialogForm.content_type)">{{ dialogForm.content_type || '未分类' }}</el-tag>
          </template>
        </el-form-item>
        <el-form-item label="快速检索">
          <template v-if="dialogMode !== 'view'">
            <el-input v-model="dialogForm.speed_lookup" placeholder="简短摘要，用于快速检索" maxlength="200" />
          </template>
          <template v-else>{{ dialogForm.speed_lookup || '-' }}</template>
        </el-form-item>
        <el-form-item label="优先级">
          <template v-if="dialogMode !== 'view'">
            <el-select v-model="dialogForm.priority" style="width: 200px">
              <el-option label="低 (2)" :value="2" />
              <el-option label="中 (4)" :value="4" />
              <el-option label="高 (6)" :value="6" />
              <el-option label="工作 (8)" :value="8" />
              <el-option label="紧急 (10)" :value="10" />
            </el-select>
          </template>
          <template v-else>
            <el-tag :type="priorityTagType(dialogForm.priority)">P{{ dialogForm.priority }} {{ priorityLabel(dialogForm.priority) }}</el-tag>
          </template>
        </el-form-item>
        <template v-if="dialogMode === 'view'">
          <el-form-item label="来源">{{ displaySource(dialogForm) || '-' }}</el-form-item>
          <el-form-item label="来源ID">{{ dialogForm.source_id || '-' }}</el-form-item>
          <el-form-item label="创建时间">{{ formatTime(dialogForm.created_at) || '-' }}</el-form-item>
          <el-form-item label="更新时间">{{ formatTime(dialogForm.updated_at) || '-' }}</el-form-item>
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">{{ dialogMode === 'view' ? '关闭' : '取消' }}</el-button>
          <el-button v-if="dialogMode !== 'view'" type="primary" :loading="dialogSaving" @click="handleDialogSave">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>
