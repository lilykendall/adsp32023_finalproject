import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// The backend serves /api and /photos. Proxying both in dev keeps the browser on
// a single origin, so no CORS preflight is involved in the upload path.
const BACKEND = process.env.FRIDGEFEST_BACKEND || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/photos': { target: BACKEND, changeOrigin: true },
    },
  },
})
