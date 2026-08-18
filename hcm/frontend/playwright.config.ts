import { defineConfig, devices } from '@playwright/test'

// Real-browser regression suite (H2). Two servers are started for you:
//   1. Django on 127.0.0.1:8000 with a throwaway, freshly seeded SQLite DB
//      (e2e/backend-server.mjs) — the same seed_demo_data logins every sprint
//      was verified against by hand;
//   2. the Vite dev server on 127.0.0.1:5173, which proxies /api to Django.
// `npm test` runs it headless; `npm run test:headed` to watch.
const CI = !!process.env.CI

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1, // one shared, seeded backend; specs mutate a little, so keep them ordered per file
  retries: CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: 'node e2e/backend-server.mjs',
      url: 'http://127.0.0.1:8000/healthz',
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
})
