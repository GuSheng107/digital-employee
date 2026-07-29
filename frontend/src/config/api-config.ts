/** 前端 API 地址统一配置。 */

export const BACKEND_AUTH_API_BASE_URL =
  import.meta.env.VITE_BACKEND_AUTH_API_BASE_URL || '/backend-auth-api/api/v1';

export const BACKEND_AGENT_API_BASE_URL =
  import.meta.env.VITE_BACKEND_AGENT_API_BASE_URL || '/backend-agent-api';

export const DATA_PLATFORM_API_BASE_URL =
  import.meta.env.VITE_DATA_PLATFORM_API_BASE_URL || '/data-platform-api';
