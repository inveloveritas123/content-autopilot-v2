/**
 * E2E Stichproben: Telegram-Settings, Modell-Modus, Admin-Panel, Navigation
 * Perspektiven: Pentester + Bug-Tester + DAU-User + UX-Designer
 * 3 Checks pro Feature-Gruppe
 */
import { test, expect } from './fixtures.js'

const BASE = process.env.E2E_BASE_URL || 'http://localhost:8601'

// ─────────────────────────────────────────────────────────────
// 1. TELEGRAM-SETTINGS (#89 / #97)
// ─────────────────────────────────────────────────────────────

test('TG-1: Settings-Seite lädt, Telegram-Sektion sichtbar', async ({ page }) => {
  // SSE/WS blockieren — /settings hält Streams offen und crasht Browser
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  await page.route('**/ws/**', route => route.abort().catch(() => {}))
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)
  await expect(page.locator('text=Telegram').first()).toBeVisible({ timeout: 8000 })
  await page.screenshot({ path: 'test-results/tg-1-settings-overview.png', fullPage: true })
})

test('TG-2: Token-Input ist Passwort-Feld (Pentester — kein Klartext)', async ({ page }) => {
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)
  // Korrekter Placeholder laut TelegramBotSettings.jsx Z.230: "123456789:ABCDefGhIjKlmNoPQRsTUVwxyz"
  const tokenInput = page.locator('input[placeholder*="123456"], input[type="password"][placeholder*="Bot"]').first()
  const botVerbinden = page.locator('button:has-text("Bot verbinden")').first()
  const tokenWiderrufen = page.locator('button:has-text("Token widerrufen")').first()

  if (await tokenInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    // Bot NICHT konfiguriert: Form mit Token-Input sichtbar
    await expect(tokenInput).toHaveAttribute('type', 'password')
    console.log('TG-2: Token-Input type=password ✓ (kein Bot konfiguriert)')
  } else if (await tokenWiderrufen.isVisible({ timeout: 3000 }).catch(() => false)) {
    // Bot konfiguriert: Status-View aktiv → kein Token-Input (expected)
    console.log('TG-2: Bot bereits konfiguriert (Status-View) — Token-Input korrekt versteckt ✓')
    await expect(tokenWiderrufen).toBeVisible()
  } else {
    // Fallback: Telegram-Sektion sichtbar prüfen
    await expect(page.locator('text=Telegram').first()).toBeVisible()
    console.log('TG-2: Telegram-Sektion sichtbar, Status unbekannt')
  }
})

test('TG-3: Telegram-Bot-Verbindungs-State korrekt (Bug-Tester)', async ({ page }) => {
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)

  const botVerbinden = page.locator('button:has-text("Bot verbinden")').first()
  const tokenWiderrufen = page.locator('button:has-text("Token widerrufen")').first()

  const hasConnectBtn = await botVerbinden.isVisible({ timeout: 3000 }).catch(() => false)
  const hasRevokeBtn = await tokenWiderrufen.isVisible({ timeout: 3000 }).catch(() => false)

  if (hasConnectBtn) {
    // Kein Bot → "Bot verbinden"-Button muss bei leerem Input disabled sein
    await expect(botVerbinden).toBeDisabled({ timeout: 3000 })
    console.log('TG-3: "Bot verbinden" disabled bei leerem Token ✓')
    // UX-Prüfung: aria-label/title für DAU?
    const title = await botVerbinden.getAttribute('title')
    const ariaLabel = await botVerbinden.getAttribute('aria-label')
    if (!title && !ariaLabel) {
      console.warn('UX-BUG: "Bot verbinden"-Button kein title/aria-label — Backlog-Item')
    }
  } else if (hasRevokeBtn) {
    // Bot konfiguriert → Status-View, "Token widerrufen" sichtbar ✓
    await expect(tokenWiderrufen).toBeVisible()
    console.log('TG-3: Bot konfiguriert — Status-View + "Token widerrufen" sichtbar ✓')
  } else {
    // Weder Verbinden noch Widerrufen → Telegram-Sektion prüfen
    await expect(page.locator('text=Telegram').first()).toBeVisible()
    console.warn('TG-3: Telegram-State unklar — weder Connect noch Revoke Button sichtbar')
  }
})

// ─────────────────────────────────────────────────────────────
// 2. MODELL-MODUS-SWITCH (#72)
// ─────────────────────────────────────────────────────────────

