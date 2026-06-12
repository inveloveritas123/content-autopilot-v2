// Goldene Pfade: die Hauptrouten der SPA muessen ohne Konsolen-Fehler rendern.
// Kein Klick-Workflow — nur Navigation + Top-Level-Render-Check.

import { test, expect } from './fixtures.js'

const ROUTES = [
  { path: '/', name: 'Dashboard' },
  { path: '/sources', name: 'Sources' },
  { path: '/ideas', name: 'Ideas' },
  { path: '/posts', name: 'Posts' },
  { path: '/calendar', name: 'Calendar' },
  { path: '/brand-voice', name: 'Brand Voice' },
  { path: '/analytics', name: 'Analytics' },
  { path: '/memory', name: 'Memory' },
]

for (const { path, name } of ROUTES) {
  test(`Route ${path} (${name}) rendert ohne JS-Fehler`, async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(`[console] ${msg.text()}`)
    })

    await page.goto(path, { waitUntil: 'networkidle' })

    // Layout-Element ist immer sichtbar (Sidebar/Header)
    await expect(page.locator('body')).toBeVisible()

    // Keine roten Errors. Warnings ignorieren wir hier — werden im
    // Browser-Use-Explore-Workflow tiefer geprueft.
    expect(errors.filter((e) => !e.includes('favicon') && !e.includes('DevTools'))).toEqual([])
  })
}
