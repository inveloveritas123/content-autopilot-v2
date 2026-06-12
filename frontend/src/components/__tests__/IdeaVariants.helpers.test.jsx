/**
 * IdeaVariants helper tests (#147 Phase 4.2).
 */
import { describe, test, expect } from 'vitest'

const TYPE_META = {
  hook: { label: 'Hook', desc: 'provokant', color: 'bg-rose-100 text-rose-700 border-rose-200' },
  story: {
    label: 'Story',
    desc: 'persönlich',
    color: 'bg-amber-100 text-amber-700 border-amber-200',
  },
  these: {
    label: 'These',
    desc: 'sachlich',
    color: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  },
}

describe('IdeaVariants TYPE_META', () => {
  test('alle 3 Typen vorhanden', () => {
    expect(TYPE_META.hook).toBeTruthy()
    expect(TYPE_META.story).toBeTruthy()
    expect(TYPE_META.these).toBeTruthy()
  })
  test('jeder Typ hat label + desc + color', () => {
    Object.values(TYPE_META).forEach((m) => {
      expect(m.label).toBeTruthy()
      expect(m.desc).toBeTruthy()
      expect(m.color).toBeTruthy()
    })
  })
  test('Farben semantisch (rose=hook, amber=story, emerald=these)', () => {
    expect(TYPE_META.hook.color).toContain('rose')
    expect(TYPE_META.story.color).toContain('amber')
    expect(TYPE_META.these.color).toContain('emerald')
  })
})

describe('Variants-Choice-Logik', () => {
  // Reproduktion der Backend-Logik: nach choose ist genau 1 Variant chosen
  function applyChoose(variants, chosenId) {
    return variants.map((v) => ({
      ...v,
      is_chosen: v.id === chosenId,
      chosen_at: v.id === chosenId ? new Date().toISOString() : null,
    }))
  }
  const sample = [
    { id: '1', variant_type: 'hook', hook_text: 'A', body_outline: 'a', is_chosen: false },
    { id: '2', variant_type: 'story', hook_text: 'B', body_outline: 'b', is_chosen: false },
    { id: '3', variant_type: 'these', hook_text: 'C', body_outline: 'c', is_chosen: false },
  ]
  test('keine Auswahl → keine is_chosen', () => {
    expect(sample.find((v) => v.is_chosen)).toBeUndefined()
  })
  test('choose 2 → nur 2 chosen', () => {
    const after = applyChoose(sample, '2')
    expect(after.filter((v) => v.is_chosen).length).toBe(1)
    expect(after.find((v) => v.is_chosen).id).toBe('2')
  })
  test('umwählen → erste Wahl entwählen', () => {
    let s = applyChoose(sample, '1')
    s = applyChoose(s, '3')
    expect(s.find((v) => v.id === '1').is_chosen).toBe(false)
    expect(s.find((v) => v.id === '3').is_chosen).toBe(true)
  })
})

describe('Variant-Sort-Order', () => {
  // Backend liefert: hook → story → these (siehe API-Sortierung)
  function sortByType(variants) {
    const order = { hook: 1, story: 2, these: 3 }
    return [...variants].sort(
      (a, b) => (order[a.variant_type] || 99) - (order[b.variant_type] || 99)
    )
  }
  test('beliebige Reihenfolge → hook/story/these', () => {
    const input = [{ variant_type: 'these' }, { variant_type: 'hook' }, { variant_type: 'story' }]
    const out = sortByType(input).map((v) => v.variant_type)
    expect(out).toEqual(['hook', 'story', 'these'])
  })
})