test('MM-1: Modell-Modus Sektion in Settings sichtbar', async ({ page }) => {
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)
  const modeSection = page.getByText('KI-Qualitätsmodus').or(page.getByText('Testmodus')).or(page.getByText('Produktivmodus')).first()
  await page.screenshot({ path: 'test-results/mm-1-model-mode.png', fullPage: true })
  await expect(modeSection).toBeVisible({ timeout: 5000 })
  console.log('MM-1: KI-Qualitätsmodus-Sektion sichtbar ✓')
})

test('MM-2: GET /api/tenants/me/model-mode liefert 200 (Pentester)', async ({ page, request }) => {
  const apiKey = process.env.E2E_API_KEY || 'ci-test-tenant-key'
  const resp = await request.get(`${BASE}/api/tenants/me/model-mode`, {
    headers: { 'X-API-Key': apiKey },
    failOnStatusCode: false,
  })
  console.log('MM-2: /api/tenants/me/model-mode Status:', resp.status())
  expect(resp.status()).toBe(200)
  const body = await resp.json()
  console.log('MM-2: Response:', JSON.stringify(body))
  expect(body).toHaveProperty('model_mode')
})

test('MM-3: Keine JS-Fehler auf Settings-Seite (DAU-User)', async ({ page }) => {
  const jsErrors = []
  page.on('pageerror', err => jsErrors.push(err.message))
  page.on('console', msg => { if (msg.type() === 'error') jsErrors.push(msg.text()) })
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3000)
  const critical = jsErrors.filter(e =>
    !e.includes('favicon') && !e.includes('ResizeObserver') && !e.includes('Non-Error')
  )
  if (critical.length) console.error('MM-3: JS-Fehler:', critical)
  expect(critical).toHaveLength(0)
})

// ─────────────────────────────────────────────────────────────
// 3. ADMIN-PANEL (#98)
// ─────────────────────────────────────────────────────────────

test('AP-1: /admin lädt Login-Seite (kein 404)', async ({ page }) => {
  await page.goto('/admin')
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: 'test-results/ap-1-admin-login.png', fullPage: true })
  // Login-Form oder Redirect erwartet, kein 500er
  const notFound = await page.locator('text=404').isVisible({ timeout: 2000 }).catch(() => false)
  expect(notFound).toBe(false)
  const has500 = await page.locator('text=500').isVisible({ timeout: 2000 }).catch(() => false)
  const hasServerError = await page.locator('text=Internal Server Error').isVisible({ timeout: 2000 }).catch(() => false)
  expect(has500).toBe(false)
  expect(hasServerError).toBe(false)
  console.log('AP-1: Admin-Seite URL:', page.url())
})

test('AP-2: Falsches Passwort → kein Stack-Trace im Response (Pentester)', async ({ page }) => {
  await page.goto('/admin')
  await page.waitForLoadState('networkidle')
  const passInput = page.locator('input[type="password"]').first()
  if (await passInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    const userInput = page.locator('input[type="text"]').first()
    if (await userInput.isVisible({ timeout: 1000 }).catch(() => false)) {
      await userInput.fill('admin')
    }
    await passInput.fill('wrong-password-pentest-123')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1500)
    const html = await page.content()
    expect(html).not.toContain('Traceback')
    expect(html).not.toContain('sqlalchemy')
    expect(html).not.toContain('psycopg')
    expect(html).not.toContain('SECRET')
    console.log('AP-2: Kein Stack-Trace im Fehler-Response ✓')
  } else {
    console.log('AP-2: Kein Login-Formular gefunden (möglicherweise schon eingeloggt)')
  }
})

// /admin/session gibt absichtlich 200 + {authenticated:false} zurück (Status-Endpoint)
// Geschützte Endpoints wie /admin/users müssen 401/403 liefern
test('AP-3: Geschützte Admin-Endpoints ohne Cookie → 401/403 (Pentester)', async ({ request }) => {
  const session = await request.get(`${BASE}/api/admin/session`, { failOnStatusCode: false })
  const body = await session.json()
  console.log('AP-3: /admin/session:', session.status(), JSON.stringify(body))
  expect(session.status()).toBe(200)
  expect(body.authenticated).toBe(false)

  const users = await request.get(`${BASE}/api/admin/users`, { failOnStatusCode: false })
  console.log('AP-3: /admin/users ohne Auth:', users.status())
  expect([401, 403]).toContain(users.status())
})

