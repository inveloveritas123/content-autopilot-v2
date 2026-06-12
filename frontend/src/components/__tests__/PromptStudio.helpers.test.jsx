/**
 * PromptStudio.jsx-Helper-Tests (P3).
 * Reine Pure-Function-Tests — kein DOM, kein Fetch.
 *
 * Muster: Memory.helpers.test.jsx (Vitest, describe/test/expect, inline-Kopie der Helpers)
 */
import { describe, test, expect } from 'vitest'

// Reproduziert kindToGroup aus PromptStudio.jsx
function kindToGroup(kind) {
  if (kind === 'prompt') return 'Prompts'
  if (kind === 'rule') return 'Rules'
  if (kind === 'schema') return 'Schemas'
  return 'Sonstige'
}

// Reproduziert sourceBadgeColor aus PromptStudio.jsx
function sourceBadgeColor(source) {
  return source === 'overlay' ? 'yellow' : 'gray'
}

// Reproduziert isBaseNewerThanOverlay aus PromptStudio.jsx
function isBaseNewerThanOverlay(file) {
  if (!file.has_overlay || !file.base_mtime) return false
  const baseMtime = new Date(file.base_mtime).getTime()
  const effectiveMtime = new Date(file.mtime).getTime()
  return baseMtime > effectiveMtime
}

// Reproduziert isDirty aus PromptStudio.jsx
function isDirty(current, loaded) {
  return current !== loaded
}

// ─── kindToGroup ──────────────────────────────────────────────────────────────

describe('kindToGroup', () => {
  test('prompt → Prompts', () => {
    expect(kindToGroup('prompt')).toBe('Prompts')
  })
  test('rule → Rules', () => {
    expect(kindToGroup('rule')).toBe('Rules')
  })
  test('schema → Schemas', () => {
    expect(kindToGroup('schema')).toBe('Schemas')
  })
  test('unbekannte kind → Sonstige', () => {
    expect(kindToGroup('foobar')).toBe('Sonstige')
    expect(kindToGroup(undefined)).toBe('Sonstige')
    expect(kindToGroup(null)).toBe('Sonstige')
    expect(kindToGroup('')).toBe('Sonstige')
  })
  test('alle drei Haupt-Kinds abgedeckt', () => {
    const kinds = ['prompt', 'rule', 'schema']
    const groups = kinds.map(kindToGroup)
    expect(groups).toEqual(['Prompts', 'Rules', 'Schemas'])
  })
})

// ─── sourceBadgeColor ─────────────────────────────────────────────────────────

describe('sourceBadgeColor', () => {
  test('overlay → yellow', () => {
    expect(sourceBadgeColor('overlay')).toBe('yellow')
  })
  test('base → gray', () => {
    expect(sourceBadgeColor('base')).toBe('gray')
  })
  test('unbekannte Quelle → gray (safe default)', () => {
    expect(sourceBadgeColor(undefined)).toBe('gray')
    expect(sourceBadgeColor('unknown')).toBe('gray')
  })
  test('overlay hat auffälligere Farbe als base', () => {
    // Overlay-Edits sollen visuell hervorstechen
    const overlayColor = sourceBadgeColor('overlay')
    const baseColor = sourceBadgeColor('base')
    expect(overlayColor).not.toBe(baseColor)
  })
})

// ─── isBaseNewerThanOverlay ───────────────────────────────────────────────────

describe('isBaseNewerThanOverlay', () => {
  const older = '2024-01-01T10:00:00Z'
  const newer = '2024-06-01T10:00:00Z'

  test('false wenn kein Overlay vorhanden', () => {
    expect(isBaseNewerThanOverlay({ has_overlay: false, base_mtime: newer, mtime: older })).toBe(
      false
    )
  })
  test('false wenn base_mtime fehlt', () => {
    expect(isBaseNewerThanOverlay({ has_overlay: true, base_mtime: null, mtime: older })).toBe(
      false
    )
  })
  test('true wenn Base neuer ist als Overlay', () => {
    // mtime = Overlay-Zeit (älter), base_mtime = Base-Zeit (neuer)
    expect(isBaseNewerThanOverlay({ has_overlay: true, base_mtime: newer, mtime: older })).toBe(
      true
    )
  })
  test('false wenn Overlay neuer ist als Base', () => {
    // Normaler Fall: Overlay wurde nach dem Base-Stand erstellt
    expect(isBaseNewerThanOverlay({ has_overlay: true, base_mtime: older, mtime: newer })).toBe(
      false
    )
  })
  test('false wenn Zeiten gleich sind', () => {
    expect(isBaseNewerThanOverlay({ has_overlay: true, base_mtime: older, mtime: older })).toBe(
      false
    )
  })
})

// ─── isDirty ──────────────────────────────────────────────────────────────────

describe('isDirty', () => {
  test('identischer Inhalt → nicht dirty', () => {
    expect(isDirty('abc', 'abc')).toBe(false)
    expect(isDirty('', '')).toBe(false)
  })
  test('veränderter Inhalt → dirty', () => {
    expect(isDirty('abc', 'abcd')).toBe(true)
    expect(isDirty('new content', 'old content')).toBe(true)
  })
  test('leerer String vs. nicht-leerer → dirty', () => {
    expect(isDirty('', 'original')).toBe(true)
    expect(isDirty('new', '')).toBe(true)
  })
  test('whitespace-Unterschied zählt als dirty', () => {
    // Kein trim — Operator muss explizit entscheiden
    expect(isDirty('text\n', 'text')).toBe(true)
    expect(isDirty(' text', 'text')).toBe(true)
  })
})

// ─── Pfad-zu-Gruppe-Mapping (Integration der Helpers) ────────────────────────

describe('Pfad → Gruppe (via kind)', () => {
  // Repräsentiert die API-Antwort PromptFileInfo
  function makeFileInfo(path, kind) {
    return { path, name: path.split('/').pop(), kind }
  }

  test('prompts/-Dateien werden als Prompts gruppiert', () => {
    const f = makeFileInfo('prompts/P12-post-generierung.md', 'prompt')
    expect(kindToGroup(f.kind)).toBe('Prompts')
  })
  test('rules/-Dateien werden als Rules gruppiert', () => {
    const f = makeFileInfo('rules/brand-rules.md', 'rule')
    expect(kindToGroup(f.kind)).toBe('Rules')
  })
  test('schemas/-Dateien werden als Schemas gruppiert', () => {
    const f = makeFileInfo('schemas/output-schema.json', 'schema')
    expect(kindToGroup(f.kind)).toBe('Schemas')
  })
})
