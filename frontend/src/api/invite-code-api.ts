import backendAuthRequest from '@/utils/backend-auth-request';

export interface InviteCodeItem {
  code: string;
  remaining: number;
  expires_at: number;
  created_by: number;
  created_at: number;
  is_valid: boolean;
}

export interface CreateInviteCodePayload {
  remaining: number;
  expires_in_hours: number;
  custom_code?: string;
}

export interface CreateInviteCodeResult {
  code: string;
  remaining: number;
  expires_at: number;
  expires_in: number;
}

export interface InviteCodeListResponse {
  items: InviteCodeItem[];
  total: number;
  page: number;
  page_size: number;
}

export function fetchInviteCodes(
  page: number,
  pageSize: number,
): Promise<InviteCodeListResponse> {
  return backendAuthRequest.get<InviteCodeListResponse>('/invite-codes', {
    params: { page, page_size: pageSize },
  });
}

export function createInviteCode(payload: CreateInviteCodePayload): Promise<CreateInviteCodeResult> {
  return backendAuthRequest.post('/invite-codes', payload);
}
