/**
 * IndustryAndHooks helper-Logik (Phase 4.4 + 7.4).
 */
import { describe, test, expect } from 'vitest'

const HOOK_TYPES = ['general', 'hook', 'story', 'these', 'manual']

describe('IndustryAndHooks Validation-Helpers', () => {
  function validateIndustry(s) {
    return typeof s === 'string' && s.trim().length >= 3 && s.length <= 100
  }
  function validateHook(s) {
    return typeof s === 'string' && s.trim().length >= 5 && s.length <= 500
  }

  test('industry: zu kurz → invalid', () => {
    expect(validateIndustry('')).toBe(false)
    expect(validateIndustry('AB')).toBe(false)
    expect(validateIndustry('Coaching')).toBe(true)
  })

  test('industry: zu lang → invalid', () => {
    expect(validateIndustry('X'.repeat(101))).toBe(false)
    expect(validateIndustry('X'.repeat(99))).toBe(true)
  })

  test('hook: < 5 chars → invalid', () => {
    expect(validateHook('Hi')).toBe(false)
    expect(validateHook('Hallo')).toBe(true)
  })

  test('hook: > 500 chars → invalid', () => {
    expect(validateHook('X'.repeat(501))).toBe(false)
  })
})

describe('Hook-Type-Whitelist', () => {
  test('alle 5 Typen', () => {
    expect(HOOK_TYPES).toContain('general')
    expect(HOOK_TYPES).toContain('hook')
    expect(HOOK_TYPES).toContain('story')
    expect(HOOK_TYPES).toContain('these')
    expect(HOOK_TYPES).toContain('manual')
  })
})

describe('Industry-Context-Display-Helpers', () => {
  // top_themen / trigger_woerter / typische_kundenfragen vom Backend
  function safeArray(maybe) {
    return Array.isArray(maybe) ? maybe : []
  }
  test('null → leeres Array', () => {
    expect(safeArray(null)).toEqual([])
    expect(safeArray(undefined)).toEqual([])
  })
  test('Array bleibt', () => {
    expect(safeArray(['a', 'b'])).toEqual(['a', 'b'])
  })
  test('Non-Array → leeres Array', () => {
    expect(safeArray('foo')).toEqual([])
    expect(safeArray(42)).toEqual([])
  })
})

describe('Hook-Sort-Order', () => {
  function sortHooks(hooks, by = 'performance') {
    const arr = [...hooks]
    if (by === 'performance')
      return arr.sort((a, b) => (b.performance_score || 0) - (a.performance_score || 0))
    if (by === 'usage') return arr.sort((a, b) => (b.used_count || 0) - (a.used_count || 0))
    if (by === 'recent') return arr.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    return arr
  }
  const sample = [
    { id: '1', performance_score: 0.5, used_count: 10, created_at: '2026-01-01' },
    { id: '2', performance_score: 0.9, used_count: 2, created_at: '2026-03-01' },
    { id: '3', performance_score: 0.2, used_count: 50, created_at: '2026-02-01' },
  ]
  test('sort by performance', () => {
    expect(sortHooks(sample, 'performance').map((h) => h.id)).toEqual(['2', '1', '3'])
  })
  test('sort by usage', () => {
    expect(sortHooks(sample, 'usage').map((h) => h.id)).toEqual(['3', '1', '2'])
  })
  test('sort by recent', () => {
    expect(sortHooks(sample, 'recent').map((h) => h.id)).toEqual(['2', '3', '1'])
  })
})
