<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '../api/request'
import {
  createDataItem,
  deleteDataItem,
  listDataItems,
  updateDataItem,
  type DataItem,
  type DataItemPayload,
} from '../api/dataItems'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const jsonDialogVisible = ref(false)
const editingId = ref('')
const namespaceFilter = ref('')
const items = ref<DataItem[]>([])
const currentJson = ref('')

const form = reactive({
  namespace: 'default',
  item_key: '',
  description: '',
  item_value_text: '{\n  "hello": "world"\n}',
})

function resetForm() {
  editingId.value = ''
  form.namespace = 'default'
  form.item_key = ''
  form.description = ''
  form.item_value_text = '{\n  "hello": "world"\n}'
}

function parsePayload(): DataItemPayload {
  return {
    namespace: form.namespace,
    item_key: form.item_key,
    description: form.description,
    item_value: JSON.parse(form.item_value_text || '{}'),
  }
}

async function loadItems() {
  loading.value = true
  try {
    const response = await listDataItems(namespaceFilter.value)
    items.value = response.data
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(item: DataItem) {
  editingId.value = item.id
  form.namespace = item.namespace
  form.item_key = item.item_key
  form.description = item.description
  form.item_value_text = JSON.stringify(item.item_value, null, 2)
  dialogVisible.value = true
}

async function saveItem() {
  saving.value = true
  try {
    const payload = parsePayload()
    if (editingId.value) {
      await updateDataItem(editingId.value, payload)
      ElMessage.success('数据项已更新')
    } else {
      await createDataItem(payload)
      ElMessage.success('数据项已创建')
    }
    dialogVisible.value = false
    await loadItems()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeItem(item: DataItem) {
  try {
    await ElMessageBox.confirm(`确认删除 ${item.item_key}？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteDataItem(item.id)
    ElMessage.success('数据项已删除')
    await loadItems()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

function showJson(item: DataItem) {
  currentJson.value = JSON.stringify(item.item_value, null, 2)
  jsonDialogVisible.value = true
}

onMounted(loadItems)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Data Items</h2>
        <p>验证 PostgreSQL 数据读写链路</p>
      </div>
      <el-button type="primary" @click="openCreate">新增数据项</el-button>
    </div>

    <div class="toolbar">
      <el-input
        v-model="namespaceFilter"
        clearable
        placeholder="按 namespace 过滤"
        class="filter-input"
        @keyup.enter="loadItems"
      />
      <el-button :loading="loading" @click="loadItems">查询列表</el-button>
    </div>

    <el-table v-loading="loading" :data="items" border>
      <el-table-column prop="namespace" label="Namespace" width="150" />
      <el-table-column prop="item_key" label="Key" min-width="180" />
      <el-table-column prop="description" label="描述" min-width="180" />
      <el-table-column prop="created_at" label="创建时间" width="220" />
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="showJson(row)">JSON</el-button>
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="removeItem(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑数据项' : '新增数据项'"
      width="720px"
    >
      <el-form label-width="110px">
        <el-form-item label="Namespace">
          <el-input v-model="form.namespace" />
        </el-form-item>
        <el-form-item label="Key">
          <el-input v-model="form.item_key" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" />
        </el-form-item>
        <el-form-item label="JSON Value">
          <el-input
            v-model="form.item_value_text"
            type="textarea"
            :rows="10"
            spellcheck="false"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="jsonDialogVisible" title="JSON 内容" width="640px">
      <pre class="result-box">{{ currentJson }}</pre>
    </el-dialog>
  </div>
</template>
