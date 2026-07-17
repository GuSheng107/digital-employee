const API_BASE = import.meta.env.VITE_API_BASE ||
  (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    ? 'http://127.0.0.1:8765'
    : '')

export function resolveApiUrl(url) {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  if (API_BASE) {
    return new URL(url, API_BASE).toString()
  }
  return url
}

const MAX_RETRIES = 2
const RETRY_DELAY_MS = 1000
const RETRYABLE_STATUS_CODES = new Set([502, 503, 504])
let authTokenProvider = () => ''
let authFailureHandler = null

// 鈹€鈹€ 鍙?Token 鑷姩鍒锋柊 鈹€鈹€
let refreshTokenProvider = () => ''
let onTokensRefreshed = null  // callback({ access_token, refresh_token, expires_in })
let _refreshPromise = null    // mutex: 闃叉骞跺彂鍒锋柊

export function setAuthTokenProvider(provider) {
  authTokenProvider = typeof provider === 'function' ? provider : () => ''
}

export function setRefreshTokenProvider(provider) {
  refreshTokenProvider = typeof provider === 'function' ? provider : () => ''
}

export function setOnTokensRefreshed(callback) {
  onTokensRefreshed = typeof callback === 'function' ? callback : null
}

export function setAuthFailureHandler(handler) {
  authFailureHandler = typeof handler === 'function' ? handler : null
}

async function tryAutoRefresh() {
  const rt = String(refreshTokenProvider() || '').trim()
  if (!rt) return false

  // 闃叉骞跺彂鍒锋柊
  if (_refreshPromise) {
    return await _refreshPromise
  }

  _refreshPromise = (async () => {
    try {
      const response = await fetch(resolveApiUrl('/api/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      })
      if (!response.ok) return false
      const data = await response.json()
      if (data.access_token && onTokensRefreshed) {
        onTokensRefreshed({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          expires_in: data.expires_in,
        })
      }
      return true
    } catch {
      return false
    }
  })()

  try {
    return await _refreshPromise
  } finally {
    _refreshPromise = null
  }
}

export function authHeaders(headers = {}) {
  const next = { ...headers }
  const token = String(authTokenProvider() || '').trim()
  if (token && !next.Authorization && !next.authorization) {
    next.Authorization = `Bearer ${token}`
  }
  return next
}

export async function fetchWithAuth(url, options = {}) {
  const request = () => fetch(resolveApiUrl(url), {
    ...options,
    headers: authHeaders(options.headers || {}),
  })

  let response = await request()
  if (response.status === 401 && await tryAutoRefresh()) {
    response = await request()
  }
  if (response.status === 401 && typeof authFailureHandler === 'function') {
    authFailureHandler(new Error('登录已过期，请重新登录'))
  }
  return response
}
export function urlWithAuthToken(url) {
  return resolveApiUrl(url)
}
function isRetryableError(error) {
  if (error.name === 'AbortError') return false
  if (error.status && RETRYABLE_STATUS_CODES.has(error.status)) return true
  if (!error.status && (error.name === 'TypeError' || error.message?.includes('Failed to fetch'))) return true
  return false
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export async function api(url, options = {}) {
  const headers = {
    ...(options.headers || {}),
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  Object.assign(headers, authHeaders(headers))

  let lastError = null
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(resolveApiUrl(url), {
        headers,
        ...options,
      })

      if (!response.ok) {
        const contentType = response.headers.get('content-type') || ''
        let body = {}
        if (contentType.includes('application/json')) {
          body = await response.json().catch(() => ({}))
        } else {
          const text = await response.text().catch(() => '')
          body = { message: text || response.statusText }
        }
        const message = body.message || response.statusText || '璇锋眰澶辫触'
        const traceId = body.trace_id || ''
        const error = new Error(message)
        error.status = response.status
        error.trace_id = traceId
        error.body = body
        error.toString = () => error.message
        if (RETRYABLE_STATUS_CODES.has(response.status) && attempt < MAX_RETRIES) {
          lastError = error
          await delay(RETRY_DELAY_MS * (attempt + 1))
          continue
        }
        if (response.status === 401) {
          // 灏濊瘯鑷姩鍒锋柊 (鍙?Token)
          if (await tryAutoRefresh()) {
            // 鍒锋柊鎴愬姛 鈥?鐢ㄦ柊 token 閲嶈瘯
            headers.Authorization = `Bearer ${authTokenProvider()}`
            continue
          }
          if (typeof authFailureHandler === 'function') {
            authFailureHandler(error)
          }
        }
        throw error
      }

      return response.json()
    } catch (error) {
      if (isRetryableError(error) && attempt < MAX_RETRIES) {
        lastError = error
        await delay(RETRY_DELAY_MS * (attempt + 1))
        continue
      }
      throw error
    }
  }
  throw lastError
}

export class AbortableApi {
  constructor() {
    this._controller = null
  }

  abort() {
    if (this._controller) {
      this._controller.abort()
      this._controller = null
    }
  }

  async api(url, options = {}) {
    this.abort()
    this._controller = new AbortController()
    return api(url, { ...options, signal: this._controller.signal })
  }
}
