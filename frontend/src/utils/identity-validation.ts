import { parsePhoneNumberFromString } from 'libphonenumber-js';
import { PHONE_DEFAULT_REGION } from '@/config/identity-config';

export const PASSWORD_MIN_LENGTH = 11;
export const PASSWORD_MAX_LENGTH = 128;
export const PASSWORD_COMPLEXITY_MESSAGE =
  '密码至少 11 位，且必须包含英文字母、数字和符号';

export const PASSWORD_COMPLEXITY_PATTERN =
  /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).{11,128}$/;

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
export const INVITE_CODE_PATTERN = /^[A-Za-z0-9_-]{4,32}$/;
export const INVITE_CODE_MESSAGE =
  '邀请码需为 4-32 位字母、数字、短横线或下划线';

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}

/**
 * 校验当前配置地区的号码并返回 E.164；无效或不属于当前地区时返回 null。
 */
export function normalizePhoneNumber(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = parsePhoneNumberFromString(trimmed, PHONE_DEFAULT_REGION);
  if (
    !parsed
    || !parsed.isValid()
    || parsed.country !== PHONE_DEFAULT_REGION
  ) {
    return null;
  }
  return parsed.number;
}

/** 把已保存的 E.164 号码转换为当前地区表单中的本地号码。 */
export function formatPhoneNumberForInput(value: string | null): string {
  if (!value) {
    return '';
  }
  const parsed = parsePhoneNumberFromString(value);
  if (!parsed || parsed.country !== PHONE_DEFAULT_REGION) {
    return value;
  }
  return parsed.nationalNumber;
}
