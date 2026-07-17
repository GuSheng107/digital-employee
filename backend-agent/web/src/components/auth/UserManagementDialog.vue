<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import { Delete, Edit, Key, Plus, Refresh } from '@element-plus/icons-vue'
import { formatTime } from '../../utils/format'
import {
  createConsoleUser,
  deleteConsoleUser,
  getConsoleUsers,
  getGuestAccount,
  kickConsoleUser,
  resetConsoleUserPassword,
  updateConsoleUser,
} from '../../api/auth'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  currentUser: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const users = ref([])
const loading = ref(false)
const saving = ref(false)
const editorVisible = ref(false)
const passwordVisible = ref(false)
const editingUsername = ref('')
const passwordUsername = ref('')
const guestAccount = ref(null)

const userFormRef = ref(null)
const passwordFormRef = ref(null)

const userForm = reactive({
  username: '',
  display_name: '',
  password: '',
  user_type: 'registered',
})

const passwordForm = reactive({
  password: '',
})

const isEditing = computed(() => Boolean(editingUsername.value))

const userRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{
    validator: (_rule, value, callback) => {
      const text = String(value || '')
      if (isEditing.value) {
        callback()
        return
      }
      if (text.length < 8) {
        callback(new Error('密码至少需要 8 位'))
        return
      }
      if (!/^[A-Za-z0-9]+$/.test(text)) {
        callback(new Error('密码只能包含英文字母和数字'))
        return
      }
      if (!/[A-Za-z]/.test(text) || !/\d/.test(text)) {
        callback(new Error('密码必须同时包含英文字母和数字'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

const passwordRules = {
  password: [{
    validator: (_rule, value, callback) => {
      const text = String(value || '')
      if (text.length < 8) {
        callback(new Error('密码至少需要 8 位'))
        return
      }
      if (!/^[A-Za-z0-9]+$/.test(text)) {
        callback(new Error('密码只能包含英文字母和数字'))
        return
      }
      if (!/[A-Za-z]/.test(text) || !/\d/.test(text)) {
        callback(new Error('密码必须同时包含英文字母和数字'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

watch(() => props.modelValue, (opened) => {
  if (opened) {
    loadUsers()
    loadGuestAccount()
  }
})

async function loadUsers() {
  loading.value = true
  try {
    const response = await getConsoleUsers()
    const allUsers = response.users || []
    users.value = allUsers.filter((u) => u.username !== props.currentUser?.username)
  } catch (error) {
    ElMessage.error(error?.message || '加载用户失败')
  } finally {
    loading.value = false
  }
}

async function loadGuestAccount() {
  try {
    const response = await getGuestAccount()
    guestAccount.value = response.guest_account || null
  } catch {
    guestAccount.value = null
  }
}

function openCreate() {
  editingUsername.value = ''
  Object.assign(userForm, {
    username: '',
    display_name: '',
    password: '',
    user_type: 'registered',
  })
  editorVisible.value = true
}

function openEdit(row) {
  editingUsername.value = row.username
  Object.assign(userForm, {
    username: row.username,
    display_name: row.display_name || '',
    password: '',
    user_type: row.user_type || 'registered',
  })
  editorVisible.value = true
}

async function saveUser() {
  await userFormRef.value?.validate()
  saving.value = true
  try {
    if (isEditing.value) {
      await updateConsoleUser(editingUsername.value, {
        display_name: userForm.display_name,
        user_type: userForm.user_type,
      })
      ElMessage.success('用户已更新')
    } else {
      await createConsoleUser({
        username: userForm.username,
        display_name: userForm.display_name,
        password: userForm.password,
        user_type: userForm.user_type,
      })
      ElMessage.success('用户已添加')
    }
    editorVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    saving.value = false
  }
}

function openResetPassword(row) {
  passwordUsername.value = row.username
  passwordForm.password = ''
  passwordVisible.value = true
}

async function savePassword() {
  await passwordFormRef.value?.validate()
  saving.value = true
  try {
    await resetConsoleUserPassword(passwordUsername.value, passwordForm.password)
    ElMessage.success('密码已重置')
    passwordVisible.value = false
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    saving.value = false
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(`确定要删除用户「${row.username}」吗？`, '删除用户', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await deleteConsoleUser(row.username)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || String(error))
    }
  }
}

async function kickUser(row) {
  try {
    await ElMessageBox.confirm(`确定要让用户「${row.username}」强制下线吗？`, '强制下线', {
      type: 'warning',
      confirmButtonText: '下线',
      cancelButtonText: '取消',
    })
    await kickConsoleUser(row.username)
    ElMessage.success('已强制下线')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || String(error))
    }
  }
}

async function kickGuest() {
  if (!guestAccount.value) return
  try {
    await ElMessageBox.confirm('确定要让所有游客账号强制下线吗？', '强制下线', {
      type: 'warning',
      confirmButtonText: '下线',
      cancelButtonText: '取消',
    })
    await kickConsoleUser(guestAccount.value.username)
    ElMessage.success('游客账号已全部强制下线')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || String(error))
    }
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="用户管理" width="900px" class="user-admin-dialog">
    <div v-if="guestAccount" class="guest-account-bar">
      <el-alert :closable="false" type="info">
        <template #title>
          <span>游客账号：<strong>{{ guestAccount.username }}</strong> / 密码：<strong>{{ guestAccount.password }}</strong></span>
          <el-button link type="warning" size="small" style="margin-left: 12px;" @click="kickGuest">全部下线</el-button>
        </template>
      </el-alert>
    </div>
    <div class="user-admin-toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">添加用户</el-button>
      <el-button :icon="Refresh" :loading="loading" @click="loadUsers">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="users" class="user-admin-table">
      <el-table-column prop="username" label="用户名" min-width="150" />
      <el-table-column prop="display_name" label="显示名" min-width="140">
        <template #default="{ row }">{{ row.display_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'primary' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="user_type" label="用户类型" width="110">
        <template #default="{ row }">
          <el-tag :type="row.user_type === 'internal' ? 'success' : 'info'" size="small" effect="plain">
            {{ row.user_type === 'internal' ? '内部主体' : '注册用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_online" label="状态" width="90">
        <template #default="{ row }">
          <span class="online-status" :class="{ online: row.is_online }">
            <span class="status-dot" />
            <span class="status-text">{{ row.is_online ? '在线' : '离线' }}</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" min-width="170">
        <template #default="{ row }">{{ formatTime(row.last_login_at) || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" :icon="Key" @click="openResetPassword(row)">重置密码</el-button>
          <el-button link type="warning" @click="kickUser(row)">下线</el-button>
          <el-button
            link
            type="danger"
            :icon="Delete"
            :disabled="row.username === currentUser?.username"
            @click="removeUser(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editorVisible" :title="isEditing ? '编辑用户' : '添加用户'" width="440px" append-to-body>
      <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" :disabled="isEditing" maxlength="64" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="userForm.display_name" maxlength="80" />
        </el-form-item>
        <el-form-item label="用户类型">
          <el-select v-model="userForm.user_type" placeholder="选择用户类型">
            <el-option label="注册用户" value="registered" />
            <el-option label="内部主体" value="internal" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!isEditing" label="初始密码" prop="password">
          <el-input v-model="userForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordVisible" title="重置密码" width="420px" append-to-body>
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top">
        <el-form-item :label="`用户：${passwordUsername}`" prop="password">
          <el-input v-model="passwordForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePassword">保存</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.guest-account-bar {
  margin-bottom: 12px;
}

.online-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #909399;
}

.online-status.online {
  color: #67c23a;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #c0c4cc;
  position: relative;
}

.online-status.online .status-dot {
  background-color: #67c23a;
}

.online-status.online .status-dot::after {
  content: '';
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: -2px;
  border-radius: 50%;
  border: 2px solid #67c23a;
  opacity: 0.4;
  animation: status-pulse 2s ease-in-out infinite;
}

@keyframes status-pulse {
  0% {
    transform: scale(1);
    opacity: 0.4;
  }
  50% {
    transform: scale(1.3);
    opacity: 0;
  }
  100% {
    transform: scale(1);
    opacity: 0.4;
  }
}
</style>
