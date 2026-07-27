import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 读取 .env 中的代理目标地址（仅开发环境使用）
  const env = loadEnv(mode, process.cwd(), '');
  const backendAgentTarget = env.VITE_BACKEND_AGENT_TARGET || 'http://127.0.0.1:8765';
  const dataPlatformTarget = env.VITE_DATA_PLATFORM_TARGET || 'http://127.0.0.1:8010';

  return {
    plugins: [react()],
    resolve: {
      alias: [{ find: '@', replacement: path.resolve(__dirname, 'src') }],
    },
    server: {
      proxy: {
        // backend-agent，开发环境通过代理转发避免跨域
        '/backend-agent-api': {
          target: backendAgentTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/backend-agent-api/, ''),
        },
        // 数据中台后端，开发环境通过代理转发避免跨域
        '/data-platform-api': {
          target: dataPlatformTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/data-platform-api/, ''),
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('antd')) {
                return 'antd';
              }
              if (id.match(/node_modules\/(react|react-dom|react-router-dom|zustand|@types\/react|@types\/react-dom)/)) {
                return 'react-vendor';
              }
              return 'vendor';
            }
          },
        },
      },
    },
  };
});
