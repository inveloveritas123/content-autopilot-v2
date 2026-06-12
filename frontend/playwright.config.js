// Playwright Smoke-Test-Config — deckt die 'goldenen Pfade' der UI ab.
// Browser-Use uebernimmt die explorative LLM-driven Layer separat (Constraint #14).
//
// Lokal:    cd frontend && npx playwright test
// Headed:   cd frontend && npx playwright test --headed
// Debug:    cd frontend && npx playwright test --debug
//
// CI: e2e-smoke.yml laeuft headless gegen den per docker-compose hochgezogenen Stack.

import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://localhost:8601'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Sequential — wir teilen einen Tenant + State
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // Test-Tenant-API-Key wird vor jedem Test in localStorage gesetzt
    // (siehe e2e/fixtures.js)
    extraHTTPHeaders: {
      'X-API-Key': process.env.E2E_API_KEY || 'ci-test-tenant-key',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
