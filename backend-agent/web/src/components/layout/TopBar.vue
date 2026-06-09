<script setup>
import { Key, UserFilled, SwitchButton, Setting } from '@element-plus/icons-vue'

defineProps({
  user: {
    type: Object,
    default: null,
  },
  isAdmin: {
    type: Boolean,
    default: false,
  },
  isGuest: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['exit', 'logout', 'open-users', 'change-password'])
</script>

<template>
  <header class="topbar">
    <div>
      <p class="eyebrow">Local Runtime</p>
      <h1>企微数字员工V1.0</h1>
    </div>
    <div class="topbar-actions">
      <div v-if="user" class="topbar-user">
        <el-icon><UserFilled /></el-icon>
        <span>{{ user.display_name || user.username }}</span>
        <em>{{ user.role === 'admin' ? '管理员' : user.role === 'guest' ? '游客' : '普通用户' }}</em>
      </div>
      <el-button v-if="isAdmin" :icon="Setting" @click="emit('open-users')">
        用户管理
      </el-button>
      <el-button v-if="!isGuest" :icon="Key" @click="emit('change-password')">
        修改密码
      </el-button>
      <el-button :icon="SwitchButton" @click="emit('logout')">
        退出登录
      </el-button>
      <el-button v-if="!isGuest" type="danger" @click="emit('exit')">
        退出系统
      </el-button>
    </div>
  </header>
</template>
