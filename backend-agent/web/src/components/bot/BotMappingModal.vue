<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { Check } from '@element-plus/icons-vue'
import { getBotSkills, saveBotSkills, getBotMcpServers, saveBotMcpServers } from '../../api/runtime'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  bot: {
    type: Object,
    default: null
  },
  type: {
    type: String,
    default: 'skills'
  }
})

const emit = defineEmits(['update:modelValue', 'saved'])

const localVisible = ref(props.modelValue)
const loading = ref(false)
const saving = ref(false)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const allItems = ref([])
const checkedIds = ref([])

const modalTitle = computed(() => {
  if (props.type === 'skills') {
    return `Skills 配置 - ${props.bot?.name || ''}`
  }
  return `MCP 配置 - ${props.bot?.name || ''}`
})

const filteredItems = computed(() => {
  let items = allItems.value.filter(item => item.scope !== 'system')
  if (!searchKeyword.value) {
    return items
  }
  const keyword = searchKeyword.value.toLowerCase()
  return items.filter(item => {
    if (props.type === 'skills') {
      return (item.display_name || item.name || '').toLowerCase().includes(keyword)
    }
    return (item.name || '').toLowerCase().includes(keyword)
  })
})

const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredItems.value.slice(start, end)
})

const totalItems = computed(() => filteredItems.value.length)
const totalPages = computed(() => Math.ceil(totalItems.value / pageSize.value))

async function loadData() {
  if (!props.bot?.bot_key) return

  loading.value = true
  try {
    if (props.type === 'skills') {
      const result = await getBotSkills(props.bot.bot_key)
      allItems.value = result.all_skills || []
      checkedIds.value = result.checked_skill_names || []
    } else {
      const result = await getBotMcpServers(props.bot.bot_key)
      allItems.value = result.all_servers || []
      checkedIds.value = result.checked_server_ids || []
    }
    currentPage.value = 1
    searchKeyword.value = ''
  } catch (error) {
    ElMessage.error(props.type === 'skills' ? '获取 Skills 数据失败' : '获取 MCP 数据失败')
  } finally {
    loading.value = false
  }
}

async function saveData() {
  if (!props.bot?.bot_key) return

  saving.value = true
  try {
    if (props.type === 'skills') {
      await saveBotSkills(props.bot.bot_key, checkedIds.value)
    } else {
      await saveBotMcpServers(props.bot.bot_key, checkedIds.value)
    }
    ElMessage.success(props.type === 'skills' ? 'Skills 映射已保存' : 'MCP 映射已保存')
    emit('saved')
    closeModal()
  } catch (error) {
    ElMessage.error(props.type === 'skills' ? '保存 Skills 失败' : '保存 MCP 失败')
  } finally {
    saving.value = false
  }
}

function closeModal() {
  localVisible.value = false
  emit('update:modelValue', false)
}

function handlePageChange(page) {
  currentPage.value = page
}

function handleSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
}

function isChecked(id) {
  return checkedIds.value.includes(id)
}

function toggleCheck(id) {
  const index = checkedIds.value.indexOf(id)
  if (index > -1) {
    checkedIds.value.splice(index, 1)
  } else {
    checkedIds.value.push(id)
  }
}

watch(() => props.modelValue, (newVal) => {
  localVisible.value = newVal
  if (newVal && props.bot) {
    loadData()
  }
})

watch(localVisible, (newVal) => {
  emit('update:modelValue', newVal)
})
</script>

<template>
  <el-dialog
    v-model="localVisible"
    :title="modalTitle"
    width="700px"
    :close-on-click-modal="false"
    @closed="() => { searchKeyword = ''; currentPage = 1 }"
  >
    <div class="mapping-modal-wrapper">
      <div class="search-section">
        <el-input
          v-model="searchKeyword"
          :placeholder="type === 'skills' ? '搜索 Skills（按显示名称）' : '搜索 MCP（按名称）'"
          clearable
          prefix-icon="Search"
        />
      </div>

      <div v-loading="loading" class="mapping-content">
        <div v-if="!loading && allItems.length === 0" class="mapping-empty">
          {{ type === 'skills' ? '暂无全局已启用的 Skills' : '暂无全局已启用的 MCP 服务' }}
        </div>

        <div v-else class="mapping-list">
          <div
            v-for="item in pagedItems"
            :key="type === 'skills' ? item.name : item.server_id"
            class="mapping-item"
            :class="{ checked: isChecked(type === 'skills' ? item.name : item.server_id) }"
            @click="toggleCheck(type === 'skills' ? item.name : item.server_id)"
          >
            <div class="item-checkbox">
              <el-icon :class="isChecked(type === 'skills' ? item.name : item.server_id) ? 'checked' : ''">
                <Check v-if="isChecked(type === 'skills' ? item.name : item.server_id)" />
              </el-icon>
            </div>
            <div class="item-info">
              <div class="item-name">
                {{ type === 'skills' ? (item.display_name || item.name) : item.name }}
              </div>
              <div class="item-desc" v-if="type === 'skills' && item.description">
                {{ item.description }}
              </div>
              <div class="item-desc" v-else-if="type === 'mcp'">
                {{ item.server_type }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="totalPages > 1" class="pagination-section">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="totalItems"
          layout="total, sizes, prev, pager, next"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="closeModal">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveData">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
