<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { Upload, MagicStick, Refresh, Plus, Edit } from '@element-plus/icons-vue'
import { useRuntimeConsole } from '../composables/useRuntimeConsole'
import { getSkills } from '../api/runtime'

const {
  uploadSkills,
  uploadingSkills,
  deleteSkill,
  toggleSkill,
  parseSkills,
} = useRuntimeConsole()

const dialogVisible = ref(false)
const uploading = ref(false)
const saving = ref(false)
const selectedFile = ref(null)
const parsedSkills = ref(null)
const editableSkills = ref([])
const uploadRef = ref(null)
const localSkills = ref([])
const loadingSkills = ref(false)

const sortedSkills = computed(() => {
  return [...localSkills.value].sort((a, b) => {
    const aIsSystem = isSystemSkill(a)
    const bIsSystem = isSystemSkill(b)
    if (aIsSystem && !bIsSystem) return -1
    if (!aIsSystem && bIsSystem) return 1
    return 0
  })
})

const editDialogVisible = ref(false)
const editingSkill = ref(null)
const editingDisplayName = ref('')
const savingSkillEdit = ref(false)

function isMountedByBot(skill) {
  return Boolean(skill?.is_bound_to_bot)
}

function isSystemSkill(skill) {
  return skill?.scope === 'system'
}

function mountedBotText(skill) {
  return (skill?.mounted_bot_names || []).join(', ')
}

async function loadSkills() {
  loadingSkills.value = true
  try {
    const result = await getSkills()
    localSkills.value = result.skills || []
    return true
  } catch (error) {
    ElMessage.error(String(error))
    return false
  } finally {
    loadingSkills.value = false
  }
}

async function handleRefresh() {
  const success = await loadSkills()
  if (success) {
    ElMessage.success('Skills 已刷新')
  }
}

function openDialog() {
  dialogVisible.value = true
  resetDialog()
}

function resetDialog() {
  selectedFile.value = null
  parsedSkills.value = null
  editableSkills.value = []
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

function handleClose() {
  dialogVisible.value = false
  setTimeout(resetDialog)
}

function openEditDialog(skill) {
  editingSkill.value = skill
  editingDisplayName.value = skill.display_name || skill.name
  editDialogVisible.value = true
}

function closeEditDialog() {
  editDialogVisible.value = false
  editingSkill.value = null
  editingDisplayName.value = ''
}

async function handleFileChange(file) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    ElMessage.error('只支持上传 zip 文件')
    return false
  }
  selectedFile.value = file.raw
  await doParse()
  return false
}

async function doParse() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const result = await parseSkills(selectedFile.value)
    parsedSkills.value = result
    editableSkills.value = (result.skills || []).map((skill) => ({
      ...skill,
      display_name: skill.display_name || skill.name,
    }))
  } catch (error) {
    parsedSkills.value = null
    editableSkills.value = []
  } finally {
    uploading.value = false
  }
}

async function handleSave() {
  if (!selectedFile.value || !editableSkills.value.length) return
  saving.value = true
  try {
    const displayNames = Object.fromEntries(
      editableSkills.value.map((skill) => [
        skill.name,
        (skill.display_name || skill.name).trim() || skill.name,
      ]),
    )
    const ok = await uploadSkills(selectedFile.value, displayNames, 'new')
    if (!ok) {
      return
    }
    ElMessage.success('技能已上传并保存')
    dialogVisible.value = false
    resetDialog()
    await loadSkills()
  } finally {
    saving.value = false
  }
}

async function handleSaveSkillEdit() {
  if (!editingSkill.value) return
  savingSkillEdit.value = true
  try {
    const displayName = editingDisplayName.value.trim() || editingSkill.value.name
    const ok = await uploadSkills(
      null,
      { [editingSkill.value.name]: displayName },
      'edit',
      editingSkill.value.name,
    )
    if (!ok) {
      return
    }
    ElMessage.success('技能名称已保存')
    closeEditDialog()
    await loadSkills()
  } finally {
    savingSkillEdit.value = false
  }
}

async function handleToggle(newEnabled, skill) {
  const ok = await toggleSkill(skill.name, newEnabled)
  if (!ok) {
    skill.enabled = !newEnabled
    return
  }
  ElMessage.success(newEnabled ? '技能已启用' : '技能已禁用')
  await loadSkills()
}

