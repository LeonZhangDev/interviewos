import { defineConfig, devices } from '@playwright/test'

const FRONTEND_URL = 'http://127.0.0.1:5173'
// BACKEND_HOST_PORT lets E2E run when another dev service already owns the
// default 8000 (e.g. a second project's API). It must match the compose
// backend ports mapping, which reads the same variable.
const BACKEND_PORT = process.env.BACKEND_HOST_PORT || '8000'
const BACKEND_HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`

// The backend stack (db, redis, runner, sandboxes, backend) runs in docker
// compose — its entrypoint applies Alembic migrations before booting uvicorn.
// The frontend runs as a local vite dev server proxying /api to the backend
// port, so the browser exercises the exact same code path as development.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list']],
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'docker compose up -d --build --wait backend',
      cwd: '..',
      url: BACKEND_HEALTH_URL,
      reuseExistingServer: true,
      timeout: 420_000,
    },
    {
      command: 'npm run dev',
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_PROXY: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
})
