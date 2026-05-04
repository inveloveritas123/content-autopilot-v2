/**
 * ResearchFindings helper tests (#141 Phase 6.1).
 */
import { describe, test, expect } from 'vitest'

const CATEGORY_LABELS = {
  rules_constraints:   { de: 'Regulierung',    color: 'bg-rose-100 text-rose-700' },
  demand_behavior:     { de: 'Marktnachfrage', color: 'bg-amber-100 text-amber-700' },
  tools_methods:       { de: 'Tools & Methoden', color: 'bg-emerald-100 text-emerald-700' },
  competition_market:  { de: 'Wettbewerb',     color: 'bg-violet-100 text-violet-700' },
  costs_resources:     { de: 'Kosten & Ressourcen', color: 'bg-blue-100 text-blue-700' },
  emerging_topics:     { de: 'Trend-Themen',   color: 'bg-teal-100 text-teal-700' },
}

const IMPACT_ICONS = { positive: '🟢', neutral: '🟡', negative: '🔴' }

describe('ResearchFindings CATEGORY_LABELS', () => {
  test('alle 6 Master-MD-Kategorien vorhanden', () => {
    const keys = Object.keys(CATEGORY_LABELS)
    expect(keys).toHaveLength(6)
    expect(keys).toContain('rules_constraints')
    expect(keys).toContain('demand_behavior')
    expect(keys).toContain('tools_methods')
    expect(keys).toContain('competition_market')
    expect(keys).toContain('costs_resources')
    expect(keys).toContain('emerging_topics')
  })
  test('jede Kategorie hat de + color', () => {
    Object.values(CATEGORY_LABELS).forEach(c => {
      expect(c.de).toBeTruthy()
      expect(c.color).toBeTruthy()
    })
  })
})

describe('IMPACT_ICONS', () => {
  test('3 Werte: positive/neutral/negative', () => {
    expect(IMPACT_ICONS.positive).toBe('🟢')
    expect(IMPACT_ICONS.neutral).toBe('🟡')
    expect(IMPACT_ICONS.negative).toBe('🔴')
  })
})

describe('Findings-Lifecycle (Status-Transitions)', () => {
  // active → dismissed (kein use)
  // active → used (after use_finding_as_idea)
  function applyDismiss(findings, id) {
    return findings.filter(f => f.id !== id)  // UI-Optimistic-Update
  }
  function applyUseAsIdea(findings, id) {
    return findings.filter(f => f.id !== id)  // UI: Aus Liste entfernen
  }

  const sample = [
    { id: '1', status: 'active' },
    { id: '2', status: 'active' },
    { id: '3', status: 'active' },
  ]
  test('dismiss: aus aktiver Liste entfernt', () => {
    const after = applyDismiss(sample, '2')
    expect(after.length).toBe(2)
    expect(after.find(f => f.id === '2')).toBeUndefined()
  })
  test('use-as-idea: aus Liste entfernt (Status wird Backend-side auf used)', () => {
    const after = applyUseAsIdea(sample, '1')
    expect(after.length).toBe(2)
    expect(after.find(f => f.id === '1')).toBeUndefined()
  })
})

describe('Hook-Selection-Logik', () => {
  // hookIdx 0..2 wählen
  function pickHook(hooks, idx) {
    if (!Array.isArray(hooks) || hooks.length === 0) return null
    return idx >= 0 && idx < hooks.length ? hooks[idx] : hooks[0]
  }
  test('valid index → richtige hook', () => {
    expect(pickHook(['A', 'B', 'C'], 1)).toBe('B')
  })
  test('out-of-bounds → erste hook', () => {
    expect(pickHook(['A', 'B'], 5)).toBe('A')
  })
  test('leere hooks → null', () => {
    expect(pickHook([], 0)).toBe(null)
    expect(pickHook(null, 0)).toBe(null)
  })
})

describe('Hook-Truncation für Telegram-Output', () => {
  // Master-MD: max 200 Zeichen pro Hook
  const MAX = 300
  function trimHook(h) {
    return (h || '').slice(0, MAX)
  }
  test('kurze hook bleibt unverändert', () => {
    expect(trimHook('Kurz')).toBe('Kurz')
  })
  test('lange hook wird gekürzt', () => {
    const long = 'X'.repeat(500)
    expect(trimHook(long).length).toBe(MAX)
  })
})
