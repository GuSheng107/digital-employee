<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import UserManagementDialog from './components/auth/UserManagementDialog.vue'
import SideRail from './components/layout/SideRail.vue'
import TopBar from './components/layout/TopBar.vue'
import { changeOwnPassword } from './api/auth'
import { useAuthSession } from './composables/useAuthSession'
import { useRuntimeConsole } from './composables/useRuntimeConsole'
import LoginView from './views/LoginView.vue'

const AgentConfigView = defineAsyncComponent(() => import('./views/AgentConfigView.vue'))
const BotConfigView = defineAsyncComponent(() => import('./views/BotConfigView.vue'))
const ControlView = defineAsyncComponent(() => import('./views/ControlView.vue'))
const ConversationsView = defineAsyncComponent(() => import('./views/ConversationsView.vue'))
const DataManagementView = defineAsyncComponent(() => import('./views/DataManagementView.vue'))
const FeedbackStatsView = defineAsyncComponent(() => import('./views/FeedbackStatsView.vue'))
const McpConfigView = defineAsyncComponent(() => import('./views/McpConfigView.vue'))
const MemoryManagementView = defineAsyncComponent(() => import('./views/MemoryManagementView.vue'))
const ProjectLogsView = defineAsyncComponent(() => import('./views/ProjectLogsView.vue'))
const SkillsConfigView = defineAsyncComponent(() => import('./views/SkillsConfigView.vue'))
const SystemSettingsView = defineAsyncComponent(() => import('./views/SystemSettingsView.vue'))
const TaskManagementView = defineAsyncComponent(() => import('./views/TaskManagementView.vue'))

const consoleState = useRuntimeConsole()
const authSession = useAuthSession()
const {
  checked: authChecked,
  user: authUser,
  isAuthenticated,
  isAdmin,
  isGuest,
  initializeSession,
  login,
  logout,
  setRedirectTarget,
  consumeRedirectTarget,
} = authSession
const {
  activeBotKey,
  activeBotStatus,
  activeChat,
  activeChatId,
  activeChatReplyMode,
  activeView,
  aiDisabledReason,
  agents,
  archiveSelectedChat,
  unarchiveSelectedChat,
  bots,
  botStatuses,
  startingBots,
  stoppingBots,
  canManualReply,
  canUseAiReply,
  chats,
  compressingContext,
  compressActiveChatContext,
  dataOverview,
  deleteSelectedChats,
  deletingChats,
  exitSystem,
  generateManualAiReply,
  cancelAiDraft,
  generatingAiReply,
  initialize,
  loadChats,
  loadDataOverview,
  loadTokenUsage,
  loading,
  loadingChats,
  loadingChatDetail,
  manualReply,
  replyAttachments,
  markAllBotRead,
  optimizeData,
  optimizingData,
  platformSettings,
  refreshAll,
  renameActiveChat,
  renameUserDisplayName,
  removeReplyAttachment,
  selectBot,
  selectChat,
  selectedChatIds,
  sendManualReply,
  sendingReply,
  shutdownOverlay,
  startPolling,
  status,
  stopPolling,
  tokenUsage,
  toggleChatReplyMode,
  handleStartBot,
  handleStopBot,
  addReplyAttachments,
  setSelectedChatIds,
  hasMoreChats,
  loadingMoreChats,
  loadMoreChats,
} = consoleState

