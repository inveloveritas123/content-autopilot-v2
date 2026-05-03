import { useState, useEffect, useCallback } from 'react'
import {
  Brain,
  Pencil,
  ChevronRight,
  ChevronLeft,
  Loader2,
  AlertCircle,
  Quote,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
} from 'lucide-react'
import { Dialog } from './ui/Dialog'
import { getBrandVoiceStatus, patchBrandVoiceField } from '../api'

const TENANT_ID = 'me'

// ─── Allow-List editierbarer Felder (clientseitige Spiegelung vom Backend) ─────

const EDITABLE_PATHS = {
  voice_profile: [
    'grundton',
    'satzarchitektur',
    'signalwoerter',
    'verbotene_woerter',
    'intensitaetsmarker',
    'erzaehlmuster',
    'persoenlichkeits_stance',
    'vermeidungsprofil',
  ],
  customer_context: ['person', 'angebot', 'positionierung', 'kernbotschaft', 'expertise'],
  audience_avatar: ['identitaet', 'content_trigger', 'sprache_der_zielgruppe'],
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

function formatDateShort(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const yy = String(d.getFullYear()).slice(2)
    return `${dd}.${mm}.${yy}`
  } catch {
    return iso
  }
}

const SOURCE_LABELS = {
  wizard: 'Wizard',
  manual_edit: 'Manuell',
  drift_update: 'Drift',
  md_upload: 'Upload',
}

function sourceBadgeClass(source) {
  switch (source) {
    case 'wizard':
      return 'bg-blue-50 text-blue-700 border-blue-200'
    case 'manual_edit':
      return 'bg-violet-50 text-violet-700 border-violet-200'
    case 'drift_update':
      return 'bg-amber-50 text-amber-700 border-amber-200'
    case 'md_upload':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200'
    default:
      return 'bg-gray-50 text-gray-600 border-gray-200'
  }
}

function isArrayField(value) {
  return Array.isArray(value)
}

function fieldChanged(currentPayload, comparePayload, fieldPath) {
  if (!comparePayload) return false
  return (
    JSON.stringify(currentPayload?.[fieldPath]) !==
    JSON.stringify(comparePayload?.[fieldPath])
  )
}

// ─── Render-Komponenten ───────────────────────────────────────────────────────

