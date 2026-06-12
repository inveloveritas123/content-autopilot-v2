/**
 * Company-Profile-Form (Phase 8.x, Issue #148).
 *
 * - Optional: alle Felder leer lassen ist erlaubt
 * - Auto-fillable: Wizard / MD-Upload / Voice-Extraction (zeigt Provenance)
 * - Self-Learning Vorschläge unter 0.85 → Review-Liste mit Accept/Reject
 */
import { useState, useEffect } from 'react'
import { Building2, Save, Loader2, History, AlertCircle, Check, X, Upload } from 'lucide-react'
import { Button } from './ui/Button'
import {
  getCompanyProfile,
  updateCompanyProfile,
  getCompanyProvenance,
  getCompanyProfilePending,
  reviewCompanyProfileSuggestion,
  importCompanyProfileMd,
} from '../api'

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

const SOURCE_BADGES = {
  manual_input: { label: 'Manuell', color: '#16a34a' },
  md_upload: { label: 'MD-Upload', color: '#2563eb' },
  wizard_explicit: { label: 'Wizard', color: '#7c3aed' },
  auto_enrich: { label: 'Auto-Enrich', color: '#0891b2' },
  voice_extracted: { label: 'Voice', color: '#db2777' },
  wizard_inferred: { label: 'Wizard (KI)', color: '#a78bfa' },
  legacy_migration: { label: 'Legacy', color: '#6b7280' },
}

