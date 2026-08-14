// Echter Login-Flow (docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md, Königsweg #1):
// alle bisherigen Specs umgehen den Login komplett (fixtures.js setzt den
// API-Key direkt in localStorage). Dieser Test spielt den tatsächlichen
// Formular-Flow durch — genau der Pfad, den der neue Session-Login-Schutz
// (backend/dependencies.py::_resolve_tenant) jetzt zusätzlich zum API-Key
// prüft. CI-Bootstrap legt dafür einen echten User + Agency + Tenant an
// (.github/workflows/e2e-smoke.yml, Schritt "Bootstrap CI-Login-User").
//
// WICHTIG: nutzt bewusst NICHT fixtures.js (die Fixture würde den Login
// überspringen, was hier gerade das Testziel ist) — eigener `test`-Import
// aus @playwright/test direkt.

import { test, expect } from '@playwright/test'

const EMAIL = process.env.E2E_LOGIN_EMAIL || 'e2e-owner@ci-test.local'
const PASSWORD = process.env.E2E_LOGIN_PASSWORD || 'ci-test-password-2026'

test.describe('Login-Flow (Königsweg)', () => {
  test('Falsches Passwort zeigt Fehlermeldung, kein Zugriff', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('du@firma.de').fill(EMAIL)
    await page.getByPlaceholder('••••••••').fill('definitiv-falsches-passwort')
    await page.getByRole('button', { name: /anmelden|login|einloggen/i }).click()

    // Muss auf der Login-Seite bleiben — kein Dashboard-Inhalt sichtbar —
    // UND die konkrete Fehlermeldung zeigen (Login.jsx: 401 → "E-Mail oder
    // Passwort falsch."), nicht nur irgendeinen Fehler.
    await expect(page.getByText('E-Mail oder Passwort falsch.')).toBeVisible()
    await expect(page.getByPlaceholder('du@firma.de')).toBeVisible()
  })

  test('Korrekter Login führt zum Dashboard', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('du@firma.de').fill(EMAIL)
    await page.getByPlaceholder('••••••••').fill(PASSWORD)
    await page.getByRole('button', { name: /anmelden|login|einloggen/i }).click()

    // Nach erfolgreichem Login verschwindet das Login-Formular und die
    // Sidebar-Navigation (Layout.jsx) wird sichtbar — Dashboard ist Default-Route.
    await expect(page.getByPlaceholder('du@firma.de')).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
  })

  test('Session-Cookie schützt eine Business-Route ohne API-Key im localStorage', async ({
    page,
  }) => {
    // Nähte-Test für backend/dependencies.py::_resolve_tenant (Task 1,
    // Highlander-Integration 2026-08-14): vor dem Fix schützte NUR der
    // API-Key im localStorage die Business-Routen. Dieser Test räumt den
    // localStorage bewusst leer, loggt sich nur per Session-Cookie ein und
    // erwartet trotzdem echten Dashboard-Zugriff — belegt, dass der Login
    // selbst (nicht nur ein zufällig mitgesendeter Key) den Zugriff trägt.
    await page.goto('/')
    await page.evaluate(() => window.localStorage.removeItem('apiKey'))
    await page.getByPlaceholder('du@firma.de').fill(EMAIL)
    await page.getByPlaceholder('••••••••').fill(PASSWORD)
    await page.getByRole('button', { name: /anmelden|login|einloggen/i }).click()

    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible({ timeout: 10_000 })

    const resp = await page.request.get('/api/dashboard')
    expect(resp.status()).not.toBe(401)
    expect(resp.status()).not.toBe(403)
  })

  test('Logout beendet die Session, Business-Route ist danach gesperrt', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('du@firma.de').fill(EMAIL)
    await page.getByPlaceholder('••••••••').fill(PASSWORD)
    await page.getByRole('button', { name: /anmelden|login|einloggen/i }).click()
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible({ timeout: 10_000 })

    await page.request.post('/api/auth/logout')
    await page.evaluate(() => window.localStorage.removeItem('apiKey'))
    await page.reload()

    await expect(page.getByPlaceholder('du@firma.de')).toBeVisible({ timeout: 10_000 })
  })
})
