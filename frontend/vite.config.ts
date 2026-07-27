import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: '@', replacement: path.resolve(__dirname, 'src') }],
  },
  server: {
    proxy: {
      // backend-agent 运行在 8765 端口，开发环境通过代理转发避免跨域
      '/backend-agent-api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/backend-agent-api/, ''),
      },
      // 数据中台后端运行在 8010 端口，开发环境通过代理转发避免跨域
      '/data-platform-api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/data-platform-api/, ''),
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
});
