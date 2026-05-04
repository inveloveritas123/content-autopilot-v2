/**
 * Industry-Boost-Logik (Phase 4.4) als Frontend-Test reproduziert.
 * Spiegelt die Backend-Logik für UI-Hinweise (z.B. „+1.0 Branchen-Bonus").
 */
import { describe, test, expect } from 'vitest'

const HIT_BOOST = { 0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5 }
const MAX_BOOST = 2.5

function countHits(text, triggers) {
  if (!text || !triggers || !triggers.length) return 0
  const lower = text.toLowerCase()
  const seen = new Set()
  let hits = 0
  for (const w of triggers) {
    const wl = (w || '').toLowerCase().trim()
    if (wl && !seen.has(wl) && lower.includes(wl)) {
      hits += 1
      seen.add(wl)
    }
  }
  return hits
}

function computeBoost(hits) {
  if (hits >= 5) return MAX_BOOST
  return HIT_BOOST[hits] || 0
}

describe('Industry-Boost JS-Reproduktion', () => {
  test('keine Trigger → kein Boost', () => {
    expect(countHits('hallo welt', [])).toBe(0)
    expect(computeBoost(0)).toBe(0)
  })
  test('1 Trigger → 0.5', () => {
    expect(countHits('Coaching ist KING', ['coaching'])).toBe(1)
    expect(computeBoost(1)).toBe(0.5)
  })
  test('3 Trigger → 1.5', () => {
    expect(countHits('A B C', ['a', 'b', 'c'])).toBe(3)
    expect(computeBoost(3)).toBe(1.5)
  })
  test('5+ Trigger → MAX 2.5', () => {
    expect(computeBoost(5)).toBe(2.5)
    expect(computeBoost(7)).toBe(2.5)
  })
  test('Dedupe', () => {
    expect(countHits('coaching coaching coaching', ['coaching'])).toBe(1)
  })
  test('Case-insensitive', () => {
    expect(countHits('LEADERSHIP-Skill', ['leadership'])).toBe(1)
  })
})

describe('Frontend-UI: Boost-Hinweis-Format', () => {
  function fmtBoostHint(hits, boost) {
    if (hits === 0) return ''
    const sign = boost >= 0 ? '+' : ''
    return `${sign}${boost.toFixed(1)} Branchen-Bonus (${hits} Treffer)`
  }
  test('format mit hits=2', () => {
    expect(fmtBoostHint(2, 1.0)).toBe('+1.0 Branchen-Bonus (2 Treffer)')
  })
  test('format ohne hits → leer', () => {
    expect(fmtBoostHint(0, 0)).toBe('')
  })
})