async function handleDelete(skill) {
  try {
    await ElMessageBox.confirm(
      `确定要删除技能「${skill.display_name || skill.name}」吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    const ok = await deleteSkill(skill.name)
    if (!ok) {
      return
    }
    ElMessage.success('技能已删除')
    await loadSkills()
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = error?.message || '删除失败'
      ElMessage.error(errorMsg)
    }
  }
}

onMounted(() => {
  loadSkills()
})

onActivated(() => {
  loadSkills()
})
</script>

<template>
  <div class="skills-config">
    <div class="header">
      <h2>Skills 配置</h2>
      <div class="actions">
        <el-button type="primary" :icon="Refresh" @click="handleRefresh" :loading="loadingSkills">
          刷新技能
        </el-button>
        <el-button type="primary" :icon="Plus" @click="openDialog">
          新增技能
        </el-button>
      </div>
    </div>

    <div class="skills-container">
      <div class="skills-grid">
        <div v-if="!sortedSkills.length" class="empty-state">
          <el-icon size="64"><MagicStick /></el-icon>
          <p>暂无技能，请点击“新增技能”上传 zip 文件</p>
        </div>

        <el-card
          v-for="skill in sortedSkills"
          :key="skill.name"
          class="skill-card"
          shadow="hover"
        >
          <div class="skill-header">
            <div class="skill-title-group">
              <div class="skill-name">{{ skill.display_name || skill.name }}</div>
              <div class="skill-code-name">{{ skill.name }}</div>
            </div>
            <div class="skill-tags">
              <el-tag v-if="isSystemSkill(skill)" type="warning" size="small">系统</el-tag>
              <el-tag v-if="skill.mounted_bot_count" type="danger" size="small">Mounted {{ skill.mounted_bot_count }} </el-tag>
              <el-switch
                v-model="skill.enabled"
                :disabled="isSystemSkill(skill) || (isMountedByBot(skill) && skill.enabled)"
                @change="(val) => handleToggle(val, skill)"
                active-text="已启用"
                inactive-text="已禁用"
              />
            </div>
          </div>
          <div class="skill-description">{{ skill.description || '暂无描述' }}</div>
          <div class="skill-footer">
            <el-button type="primary" size="small" link :icon="Edit" @click="openEditDialog(skill)">
              {{ isSystemSkill(skill) ? '查看' : '编辑' }}
            </el-button>
            <el-button type="danger" size="small" link @click="handleDelete(skill)" :disabled="isSystemSkill(skill)">
              删除
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      title="新增技能"
      width="600px"
      :close-on-click-modal="false"
      @closed="resetDialog"
    >
      <div class="upload-section">
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :on-change="handleFileChange"
          :show-file-list="false"
          accept=".zip"
          :disabled="uploading || saving"
        >
          <el-icon class="el-icon--upload"><Upload /></el-icon>
          <div class="el-upload__text">
            将 zip 文件拖到此处，或<em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              请上传包含技能定义的 zip 文件
            </div>
          </template>
        </el-upload>
      </div>

      <div v-if="parsedSkills && parsedSkills.ok" class="preview-section">
        <el-divider>解析结果</el-divider>
        <p class="preview-summary">
          共找到 {{ editableSkills.length }} 个技能文件
        </p>
        <div class="preview-list">
          <div v-for="skill in editableSkills" :key="skill.relative_path" class="preview-item">
            <div class="preview-field">
              <label>技能名称</label>
              <el-input v-model="skill.display_name" placeholder="请输入技能显示名称" />
            </div>
            <div class="preview-field">
              <label>原始标识</label>
              <el-input :model-value="skill.name" readonly />
            </div>
            <div class="preview-field">
              <label>技能描述</label>
              <el-input
                :model-value="skill.description || '暂无描述'"
                type="textarea"
                :rows="2"
                readonly
              />
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="handleClose" :disabled="uploading || saving">取消</el-button>
        <el-button
          type="primary"
          @click="handleSave"
          :loading="saving"
          :disabled="!editableSkills.length || uploading"
        >
          确认保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editDialogVisible"
      :title="isSystemSkill(editingSkill) ? '查看技能' : '编辑技能'"
      width="520px"
      :close-on-click-modal="false"
      @closed="closeEditDialog"
    >
      <div v-if="editingSkill" class="skill-edit-form">
        <div class="preview-field">
          <label>技能名称</label>
          <el-input v-model="editingDisplayName" maxlength="100" show-word-limit :disabled="isSystemSkill(editingSkill)" />
        </div>
        <div class="preview-field">
          <label>原始标识</label>
          <el-input :model-value="editingSkill.name" readonly />
        </div>
        <div class="preview-field">
          <label>技能描述</label>
          <el-input
            :model-value="editingSkill.description || '暂无描述'"
            type="textarea"
            :rows="4"
            readonly
          />
        </div>
      </div>

      <template #footer>
        <el-button @click="closeEditDialog" :disabled="savingSkillEdit">关闭</el-button>
        <el-button v-if="!isSystemSkill(editingSkill)" type="primary" @click="handleSaveSkillEdit" :loading="savingSkillEdit">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
