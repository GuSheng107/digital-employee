/**
 * Format utilities — ported from frontend-vue/src/utils/format.js
 */

export function formatTime(value: string | Date | null | undefined): string {
  if (!value) return '';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

export function formatTimeOnly(value: string | null | undefined): string {
  if (!value) return '--';
  try {
    return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return String(value).slice(11, 19);
  }
}

export function getAgentLabel(providerKey: string | undefined, agents: Array<{ provider_key: string; label?: string; provider_name?: string }>): string {
  if (!providerKey) return '-';
  const agent = agents.find((item) => item.provider_key === providerKey);
  return agent?.label || agent?.provider_name || providerKey;
}

export function formatBytes(value: number | null | undefined): string {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

export function conversationAvatar(chat?: { conversation_kind?: string; chat_type?: string } | null): string {
  if (chat?.conversation_kind === 'me') return '/avatars/me.svg';
  if (chat?.chat_type === 'group' || chat?.chat_type === 'room') return '/avatars/group.svg';
  return '/avatars/user.svg';
}

export function displayUserName(name?: string, id?: string): string {
  if (name && name !== id && !looksLikeWeComId(name)) return name;
  if (!id) return name || '未知用户';
  if (id.length <= 10) return `企微用户 ${id}`;
  return `企微用户 ${id.slice(0, 8)}`;
}

function looksLikeWeComId(value: string): boolean {
  return /^(wo|wm|wb|wr)[A-Za-z0-9_-]{12,}$/.test(value) || /^[A-Za-z0-9_-]{24,}$/.test(value);
}

export function escapeHtml(value: string): string {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