// ─────────────────────────────────────────────────────────────
// 4. NAVIGATION + UX (alle Hauptrouten + Overlap-Check)
// ─────────────────────────────────────────────────────────────

test('NAV-1: Alle Hauptrouten liefern 200 + kein "404" im DOM (Bug-Tester)', async ({ page }) => {
  // SSE/WS blockieren — /settings und /pipeline halten Streams offen
  await page.route('**/*events*', route => route.abort().catch(() => {}))
  await page.route('**/*sse*', route => route.abort().catch(() => {}))
  const routes = ['/', '/sources', '/pipeline', '/ideas', '/posts', '/brand-voice', '/settings', '/analytics', '/memory']
  const failures = []
  for (const route of routes) {
    await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(800)
    const has404 = await page.locator('text=404').isVisible({ timeout: 1000 }).catch(() => false)
    const hasError = await page.locator('text=Something went wrong').isVisible({ timeout: 1000 }).catch(() => false)
    if (has404 || hasError) failures.push(route)
    console.log(`NAV-1: ${route} → ${has404 ? '404' : hasError ? 'Fehler' : 'OK'}`)
  }
  if (failures.length) console.error('NAV-1: Fehler-Routen:', failures)
  expect(failures).toHaveLength(0)
})

test('NAV-2: Dashboard lädt + kein Element überlappt Nav (UX-Designer)', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  // Viewport prüfen (Mobile-Overlap-Risiko)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.screenshot({ path: 'test-results/nav-2-dashboard-1280.png' })
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.screenshot({ path: 'test-results/nav-2-dashboard-768.png' })
  // Nav-Links zählen
  const navLinks = await page.locator('nav a, aside a').count()
  console.log('NAV-2: Nav-Links:', navLinks)
  expect(navLinks).toBeGreaterThan(0)
})

test('NAV-3: Dashboard-KPIs laden ohne Network-Fehler (DAU-User)', async ({ page }) => {
  const failed = []
  page.on('response', resp => {
    if (resp.status() >= 500 && resp.url().includes('/api/')) {
      failed.push(`${resp.status()} ${resp.url()}`)
    }
  })
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)
  await page.screenshot({ path: 'test-results/nav-3-dashboard-loaded.png', fullPage: true })
  if (failed.length) console.error('NAV-3: Server-Fehler:', failed)
  expect(failed).toHaveLength(0)
})

// ─────────────────────────────────────────────────────────────
// 5. WEBHOOK-SECURITY (Pentester — direkte API-Calls)
// ─────────────────────────────────────────────────────────────

test('SEC-1: Webhook ohne Secret → 401 oder 403', async ({ request }) => {
  const resp = await request.post(`${BASE}/api/telegram/webhook`, {
    data: { update_id: 1, message: { text: 'test' } },
    headers: { 'Content-Type': 'application/json' },
    failOnStatusCode: false,
  })
  console.log('SEC-1: Webhook ohne Secret:', resp.status())
  expect([401, 403]).toContain(resp.status())
})

test('SEC-2: Webhook mit falschem Secret → 401', async ({ request }) => {
  const resp = await request.post(`${BASE}/api/telegram/webhook`, {
    data: { update_id: 1 },
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Bot-Api-Secret-Token': 'wrong-secret-pentest',
    },
    failOnStatusCode: false,
  })
  console.log('SEC-2: Webhook mit falschem Secret:', resp.status())
  expect([401, 403]).toContain(resp.status())
})

test('SEC-3: Kein Token in API-Fehler-Responses (Pentester)', async ({ request }) => {
  // Ungültige API-Calls provozieren Fehler-Responses und prüfen ob Token leakt
  const endpoints = ['/api/sources', '/api/ideas', '/api/content', '/api/pipeline/progress']
  for (const ep of endpoints) {
    const resp = await request.get(`${BASE}${ep}`, {
      headers: { 'X-API-Key': 'invalid-key-pentest' },
      failOnStatusCode: false,
    })
    const text = await resp.text().catch(() => '')
    // Token-Pattern: digits:base64 (Telegram Bot Token Format)
    const tokenPattern = /\d{6,12}:[A-Za-z0-9_\-]{30,}/
    const hasToken = tokenPattern.test(text)
    if (hasToken) console.error(`SEC-3: Token-Leak in ${ep}:`, text.substring(0, 100))
    expect(hasToken).toBe(false)
  }
  console.log('SEC-3: Kein Token-Leak in Fehler-Responses ✓')
})
