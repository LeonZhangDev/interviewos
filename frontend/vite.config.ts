import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import pkg from './package.json'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  // loadEnv only reads .env files, not process env — check process.env first
  // so compose/playwright can inject the API target (e.g. docker-internal
  // http://backend:8000, or an alternate host port when 8000 is occupied).
  const apiTarget = process.env.VITE_API_PROXY || env.VITE_API_PROXY || 'http://localhost:8000'

  return {
    plugins: [react()],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    server: {
      port: 5173,
      proxy: {
        '/api': apiTarget,
        '/health': apiTarget,
      },
    },
  }
})
