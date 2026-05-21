import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  root: 'D:/PythonProjects/pipescan/frontend',
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5317,
    strictPort: true
  },
  preview: {
    host: '0.0.0.0',
    port: 5317,
    strictPort: true
  }
})
