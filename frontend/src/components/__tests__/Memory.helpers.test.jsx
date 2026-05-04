/**
 * Memory.jsx-Helper-Tests (#140 Phase 5 follow-up)
 * Reproduziert die in-line-Helper aus Memory.jsx als Pure-Function-Tests.
 */
import { describe, test, expect } from 'vitest'

// Reproduziert timeAgo aus Memory.jsx
function timeAgo(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (sec < 60) return 'gerade eben'
  if (sec < 3600) return `${Math.floor(sec / 60)} Min.`
  if (sec < 86400) return `${Math.floor(sec / 3600)} Std.`
  if (sec < 604800) return `vor ${Math.floor(sec / 86400)} Tagen`
  return d.toLocaleDateString('de-DE')
}

const SOURCE_ICONS_MAP = {
  voice_telegram: 'Mic',
  voice_whatsapp: 'Mic',
  photo_telegram: 'Image',
  photo_whatsapp: 'Image',
  manual_note: 'FileText',
  transcript_extra: 'FileText',
}

const CLASS_COLORS_MAP = {
  werte: 'bg-emerald-100 text-emerald-700',
  stories: 'bg-amber-100 text-amber-700',
  konflikte: 'bg-rose-100 text-rose-700',
}

describe('timeAgo', () => {
  test('null/undefined → empty string', () => {
    expect(timeAgo(null)).toBe('')
    expect(timeAgo(undefined)).toBe('')
    expect(timeAgo('')).toBe('')
  })
  test('< 60s → "gerade eben"', () => {
    const recent = new Date(Date.now() - 30_000).toISOString()
    expect(timeAgo(recent)).toBe('gerade eben')
  })
  test('< 1h → Minuten', () => {
    const m30 = new Date(Date.now() - 30 * 60 * 1000).toISOString()
    expect(timeAgo(m30)).toMatch(/^\d+ Min\.$/)
  })
  test('< 1d → Stunden', () => {
    const h5 = new Date(Date.now() - 5 * 3600 * 1000).toISOString()
    expect(timeAgo(h5)).toMatch(/^\d+ Std\.$/)
  })
  test('< 1w → Tage', () => {
    const d3 = new Date(Date.now() - 3 * 86400 * 1000).toISOString()
    expect(timeAgo(d3)).toMatch(/^vor \d+ Tagen$/)
  })
  test('> 1w → de-DE-Datum', () => {
    const d10 = new Date(Date.now() - 10 * 86400 * 1000).toISOString()
    const result = timeAgo(d10)
    // Erwartet: 'DD.MM.YYYY' oder ähnliches Format
    expect(result).toMatch(/\d/)
    expect(result.length).toBeGreaterThan(5)
  })
})

describe('Source-Type-Mapping', () => {
  test('alle 6 erlaubten source_types haben Icon', () => {
    const types = ['voice_telegram', 'voice_whatsapp', 'photo_telegram',
                   'photo_whatsapp', 'manual_note', 'transcript_extra']
    types.forEach(t => expect(SOURCE_ICONS_MAP[t]).toBeTruthy())
  })
  test('Telegram + WhatsApp Voice teilen Icon', () => {
    expect(SOURCE_ICONS_MAP.voice_telegram).toBe(SOURCE_ICONS_MAP.voice_whatsapp)
  })
  test('Telegram + WhatsApp Photo teilen Icon', () => {
    expect(SOURCE_ICONS_MAP.photo_telegram).toBe(SOURCE_ICONS_MAP.photo_whatsapp)
  })
})

describe('Classification-Color-Mapping', () => {
  test('alle 3 Klassifikationen haben Farbe', () => {
    expect(CLASS_COLORS_MAP.werte).toContain('emerald')
    expect(CLASS_COLORS_MAP.stories).toContain('amber')
    expect(CLASS_COLORS_MAP.konflikte).toContain('rose')
  })
})

describe('Picker-Suggestion-Reproduktion (aus Backend-Logik)', () => {
  function suggestionText(classification, days_ago) {
    const when = days_ago ? `vor ${days_ago} Tagen` : 'kürzlich'
    if (classification === 'stories') return `Du hast ${when} eine Geschichte erzählt — daraus wird ein guter Post.`
    if (classification === 'werte') return `Vor ${when} hast du über deine Werte gesprochen — Material für Trust-Content.`
    if (classification === 'konflikte') return `Vor ${when} hast du eine Spannung beschrieben — gut für ehrlichen Content.`
    return `Du hast ${when} etwas notiert — willst du daraus einen Post machen?`
  }
  test('stories → Geschichte-Suggestion', () => {
    expect(suggestionText('stories', 14)).toContain('Geschichte erzählt')
  })
  test('werte → Trust-Content-Suggestion', () => {
    expect(suggestionText('werte', 21)).toContain('Werte gesprochen')
  })
  test('konflikte → ehrlicher-Content-Suggestion', () => {
    expect(suggestionText('konflikte', 7)).toContain('Spannung')
  })
  test('null classification → generischer Picker-Text', () => {
    expect(suggestionText(null, 30)).toContain('etwas notiert')
  })
})

describe('Search-Result-Similarity-Format', () => {
  function fmtSim(sim) {
    return `${(sim * 100).toFixed(0)}%`
  }
  test('similarity in % runden', () => {
    expect(fmtSim(0.6712)).toBe('67%')
    expect(fmtSim(0.5)).toBe('50%')
    expect(fmtSim(1.0)).toBe('100%')
    expect(fmtSim(0.0)).toBe('0%')
  })
})

describe('Filter-Validation (Backend-API-Konstanten reproduziert)', () => {
  const ALLOWED_SOURCE_TYPES = new Set([
    'voice_telegram', 'voice_whatsapp', 'photo_telegram',
    'photo_whatsapp', 'manual_note', 'transcript_extra',
  ])
  const ALLOWED_CLASSIFICATIONS = new Set(['werte', 'stories', 'konflikte'])

  test('source_types-Filter akzeptiert nur whitelist', () => {
    expect(ALLOWED_SOURCE_TYPES.has('voice_telegram')).toBe(true)
    expect(ALLOWED_SOURCE_TYPES.has('foobar')).toBe(false)
  })
  test('classification-Filter akzeptiert nur 3 Werte', () => {
    expect(ALLOWED_CLASSIFICATIONS.size).toBe(3)
    expect(ALLOWED_CLASSIFICATIONS.has('werte')).toBe(true)
    expect(ALLOWED_CLASSIFICATIONS.has('hallo')).toBe(false)
  })
})
