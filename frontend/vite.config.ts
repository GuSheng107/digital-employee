import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 读取 .env 中的代理目标地址（仅开发环境使用，只加载 VITE_ 前缀变量）
  const env = loadEnv(mode, process.cwd());
  const backendAuthTarget = env.VITE_BACKEND_AUTH_TARGET || 'http://127.0.0.1:8020';
  const dataPlatformTarget = env.VITE_DATA_PLATFORM_TARGET || 'http://127.0.0.1:8010';
  const proxy = {
    '/backend-auth-api': {
      target: backendAuthTarget,
      changeOrigin: true,
      xfwd: true,
      rewrite: (requestPath: string) => requestPath.replace(/^\/backend-auth-api/, ''),
    },
    '/data-platform-api': {
      target: dataPlatformTarget,
      changeOrigin: true,
      rewrite: (requestPath: string) => requestPath.replace(/^\/data-platform-api/, ''),
    },
  };

  return {
    plugins: [react()],
    resolve: {
      alias: [{ find: '@', replacement: path.resolve(__dirname, 'src') }],
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy,
    },
    preview: {
      port: 5173,
      strictPort: true,
      proxy,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id: string): string | undefined {
            if (id.includes('node_modules')) {
              if (id.includes('antd')) {
                return 'antd';
              }
              if (id.match(/node_modules\/(react|react-dom|react-router|zustand|@types\/react|@types\/react-dom)/)) {
                return 'react-vendor';
              }
              return 'vendor';
            }
            return undefined;
          },
        },
      },
    },
  };
});
