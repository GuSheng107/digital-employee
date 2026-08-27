import { EXCLUSIVE_ROLE_CODES, IDENTITY_ROLE_CODES } from '@/constants/access-control';

/**
 * 按角色分配规则规范化选中的角色集合：
 * - 身份角色（super_admin / manager / user）之间互斥，最多保留一个。
 * - 独占角色（super_admin / manager）不能叠加任何其他角色。
 * - user 可叠加自定义角色。
 *
 * 身份角色冲突时的优先级：super_admin > manager > user，
 * 即同时选中多个身份角色时保留权限最高者，避免依赖数组顺序。
 */
export function normalizeRoleCodes(selected: string[]): string[] {
  const codes = [...new Set(selected)];
  const identity = codes.filter((code) => IDENTITY_ROLE_CODES.has(code));

  // 身份角色互斥：按固定优先级保留一个
  if (identity.length > 1) {
    const keptIdentity = identityPriority(identity);
    // 若保留下来的身份角色是独占角色（super_admin / manager），
    // 同样不能叠加自定义角色，需一并丢弃。
    if (EXCLUSIVE_ROLE_CODES.has(keptIdentity)) {
      return [keptIdentity];
    }
    return codes.filter(
      (code) => !IDENTITY_ROLE_CODES.has(code) || code === keptIdentity,
    );
  }
  // 独占角色不能叠加其他角色：保留独占角色，丢弃其他
  const exclusive = codes.filter((code) => EXCLUSIVE_ROLE_CODES.has(code));
  if (exclusive.length > 0 && codes.length > 1) {
    return exclusive.slice(0, 1);
  }
  return codes;
}

/** 身份角色优先级：super_admin > manager > user。 */
function identityPriority(identity: string[]): string {
  if (identity.includes('super_admin')) return 'super_admin';
  if (identity.includes('manager')) return 'manager';
  return 'user';
}
