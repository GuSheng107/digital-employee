<script setup>
import {
  Monitor,
  Cpu,
  Platform,
  ChatDotRound,
  SetUp,
  MagicStick,
  Document,
  FolderOpened,
  Calendar,
  Tools,
  Notebook,
  Star,
} from '@element-plus/icons-vue'

defineProps({
  activeView: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:activeView'])

const items = [
  { name: 'control', label: '工作台', icon: Monitor },
  { name: 'agent', label: 'Agents配置', icon: Cpu },
  { name: 'bot', label: 'Bot配置', icon: Platform },
  { name: 'chats', label: '会话管理', icon: ChatDotRound },
  { name: 'mcp', label: 'MCP配置', icon: SetUp },
  { name: 'skills', label: 'Skills配置', icon: MagicStick },
  { name: 'projectLogs', label: '日志查询', icon: Document },
  { name: 'data', label: '数据管理', icon: FolderOpened },
  { name: 'feedback', label: '反馈分析', icon: Star },
  { name: 'memory', label: '记忆管理', icon: Notebook },
  { name: 'tasks', label: '任务管理', icon: Calendar },
  { name: 'settings', label: '系统设置', icon: Tools },
]
</script>

<template>
  <aside class="rail">
    <div class="brand">
      <img class="brand-mark" src="/brand/wecom-agent-mark.svg" alt="WeCom Agent" />
      <div>
        <strong>WeCom Agent</strong>
        <span>Control Console</span>
      </div>
    </div>

    <button
      v-for="item in items"
      :key="item.name"
      :class="{ active: activeView === item.name }"
      @click="emit('update:activeView', item.name)"
    >
      <el-icon>
        <component :is="item.icon" />
      </el-icon>
      {{ item.label }}
    </button>
  </aside>
</template>