export default function CompanyProfile() {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({})
  const [provenance, setProvenance] = useState({})
  const [pending, setPending] = useState([])
  const [tab, setTab] = useState('form')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [savedAt, setSavedAt] = useState(null)
  const [mdContent, setMdContent] = useState('')
  const [importAutoApply, setImportAutoApply] = useState(true)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)

  async function loadAll() {
    try {
      const [p, prov, pend] = await Promise.all([
        getCompanyProfile(),
        getCompanyProvenance(),
        getCompanyProfilePending(),
      ])
      setProfile(p)
      const initial = {}
      Object.keys(FIELD_LABELS).forEach((k) => {
        initial[k] = p[k] ?? ''
      })
      setForm(initial)
      setProvenance(prov.fields || {})
      setPending(pend.pending || [])
    } catch (e) {
      setError(e.message)
    }
  }
  useEffect(() => {
    loadAll()
  }, [])

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSave(e) {
    e?.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {}
      for (const [k, v] of Object.entries(form)) {
        if (v === '' || v === null) continue
        if (k === 'founded_year' || k === 'headcount') {
          const n = parseInt(v, 10)
          if (!isNaN(n)) payload[k] = n
        } else {
          payload[k] = v
        }
      }
      if (Object.keys(payload).length === 0) {
        setError('Keine Änderungen zum Speichern')
        return
      }
      await updateCompanyProfile(payload)
      setSavedAt(new Date())
      await loadAll()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleReview(id, action) {
    try {
      await reviewCompanyProfileSuggestion(id, action)
      await loadAll()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleImportMd() {
    if (!mdContent.trim() || mdContent.trim().length < 10) {
      setError('MD-Inhalt zu kurz (min. 10 Zeichen)')
      return
    }
    setImporting(true)
    setError(null)
    setImportResult(null)
    try {
      const r = await importCompanyProfileMd(mdContent, importAutoApply)
      setImportResult(r)
      await loadAll()
    } catch (e) {
      setError(e.message)
    } finally {
      setImporting(false)
    }
  }

  async function handleFileUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith('.md')) {
      setError('Nur .md-Dateien werden unterstützt')
      return
    }
    const text = await file.text()
    setMdContent(text)
  }

  if (!profile)
    return (
      <div style={{ padding: 24 }}>
        <Loader2 className="animate-spin" /> Lade Profil…
      </div>
    )

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        <Building2 size={22} style={{ display: 'inline', marginRight: 8 }} />
        Unternehmens-Profil
      </h1>
      <p style={{ color: '#6b7280', marginBottom: 16, fontSize: 14 }}>
        Optional — wird automatisch aus Wizard, MD-Upload und Sprachnotizen ergänzt. Alle Quellen
        sind nachvollziehbar (Audit-Trail).
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, borderBottom: '1px solid #e5e7eb' }}>
        <button
          onClick={() => setTab('form')}
          style={{
            padding: '8px 16px',
            background: 'none',
            border: 'none',
            borderBottom: tab === 'form' ? '2px solid #2563eb' : 'none',
            cursor: 'pointer',
          }}
        >
          Formular
        </button>
        <button
          onClick={() => setTab('provenance')}
          style={{
            padding: '8px 16px',
            background: 'none',
            border: 'none',
            borderBottom: tab === 'provenance' ? '2px solid #2563eb' : 'none',
            cursor: 'pointer',
          }}
        >
          <History size={14} style={{ display: 'inline', marginRight: 4 }} />
          Audit-Trail ({Object.keys(provenance).length} Felder)
        </button>
        <button
          onClick={() => setTab('pending')}
          style={{
            padding: '8px 16px',
            background: 'none',
            border: 'none',
            borderBottom: tab === 'pending' ? '2px solid #2563eb' : 'none',
            cursor: 'pointer',
          }}
        >
          <AlertCircle size={14} style={{ display: 'inline', marginRight: 4 }} />
          Vorschläge ({pending.length})
        </button>
        <button
          onClick={() => setTab('import')}
          style={{
            padding: '8px 16px',
            background: 'none',
            border: 'none',
            borderBottom: tab === 'import' ? '2px solid #2563eb' : 'none',
            cursor: 'pointer',
          }}
        >
          <Upload size={14} style={{ display: 'inline', marginRight: 4 }} />
          MD-Import
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: 12,
            background: '#fee2e2',
            color: '#991b1b',
            borderRadius: 6,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}
      {savedAt && (
        <div
          style={{
            padding: 12,
            background: '#dcfce7',
            color: '#166534',
            borderRadius: 6,
            marginBottom: 12,
          }}
        >
          Gespeichert um {savedAt.toLocaleTimeString('de-DE')}
        </div>
      )}

      {tab === 'form' && (
        <form onSubmit={handleSave}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {Object.entries(FIELD_LABELS).map(([field, label]) => (
              <div key={field}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    marginBottom: 4,
                    color: '#374151',
                  }}
                >
                  {label}
                </label>
                {field === 'usp' || field === 'target_audience' || field === 'values_short' ? (
                  <textarea
                    data-field={field}
                    value={form[field] || ''}
                    onChange={(e) => update(field, e.target.value)}
                    rows={3}
                    style={{
                      width: '100%',
                      padding: 8,
                      border: '1px solid #d1d5db',
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  />
                ) : (
                  <input
                    data-field={field}
                    type={field === 'founded_year' || field === 'headcount' ? 'number' : 'text'}
                    value={form[field] || ''}
                    onChange={(e) => update(field, e.target.value)}
                    style={{
                      width: '100%',
                      padding: 8,
                      border: '1px solid #d1d5db',
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  />
                )}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 24 }}>
            <Button type="submit" disabled={saving} data-testid="btn-save-company-profile">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {saving ? ' Speichere…' : ' Speichern'}
            </Button>
          </div>
        </form>
      )}

      {tab === 'provenance' && (
        <div>
          {Object.keys(provenance).length === 0 ? (
            <p style={{ color: '#6b7280' }}>Noch kein Audit-Trail.</p>
          ) : (
            Object.entries(provenance).map(([field, entries]) => (
              <div
                key={field}
                style={{
                  marginBottom: 16,
                  padding: 12,
                  border: '1px solid #e5e7eb',
                  borderRadius: 6,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 8 }}>
                  {FIELD_LABELS[field] || field}
                </div>
                {entries.map((e, i) => {
                  const badge = SOURCE_BADGES[e.source] || { label: e.source, color: '#6b7280' }
                  return (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: 13,
                        padding: 6,
                        opacity: e.applied ? 1 : 0.5,
                      }}
                    >
                      <span
                        style={{
                          background: badge.color,
                          color: 'white',
                          padding: '2px 8px',
                          borderRadius: 12,
                          fontSize: 11,
                        }}
                      >
                        {badge.label}
                      </span>
                      <span style={{ color: '#374151', flex: 1 }}>{e.value}</span>
                      <span style={{ color: '#9ca3af', fontSize: 11 }}>
                        conf {e.confidence.toFixed(2)}
                      </span>
                      <span style={{ color: '#9ca3af', fontSize: 11 }}>
                        {new Date(e.created_at).toLocaleDateString('de-DE')}
                      </span>
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'import' && (
        <div>
          <p style={{ marginBottom: 12, color: '#374151', fontSize: 14 }}>
            Lade eine MD-Datei mit Onboarding-Notizen (Eric/Chris) hoch, oder paste den Inhalt
            direkt. Erwartete Sektionen: <code>## Firma</code>, <code>## Ansprechpartner</code>,{' '}
            <code>## USP</code>, <code>## Zielgruppe</code>, <code>## Werte</code>.
          </p>
          <input
            type="file"
            accept=".md,.markdown,text/markdown"
            onChange={handleFileUpload}
            data-testid="md-file-input"
            style={{ marginBottom: 12 }}
          />
          <textarea
            data-testid="md-content"
            value={mdContent}
            onChange={(e) => setMdContent(e.target.value)}
            rows={14}
            placeholder="# Onboarding — Firma&#10;&#10;## Firma&#10;- Name: ZKG GmbH&#10;- Branche: Coaching&#10;..."
            style={{
              width: '100%',
              padding: 8,
              border: '1px solid #d1d5db',
              borderRadius: 4,
              fontSize: 13,
              fontFamily: 'monospace',
            }}
          />
          <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
            <label style={{ fontSize: 13 }}>
              <input
                type="checkbox"
                checked={importAutoApply}
                onChange={(e) => setImportAutoApply(e.target.checked)}
                data-testid="md-auto-apply"
              />{' '}
              Automatisch übernehmen (sonst nur als Vorschlag in Review-Queue)
            </label>
            <Button data-testid="btn-import-md" onClick={handleImportMd} disabled={importing}>
              {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {importing ? ' Importiere…' : ' Importieren'}
            </Button>
          </div>
          {importResult && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: '#dbeafe',
                borderRadius: 6,
                fontSize: 14,
              }}
            >
              <strong>{importResult.parsed} Felder erkannt</strong> — {importResult.applied}{' '}
              übernommen, {importResult.pending} als Vorschlag.
              {importResult.fields_applied?.length > 0 && (
                <div style={{ marginTop: 4, fontSize: 12, color: '#1e40af' }}>
                  Felder: {importResult.fields_applied.join(', ')}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'pending' && (
        <div>
          {pending.length === 0 ? (
            <p style={{ color: '#6b7280' }}>Keine offenen Vorschläge.</p>
          ) : (
            pending.map((p) => {
              const badge = SOURCE_BADGES[p.source] || { label: p.source, color: '#6b7280' }
              return (
                <div
                  key={p.id}
                  style={{
                    marginBottom: 12,
                    padding: 12,
                    border: '1px solid #fcd34d',
                    borderRadius: 6,
                    background: '#fffbeb',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        background: badge.color,
                        color: 'white',
                        padding: '2px 8px',
                        borderRadius: 12,
                        fontSize: 11,
                      }}
                    >
                      {badge.label}
                    </span>
                    <strong style={{ flex: 1 }}>
                      {FIELD_LABELS[p.field_name] || p.field_name}
                    </strong>
                    <span style={{ color: '#92400e', fontSize: 12 }}>
                      conf {p.confidence.toFixed(2)}
                    </span>
                  </div>
                  <div style={{ marginTop: 6, color: '#374151' }}>{p.value}</div>
                  <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                    <Button
                      data-testid={`btn-accept-${p.id}`}
                      onClick={() => handleReview(p.id, 'accept')}
                    >
                      <Check size={14} /> Übernehmen
                    </Button>
                    <Button
                      data-testid={`btn-reject-${p.id}`}
                      onClick={() => handleReview(p.id, 'reject')}
                      variant="ghost"
                    >
                      <X size={14} /> Ablehnen
                    </Button>
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
