/** 用户身份、VIP 与权限码的前端统一定义。 */

interface RoleCodeMap {
  USER: string;
  MANAGER: string;
  SUPER_ADMIN: string;
}

interface VipLevelMap {
  NORMAL: number;
  MANAGER: number;
  SUPER_ADMIN: number;
}

interface PermissionCodeMap {
  USER_MANAGE: string;
  USER_PERMISSION: string;
  INVITE_CODE_MANAGE: string;
  MENU_MANAGE: string;
  DATA_PLATFORM_DASHBOARD: string;
  DATA_PLATFORM_DATA_ITEMS: string;
  DATA_PLATFORM_CONFIG: string;
}

export const ROLE_CODE: Readonly<RoleCodeMap> = Object.freeze({
  USER: 'user',
  MANAGER: 'manager',
  SUPER_ADMIN: 'super_admin',
});

export const VIP_LEVEL: Readonly<VipLevelMap> = Object.freeze({
  NORMAL: 0,
  MANAGER: 66,
  SUPER_ADMIN: 99,
});

export const PERMISSION_CODE: Readonly<PermissionCodeMap> = Object.freeze({
  USER_MANAGE: 'admin:user:manage',
  USER_PERMISSION: 'admin:user:permission',
  INVITE_CODE_MANAGE: 'admin:invite_code:manage',
  MENU_MANAGE: 'admin:menu:manage',
  DATA_PLATFORM_DASHBOARD: 'admin:data_platform:dashboard',
  DATA_PLATFORM_DATA_ITEMS: 'admin:data_platform:data_items',
  DATA_PLATFORM_CONFIG: 'admin:data_platform:config',
});

/** 超级管理员拥有全权限旁路；普通管理员仍按权限码授权。 */
export function hasFullAccessRole(roleCodes: readonly string[]): boolean {
  return roleCodes.includes(ROLE_CODE.SUPER_ADMIN);
}

/** 判断用户是否持有任一目标权限。 */
export function hasAnyPermission(
  roleCodes: readonly string[],
  permissionCodes: readonly string[],
  requiredCodes: readonly string[],
): boolean {
  return (
    hasFullAccessRole(roleCodes)
    || requiredCodes.some((code) => permissionCodes.includes(code))
  );
}

/** 后端展示字段缺失时使用的统一 VIP 文案。 */
export function getVipDisplayFallback(
  vipLevel: number | null | undefined,
  isVip: boolean,
): string {
  if (vipLevel === VIP_LEVEL.SUPER_ADMIN) return '超级管理员';
  if (vipLevel === VIP_LEVEL.MANAGER) return '管理员';
  if (isVip && typeof vipLevel === 'number' && vipLevel > VIP_LEVEL.NORMAL) {
    return `VIP${vipLevel}`;
  }
  return '普通用户';
}