function TagCloud({ tags, isVerboten }) {
  if (!tags || tags.length === 0) return <span className="text-xs text-ink-muted italic">—</span>
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {tags.map((tag, i) => (
        <span
          key={i}
          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${
            isVerboten
              ? 'bg-red-50 text-red-700 border-red-200'
              : 'bg-primary-50 text-primary-700 border-primary-100'
          }`}
        >
          {tag}
        </span>
      ))}
    </div>
  )
}

function DescriptionCard({ value }) {
  if (!value) return <span className="text-xs text-ink-muted italic">—</span>
  return (
    <p className="text-sm text-ink leading-relaxed mt-1 whitespace-pre-wrap">{value}</p>
  )
}

function QuoteBlock({ quotes }) {
  if (!quotes || quotes.length === 0)
    return <span className="text-xs text-ink-muted italic">—</span>
  return (
    <div className="mt-2 space-y-2">
      {quotes.map((q, i) => (
        <div key={i} className="flex items-start gap-2 bg-gray-50 rounded-lg p-3 border border-gray-100">
          <Quote className="w-4 h-4 text-primary-400 shrink-0 mt-0.5" />
          <p className="text-sm text-ink leading-relaxed">{q}</p>
        </div>
      ))}
    </div>
  )
}

function FieldValue({ fieldPath, value }) {
  if (fieldPath === 'referenz_saetze' && Array.isArray(value)) {
    return <QuoteBlock quotes={value} />
  }
  if (fieldPath === 'verbotene_woerter' && Array.isArray(value)) {
    return <TagCloud tags={value} isVerboten />
  }
  if (Array.isArray(value)) {
    return <TagCloud tags={value} isVerboten={false} />
  }
  if (typeof value === 'object' && value !== null) {
    return (
      <pre className="text-xs text-ink leading-relaxed mt-1 bg-gray-50 rounded-lg p-3 border border-gray-100 overflow-x-auto whitespace-pre-wrap">
        {JSON.stringify(value, null, 2)}
      </pre>
    )
  }
  return <DescriptionCard value={value} />
}

// ─── EditFieldModal ───────────────────────────────────────────────────────────

function EditFieldModal({ open, onClose, profileType, fieldPath, currentValue, onSaved }) {
  const isArray = Array.isArray(currentValue)
  const initialText = isArray
    ? JSON.stringify(currentValue, null, 2)
    : (currentValue ?? '')

  const [text, setText] = useState(initialText)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Reset wenn das Modal neu geöffnet wird
  useEffect(() => {
    if (open) {
      setText(isArray ? JSON.stringify(currentValue, null, 2) : (currentValue ?? ''))
      setError(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function handleSave() {
    setError(null)
    setSaving(true)
    try {
      let parsedValue
      if (isArray) {
        try {
          parsedValue = JSON.parse(text)
          if (!Array.isArray(parsedValue)) throw new Error('Kein Array')
        } catch {
          // Fallback: Zeilen aufteilen
          parsedValue = text
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean)
        }
      } else {
        parsedValue = text
      }
      await patchBrandVoiceField(TENANT_ID, profileType, fieldPath, parsedValue)
      onSaved(fieldPath, parsedValue)
      onClose()
    } catch (e) {
      setError(e.message || 'Speichern fehlgeschlagen.')
    } finally {
      setSaving(false)
    }
  }

  const readonlyText = isArray
    ? JSON.stringify(currentValue, null, 2)
    : (currentValue ?? '')

  return (
    <Dialog open={open} onClose={onClose} title={`Feld bearbeiten: ${fieldPath}`}>
      <div className="space-y-4">
        <div>
          <p className="text-xs font-medium text-ink-muted mb-1">Aktueller Wert</p>
          <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-ink-muted leading-relaxed overflow-x-auto max-h-32 overflow-y-auto whitespace-pre-wrap select-none">
            {readonlyText || '—'}
          </pre>
        </div>
        <div>
          <p className="text-xs font-medium text-ink mb-1">Neuer Wert</p>
          <textarea
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-y min-h-[100px]"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {isArray && (
            <p className="text-[11px] text-ink-muted mt-1">
              JSON-Array oder ein Eintrag pro Zeile (Fallback).
            </p>
          )}
        </div>
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Speichern
          </button>
        </div>
      </div>
    </Dialog>
  )
}

// ─── FieldBlock ───────────────────────────────────────────────────────────────

function FieldBlock({ profileType, fieldPath, value, editable, highlighted, onEdit }) {
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        highlighted
          ? 'bg-amber-50 border-amber-200'
          : 'bg-white border-surface-border'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide">
          {fieldPath}
        </p>
        {editable && (
          <button
            onClick={() => onEdit(fieldPath, value)}
            className="p-1 text-ink-muted hover:text-primary-600 hover:bg-primary-50 rounded-md transition-colors shrink-0"
            title="Feld bearbeiten"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <FieldValue fieldPath={fieldPath} value={value} />
    </div>
  )
}

// ─── ProfilePanel ─────────────────────────────────────────────────────────────

function ProfilePanel({ profileType, payload, comparePayload, editablePaths, onFieldSaved }) {
  const [editModal, setEditModal] = useState(null) // { fieldPath, value }

  if (!payload) {
    return (
      <div className="flex items-center justify-center py-16 text-ink-muted text-sm">
        Kein Profil vorhanden.
      </div>
    )
  }

  function handleEdit(fieldPath, value) {
    setEditModal({ fieldPath, value })
  }

  function handleSaved(fieldPath, newValue) {
    onFieldSaved(profileType, fieldPath, newValue)
  }

  return (
    <div className="space-y-3">
      {Object.entries(payload).map(([key, value]) => {
        const editable = editablePaths.includes(key)
        const highlighted = fieldChanged(payload, comparePayload, key)
        return (
          <FieldBlock
            key={key}
            profileType={profileType}
            fieldPath={key}
            value={value}
            editable={editable}
            highlighted={highlighted}
            onEdit={handleEdit}
          />
        )
      })}

      {editModal && (
        <EditFieldModal
          open
          onClose={() => setEditModal(null)}
          profileType={profileType}
          fieldPath={editModal.fieldPath}
          currentValue={editModal.value}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

// ─── VersionsSidebar ──────────────────────────────────────────────────────────

function VersionsSidebar({ history, compareVersion, onCompare, onReset, collapsed, onToggle }) {
  return (
    <div
      className={`shrink-0 transition-all duration-200 ${
        collapsed ? 'w-10' : 'w-48'
      }`}
    >
      <div className="sticky top-0 bg-white border border-surface-border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-surface-border">
          {!collapsed && (
            <span className="text-xs font-semibold text-ink">Versionen</span>
          )}
          <button
            onClick={onToggle}
            className="p-1 text-ink-muted hover:text-primary-600 rounded-md ml-auto"
            title={collapsed ? 'Sidebar aufklappen' : 'Sidebar einklappen'}
          >
            {collapsed ? (
              <PanelRightOpen className="w-4 h-4" />
            ) : (
              <PanelRightClose className="w-4 h-4" />
            )}
          </button>
        </div>

        {!collapsed && (
          <div className="max-h-[calc(100vh-200px)] overflow-y-auto">
            {compareVersion !== null && (
              <div className="px-3 py-2 border-b border-surface-border">
                <button
                  onClick={onReset}
                  className="flex items-center gap-1.5 text-xs text-primary-700 font-medium hover:underline"
                >
                  <RotateCcw className="w-3 h-3" />
                  Aktuelle Version
                </button>
              </div>
            )}
            {(!history || history.length === 0) ? (
              <p className="text-xs text-ink-muted px-3 py-3 italic">Keine Versionen</p>
            ) : (
              history.map((entry) => (
                <button
                  key={entry.version}
                  onClick={() => onCompare(entry.version)}
                  className={`w-full text-left px-3 py-2.5 border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors ${
                    compareVersion === entry.version ? 'bg-amber-50' : ''
                  }`}
                >
                  <p className="text-xs font-medium text-ink">
                    v{entry.version}
                  </p>
                  <p className="text-[11px] text-ink-muted">
                    {formatDateShort(entry.created_at)}
                  </p>
                  <span
                    className={`inline-block mt-1 px-1.5 py-0.5 rounded border text-[10px] font-medium ${sourceBadgeClass(
                      entry.source
                    )}`}
                  >
                    {SOURCE_LABELS[entry.source] || entry.source}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Tab-Konfiguration ────────────────────────────────────────────────────────

const TABS = [
  {
    key: 'voice_profile',
    label: 'Stimme (P03)',
    profileKey: 'voice_profile',
  },
  {
    key: 'customer_context',
    label: 'Kontext (P01)',
    profileKey: 'customer_context',
  },
  {
    key: 'audience_avatar',
    label: 'Avatar (P04)',
    profileKey: 'audience_avatar',
  },
]

// ─── Main: VoiceInsights ──────────────────────────────────────────────────────

export default function VoiceInsights() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('voice_profile')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [compareVersion, setCompareVersion] = useState(null)

  // Daten-State
  const [activeProfiles, setActiveProfiles] = useState({})
  const [historyByPillar, setHistoryByPillar] = useState({})

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getBrandVoiceStatus(TENANT_ID)
      setActiveProfiles(data?.active_profiles || {})
      // history is an object {voice_profile: [], customer_context: [], audience_avatar: []}
      const h = data?.history
      setHistoryByPillar(h && typeof h === 'object' && !Array.isArray(h) ? h : {})
    } catch (e) {
      setError(e.message || 'Laden fehlgeschlagen.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Lokalen State eines Feldes aktualisieren nach erfolgreichem Patch
  function handleFieldSaved(profileType, fieldPath, newValue) {
    setActiveProfiles((prev) => {
      const profile = prev[profileType]
      if (!profile) return prev
      return {
        ...prev,
        [profileType]: {
          ...profile,
          payload: {
            ...profile.payload,
            [fieldPath]: newValue,
          },
        },
      }
    })
  }

  const history = historyByPillar[activeTab] || []

  // Vergleichs-Payload aus History ermitteln
  const compareEntry = compareVersion !== null
    ? history.find((h) => h.version === compareVersion)
    : null
  const comparePayload = compareEntry?.payload ?? null

  const currentTab = TABS.find((t) => t.key === activeTab)
  const currentProfile = activeProfiles[currentTab?.profileKey]
  const currentPayload = currentProfile?.payload ?? null

  // Wenn compareVersion gesetzt: historischen Payload verwenden
  const displayPayload = compareVersion !== null
    ? (compareEntry?.payload ?? currentPayload)
    : currentPayload

  // Diff: Vergleich zwischen aktuellem und Vergleichs-Payload
  const diffPayload = compareVersion !== null ? currentPayload : null

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <Brain className="w-5 h-5 text-primary-600" />
            So liest die KI dich
          </h1>
          <p className="text-sm text-ink-light mt-0.5">
            Dein Brand Voice, Kundenkontext und Zielgruppen-Avatar auf einen Blick.
          </p>
        </div>
      </div>

      {/* Source-Hinweis bei md_upload */}
      {activeProfiles.voice_profile?.source === 'md_upload' && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 text-sm text-blue-700">
          Diese Stimme entwickelt sich automatisch durch deine Posts und Antworten weiter.
          Letzte Aktualisierung: {formatDate(activeProfiles.voice_profile?.updated_at)}
        </div>
      )}

      {/* Vergleichs-Modus Banner */}
      {compareVersion !== null && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4 flex items-center justify-between text-sm text-amber-700">
          <span>
            Vergleichsansicht: Version {compareVersion} — Gelb markierte Felder weichen von der aktuellen Version ab.
          </span>
          <button
            onClick={() => setCompareVersion(null)}
            className="flex items-center gap-1.5 text-xs font-medium text-amber-700 underline hover:no-underline ml-4 shrink-0"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Zurück zur aktuellen Version
          </button>
        </div>
      )}

      {/* Fehler */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Ladezustand */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-ink-muted text-sm gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Lade Brand Voice...
        </div>
      )}

      {!loading && !error && (
        <div className="flex gap-4 items-start">
          {/* Haupt-Content */}
          <div className="flex-1 min-w-0">
            {/* Tabs */}
            <div className="flex gap-1 mb-4 border-b border-surface-border">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => { setActiveTab(tab.key); setCompareVersion(null) }}
                  className={`px-4 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                    activeTab === tab.key
                      ? 'text-primary-700 border-primary-700 bg-primary-50'
                      : 'text-ink-muted border-transparent hover:text-ink hover:bg-gray-50'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Profil-Inhalt */}
            {currentTab && (
              <ProfilePanel
                profileType={currentTab.profileKey}
                payload={displayPayload}
                comparePayload={diffPayload}
                editablePaths={compareVersion !== null ? [] : (EDITABLE_PATHS[currentTab.profileKey] || [])}
                onFieldSaved={handleFieldSaved}
              />
            )}
          </div>

          {/* Versions-Sidebar */}
          <VersionsSidebar
            history={history}
            compareVersion={compareVersion}
            onCompare={(version) => setCompareVersion(version)}
            onReset={() => setCompareVersion(null)}
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((v) => !v)}
          />
        </div>
      )}
    </div>
  )
}
