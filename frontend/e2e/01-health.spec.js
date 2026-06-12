// Backend-Health: ist die API ueberhaupt da? Erstes Gate, kein Frontend involved.

import { test, expect } from './fixtures.js'

test.describe('Backend Health', () => {
  test('/api/health antwortet mit overall=ok', async ({ request }) => {
    const resp = await request.get('/api/health')
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('overall')
    // 'ok' im CI mit frischer DB/Redis; 'degraded' tolerieren wir,
    // wenn z.B. Redis kurz nach Start noch warm-up macht — Smoke darf
    // hier nicht zu streng sein.
    expect(['ok', 'degraded']).toContain(body.overall)
    expect(body.checks).toHaveProperty('db', 'ok')
  })

  test('/api/tenant-init validiert den X-API-Key', async ({ request }) => {
    const resp = await request.get('/api/tenant-init')
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('tenant_key')
    expect(body).toHaveProperty('tenant_id')
    expect(body.tenant_name).toBeTruthy()
  })
})
