import request from '@/utils/request';

export interface SessionUser {
  username: string;
  display_name?: string;
  role?: string;
  user_type?: string;
  is_active?: boolean;
  created_at?: string;
}

export interface SessionResponse {
  user?: SessionUser;
  expires_at?: number;
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
}

export interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
  user?: SessionUser;
  ok?: boolean;
}

export function loginConsole(username: string, password: string): Promise<LoginResponse> {
  return request.post('/auth/login', { username, password });
}

export function getCurrentSession(): Promise<SessionResponse> {
  return request.get('/auth/session');
}

export function logoutConsole(): Promise<void> {
  return request.post('/auth/logout');
}

export function changeOwnPassword(currentPassword: string, newPassword: string): Promise<void> {
  return request.post('/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export function getConsoleUsers(): Promise<SessionUser[]> {
  return request.get('/auth/users');
}

export function createConsoleUser(payload: {
  username: string;
  password: string;
  display_name?: string;
  role?: string;
  user_type?: string;
}): Promise<void> {
  return request.post('/auth/users', payload);
}

export function updateConsoleUser(
  username: string,
  payload: { display_name?: string; role?: string; user_type?: string; is_active?: boolean }
): Promise<void> {
  return request.put(`/auth/users/${encodeURIComponent(username)}`, payload);
}

export function resetConsoleUserPassword(username: string, password: string): Promise<void> {
  return request.post(`/auth/users/${encodeURIComponent(username)}/password`, { password });
}

export function deleteConsoleUser(username: string): Promise<void> {
  return request.delete(`/auth/users/${encodeURIComponent(username)}`);
}

export function kickConsoleUser(username: string): Promise<void> {
  return request.post(`/auth/users/${encodeURIComponent(username)}/kick`);
}

export function refreshToken(refreshTokenValue: string): Promise<LoginResponse> {
  return request.post('/auth/refresh', { refresh_token: refreshTokenValue });
}

export function getGuestAccount(): Promise<{ username: string; password: string; user_type: string }> {
  return request.get('/auth/guest-account');
}
