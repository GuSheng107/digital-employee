/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend Agent API 基础路径（开发环境默认走 Vite proxy /api） */
  readonly VITE_API_BASE_URL?: string;
  /** 数据中台 API 基础路径（开发环境默认走 Vite proxy /data-platform-api） */
  readonly VITE_DATA_PLATFORM_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
