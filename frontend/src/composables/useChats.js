import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import {
  archiveChat,
  cancelAiWork,
  compressChatContext,
  deleteChats as deleteChatsApi,
  generateAiDraftStream,
  getChatDetail,
  getChats,
  getManualReplyStatus,
  markAllBotChatsRead,
  markChatRead,
  pinChat,
  sendManualReply as sendManualReplyApi,
  setChatReplyMode,
  unarchiveChat,
  updateChatDisplayName,
  updateUserDisplayName,
} from '../api/runtime'
import { useRuntimeCore } from './useRuntimeCore'

let _instance = null

if (import.meta.hot) {
  import.meta.hot.accept(() => {
    _instance = null
  })
}

function _createSharedState() {
  const { activeBotKey, activeBot, activeBotStatus, status } = useRuntimeCore()

  const chats = ref([])
  const activeChatDetail = ref(null)
  const selectedChatIds = ref([])
  const activeChatId = ref('')
  const manualReply = ref('')
  const replyAttachments = ref([])
  const sendingReply = ref(false)
  const generatingAiReply = ref(false)
  const draftTraceId = ref('')
  const draftAbortController = ref(null)
  const deletingChats = ref(false)
  const loadingChats = ref(false)
  const loadingChatDetail = ref(false)
  const compressingContext = ref(false)
  const pendingDraftAfterCompress = ref(false)
  const lastLoadedBotKey = ref('')
  const reportedSendErrors = new Set()
  const chatPage = ref(1)
  const chatPageSize = 50
  const chatTotal = ref(0)
  const loadingMoreChats = ref(false)
  let attachmentSeed = 0
  let _loadChatsAbortController = null
  let _loadChatsRequestVersion = 0

  const hasMoreChats = computed(() => chats.value.length < chatTotal.value)

  const activeChat = computed(() => {
    const summary = chats.value.find((chat) => chat.chat_id === activeChatId.value) || chats.value[0] || null
    if (!summary) return null
    if (!activeChatDetail.value || activeChatDetail.value.chat_id !== summary.chat_id) {
      return summary
    }
    return {
      ...summary,
      ...activeChatDetail.value,
      messages: activeChatDetail.value.messages || [],
    }
  })
  const activeChatReplyMode = computed(() => activeChat.value?.reply_mode || 'manual')

  function getContextCompressionDisabledReason(chat = activeChat.value) {
    if (!chat) return '请先选择会话'
    if (chat.conversation_status === 'archived') {
      return '已归档会话不能压缩上下文'
    }
    const replyMode = String(chat.reply_mode || 'manual').trim().toLowerCase()
    if (replyMode !== 'ai') {
      return '手动回复模式不触发上下文压缩'
    }
    return ''
  }

  function chatSortTime(chat) {
    return Date.parse(chat.last_message_at || chat.created_at || '') || 0
  }

  function sortChatsByPriority(items) {
    return [...items].sort((left, right) => {
      const leftArchived = left.conversation_status === 'archived'
      const rightArchived = right.conversation_status === 'archived'
      if (leftArchived !== rightArchived) return leftArchived ? 1 : -1

      const leftIsMe = left.conversation_kind === 'me'
      const rightIsMe = right.conversation_kind === 'me'
      if (leftIsMe !== rightIsMe) return leftIsMe ? -1 : 1

      const pinRankDiff = Number(right.pin_rank || 0) - Number(left.pin_rank || 0)
      if (pinRankDiff !== 0) return pinRankDiff

      const pinnedDiff = Number(Boolean(right.pinned)) - Number(Boolean(left.pinned))
      if (pinnedDiff !== 0) return pinnedDiff

      const activityDiff = chatSortTime(right) - chatSortTime(left)
      if (activityDiff !== 0) return activityDiff

      return String(left.chat_id || '').localeCompare(String(right.chat_id || ''))
    })
  }

  const canManualReply = computed(() => Boolean(
    activeBotStatus.value.running &&
      activeChat.value &&
      activeChat.value.chat_id &&
      activeChat.value.chat_id !== 'unknown' &&
      (activeChatReplyMode.value === 'manual' || activeChat.value.last_send_error),
  ))

  const aiDisabledReason = computed(() => {
    if (activeChat.value?.last_send_error) {
      return '该会话最近发送失败，已自动切换到手动模式。请先手动发送成功后再重新启用 AI。'
    }
    if (!activeBot.value) {
      return '请先选择 Bot'
    }
    if (!String(activeBot.value.agent_provider || '').trim()) {
      return '该 Bot 未挂载 Agent，只能手动回复'
    }
    if (!String(status.value?.agent?.provider || '').trim()) {
      return '请先在系统设置中配置平台 Agent'
    }
    return ''
  })

  const canUseAiReply = computed(() => !aiDisabledReason.value)

  async function loadChats(manualTrigger = false) {
    if (!activeBotKey.value) {
      clearReplyAttachments()
      chats.value = []
      activeChatDetail.value = null
      activeChatId.value = ''
      lastLoadedBotKey.value = ''
      chatPage.value = 1
      chatTotal.value = 0
      loadingChats.value = false
      return
    }

    const currentBotKey = activeBotKey.value
    const isBotChanged = lastLoadedBotKey.value !== currentBotKey
    const isSilentRefresh = !manualTrigger && !isBotChanged

      if (manualTrigger || isBotChanged) {
        if (isBotChanged) {
          clearReplyAttachments()
          activeChatDetail.value = null
        }
      loadingChats.value = true
      if (isBotChanged) {
        lastLoadedBotKey.value = ''
        chatPage.value = 1
      }
    }

    const requestVersion = ++_loadChatsRequestVersion
    try {
      if (_loadChatsAbortController) {
        _loadChatsAbortController.abort()
      }
      _loadChatsAbortController = new AbortController()
      const loadId = _loadChatsAbortController.signal
      const result = await getChats({ bot_key: currentBotKey, page: 1, page_size: chatPageSize })
      if (loadId.aborted || requestVersion !== _loadChatsRequestVersion) return

      if (result.chats && result.chats.length > 0 || manualTrigger || isBotChanged) {
        chats.value = sortChatsByPriority(result.chats || [])
        chatTotal.value = result.page?.total || chats.value.length
        chatPage.value = 1
        selectedChatIds.value = selectedChatIds.value.filter((chatId) =>
          chats.value.some((chat) => chat.chat_id === chatId),
        )
        if (!chats.value.length) {
          activeChatId.value = ''
        } else if (!activeChatId.value || !chats.value.some((chat) => chat.chat_id === activeChatId.value)) {
          activeChatId.value = chats.value[0].chat_id
        }
        if (activeChatId.value && activeChatId.value !== 'unknown') {
          markChatRead(activeChatId.value).catch(() => undefined)
          await loadChatDetail(activeChatId.value, 200, isSilentRefresh)
        }
        lastLoadedBotKey.value = currentBotKey
        checkSendErrors()
      }
    } finally {
      loadingChats.value = false
    }
  }

  async function loadMoreChats() {
    if (!activeBotKey.value || loadingMoreChats.value || !hasMoreChats.value) return
    loadingMoreChats.value = true
    const nextPage = chatPage.value + 1
    try {
      const result = await getChats({ bot_key: activeBotKey.value, page: nextPage, page_size: chatPageSize })
      const newChats = result.chats || []
      const existingIds = new Set(chats.value.map((c) => c.chat_id))
      const uniqueNew = newChats.filter((c) => !existingIds.has(c.chat_id))
      if (uniqueNew.length) {
        chats.value = sortChatsByPriority([...chats.value, ...uniqueNew])
        chatTotal.value = result.page?.total || chatTotal.value
        chatPage.value = nextPage
      }
    } catch (error) {
      ElMessage.error(`加载更多会话失败：${error?.message || error}`)
    } finally {
      loadingMoreChats.value = false
    }
  }

  async function loadChatDetail(chatId, limit = 200, silent = false) {
    if (!chatId || chatId === 'unknown') {
      activeChatDetail.value = null
      return
    }
    if (!silent) {
      loadingChatDetail.value = true
    }
    try {
      const result = await getChatDetail(chatId, { limit })
      if (activeChatId.value !== chatId) return
      const newDetail = result.chat || null
      if (silent && activeChatDetail.value) {
        const oldMsgs = activeChatDetail.value.messages || []
        const newMsgs = newDetail?.messages || []
        const msgsUnchanged = oldMsgs.length === newMsgs.length &&
          (oldMsgs.length === 0 || oldMsgs[oldMsgs.length - 1]?.id === newMsgs[newMsgs.length - 1]?.id)
        const ctxUnchanged = (activeChatDetail.value.context?.used_chars ?? 0) === (newDetail?.context?.used_chars ?? 0)
        const metaKeys = [
          'reply_mode',
          'conversation_status',
          'last_send_error',
          'display_name',
          'unread_count',
          'updated_at',
        ]
        const metaUnchanged = metaKeys.every((key) => activeChatDetail.value?.[key] === newDetail?.[key])
        if (msgsUnchanged && ctxUnchanged && metaUnchanged) return
      }
      activeChatDetail.value = newDetail
    } catch (error) {
      if (!silent && activeChatId.value === chatId) {
        activeChatDetail.value = null
        ElMessage.error(error?.message || '加载会话详情失败')
      }
    } finally {
      if (!silent) {
        loadingChatDetail.value = false
      }
    }
  }

  async function selectChat(chatId) {
    if (activeChatId.value !== chatId) {
      clearReplyAttachments()
    }
    activeChatId.value = chatId
    activeChatDetail.value = null
    if (chatId && chatId !== 'unknown') {
      const chat = chats.value.find((c) => c.chat_id === chatId)
      if (chat) chat.unread_count = 0
      markChatRead(chatId).catch(() => undefined)
      await loadChatDetail(chatId)
    }
  }

  function addReplyAttachments(files) {
    const incoming = Array.from(files || [])
    if (!incoming.length) return
    const existingKeys = new Set(
      replyAttachments.value.map((item) => `${item.filename}:${item.size}:${item.lastModified}`),
    )
    const next = []
    for (const file of incoming) {
      if (!(file instanceof File)) continue
      const dedupeKey = `${file.name}:${file.size}:${file.lastModified}`
      if (existingKeys.has(dedupeKey)) continue
      existingKeys.add(dedupeKey)
      const kind = file.type.startsWith('image/')
        ? 'image'
        : file.type.startsWith('video/')
          ? 'video'
          : 'file'
      next.push({
        id: `reply-attachment-${attachmentSeed += 1}`,
        file,
        kind,
        filename: file.name,
        mimeType: file.type || '',
        size: file.size || 0,
        lastModified: file.lastModified || 0,
        previewUrl: kind === 'image' || kind === 'video'
          ? window.URL.createObjectURL(file)
          : '',
      })
    }
    if (next.length) {
      replyAttachments.value = [...replyAttachments.value, ...next]
    }
  }

  function removeReplyAttachment(attachmentId) {
    const target = replyAttachments.value.find((item) => item.id === attachmentId)
    if (target?.previewUrl) {
      window.URL.revokeObjectURL(target.previewUrl)
    }
    replyAttachments.value = replyAttachments.value.filter((item) => item.id !== attachmentId)
  }

  function clearReplyAttachments() {
    for (const item of replyAttachments.value) {
      if (item.previewUrl) {
        window.URL.revokeObjectURL(item.previewUrl)
      }
    }
    replyAttachments.value = []
  }

  function checkSendErrors() {
    const failedChats = chats.value.filter(
      (chat) => chat.last_send_error && chat.conversation_status !== 'archived',
    )
    const activeErrorKeys = new Set(
      failedChats.map((chat) => `${chat.chat_id}:${chat.last_send_error}`),
    )
    for (const key of [...reportedSendErrors]) {
      if (!activeErrorKeys.has(key)) {
        reportedSendErrors.delete(key)
      }
    }
    for (const chat of failedChats) {
      const errorKey = `${chat.chat_id}:${chat.last_send_error}`
      if (reportedSendErrors.has(errorKey)) {
        continue
      }
      reportedSendErrors.add(errorKey)
      ElMessage({
        type: 'warning',
        message: `会话「${chat.display_name || chat.chat_name || chat.chat_id}」发送失败，已自动切换到手动模式`,
        duration: 4000,
      })
    }
  }

  function setSelectedChatIds(ids) {
    selectedChatIds.value = ids
  }

  async function deleteSelectedChats() {
    if (!selectedChatIds.value.length) return

    const activeSelectedChat = chats.value.find((chat) => chat.chat_id === activeChatId.value)
    const isActiveSelectedChat = activeSelectedChat?.conversation_status === 'active'
    if (isActiveSelectedChat && selectedChatIds.value.includes(activeChatId.value)) {
      ElMessage.warning('活跃中的对话不能删除')
      return
    }

    // 确认删除弹窗
    try {
      await ElMessageBox.confirm(
        `确定要删除选中的 ${selectedChatIds.value.length} 个会话吗？删除后无法恢复。`,
        '确认删除',
        {
          type: 'warning',
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          distinguishCancelAndClose: true,
        }
      )
    } catch (error) {
      // 用户点击取消或关闭弹窗
      if (error !== 'cancel' && error !== 'close') {
        ElMessage.error(String(error))
      }
      return
    }

    deletingChats.value = true
    try {
      await deleteChatsApi(selectedChatIds.value)
      selectedChatIds.value = []
      await loadChats()
      ElMessage.success('会话已删除')
    } catch (error) {
      ElMessage.error(String(error))
    } finally {
      deletingChats.value = false
    }
  }

  async function sendManualReply() {
    if (!activeChat.value) return
    const content = manualReply.value.trim()
    if (!content && !replyAttachments.value.length) return
    sendingReply.value = true
    try {
      const sourceTraceId = resolveSourceTraceId(activeChat.value)
      const payload = buildManualReplyPayload({
        botKey: activeChat.value.bot_key || activeBotKey.value,
        externalChatId: activeChat.value.external_chat_id || activeChat.value.chat_id,
        chatName: activeChat.value.display_name || activeChat.value.chat_name,
        content,
        attachments: replyAttachments.value,
        sourceTraceId,
      })
      const response = await sendManualReplyApi(activeChat.value.chat_id, payload)
      manualReply.value = ''
      clearReplyAttachments()
      const commandId = response.command?.id || response.trace_id || ''
      const finalStatus = commandId ? await waitForManualReplyResult(commandId) : null
      await loadChats()
      if (finalStatus?.status === 'sent') {
        ElMessage.success('手动回复发送成功')
      } else if (finalStatus?.status === 'failed') {
        ElMessage.error(`手动回复发送失败：${finalStatus.error || '未知错误'}`)
      } else if (!finalStatus) {
        ElMessage.warning('手动回复已进入队列，仍在等待发送结果')
      }
    } catch (error) {
      // 手动回复发送队列失败时的处理
      ElMessage.error(error?.message || '手动回复发送失败')
    } finally {
      sendingReply.value = false
    }
  }

  async function handleSendFailed(chat, error = null) {
    await loadChats()
    const detail = error?.message || '发送失败'
    ElMessage.error(`${detail}；已自动切换到手动模式并禁用当前会话 AI`)
    try {
      await ElMessageBox.confirm(
        '该会话可能已失效，例如群聊已解散或用户已被注销。是否立即归档？\n\n如果暂不归档，该会话会保留在列表中，但只能继续手动回复。',
        '发送失败',
        {
          type: 'warning',
          confirmButtonText: '归档会话',
          cancelButtonText: '暂不归档',
        },
      )
      await archiveChat(chat.chat_id)
      await loadChats()
      ElMessage.success('会话已归档')
    } catch (promptError) {
      if (promptError !== 'cancel' && promptError !== 'close') {
        ElMessage.error(promptError?.message || String(promptError))
      }
    }
  }

  async function archiveSelectedChat(chatId) {
    try {
      const chat = chats.value.find((c) => c.chat_id === chatId)
      if (!chat) return
      await ElMessageBox.confirm('确定要归档该会话吗？', '确认归档', {
        type: 'warning',
        confirmButtonText: '归档',
        cancelButtonText: '取消',
      })
      await archiveChat(chatId)
      await loadChats()
      ElMessage.success('会话已归档')
    } catch (error) {
      if (error !== 'cancel') {
        ElMessage.error(String(error))
      }
    }
  }

  async function unarchiveSelectedChat(chatId) {
    try {
      await unarchiveChat(chatId)
      await loadChats()
      ElMessage.success('会话已恢复为活跃状态')
    } catch (error) {
      ElMessage.error(error?.message || String(error))
    }
  }

  let _manualReplyPollController = null

  async function waitForManualReplyResult(commandId, timeoutMs = 15000, intervalMs = 500) {
    _manualReplyPollController = new AbortController()
    const signal = _manualReplyPollController.signal
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      if (signal.aborted) return null
      try {
        const response = await getManualReplyStatus(commandId)
        const command = response.command || {}
        if (command.status === 'sent' || command.status === 'failed') {
          return command
        }
      } catch (error) {
      }
      await new Promise((resolve) => window.setTimeout(resolve, intervalMs))
    }
    return null
  }

  function cancelWaitForManualReply() {
    if (_manualReplyPollController) {
      _manualReplyPollController.abort()
      _manualReplyPollController = null
    }
  }

  async function generateManualAiReply() {
    if (!activeChat.value) return
    if (!canUseAiReply.value) {
      ElMessage.warning(aiDisabledReason.value)
      return
    }
    if (compressingContext.value) {
      ElMessage.info('当前会话正在压缩上下文，压缩完成后自动生成 AI 草稿')
      pendingDraftAfterCompress.value = true
      return
    }
    pendingDraftAfterCompress.value = false
    generatingAiReply.value = true
    draftTraceId.value = ''
    draftAbortController.value = new AbortController()
    manualReply.value = ''
    
    // 显示生成中提示
    const loadingMessage = ElMessage({
      message: '生成中 请勿离开页面',
      type: 'info',
      duration: 0,
    })
    
    const maxRetries = 2
    let attempt = 0
    try {
      while (attempt <= maxRetries) {
        try {
          const response = await generateAiDraftStream(
            activeChat.value.chat_id,
            {
              bot_key: activeBotKey.value,
              chat_name: activeChat.value.display_name || activeChat.value.chat_name,
            },
            draftAbortController.value.signal
          )
          if (!response.ok) {
            let errorDetail = response.statusText || '请求失败'
            try {
              const errorBody = await response.json()
              errorDetail = errorBody.detail || errorBody.message || errorDetail
            } catch { /* ignore */ }
            const error = new Error(errorDetail)
            error.response = response
            throw error
          }
          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''
            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'start') {
                  draftTraceId.value = data.trace_id || ''
                } else if (data.type === 'compressing') {
                  ElMessage.info(data.message || '当前会话正在压缩上下文，压缩完成后自动生成 AI 草稿')
                } else if (data.type === 'token' && data.content) {
                  manualReply.value += data.content
                } else if (data.type === 'done') {
                  draftTraceId.value = data.trace_id || ''
                } else if (data.type === 'cancelled') {
                  draftTraceId.value = data.trace_id || ''
                  loadingMessage.close()
                  ElMessage.info('AI 回复已取消')
                  return
                } else if (data.type === 'error') {
                  throw new Error(data.error || 'AI 回复生成失败')
                }
              } catch (e) {
                if (e.name !== 'SyntaxError') throw e
              }
            }
          }
          loadingMessage.close()
          ElMessage.success('AI 回复已生成，可检查后手动发送')
          return
        } catch (error) {
          if (error.name === 'AbortError') {
            loadingMessage.close()
            ElMessage.info('AI 回复已取消')
            return
          }
          const isNetworkError = !error?.response && (error?.name === 'TypeError' || error?.message?.includes('network') || error?.message?.includes('fetch') || error?.message?.includes('Failed to fetch') || error?.message?.includes('NetworkError'))
          if (isNetworkError && attempt < maxRetries && !manualReply.value) {
            if (draftTraceId.value) {
              try { await cancelAiWork(draftTraceId.value) } catch { /* ignore */ }
            }
            attempt += 1
            await new Promise((resolve) => window.setTimeout(resolve, 1000 * attempt))
            continue
          }
          throw error
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        loadingMessage.close()
        ElMessage.error(error?.message || String(error))
      }
    } finally {
      generatingAiReply.value = false
      draftAbortController.value = null
      draftTraceId.value = ''
    }
  }

  async function cancelAiDraft() {
    // 首先尝试中止当前的 fetch 请求
    if (draftAbortController.value) {
      draftAbortController.value.abort()
    }
    // 如果有 traceId，也调用后端取消接口
    if (draftTraceId.value) {
      try {
        await cancelAiWork(draftTraceId.value)
      } catch { /* ignore */ }
    }
  }

  async function compressActiveChatContext() {
    if (!activeChat.value || compressingContext.value) return
    const disabledReason = getContextCompressionDisabledReason(activeChat.value)
    if (disabledReason) {
      ElMessage.warning(disabledReason)
      return
    }
    compressingContext.value = true
    const loadingMessage = ElMessage({
      message: '压缩中 请勿离开页面',
      type: 'info',
      duration: 0,
    })
    try {
      const result = await compressChatContext(activeChat.value.chat_id)
      if (result?.usage) {
        const chat = chats.value.find((c) => c.chat_id === activeChat.value.chat_id)
        if (chat) {
          chat.context = result.usage
        }
      }
      await loadChats()
      loadingMessage.close()
      if (result?.triggered && !result?.compressed) {
        ElMessage.success('上下文压缩已完成或无需重复压缩')
      } else if (result?.compressed) {
        ElMessage.success('上下文已压缩')
      } else {
        ElMessage.info('当前无需压缩')
      }
    } catch (error) {
      loadingMessage.close()
      ElMessage.error(error?.message || String(error))
    } finally {
      compressingContext.value = false
      if (pendingDraftAfterCompress.value) {
        pendingDraftAfterCompress.value = false
        await generateManualAiReply()
      }
    }
  }

  async function renameActiveChat(displayName) {
    if (!activeChat.value) return
    try {
      await updateChatDisplayName(activeChat.value.chat_id, displayName)
      await loadChats()
      ElMessage.success(displayName ? '会话名已保存' : '会话名已清空')
    } catch (error) {
      ElMessage.error(String(error))
    }
  }

  async function renameUserDisplayName(payload) {
    const userId = String(payload?.sender_id || '').trim()
    if (!userId || userId === 'unknown') {
      ElMessage.warning('当前消息没有可保存的用户唯一标识')
      return
    }
    const currentCustomDisplayName = String(payload?.sender_custom_display_name || '').trim()
    const currentDisplayName = String(payload?.sender_display_name || payload?.sender_name || userId).trim() || userId
    try {
      const { value } = await ElMessageBox.prompt(
        `为用户「${currentDisplayName}」设置显示名称`,
        '编辑用户名称',
        {
          inputValue: currentCustomDisplayName,
          inputPlaceholder: '留空则恢复默认显示',
          confirmButtonText: '保存',
          cancelButtonText: '取消',
        },
      )
      const displayName = String(value || '').trim()
      if (displayName === currentCustomDisplayName) {
        return
      }
      await updateUserDisplayName(userId, displayName)
      await loadChats()
      ElMessage.success(displayName ? '用户显示名已保存' : '用户显示名已清空')
    } catch (error) {
      if (error === 'cancel' || error === 'close') {
        return
      }
      ElMessage.error(error?.message || String(error))
    }
  }

  async function toggleChatReplyMode(replyMode) {
    if (!activeChat.value) return
    if (replyMode === 'ai' && !canUseAiReply.value) {
      ElMessage.warning(aiDisabledReason.value)
      return
    }
    try {
      await setChatReplyMode(activeChat.value.chat_id, {
        reply_mode: replyMode,
        bot_key: activeBotKey.value,
      })
      await loadChats()
    } catch (error) {
      ElMessage.error(error?.message || String(error))
    }
  }

  async function markAllBotRead() {
    try {
      await markAllBotChatsRead(activeBotKey.value)
      await loadChats()
    } catch (error) {
      ElMessage.error(String(error))
    }
  }

  async function pinActiveChat(pinned = true) {
    if (!activeChat.value) return
    await pinChat(activeChat.value.chat_id, pinned)
    await loadChats()
  }

  function dispose() {
    clearReplyAttachments()
    cancelWaitForManualReply()
    reportedSendErrors.clear()
    chats.value = []
    selectedChatIds.value = []
    activeChatId.value = ''
    manualReply.value = ''
    sendingReply.value = false
    generatingAiReply.value = false
    draftTraceId.value = ''
    if (draftAbortController.value) {
      draftAbortController.value.abort()
      draftAbortController.value = null
    }
    deletingChats.value = false
    loadingChats.value = false
    activeChatDetail.value = null
    loadingChatDetail.value = false
    compressingContext.value = false
    lastLoadedBotKey.value = ''
    chatPage.value = 1
    chatTotal.value = 0
    loadingMoreChats.value = false
  }

  return {
    chats,
    selectedChatIds,
    activeChatId,
    manualReply,
    replyAttachments,
    activeChat,
    activeChatReplyMode,
    canManualReply,
    canUseAiReply,
    aiDisabledReason,
    sendingReply,
    generatingAiReply,
    draftTraceId,
    deletingChats,
    loadingChats,
    loadingChatDetail,
    loadingMoreChats,
    compressingContext,
    hasMoreChats,
    chatTotal,
    loadChats,
    loadMoreChats,
    selectChat,
    setSelectedChatIds,
    deleteSelectedChats,
    sendManualReply,
    addReplyAttachments,
    removeReplyAttachment,
    clearReplyAttachments,
    handleSendFailed,
    archiveSelectedChat,
    unarchiveSelectedChat,
    waitForManualReplyResult,
    generateManualAiReply,
    cancelAiDraft,
    compressActiveChatContext,
    renameActiveChat,
    renameUserDisplayName,
    toggleChatReplyMode,
    markAllBotRead,
    pinActiveChat,
    dispose,
  }
}

