import { api } from './http'

export function loginConsole(username, password) {
  return api('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function getCurrentSession() {
  return api('/api/auth/session')
}

export function logoutConsole() {
  return api('/api/auth/logout', { method: 'POST' })
}

export function changeOwnPassword(currentPassword, newPassword) {
  return api('/api/auth/password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
}

export function getConsoleUsers() {
  return api('/api/auth/users')
}

export function createConsoleUser(payload) {
  return api('/api/auth/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateConsoleUser(username, payload) {
  return api(`/api/auth/users/${encodeURIComponent(username)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function resetConsoleUserPassword(username, password) {
  return api(`/api/auth/users/${encodeURIComponent(username)}/password`, {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}

export function deleteConsoleUser(username) {
  return api(`/api/auth/users/${encodeURIComponent(username)}`, {
    method: 'DELETE',
  })
}

export function kickConsoleUser(username) {
  return api(`/api/auth/users/${encodeURIComponent(username)}/kick`, {
    method: 'POST',
  })
}

export function refreshToken(refreshTokenValue) {
  return api('/api/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshTokenValue }),
  })
}

export function getGuestAccount() {
  return api('/api/auth/guest-account')
}
