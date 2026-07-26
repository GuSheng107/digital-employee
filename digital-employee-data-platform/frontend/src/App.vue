<script setup lang="ts">
import { DataLine, Monitor, Setting } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import Dashboard from './views/Dashboard.vue'
import DataItems from './views/DataItems.vue'
import SystemConfig from './views/SystemConfig.vue'

const activeView = ref('dashboard')

const currentComponent = computed(() => {
  if (activeView.value === 'system') return SystemConfig
  if (activeView.value === 'data-items') return DataItems
  return Dashboard
})
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="app-sidebar">
      <div class="brand">
        <strong>数字员工数据中台</strong>
        <span>Digital Employee</span>
      </div>
      <el-menu
        :default-active="activeView"
        class="side-menu"
        @select="activeView = String($event)"
      >
        <el-menu-item index="dashboard">
          <el-icon><Monitor /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="system">
          <el-icon><Setting /></el-icon>
          <span>System Config</span>
        </el-menu-item>
        <el-menu-item index="data-items">
          <el-icon><DataLine /></el-icon>
          <span>Data Items</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="app-main">
      <component :is="currentComponent" />
    </el-main>
  </el-container>
</template>
