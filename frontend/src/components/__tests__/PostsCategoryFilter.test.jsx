/**
 * Phase 4.1 / #145 — Posts.jsx category-Filter
 * Testet die Filter-Logic isoliert (Posts-Component ist zu groß für full mount).
 */
import { describe, test, expect } from 'vitest'

// Reproduziere die Filter-Logik aus Posts.jsx visibleList (Z. 2346-2371)
function applyCategoryFilter(list, categoryFilter) {
  if (!categoryFilter) return list
  return list.filter(p => p.category === categoryFilter)
}

const samplePosts = [
  { id: 1, content_text: 'News', category: 'news' },
  { id: 2, content_text: 'Story', category: 'persoenlich' },
  { id: 3, content_text: 'Beleg', category: 'trust' },
  { id: 4, content_text: 'How-to', category: 'praxis' },
  { id: 5, content_text: 'Alt-Post ohne Kategorie', category: null },
]

describe('Posts category-Filter (#145 Phase 4.1)', () => {
  test('leerer Filter → alle Posts (inkl. category=null)', () => {
    const r = applyCategoryFilter(samplePosts, '')
    expect(r.length).toBe(5)
  })
  test('news-Filter → nur news-Posts', () => {
    const r = applyCategoryFilter(samplePosts, 'news')
    expect(r.length).toBe(1)
    expect(r[0].category).toBe('news')
  })
  test('persoenlich-Filter (mit ASCII-statt-Umlaut)', () => {
    const r = applyCategoryFilter(samplePosts, 'persoenlich')
    expect(r.length).toBe(1)
    expect(r[0].content_text).toBe('Story')
  })
  test('trust-Filter', () => {
    expect(applyCategoryFilter(samplePosts, 'trust').length).toBe(1)
  })
  test('praxis-Filter', () => {
    expect(applyCategoryFilter(samplePosts, 'praxis').length).toBe(1)
  })
  test('alte Posts mit category=null werden ausgefiltert wenn Kategorie aktiv', () => {
    const r = applyCategoryFilter(samplePosts, 'news')
    expect(r.find(p => p.category === null)).toBeUndefined()
  })
  test('ungültiger Filter-Wert → leer (kein Match)', () => {
    expect(applyCategoryFilter(samplePosts, 'unknown').length).toBe(0)
  })
})

describe('P12-Output Kategorie-Validierung', () => {
  // Reproduziere Backend-Validierung aus tasks/p12_task.py
  const ALLOWED = new Set(['news', 'persoenlich', 'trust', 'praxis'])
  function validateCategory(raw) {
    const cat = (raw || '').trim().toLowerCase()
    return ALLOWED.has(cat) ? cat : null
  }

  test('gültige Kategorie wird durchgereicht', () => {
    expect(validateCategory('news')).toBe('news')
    expect(validateCategory('praxis')).toBe('praxis')
  })
  test('Whitespace + Case wird normalisiert', () => {
    expect(validateCategory('  News  ')).toBe('news')
    expect(validateCategory('PERSOENLICH')).toBe('persoenlich')
  })
  test('ungültige Werte → null', () => {
    expect(validateCategory('lustig')).toBe(null)
    expect(validateCategory('')).toBe(null)
    expect(validateCategory(null)).toBe(null)
    expect(validateCategory(undefined)).toBe(null)
  })
  test('Umlaut-Variante "persönlich" akzeptieren wir NICHT (CHECK-Constraint)', () => {
    expect(validateCategory('persönlich')).toBe(null)
  })
})
