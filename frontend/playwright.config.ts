import { defineConfig, devices } from '@playwright/test'

/**
 * Runs the primary-workflow e2e suite against a real backend (MockProvider,
 * disposable SQLite DB — see backend/scripts/run_e2e_backend.sh) and a real
 * frontend dev server. Both are started and torn down by Playwright itself.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: '../backend/scripts/run_e2e_backend.sh',
      url: 'http://localhost:8000/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
      timeout: 30_000,
      env: { VITE_API_BASE_URL: 'http://localhost:8000' },
    },
  ],
})
