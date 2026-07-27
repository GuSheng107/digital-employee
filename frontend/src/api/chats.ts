import request, { fetchWithAuth } from '@/utils/request';

export interface ChatListParams {
  bot_key?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface ChatDetailParams {
  limit?: number;
}

export interface ChatMessagePart {
  type: string;
  text?: string;
  url?: string;
  preview_url?: string;
  filename?: string;
  file_size?: number;
  mime_type?: string;
  oversized?: boolean;
}

export interface ChatMessage {
  id: string;
  direction: string;
  content: string;
  sender_name?: string;
  sender_id?: string;
  sender_display_name?: string;
  reply_status?: string;
  reply_source?: string;
  created_at?: string;
  feedback?: { result: string; reason: string; count: number };
  metadata?: { parts?: ChatMessagePart[] };
}

export interface Chat {
  chat_id: string;
  display_name?: string;
  chat_type?: string;
  conversation_kind?: string;
  conversation_status?: string;
  reply_mode?: string;
  sender_name?: string;
  sender_id?: string;
  sender_display_name?: string;
  unread_count?: number;
  last_message_at?: string;
  context?: { used_chars: number; limit_chars: number };
  messages?: ChatMessage[];
  external_chat_id?: string;
  last_at?: string;
}

export interface ReplyModePayload {
  mode: string;
  [key: string]: unknown;
}

export interface ChatListResponse {
  chats: Chat[];
}

export interface ChatDetailResponse {
  chat: Chat;
}

export function getChats(params: ChatListParams = {}): Promise<ChatListResponse> {
  const search = new URLSearchParams();
  if (params.bot_key) search.set('bot_key', params.bot_key);
  if (params.keyword) search.set('keyword', params.keyword);
  if (params.page) search.set('page', String(params.page));
  if (params.page_size) search.set('page_size', String(params.page_size));
  const query = search.toString();
  return request.get(`/chats${query ? `?${query}` : ''}`) as Promise<ChatListResponse>;
}

export function getChatDetail(chatId: string, params: ChatDetailParams = {}): Promise<ChatDetailResponse> {
  const search = new URLSearchParams();
  if (params.limit) search.set('limit', String(params.limit));
  const query = search.toString();
  return request.get(`/chats/${encodeURIComponent(chatId)}${query ? `?${query}` : ''}`) as Promise<ChatDetailResponse>;
}

export function deleteChats(chatIds: string[]) {
  return request.delete('/chats', { data: { chat_ids: chatIds } });
}

export function updateChatDisplayName(chatId: string, displayName: string) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/display-name`, { display_name: displayName });
}

export function setChatReplyMode(chatId: string, payload: ReplyModePayload) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/reply-mode`, payload);
}

export function markChatRead(chatId: string) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/read`);
}

export function pinChat(chatId: string, pinned: boolean) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/pin`, { pinned });
}

export function compressChatContext(chatId: string) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/context/compress`);
}

export function generateAiDraftStream(chatId: string, payload: Record<string, unknown>, signal?: AbortSignal) {
  return fetchWithAuth(`/chats/${encodeURIComponent(chatId)}/ai-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
}

export function sendManualReply(chatId: string, payload: FormData | Record<string, unknown>) {
  if (payload instanceof FormData) {
    return request.post(`/chats/${encodeURIComponent(chatId)}/reply`, payload, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  }
  return request.post(`/chats/${encodeURIComponent(chatId)}/reply`, payload);
}

export function getManualReplyStatus(commandId: string) {
  return request.get(`/manual-replies/${encodeURIComponent(commandId)}`);
}

export function archiveChat(chatId: string) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/archive`);
}

export function unarchiveChat(chatId: string) {
  return request.post(`/chats/${encodeURIComponent(chatId)}/unarchive`);
}

export function updateUserDisplayName(userId: string, displayName: string) {
  return request.post(`/users/${encodeURIComponent(userId)}/display-name`, { display_name: displayName });
}
