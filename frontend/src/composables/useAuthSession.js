import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getCurrentSession, loginConsole, logoutConsole } from '../api/auth'
import {
  setAuthFailureHandler,
  setAuthTokenProvider,
  setRefreshTokenProvider,
  setOnTokensRefreshed,
} from '../api/http'

const STORAGE_KEY = 'wecom.console.session'
const RT_STORAGE_KEY = 'wecom.console.refresh'

const checked = ref(false)
const token = ref('')           // access_token
const refreshTok = ref('')      // refresh_token
const expiresAt = ref(0)
const user = ref(null)
let initialized = false
let expiryTimer = null

function scheduleExpiry(nextExpiresAt) {
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  const delay = Number(nextExpiresAt || 0) * 1000 - Date.now()
  if (delay <= 0) {
    return
  }
  expiryTimer = window.setTimeout(() => {
    // token 即将过期 — 尝试主动刷新
    if (refreshTok.value) {
      import('../api/auth').then(({ refreshToken }) => {
        refreshToken(refreshTok.value)
          .then((data) => persistTokens(data))
          .catch(() => clearSession())
      })
    }
  }, Math.min(delay, 2147483647))
}

function readStoredSession() {
  try {
    const session = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}')
    const rt = window.sessionStorage.getItem(RT_STORAGE_KEY) || ''
    return { ...session, _refresh_token: rt }
  } catch {
    return {}
  }
}

function isStoredSessionFresh(session) {
  const storedToken = String(session?.token || session?.access_token || '').trim()
  const storedExpiresAt = Number(session?.expires_at || 0)
  return Boolean(storedToken && storedExpiresAt && storedExpiresAt * 1000 > Date.now())
}

function persistTokens(payload) {
  // 支持双 token (payload.access_token) 和旧版单 token (payload.token)
  const nextToken = String(payload?.access_token || payload?.token || '').trim()
  const nextRefresh = String(payload?.refresh_token || '').trim()
  const nextExpiresIn = Number(payload?.expires_in || 0)
  const nextExpiresAt = nextExpiresIn
    ? Math.floor(Date.now() / 1000) + nextExpiresIn
    : Number(payload?.expires_at || 0)
  const nextUser = payload?.user || null

  token.value = nextToken
  refreshTok.value = nextRefresh
  expiresAt.value = nextExpiresAt
  user.value = nextUser

  if (nextToken && nextExpiresAt && nextUser) {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      access_token: nextToken,
      expires_at: nextExpiresAt,
      user: nextUser,
    }))
    if (nextRefresh) {
      window.sessionStorage.setItem(RT_STORAGE_KEY, nextRefresh)
    }
    scheduleExpiry(nextExpiresAt)
    return
  }
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  window.sessionStorage.removeItem(STORAGE_KEY)
  window.sessionStorage.removeItem(RT_STORAGE_KEY)
}

function clearSession({ silent = false, message = '登录已过期，请重新登录' } = {}) {
  const hadSession = Boolean(token.value || window.sessionStorage.getItem(STORAGE_KEY))
  token.value = ''
  refreshTok.value = ''
  expiresAt.value = 0
  user.value = null
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  window.sessionStorage.removeItem(STORAGE_KEY)
  window.sessionStorage.removeItem(RT_STORAGE_KEY)
  if (!silent && hadSession) {
    ElMessage.warning(message || '登录已过期，请重新登录')
  }
}

export function getAuthToken() {
  return token.value || ''
}

export function getRefreshToken() {
  return refreshTok.value || ''
}

// 注册到 http.js
setAuthTokenProvider(getAuthToken)
setRefreshTokenProvider(getRefreshToken)
setOnTokensRefreshed((data) => {
  persistTokens({ ...data, user: user.value })
})
setAuthFailureHandler((error) => clearSession({ message: error?.message || '' }))

export function useAuthSession() {
  const isAuthenticated = computed(() => Boolean(getAuthToken() && user.value))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isGuest = computed(() => user.value?.role === 'guest')

  async function initializeSession() {
    if (initialized) {
      checked.value = true
      return
    }
    initialized = true
    const stored = readStoredSession()
    if (!isStoredSessionFresh(stored)) {
      clearSession({ silent: true })
      checked.value = true
      return
    }
    // Restore from sessionStorage
    token.value = String(stored.access_token || stored.token || '')
    refreshTok.value = String(stored._refresh_token || '')
    expiresAt.value = Number(stored.expires_at || 0)
    user.value = stored.user || null
    scheduleExpiry(expiresAt.value)

    // 验证服务端 session
    try {
      const response = await getCurrentSession()
      persistTokens({
        access_token: token.value,
        refresh_token: refreshTok.value,
        expires_at: response.expires_at || expiresAt.value,
        user: response.user || stored.user,
      })
    } catch {
      clearSession({ silent: true })
    } finally {
      checked.value = true
    }
  }

  async function login(username, password) {
    const response = await loginConsole(username, password)
    persistTokens(response)
    return response.user
  }

  async function logout() {
    try {
      if (token.value) {
        await logoutConsole()
      }
    } catch {
      // Client-side session removal is authoritative
    } finally {
      clearSession({ silent: true })
    }
  }

  return {
    checked,
    user,
    token,
    refreshTok,
    expiresAt,
    isAuthenticated,
    isAdmin,
    isGuest,
    initializeSession,
    login,
    logout,
    clearSession,
  }
}
