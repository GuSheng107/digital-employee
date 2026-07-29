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

export function fetchInviteCodes(): Promise<InviteCodeItem[]> {
  return backendAuthRequest.get<InviteCodeItem[]>('/invite-codes');
}

export function createInviteCode(payload: CreateInviteCodePayload): Promise<CreateInviteCodeResult> {
  return backendAuthRequest.post('/invite-codes', payload);
}
