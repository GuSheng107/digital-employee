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

export function setAuthTokenProvider(provider) {
  authTokenProvider = typeof provider === 'function' ? provider : () => ''
}

export function setAuthFailureHandler(handler) {
  authFailureHandler = typeof handler === 'function' ? handler : null
}

export function authHeaders(headers = {}) {
  const next = { ...headers }
  const token = String(authTokenProvider() || '').trim()
  if (token && !next.Authorization && !next.authorization) {
    next.Authorization = `Bearer ${token}`
  }
  return next
}

export function fetchWithAuth(url, options = {}) {
  return fetch(resolveApiUrl(url), {
    ...options,
    headers: authHeaders(options.headers || {}),
  }).then((response) => {
    if (response.status === 401 && typeof authFailureHandler === 'function') {
      authFailureHandler(new Error('登录已过期，请重新登录'))
    }
    return response
  })
}

export function urlWithAuthToken(url) {
  const resolvedUrl = resolveApiUrl(url)
  const token = String(authTokenProvider() || '').trim()
  if (!token) return resolvedUrl
  try {
    const parsed = new URL(resolvedUrl, window.location.origin)
    if (!parsed.pathname.startsWith('/api/')) {
      return resolvedUrl
    }
    parsed.searchParams.set('session_token', token)
    if (!API_BASE && parsed.origin === window.location.origin) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`
    }
    return parsed.toString()
  } catch {
    return resolvedUrl
  }
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
        const message = body.message || response.statusText || '请求失败'
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
        if (response.status === 401 && typeof authFailureHandler === 'function') {
          authFailureHandler(error)
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
