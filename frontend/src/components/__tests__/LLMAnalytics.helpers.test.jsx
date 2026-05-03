/**
 * LLMAnalytics-Helper-Tests
 * Sicher gegen Refactor: testet die exposed Helpers ohne den ganzen
 * Component-Tree zu rendern. Echte Component-Tests (mit Mock-API)
 * folgen wenn Robert den Vitest-Setup approved hat.
 */
import { describe, test, expect } from 'vitest'

// fmtTokens ist in LLMAnalytics.jsx als interne Funktion definiert.
// Wir reproduzieren die Logik hier 1:1 als Test gegen Regression.
function fmtTokens(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(0) + 'K'
  return String(n)
}

describe('LLMAnalytics fmtTokens', () => {
  test('null/undefined/0 → "0"', () => {
    expect(fmtTokens(0)).toBe('0')
    expect(fmtTokens(null)).toBe('0')
    expect(fmtTokens(undefined)).toBe('0')
  })
  test('< 1000 → string-Zahl', () => {
    expect(fmtTokens(42)).toBe('42')
    expect(fmtTokens(999)).toBe('999')
  })
  test('1k–1M → K-Suffix', () => {
    expect(fmtTokens(1000)).toBe('1K')
    expect(fmtTokens(12500)).toBe('13K')
    expect(fmtTokens(999999)).toBe('1000K')
  })
  test('>= 1M → M-Suffix mit Decimal', () => {
    expect(fmtTokens(1_000_000)).toBe('1.0M')
    expect(fmtTokens(2_500_000)).toBe('2.5M')
    expect(fmtTokens(32_000_000)).toBe('32.0M')
  })
})

describe('Anomalie-Banner-Logik', () => {
  // Banner-Kondition aus LLMAnalytics: anomaly?.anomaly === true
  test('null anomaly → kein Banner', () => {
    const anomaly = null
    expect(!!(anomaly?.anomaly)).toBe(false)
  })
  test('anomaly=false → kein Banner', () => {
    const anomaly = { anomaly: false, factor: 1.5, current_hour_cost_cents: 5 }
    expect(!!(anomaly?.anomaly)).toBe(false)
  })
  test('anomaly=true → Banner sichtbar', () => {
    const anomaly = { anomaly: true, factor: 3.2, current_hour_cost_cents: 50 }
    expect(!!(anomaly?.anomaly)).toBe(true)
  })
})

describe('Provider-Reconciliation Diff-Logik', () => {
  // Re-implementiert aus dem IIFE in LLMAnalytics.jsx
  function calcDiff(internCostUsd, reqCostUsd) {
    const costDiff = reqCostUsd - internCostUsd
    const costDiffPct = internCostUsd > 0 ? (costDiff / internCostUsd) * 100 : null
    const significant = costDiffPct !== null && Math.abs(costDiffPct) > 10
    return { costDiff, costDiffPct, significant }
  }
  test('exakte Übereinstimmung → kein significant', () => {
    const r = calcDiff(1.0, 1.0)
    expect(r.significant).toBe(false)
    expect(r.costDiffPct).toBe(0)
  })
  test('5% Abweichung → kein significant', () => {
    const r = calcDiff(1.0, 1.05)
    expect(r.significant).toBe(false)
  })
  test('15% Abweichung → significant', () => {
    const r = calcDiff(1.0, 1.15)
    expect(r.significant).toBe(true)
    expect(r.costDiffPct).toBeCloseTo(15, 5)
  })
  test('Negative Abweichung (Requesty zeigt weniger) → significant wenn > 10%', () => {
    const r = calcDiff(1.0, 0.8)
    expect(r.significant).toBe(true)
    expect(r.costDiff).toBeCloseTo(-0.2, 5)
  })
  test('intern=0 → costDiffPct=null, kein significant', () => {
    const r = calcDiff(0, 1.0)
    expect(r.costDiffPct).toBe(null)
    expect(r.significant).toBe(false)
  })
})

describe('auto_cache Toggle-Logik (Frontend-API-Layer)', () => {
  // Frontend-Snippet: forceSave-Override verhindert dass Save ohne Test funktioniert
  function canSave(testResult, forceSave) {
    return !!(testResult?.ok || forceSave)
  }
  test('kein Test, kein Override → blocked', () => {
    expect(canSave(null, false)).toBe(false)
  })
  test('Test ok → erlaubt', () => {
    expect(canSave({ ok: true, latency_ms: 200 }, false)).toBe(true)
  })
  test('Test fail, kein Override → blocked', () => {
    expect(canSave({ ok: false, error: '403' }, false)).toBe(false)
  })
  test('Test fail, Override → erlaubt', () => {
    expect(canSave({ ok: false, error: '412' }, true)).toBe(true)
  })
})
