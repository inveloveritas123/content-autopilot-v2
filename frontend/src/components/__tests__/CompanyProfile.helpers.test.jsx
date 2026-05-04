/**
 * CompanyProfile-Helpers (Phase 8.x, Issue #148, Welle B/C).
 */
import { describe, test, expect } from 'vitest'

describe('Company-Profile Field-Mapping', () => {
  const FIELD_LABELS = {
    company_name: 'Firmenname',
    industry: 'Branche',
    contact_person_name: 'Ansprechpartner',
    contact_role: 'Rolle/Position',
    contact_email: 'Kontakt-Email',
    website: 'Website',
    region: 'Region',
    founded_year: 'Gründungsjahr',
    headcount: 'Mitarbeitende',
    company_size: 'Größe (solo/team/sme/enterprise)',
    legal_form: 'Rechtsform',
    usp: 'USP / Alleinstellung',
    target_audience: 'Zielgruppe',
    values_short: 'Werte (kurz)',
  }

  test('alle 14 Standard-Felder vorhanden', () => {
    expect(Object.keys(FIELD_LABELS)).toHaveLength(14)
    expect(FIELD_LABELS.company_name).toBe('Firmenname')
    expect(FIELD_LABELS.contact_person_name).toBe('Ansprechpartner')
    expect(FIELD_LABELS.usp).toBeTruthy()
  })
})

describe('Source-Trust-Hierarchie (UI-Badges)', () => {
  const SOURCE_BADGES = {
    manual_input: { label: 'Manuell', color: '#16a34a' },
    md_upload: { label: 'MD-Upload', color: '#2563eb' },
    wizard_explicit: { label: 'Wizard', color: '#7c3aed' },
    auto_enrich: { label: 'Auto-Enrich', color: '#0891b2' },
    voice_extracted: { label: 'Voice', color: '#db2777' },
    wizard_inferred: { label: 'Wizard (KI)', color: '#a78bfa' },
    legacy_migration: { label: 'Legacy', color: '#6b7280' },
  }

  test('alle 7 Quellen mit Badge', () => {
    expect(Object.keys(SOURCE_BADGES)).toHaveLength(7)
    expect(SOURCE_BADGES.manual_input.color).toBe('#16a34a')
  })

  test('Trust-Sortierung: manual > md > wizard_explicit > auto > voice > inferred > legacy', () => {
    const TRUST = {
      manual_input: 1.0,
      md_upload: 0.9,
      wizard_explicit: 0.85,
      auto_enrich: 0.8,
      voice_extracted: 0.7,
      wizard_inferred: 0.6,
      legacy_migration: 0.5,
    }
    const sorted = Object.entries(TRUST).sort((a, b) => b[1] - a[1]).map(e => e[0])
    expect(sorted[0]).toBe('manual_input')
    expect(sorted[6]).toBe('legacy_migration')
  })
})

describe('Form-Number-Cast', () => {
  function castNumberFields(form) {
    const out = { ...form }
    for (const k of ['founded_year', 'headcount']) {
      if (out[k] && out[k] !== '') {
        const n = parseInt(out[k], 10)
        if (!isNaN(n)) out[k] = n
        else delete out[k]
      } else {
        delete out[k]
      }
    }
    return out
  }

  test('founded_year wird Integer', () => {
    expect(castNumberFields({ founded_year: '2020' })).toEqual({ founded_year: 2020 })
  })
  test('leeres headcount wird entfernt', () => {
    expect(castNumberFields({ headcount: '' })).toEqual({})
  })
  test('NaN wird entfernt', () => {
    expect(castNumberFields({ founded_year: 'abc' })).toEqual({})
  })
})

describe('RtbF Mode-Validation', () => {
  const VALID_MODES = ['full', 'memory_selective', 'telegram_purge', 'audit_selective']
  test('alle 4 Modi', () => {
    expect(VALID_MODES).toHaveLength(4)
    expect(VALID_MODES).toContain('full')
    expect(VALID_MODES).toContain('memory_selective')
    expect(VALID_MODES).toContain('telegram_purge')
    expect(VALID_MODES).toContain('audit_selective')
  })

  function buildPayload(mode, opts = {}) {
    const p = { mode }
    if (opts.older_than_days != null) p.older_than_days = parseInt(opts.older_than_days, 10)
    if (opts.classification) p.classification = opts.classification
    if (mode === 'audit_selective' && opts.record_ids) {
      p.record_ids = opts.record_ids.split(',').map(s => s.trim()).filter(Boolean)
    }
    return p
  }

  test('memory_selective mit older_than_days', () => {
    expect(buildPayload('memory_selective', { older_than_days: '30' })).toEqual({
      mode: 'memory_selective', older_than_days: 30,
    })
  })

  test('audit_selective parst record_ids', () => {
    expect(buildPayload('audit_selective', { record_ids: 'abc, def, ghi' })).toEqual({
      mode: 'audit_selective', record_ids: ['abc', 'def', 'ghi'],
    })
  })

  test('audit_selective filter empty record_ids', () => {
    expect(buildPayload('audit_selective', { record_ids: 'abc,,ghi' })).toEqual({
      mode: 'audit_selective', record_ids: ['abc', 'ghi'],
    })
  })
})

describe('Memory-Viz Class-Color-Mapping', () => {
  const CLASS_COLORS = {
    werte: '#2563eb',
    stories: '#16a34a',
    konflikte: '#dc2626',
    unklassifiziert: '#6b7280',
  }

  test('werte=blau, stories=grün, konflikte=rot', () => {
    expect(CLASS_COLORS.werte).toBe('#2563eb')
    expect(CLASS_COLORS.stories).toBe('#16a34a')
    expect(CLASS_COLORS.konflikte).toBe('#dc2626')
  })
})
