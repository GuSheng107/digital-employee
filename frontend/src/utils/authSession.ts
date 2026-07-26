export interface TokenPairPayload {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
}

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const TOKEN_EXPIRES_AT_KEY = 'token_expires_at';
const LEGACY_TOKEN_KEY = 'token';

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY) || '';
}

export function getRefreshToken(): string {
  return localStorage.getItem(REFRESH_TOKEN_KEY) || '';
}

export function saveTokenPair(payload: TokenPairPayload): void {
  const accessToken = String(payload.access_token || '').trim();
  const refreshToken = String(payload.refresh_token || '').trim();

  if (accessToken) {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(LEGACY_TOKEN_KEY, accessToken);
  }
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  if (typeof payload.expires_in === 'number' && Number.isFinite(payload.expires_in)) {
    localStorage.setItem(TOKEN_EXPIRES_AT_KEY, String(Date.now() + payload.expires_in * 1000));
  }
}

export function clearAuthSession(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
}
