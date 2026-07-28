import { DATA_PLATFORM_API_BASE_URL } from '@/config/api-config';

const AVATAR_API_PATH_PREFIX = '/api/v1/storage/avatars/';
const AVATAR_OBJECT_PATH_MARKER = '/avatars/';

/** 拼接数据中台代理地址与服务端资源路径。 */
function buildDataPlatformUrl(resourcePath: string): string {
  const baseUrl = DATA_PLATFORM_API_BASE_URL.replace(/\/+$/, '');
  const normalizedPath = resourcePath.startsWith('/') ? resourcePath : `/${resourcePath}`;
  return `${baseUrl}${normalizedPath}`;
}

/**
 * 把后端持久化的头像地址转换为浏览器可访问地址。
 *
 * 新数据存储 backend-data 的公开头像路径；历史 MinIO 私有直链则提取
 * ``avatars/`` 后的对象路径并改走 backend-data 只读代理。
 */
export function resolveAvatarUrl(avatarUrl: string | null | undefined): string | null {
  if (!avatarUrl) return null;
  if (avatarUrl.startsWith(AVATAR_API_PATH_PREFIX)) {
    return buildDataPlatformUrl(avatarUrl);
  }

  try {
    const parsedUrl = new URL(avatarUrl);
    const markerIndex = parsedUrl.pathname.indexOf(AVATAR_OBJECT_PATH_MARKER);
    if (markerIndex >= 0) {
      const avatarPath = parsedUrl.pathname.slice(
        markerIndex + AVATAR_OBJECT_PATH_MARKER.length,
      );
      return buildDataPlatformUrl(`${AVATAR_API_PATH_PREFIX}${avatarPath}`);
    }
  } catch {
    // 非绝对 URL 保持原样，兼容由 CDN 或网关返回的相对资源地址。
  }
  return avatarUrl;
}
