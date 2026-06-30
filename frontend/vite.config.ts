import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/run': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/dashboard': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
})