const activeAgents = computed(() => agents.value.filter((agent) => Boolean(agent.is_active)))
const authLoading = ref(false)
const userManagementVisible = ref(false)
const passwordDialogVisible = ref(false)
const passwordSaving = ref(false)
const passwordFormRef = ref(null)
const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const passwordRules = {
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [{
    validator: (_rule, value, callback) => {
      const text = String(value || '')
      if (text.length < 8) {
        callback(new Error('新密码至少需要 8 位'))
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
  confirm_password: [{
    validator: (_rule, value, callback) => {
      if (!value) {
        callback(new Error('请再次输入新密码'))
        return
      }
      if (value !== passwordForm.new_password) {
        callback(new Error('两次输入的新密码不一致'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

onMounted(async () => {
  await initializeSession()
  if (isAuthenticated.value) {
    await initialize()
  }
})
onBeforeUnmount(() => {
  stopPolling()
  consoleState.dispose()
})

watch(activeView, (newView) => {
  if (!isAuthenticated.value) {
    stopPolling()
    return
  }
  if (newView === 'control') {
    refreshAll()
    stopPolling()
    return
  }
  if (newView === 'data') {
    loadDataOverview()
    loadTokenUsage()
  }
  if (newView === 'chats') {
    loadChats()
    startPolling()
    return
  }
  stopPolling()
})

watch(isAuthenticated, (authenticated) => {
  if (!authenticated) {
    // 会话失效：记录当前视图作为登录后重定向目标，停止轮询
    if (activeView.value) {
      setRedirectTarget(activeView.value)
    }
    stopPolling()
  }
})

async function handleLogin(payload) {
  authLoading.value = true
  try {
    await login(payload.username, payload.password)
    ElMessage.success('登录成功')
    await initialize()
    // 登录成功后回跳到失效前的视图（重定向）
    const target = consumeRedirectTarget()
    if (target && target !== activeView.value) {
      activeView.value = target
    }
  } catch (error) {
    const status = error?.status
    const detail = error?.message || '登录失败'
    if (status === 401 || detail.includes('密码错误') || detail.includes('用户名')) {
      ElMessage.error('用户名或密码错误，请检查后重试')
    } else {
      ElMessage.error(detail)
    }
  } finally {
    authLoading.value = false
  }
}

async function handleLogout() {
  stopPolling()
  // 主动登出：清除重定向目标，避免下次登录被回跳到旧视图
  setRedirectTarget(null)
  await logout()
  ElMessage.success('已退出登录')
}

function openPasswordDialog() {
  if (isGuest.value) {
    return
  }
  Object.assign(passwordForm, {
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  passwordDialogVisible.value = true
}

async function savePassword() {
  await passwordFormRef.value?.validate()
  passwordSaving.value = true
  try {
    await changeOwnPassword(passwordForm.current_password, passwordForm.new_password)
    ElMessage.success('密码已修改')
    passwordDialogVisible.value = false
  } catch (error) {
    ElMessage.error(error?.message || String(error))
  } finally {
    passwordSaving.value = false
  }
}
</script>

<template>
  <main v-if="!authChecked" class="login-shell" v-loading="true" />

  <LoginView v-else-if="!isAuthenticated" :loading="authLoading" @login="handleLogin" />

  <main v-else class="shell">
    <SideRail v-model:active-view="activeView" />

    <section class="workspace" v-loading="loading">
      <TopBar
        :user="authUser"
        :is-admin="isAdmin"
        :is-guest="isGuest"
        @exit="exitSystem"
        @logout="handleLogout"
        @open-users="userManagementVisible = true"
        @change-password="openPasswordDialog"
      />

      <KeepAlive>
        <ControlView v-if="activeView === 'control'" :agents="agents" :bots="bots" :bot-statuses="botStatuses"
          :starting-bots="startingBots" :stopping-bots="stoppingBots"
          @start-bot="handleStartBot" @stop-bot="handleStopBot" />

        <AgentConfigView v-else-if="activeView === 'agent'" :agents="agents" :platform-settings="platformSettings" />

        <BotConfigView v-else-if="activeView === 'bot'" />

        <ConversationsView v-else-if="activeView === 'chats'" :active-chat="activeChat"
          :active-chat-id="activeChatId" :active-chat-reply-mode="activeChatReplyMode" :active-bot-key="activeBotKey" :active-bot-status="activeBotStatus" :bots="bots" :bot-statuses="botStatuses"
          :can-manual-reply="canManualReply" :can-use-ai="canUseAiReply" :ai-disabled-reason="aiDisabledReason" :chats="chats" :deleting-chats="deletingChats"
          :loading-chats="loadingChats" :loading-chat-detail="loadingChatDetail" :has-more="hasMoreChats" :loading-more="loadingMoreChats" :compressing-context="compressingContext"
          :manual-reply="manualReply" :reply-attachments="replyAttachments" :generating-ai-reply="generatingAiReply"
          :selected-chat-ids="selectedChatIds" :sending-reply="sendingReply" :status="status"
          @delete-selected-chats="deleteSelectedChats" @cancel-ai-draft="cancelAiDraft" @compress-context="compressActiveChatContext"
          @generate-ai-reply="generateManualAiReply" @rename-chat="renameActiveChat"
          @rename-user="renameUserDisplayName"
          @add-reply-attachments="addReplyAttachments" @remove-reply-attachment="removeReplyAttachment"
          @select-chat="selectChat" @select-bot="selectBot" @send-manual-reply="sendManualReply"
          @toggle-reply-mode="toggleChatReplyMode" @mark-all-bot-read="markAllBotRead"
          @update:selected-chat-ids="setSelectedChatIds" @update:manual-reply="manualReply = $event"
          @archive-chat="archiveSelectedChat" @unarchive-chat="unarchiveSelectedChat" @load-more-chats="loadMoreChats" />

        <McpConfigView v-else-if="activeView === 'mcp'" />

        <SkillsConfigView v-else-if="activeView === 'skills'" />

        <ProjectLogsView v-else-if="activeView === 'projectLogs'" />

        <DataManagementView v-else-if="activeView === 'data'" :data-overview="dataOverview" :token-usage="tokenUsage" :bot-statuses="botStatuses" :optimizing-data="optimizingData"
          @optimize-data="optimizeData" />

        <TaskManagementView v-else-if="activeView === 'tasks'" />

        <MemoryManagementView v-else-if="activeView === 'memory'" />

        <FeedbackStatsView v-else-if="activeView === 'feedback'" />

        <SystemSettingsView v-else-if="activeView === 'settings'" :agents="activeAgents" />
      </KeepAlive>
    </section>

    <div v-if="shutdownOverlay" class="shutdown-overlay">
      <section>
        <p>WeCom Agent Console</p>
        <h1 class="h1">系统已退出</h1>
        <span>所有 Bot 和 Web 控制台服务已关闭。浏览器阻止了自动关闭页面，可以直接关闭这个标签页。</span>
      </section>
    </div>

    <UserManagementDialog
      v-model="userManagementVisible"
      :current-user="authUser"
    />

    <el-dialog v-model="passwordDialogVisible" title="修改我的密码" width="420px">
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top">
        <el-form-item label="当前账号">
          <el-input :model-value="authUser?.username || ''" disabled />
        </el-form-item>
        <el-form-item label="当前密码" prop="current_password">
          <el-input
            v-model="passwordForm.current_password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="passwordForm.new_password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input
            v-model="passwordForm.confirm_password"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="savePassword"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="savePassword">保存</el-button>
      </template>
    </el-dialog>
  </main>
</template>
