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
  USER_READONLY: string;
  PERMISSION_MANAGE: string;
  PERMISSION_READONLY: string;
  INVITE_CODE_MANAGE: string;
  INVITE_CODE_READONLY: string;
  MENU_MANAGE: string;
  MENU_READONLY: string;
  DATA_PLATFORM_DASHBOARD: string;
  DATA_PLATFORM_DATA_ITEMS: string;
  DATA_PLATFORM_CONFIG: string;
  BOT_MANAGE: string;
  BOT_READONLY: string;
  AGENT_MANAGE: string;
  AGENT_READONLY: string;
  OBSERVABILITY_LOG_VIEW: string;
}

export const ROLE_CODE: Readonly<RoleCodeMap> = Object.freeze({
  USER: 'user',
  MANAGER: 'manager',
  SUPER_ADMIN: 'super_admin',
});

/** 系统身份占用的角色代码；普通角色创建接口不可复用。 */
export const RESERVED_ROLE_CODES: ReadonlySet<string> = new Set([
  ROLE_CODE.SUPER_ADMIN,
  ROLE_CODE.MANAGER,
]);

/** 身份角色：super_admin / manager / user 三者互斥，一个用户最多持有其一。 */
export const IDENTITY_ROLE_CODES: ReadonlySet<string> = new Set([
  ROLE_CODE.SUPER_ADMIN,
  ROLE_CODE.MANAGER,
  ROLE_CODE.USER,
]);

/** 独占角色：持有后不能再叠加任何其他角色（super_admin 全局唯一，manager 独占）。 */
export const EXCLUSIVE_ROLE_CODES: ReadonlySet<string> = new Set([
  ROLE_CODE.SUPER_ADMIN,
  ROLE_CODE.MANAGER,
]);

export const VIP_LEVEL: Readonly<VipLevelMap> = Object.freeze({
  NORMAL: 0,
  MANAGER: 66,
  SUPER_ADMIN: 99,
});

export const PERMISSION_CODE: Readonly<PermissionCodeMap> = Object.freeze({
  USER_MANAGE: 'admin:user:manage',
  USER_READONLY: 'admin:user:readonly',
  PERMISSION_MANAGE: 'admin:permission:manage',
  PERMISSION_READONLY: 'admin:permission:readonly',
  INVITE_CODE_MANAGE: 'admin:invite_code:manage',
  INVITE_CODE_READONLY: 'admin:invite_code:readonly',
  MENU_MANAGE: 'admin:menu:manage',
  MENU_READONLY: 'admin:menu:readonly',
  DATA_PLATFORM_DASHBOARD: 'admin:data_platform:dashboard',
  DATA_PLATFORM_DATA_ITEMS: 'admin:data_platform:data_items',
  DATA_PLATFORM_CONFIG: 'admin:data_platform:config',
  BOT_MANAGE: 'admin:bot:manage',
  BOT_READONLY: 'admin:bot:readonly',
  AGENT_MANAGE: 'admin:agent:manage',
  AGENT_READONLY: 'admin:agent:readonly',
  OBSERVABILITY_LOG_VIEW: 'admin:observability:log:view',
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

/**
 * 判断用户是否持有指定模块的管理权限（manage）。
 *
 * 只读（readonly）权限码不在此列，因此该函数可用于区分「可管理」与「只读」：
 * 返回 true 时展示新建/编辑/删除等写操作入口，false 时仅保留查看能力。
 */
export function hasManagePermission(
  roleCodes: readonly string[],
  permissionCodes: readonly string[],
  manageCode: string,
): boolean {
  return (
    hasFullAccessRole(roleCodes)
    || permissionCodes.includes(manageCode)
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
