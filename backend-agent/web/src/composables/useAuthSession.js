import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getCurrentSession, loginConsole, logoutConsole } from '../api/auth'
import { setAuthFailureHandler, setAuthTokenProvider } from '../api/http'

const STORAGE_KEY = 'wecom.console.session'

const checked = ref(false)
const token = ref('')
const expiresAt = ref(0)
const user = ref(null)
let initialized = false
let expiryTimer = null
let sessionWatchTimer = null

function scheduleExpiry(nextExpiresAt) {
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  const delay = Number(nextExpiresAt || 0) * 1000 - Date.now()
  if (delay <= 0) {
    clearSession()
    return
  }
  expiryTimer = window.setTimeout(() => {
    clearSession()
  }, Math.min(delay, 2147483647))
}

function startSessionWatch() {
  if (sessionWatchTimer !== null) return
  sessionWatchTimer = window.setInterval(() => {
    if (token.value || window.sessionStorage.getItem(STORAGE_KEY)) {
      syncSessionFromStorage({ silent: true })
    }
  }, 1000)
}

function stopSessionWatch() {
  if (sessionWatchTimer !== null) {
    window.clearInterval(sessionWatchTimer)
    sessionWatchTimer = null
  }
}

function readStoredSession() {
  try {
    return JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function syncSessionFromStorage({ silent = true } = {}) {
  const session = readStoredSession()
  if (isStoredSessionFresh(session)) {
    token.value = String(session.token || '')
    expiresAt.value = Number(session.expires_at || 0)
    user.value = session.user || null
    scheduleExpiry(expiresAt.value)
    startSessionWatch()
    return true
  }
  clearSession({ silent })
  return false
}

function persistSession(payload) {
  const nextToken = String(payload?.token || '').trim()
  const nextExpiresAt = Number(payload?.expires_at || 0)
  const nextUser = payload?.user || null
  token.value = nextToken
  expiresAt.value = nextExpiresAt
  user.value = nextUser
  if (nextToken && nextExpiresAt && nextUser) {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        token: nextToken,
        expires_at: nextExpiresAt,
        user: nextUser,
      }),
    )
    scheduleExpiry(nextExpiresAt)
    startSessionWatch()
    return
  }
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  window.sessionStorage.removeItem(STORAGE_KEY)
}

function clearSession({ silent = false, message = '登录已过期，请重新登录' } = {}) {
  const hadSession = Boolean(token.value || window.sessionStorage.getItem(STORAGE_KEY))
  token.value = ''
  expiresAt.value = 0
  user.value = null
  if (expiryTimer !== null) {
    window.clearTimeout(expiryTimer)
    expiryTimer = null
  }
  stopSessionWatch()
  window.sessionStorage.removeItem(STORAGE_KEY)
  if (!silent && hadSession) {
    ElMessage.warning(message || '登录已过期，请重新登录')
  }
}

function isStoredSessionFresh(session) {
  const storedToken = String(session?.token || '').trim()
  const storedExpiresAt = Number(session?.expires_at || 0)
  return Boolean(storedToken && storedExpiresAt && storedExpiresAt * 1000 > Date.now())
}

export function getAuthToken() {
  if (syncSessionFromStorage({ silent: true })) {
    return token.value
  }
  return ''
}

setAuthTokenProvider(getAuthToken)
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
    persistSession(stored)
    try {
      const response = await getCurrentSession()
      persistSession({
        token: stored.token,
        expires_at: response.expires_at || stored.expires_at,
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
    persistSession(response)
    return response.user
  }

  async function logout() {
    try {
      if (token.value) {
        await logoutConsole()
      }
    } catch {
      // Client-side session removal is authoritative for this stateless token.
    } finally {
      clearSession({ silent: true })
    }
  }

  return {
    checked,
    user,
    token,
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
