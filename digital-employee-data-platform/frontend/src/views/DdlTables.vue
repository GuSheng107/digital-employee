<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '../api/request'
import {
  ddlColumnTypes,
  executeDdlTable,
  previewDdlTable,
  type DdlColumnDefinition,
  type DdlColumnType,
  type DdlTableDefinition,
} from '../api/ddl'

const loading = ref(false)
const executing = ref(false)
const ddlText = ref('')
const executionEnabled = ref(false)

const form = reactive<DdlTableDefinition>({
  schema_name: 'public',
  table_name: 'employee_profile',
  table_comment: 'employee profile table',
  columns: [
    {
      name: 'id',
      type: 'uuid',
      length: null,
      precision: null,
      scale: null,
      nullable: false,
      primary_key: true,
      default: 'gen_random_uuid()',
      comment: 'primary key',
    },
    {
      name: 'name',
      type: 'varchar',
      length: 100,
      precision: null,
      scale: null,
      nullable: false,
      primary_key: false,
      default: '',
      comment: 'display name',
    },
  ],
})

const tablePayload = computed<DdlTableDefinition>(() => ({
  schema_name: form.schema_name.trim(),
  table_name: form.table_name.trim(),
  table_comment: form.table_comment,
  columns: form.columns.map((column) => ({
    ...column,
    name: column.name.trim(),
    length: column.length || null,
    precision: column.precision || null,
    scale: column.scale || null,
    default: normalizeDefault(column),
  })),
}))

function addColumn() {
  form.columns.push({
    name: '',
    type: 'varchar',
    length: 100,
    precision: null,
    scale: null,
    nullable: true,
    primary_key: false,
    default: null,
    comment: '',
  })
}

function removeColumn(index: number) {
  if (form.columns.length === 1) {
    ElMessage.warning('至少保留一个字段')
    return
  }
  form.columns.splice(index, 1)
}

function onTypeChange(column: DdlColumnDefinition) {
  if (column.type === 'varchar') {
    column.length = column.length || 100
    column.precision = null
    column.scale = null
  } else if (column.type === 'numeric') {
    column.length = null
    column.precision = column.precision || 18
    column.scale = column.scale ?? 2
  } else {
    column.length = null
    column.precision = null
    column.scale = null
  }
}

function normalizeDefault(column: DdlColumnDefinition) {
  if (column.default === '' || column.default === undefined) return null
  if (column.type === 'boolean') return column.default === true || column.default === 'true'
  if (['smallint', 'integer', 'bigint'].includes(column.type)) return Number(column.default)
  if (column.type === 'numeric') return Number(column.default)
  if (column.type === 'json' || column.type === 'jsonb') {
    if (typeof column.default !== 'string') return column.default
    return JSON.parse(column.default || '{}')
  }
  return column.default
}

async function preview() {
  loading.value = true
  try {
    const response = await previewDdlTable(tablePayload.value)
    ddlText.value = response.data.ddl
    executionEnabled.value = response.data.execution_enabled
    ElMessage.success('DDL 预览已生成')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function execute() {
  if (!ddlText.value) await preview()
  try {
    await ElMessageBox.confirm(
      `确认在 ${form.schema_name}.${form.table_name} 创建表？后端会重新校验结构化参数，不会执行前端预览 SQL。`,
      '确认执行 DDL',
      {
        type: 'warning',
        confirmButtonText: '确认创建',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }

  executing.value = true
  try {
    const response = await executeDdlTable(tablePayload.value)
    ddlText.value = response.data.ddl
    ElMessage.success('表创建成功')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    executing.value = false
  }
}

function showLength(type: DdlColumnType) {
  return type === 'varchar'
}

function showPrecision(type: DdlColumnType) {
  return type === 'numeric'
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>DDL 建表工具</h2>
        <p>PostgreSQL 16 CREATE TABLE 预览与受控执行</p>
      </div>
      <div class="toolbar">
        <el-button :loading="loading" @click="preview">预览 DDL</el-button>
        <el-button type="primary" :loading="executing" @click="execute">确认创建表</el-button>
      </div>
    </div>

    <el-form label-width="110px" class="ddl-form">
      <el-form-item label="Schema">
        <el-input v-model="form.schema_name" />
      </el-form-item>
      <el-form-item label="表名">
        <el-input v-model="form.table_name" />
      </el-form-item>
      <el-form-item label="表注释">
        <el-input v-model="form.table_comment" />
      </el-form-item>
    </el-form>

    <div class="table-actions">
      <strong>字段定义</strong>
      <el-button size="small" type="primary" @click="addColumn">新增字段</el-button>
    </div>

    <el-table :data="form.columns" border class="ddl-column-table">
      <el-table-column label="字段名" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.name" placeholder="field_name" />
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">
          <el-select v-model="row.type" @change="onTypeChange(row)">
            <el-option v-for="type in ddlColumnTypes" :key="type" :label="type" :value="type" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="长度" width="120">
        <template #default="{ row }">
          <el-input-number
            v-if="showLength(row.type)"
            v-model="row.length"
            :min="1"
            :max="10000"
            controls-position="right"
          />
        </template>
      </el-table-column>
      <el-table-column label="精度/小数" width="190">
        <template #default="{ row }">
          <div v-if="showPrecision(row.type)" class="inline-number">
            <el-input-number v-model="row.precision" :min="1" :max="1000" controls-position="right" />
            <el-input-number v-model="row.scale" :min="0" :max="row.precision || 1000" controls-position="right" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="可空" width="80">
        <template #default="{ row }">
          <el-switch v-model="row.nullable" :disabled="row.primary_key" />
        </template>
      </el-table-column>
      <el-table-column label="主键" width="80">
        <template #default="{ row }">
          <el-switch
            v-model="row.primary_key"
            @change="row.primary_key ? (row.nullable = false) : undefined"
          />
        </template>
      </el-table-column>
      <el-table-column label="默认值" min-width="170">
        <template #default="{ row }">
          <el-input v-model="row.default" placeholder="安全字面量或允许表达式" />
        </template>
      </el-table-column>
      <el-table-column label="字段注释" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.comment" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ $index }">
          <el-button type="danger" size="small" @click="removeColumn($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      class="ddl-alert"
      :type="executionEnabled ? 'success' : 'warning'"
      :closable="false"
      :title="executionEnabled ? '当前后端配置允许执行 DDL。' : '当前后端配置未开启 DDL 执行，仍可使用预览功能。'"
    />

    <pre v-if="ddlText" class="result-box ddl-result">{{ ddlText }}</pre>
  </div>
</template>