export function useChats() {
  if (!_instance) {
    _instance = _createSharedState()
  }
  return _instance
}

export function disposeChats() {
  if (_instance) {
    _instance.dispose()
    _instance = null
  }
}


function buildManualReplyPayload({ botKey, externalChatId, chatName, content, attachments, sourceTraceId }) {
  if (!attachments?.length) {
    const body = {
      bot_key: botKey,
      external_chat_id: externalChatId,
      chat_name: chatName,
      content,
    }
    if (sourceTraceId) {
      body.source_trace_id = sourceTraceId
    }
    return body
  }
  const body = new FormData()
  body.append('bot_key', botKey)
  body.append('external_chat_id', externalChatId)
  body.append('chat_name', chatName)
  body.append('content', content)
  if (sourceTraceId) {
    body.append('source_trace_id', sourceTraceId)
  }
  for (const attachment of attachments) {
    if (attachment?.file instanceof File) {
      body.append('files', attachment.file, attachment.filename || attachment.file.name)
    }
  }
  return body
}

function resolveSourceTraceId(chat) {
  if (!chat || !Array.isArray(chat.messages)) {
    return ''
  }
  for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
    const message = chat.messages[i]
    if (message?.direction !== 'user') {
      continue
    }
    const traceId = String(message?.metadata?.trace_id || '').trim()
    if (!traceId) {
      continue
    }
    if (message.reply_status === 'unreplied') {
      return traceId
    }
  }
  for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
    const traceId = String(chat.messages[i]?.metadata?.trace_id || '').trim()
    if (chat.messages[i]?.direction === 'user' && traceId) {
      return traceId
    }
  }
  return ''
}
