import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    host: true, // Listen on all interfaces for Docker access
    proxy: {
      '/api/assistant': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        timeout: 0, // No timeout for SSE streaming
      },
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        timeout: 300000, // 5 minutes for long-running operations like print packet generation
      },
    },
  },
})
