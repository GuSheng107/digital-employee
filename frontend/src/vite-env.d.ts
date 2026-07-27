/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend Agent API 基础路径（开发环境默认走 Vite proxy /backend-agent-api） */
  readonly VITE_API_BASE_URL?: string;
  /** 数据中台 API 基础路径（开发环境默认走 Vite proxy /data-platform-api） */
  readonly VITE_DATA_PLATFORM_API_BASE_URL?: string;
  /** backend-agent 代理目标地址（仅 vite.config.ts 读取，开发环境） */
  readonly VITE_BACKEND_AGENT_TARGET?: string;
  /** 数据中台代理目标地址（仅 vite.config.ts 读取，开发环境） */
  readonly VITE_DATA_PLATFORM_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
