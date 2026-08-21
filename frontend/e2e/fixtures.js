// Shared fixtures: setzt API-Key in localStorage UND eine echte Session
// (cap_session-Cookie) VOR jedem Test, damit die SPA ohne manuellen
// Login-Formular-Durchlauf durchstartet.
//
// Nähte-Fund (2026-08-21): CustomerApp (App.jsx) prüft seit dem Auth-Guard
// vom 2026-08-13 IMMER zuerst /auth/me, bevor irgendeine Route gerendert
// wird — der localStorage-API-Key allein reicht seither nicht mehr, ohne
// Session-Cookie zeigt jede Route die Login-Seite (401 auf /auth/me).
// Login läuft hier per direktem API-Call statt Formular (schnell, DRY) —
// der Formular-Weg selbst wird bereits in 05-login-flow.spec.js geprüft.
import { test as base, expect } from '@playwright/test'

export const test = base.extend({
  page: async ({ page }, use) => {
    const apiKey = process.env.E2E_API_KEY || 'ci-test-tenant-key'
    const email = process.env.E2E_LOGIN_EMAIL || 'e2e-owner@ci-test.local'
    const password = process.env.E2E_LOGIN_PASSWORD || 'ci-test-password-2026'

    await page.request.post('/api/auth/login', { data: { email, password } })

    await page.addInitScript((key) => {
      window.localStorage.setItem('apiKey', key)
    }, apiKey)
    await use(page)
  },
})

export { expect }
