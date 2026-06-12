// Shared fixtures: setzt API-Key in localStorage VOR jedem Test, damit
// die SPA ohne manuellen Login durchstartet.

import { test as base, expect } from '@playwright/test'

export const test = base.extend({
  page: async ({ page }, use) => {
    const apiKey = process.env.E2E_API_KEY || 'ci-test-tenant-key'
    await page.addInitScript((key) => {
      window.localStorage.setItem('apiKey', key)
    }, apiKey)
    await use(page)
  },
})

export { expect }
