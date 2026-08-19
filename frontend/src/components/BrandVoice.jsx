// AUDITED-2026-08-14 (D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Mic2,
  CheckCircle2,
  AlertCircle,
  XCircle,
  RefreshCw,
  Upload,
  FolderOpen,
  ChevronRight,
  ChevronLeft,
  Loader2,
  Info,
  Sparkles,
  ShieldAlert,
  RotateCcw,
} from 'lucide-react'
import { Dialog } from './ui/Dialog'
import { Badge } from './ui/Badge'
import {
  getBrandVoiceStatus,
  uploadBrandVoiceFile,
  importBrandVoiceFromNC,
  getBrandVoicePipelineStatus,
  getReviewQueue,
} from '../api'

const TENANT_ID = 'me'
const getActiveProjectId = () => localStorage.getItem('activeProjectId') || null

// ─── Helpers ────────────────────────────────────────────────────────────────

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

function detectProfileType(content) {
  try {
    const obj = JSON.parse(content)
    if (obj && typeof obj === 'object') {
      if ('grundton' in obj) return 'voice_profile'
      if ('person' in obj) return 'customer_context'
      if ('identitaet' in obj) return 'audience_avatar'
    }
  } catch {
    // not JSON or parse failed — return null to trigger modal
  }
  return null
}

// ─── ColumnSelectModal ────────────────────────────────────────────────────

const PROFILE_OPTIONS = [
  {
    key: 'voice_profile',
    label: 'Brand Voice Profil',
    desc: 'Grundton, Stil, Sprachregeln für alle Inhalte',
    icon: Mic2,
  },
  {
    key: 'customer_context',
    label: 'Kundenkontext',
    desc: 'Persona, Painpoints, Kaufmotive des Kunden',
    icon: AlertCircle,
  },
  {
    key: 'audience_avatar',
    label: 'Zielgruppen-Avatar',
    desc: 'Demografische und psychografische Identität',
    icon: Sparkles,
  },
]

function ColumnSelectModal({ open, onClose, onConfirm }) {
  const [selected, setSelected] = useState(null)

  function handleConfirm() {
    if (!selected) return
    onConfirm(selected)
    setSelected(null)
  }

  return (
    <Dialog open={open} onClose={onClose} title="Profil-Typ auswählen">
      <p className="text-sm text-ink-muted mb-4">Welchem Brand-Voice-Bereich gehört diese Datei?</p>
      <div className="space-y-3">
        {PROFILE_OPTIONS.map((opt) => {
          const Icon = opt.icon
          const isSelected = selected === opt.key
          return (
            <button
              key={opt.key}
              onClick={() => setSelected(opt.key)}
              className={`w-full text-left p-4 rounded-xl border-2 transition-all flex items-start gap-3 ${
                isSelected
                  ? 'border-primary-600 bg-primary-50'
                  : 'border-surface-border hover:border-surface-border hover:bg-surface-bg'
              }`}
            >
              <Icon
                className={`w-5 h-5 mt-0.5 shrink-0 ${isSelected ? 'text-primary-600' : 'text-ink-light'}`}
              />
              <div>
                <span className="text-sm font-semibold text-ink block">{opt.label}</span>
                <span className="text-xs text-ink-muted">{opt.desc}</span>
                <span className="text-xs text-primary-600 block mt-1 cursor-default">
                  Vorlage anzeigen
                </span>
              </div>
            </button>
          )
        })}
      </div>
      <div className="flex justify-end gap-2 mt-6">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
        >
          Abbrechen
        </button>
        <button
          onClick={handleConfirm}
          disabled={!selected}
          className="px-5 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Upload starten
        </button>
      </div>
    </Dialog>
  )
}

// ─── NCPickerModal ────────────────────────────────────────────────────────

function Breadcrumb({ path, onNavigate }) {
  const parts = path.split('/').filter(Boolean)
  return (
    <div className="flex items-center gap-1 text-xs text-ink-muted flex-wrap">
      <button onClick={() => onNavigate('/')} className="hover:text-primary-700 font-medium">
        /
      </button>
      {parts.map((part, i) => {
        const partPath = '/' + parts.slice(0, i + 1).join('/')
        return (
          <span key={partPath} className="flex items-center gap-1">
            <ChevronRight className="w-3 h-3" />
            <button
              onClick={() => onNavigate(partPath)}
              className="hover:text-primary-700 font-medium"
            >
              {part}
            </button>
          </span>
        )
      })}
    </div>
  )
}

function NCPickerModal({ open, onClose, onImport, tenantSlug }) {
  const defaultPath = `/content-autopilot/v2/Kunde/${tenantSlug || 'default'}/voice/`
  const [currentPath, setCurrentPath] = useState(defaultPath)
  const [pathInput, setPathInput] = useState(defaultPath)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    if (open) {
      setCurrentPath(defaultPath)
      setPathInput(defaultPath)
      setSelectedFile(null)
    }
  }, [open, defaultPath])

  useEffect(() => {
    if (open) {
      setPathInput(currentPath)
      loadPath(currentPath)
    }
  }, [open, currentPath])

  async function loadPath(path) {
    setLoading(true)
    setError(null)
    setItems([])
    try {
      // use the nc/list endpoint
      const API_BASE = '/api'
      const apiKey = localStorage.getItem('apiKey') || ''
      const resp = await fetch(`${API_BASE}/nc/list?path=${encodeURIComponent(path)}`, {
        headers: { 'X-API-Key': apiKey },
      })
      const TEMPLATE_PATH = '/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/'
      if (!resp.ok) {
        if (resp.status === 404) {
          if (path !== TEMPLATE_PATH) {
            setCurrentPath(TEMPLATE_PATH)
          } else {
            setError('Pfad nicht gefunden.')
            setItems([])
          }
          setLoading(false)
          return
        } else {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }))
          throw new Error(err.detail || 'Fehler beim Laden')
        }
      } else {
        const data = await resp.json()
        setItems(Array.isArray(data) ? data : data.items || [])
      }
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const [showColumnModalForNC, setShowColumnModalForNC] = useState(false)

  async function handleImport() {
    if (!selectedFile) return
    // Profiltyp aus NC-Dateiname ableiten — zeige ColumnSelectModal wenn unklar
    const ext = selectedFile.name?.split('.').pop()?.toLowerCase()
    if (ext === 'md') {
      setShowColumnModalForNC(true)
      return
    }
    // JSON: Typ unbekannt (kein Dateiinhalt geladen) → Modal zur Auswahl
    setShowColumnModalForNC(true)
  }

  async function handleNCImportWithType(profileType) {
    setShowColumnModalForNC(false)
    if (!selectedFile) return
    setImporting(true)
    try {
      await onImport(TENANT_ID, selectedFile.path, profileType)
      onClose()
    } catch (e) {
      setError('Import fehlgeschlagen: ' + e.message)
    }
    setImporting(false)
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Datei aus Nextcloud importieren"
      className="max-w-xl"
    >
      {/* Manueller Pfad-Input */}
      <div className="mb-2 flex gap-1.5">
        <input
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter')
              setCurrentPath(pathInput.endsWith('/') ? pathInput : pathInput + '/')
          }}
          placeholder="Pfad eingeben..."
          className="flex-1 text-xs border border-surface-border rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary-500 font-mono"
        />
        <button
          onClick={() => setCurrentPath(pathInput.endsWith('/') ? pathInput : pathInput + '/')}
          className="px-2.5 py-1.5 text-xs bg-surface-bg border border-surface-border rounded-lg hover:bg-surface-bg text-ink-muted"
        >
          ↵
        </button>
      </div>

      <div className="mb-3">
        <Breadcrumb path={currentPath} onNavigate={setCurrentPath} />
      </div>

      <div className="mb-3">
        <p className="text-xs text-ink-muted mb-1.5">Schnell-Navigation:</p>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {[
            {
              label: '📋 Vorlagen-Ordner',
              path: '/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/',
            },
            {
              label: '📁 Meine Voice-Dateien',
              path: `/content-autopilot/v2/Kunde/${tenantSlug || 'default'}/voice/`,
            },
          ].map((q) => (
            <button
              key={q.path}
              onClick={() => setCurrentPath(q.path)}
              className="text-xs px-2.5 py-1 bg-primary-50 text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-100"
            >
              {q.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-ink-muted mb-1.5">Vorlage direkt auswählen:</p>
        <div className="flex flex-wrap gap-1.5">
          {[
            { label: '🏢 P01 Kundenkontext', name: 'P01-kundenkontext-extraktion.md' },
            { label: '🎙️ P03 Voice-Profil', name: 'P03-voice-profile.md' },
            { label: '👤 P04 Audience-Avatar', name: 'P04-audience-avatar.md' },
            {
              label: '📦 1-main-linkedin-ki',
              name: '1-main-notion-file-linkedin-ki-assets-prompts.md',
            },
          ].map((t) => {
            const filePath = `/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/${t.name}`
            const isSelected = selectedFile?.path === filePath
            return (
              <button
                key={t.name}
                onClick={() => setSelectedFile({ name: t.name, path: filePath })}
                className={`text-xs px-2.5 py-1 border rounded-lg transition-colors ${
                  isSelected
                    ? 'bg-primary-700 text-white border-primary-700'
                    : 'bg-surface-bg text-ink border-surface-border hover:bg-primary-50 hover:text-primary-700 hover:border-primary-200'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
      </div>

      {error && (
        <div className="mb-3 p-3 bg-accent-50 border border-accent-200 rounded-lg text-xs text-accent-700">
          {error}
          <div className="mt-1 text-ink-muted">
            Vorlagen: /zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/
          </div>
        </div>
      )}

      <div className="border border-surface-border rounded-xl overflow-hidden min-h-[200px] max-h-64 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-ink-muted text-sm">
            <Loader2 className="w-4 h-4 animate-spin mr-2" /> Lade...
          </div>
        ) : items.length === 0 && !error ? (
          <div className="flex flex-col items-center justify-center py-10 text-ink-muted text-sm px-4 text-center">
            <FolderOpen className="w-8 h-8 mb-2 text-ink-muted" />
            <p className="text-xs font-medium text-ink-light mb-1">
              Verzeichnis leer oder nicht gefunden
            </p>
            <p className="text-[11px]">
              Klicke{' '}
              <button
                onClick={() =>
                  setCurrentPath(
                    '/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/'
                  )
                }
                className="text-primary-700 underline hover:no-underline"
              >
                Vorlagen-Ordner
              </button>{' '}
              für Beispiel-Dateien.
            </p>
          </div>
        ) : (
          items.map((item) => {
            const isDir = item.type === 'dir' || item.is_dir
            const name = item.name || item.basename || item.path?.split('/').filter(Boolean).pop()
            const itemPath = item.path || `${currentPath.replace(/\/$/, '')}/${name}`
            const isSelected = selectedFile?.path === itemPath
            return (
              <button
                key={itemPath}
                onClick={() => {
                  if (isDir) {
                    setCurrentPath(itemPath + '/')
                    setSelectedFile(null)
                  } else {
                    setSelectedFile({ name, path: itemPath })
                  }
                }}
                className={`w-full text-left px-4 py-2.5 flex items-center gap-2 text-sm border-b border-surface-border last:border-0 hover:bg-surface-bg transition-colors ${
                  isSelected ? 'bg-primary-50 text-primary-700' : 'text-ink'
                }`}
              >
                {isDir ? (
                  <FolderOpen className="w-4 h-4 text-accent-500 shrink-0" />
                ) : (
                  <div className="w-4 h-4 shrink-0 rounded border border-surface-border flex items-center justify-center">
                    {isSelected && <div className="w-2 h-2 rounded-sm bg-primary-600" />}
                  </div>
                )}
                <span className="truncate">{name}</span>
                {isDir && <ChevronRight className="w-3 h-3 text-ink-light ml-auto shrink-0" />}
              </button>
            )
          })
        )}
      </div>

      {selectedFile && (
        <p className="text-xs text-ink-muted mt-2">
          Ausgewählt: <span className="font-medium text-ink">{selectedFile.name}</span>
        </p>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
        >
          Abbrechen
        </button>
        <button
          onClick={handleImport}
          disabled={!selectedFile || importing}
          className="px-5 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {importing && <Loader2 className="w-4 h-4 animate-spin" />}
          Importieren
        </button>
      </div>

      {/* Säulen-Auswahl für NC-Importe (Profiltyp unbekannt) */}
      <ColumnSelectModal
        open={showColumnModalForNC}
        onClose={() => setShowColumnModalForNC(false)}
        onConfirm={handleNCImportWithType}
      />
    </Dialog>
  )
}

// ─── PipelineRunBanner ────────────────────────────────────────────────────

function PipelineRunBanner({ runId, onDone }) {
  const [status, setStatus] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!runId) return
    async function poll() {
      try {
        const data = await getBrandVoicePipelineStatus(runId)
        setStatus(data)
        if (data?.status === 'done' || data?.status === 'error') {
          clearInterval(intervalRef.current)
          if (data?.status === 'done') onDone?.()
        }
      } catch {
        // keep polling
      }
    }
    poll()
    intervalRef.current = setInterval(poll, 3000)
    return () => clearInterval(intervalRef.current)
  }, [runId, onDone])

  if (!runId || !status) return null

  const isDone = status.status === 'done'
  const isError = status.status === 'error'

  return (
    <div
      className={`mb-4 p-3 rounded-lg border flex items-center gap-3 text-sm ${
        isDone
          ? 'bg-status-fertig-bg border-status-fertig-border text-status-fertig-text'
          : isError
            ? 'bg-status-fehler-bg border-status-fehler-border text-status-fehler-text'
            : 'bg-primary-50 border-primary-200 text-primary-700'
      }`}
    >
      {isDone ? (
        <CheckCircle2 className="w-4 h-4 shrink-0" />
      ) : isError ? (
        <XCircle className="w-4 h-4 shrink-0" />
      ) : (
        <Loader2 className="w-4 h-4 animate-spin shrink-0" />
      )}
      <span>
        {isDone
          ? 'Setup-Pipeline abgeschlossen.'
          : isError
            ? 'Pipeline-Fehler: ' + (status.error || 'Unbekannt')
            : `Pipeline läuft — Stage: ${status.stage || '...'} (${status.status || '...'})`}
      </span>
    </div>
  )
}

// ─── StatusTile ───────────────────────────────────────────────────────────

function StatusTile({ data, onRefresh, onDriftReview, onSetup }) {
  if (!data) {
    return (
      <div className="bg-white rounded-xl border border-surface-border p-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-bg animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-surface-bg rounded animate-pulse w-1/2" />
            <div className="h-3 bg-surface-bg rounded animate-pulse w-1/3" />
          </div>
        </div>
      </div>
    )
  }

  const { active_profiles, drift_available } = data
  const { customer_context, voice_profile, audience_avatar } = active_profiles || {}
  const allPresent = customer_context && voice_profile && audience_avatar
  const nonePresent = !customer_context && !voice_profile && !audience_avatar
  const missing = []
  if (!customer_context) missing.push('Kundenkontext')
  if (!voice_profile) missing.push('Voice-Profil')
  if (!audience_avatar) missing.push('Zielgruppen-Avatar')

  const lastUpdated = [customer_context, voice_profile, audience_avatar]
    .filter(Boolean)
    .map((p) => p.updated_at)
    .sort()
    .pop()

  // QW5: Säulen-Progress
  const pillars = [
    { key: 'voice_profile', label: 'Voice-Profil', value: voice_profile },
    { key: 'customer_context', label: 'Kundenkontext', value: customer_context },
    { key: 'audience_avatar', label: 'Zielgruppen-Avatar', value: audience_avatar },
  ]
  const pillarsCount = pillars.filter((p) => p.value).length
  const pillarsPercent = Math.round((pillarsCount / 3) * 100)

  return (
    <div className="space-y-3 mb-6">
      {/* QW5: Säulen-Progress-Leiste */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-ink-muted uppercase tracking-wide">
            Brand Voice Fortschritt
          </span>
          <span className="text-xs font-bold text-ink">{pillarsCount}/3 Säulen abgeschlossen</span>
        </div>
        <div className="w-full h-2 bg-surface-bg rounded-full overflow-hidden">
          <div
            className="h-full bg-status-fertig-bg rounded-full transition-all duration-500"
            style={{ width: `${pillarsPercent}%` }}
          />
        </div>
        {/* Badge pro Säule */}
        <div className="flex flex-wrap gap-2 mt-3">
          {pillars.map((p) => (
            <span
              key={p.key}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
                p.value
                  ? 'bg-status-fertig-bg text-status-fertig-text border-status-fertig-border'
                  : 'bg-accent-50 text-accent-700 border-accent-200'
              }`}
            >
              {p.value ? <CheckCircle2 className="w-3 h-3" /> : <Loader2 className="w-3 h-3" />}
              {p.label}
              {p.value ? ' Erledigt' : ' Offen'}
            </span>
          ))}
        </div>
        {/* Banner wenn alle 3 fertig */}
        {allPresent && (
          <div className="mt-3 p-3 bg-status-fertig-bg border border-status-fertig-border rounded-lg flex items-center justify-between gap-3">
            <p className="text-xs font-semibold text-status-fertig-text">Brand Voice komplett.</p>
            <Link
              to="/brand-voice/wizard"
              className="text-xs font-medium text-status-fertig-text underline hover:no-underline whitespace-nowrap"
            >
              Wizard starten →
            </Link>
          </div>
        )}
      </div>

      {drift_available && (
        <div className="p-3 bg-primary-50 border border-primary-200 rounded-lg flex items-center gap-3 text-sm text-primary-700">
          <Info className="w-4 h-4 shrink-0" />
          <span className="flex-1">Voice-Update verfügbar — Drift erkannt.</span>
          <button
            onClick={onDriftReview}
            className="text-xs font-medium text-primary-700 underline hover:no-underline"
          >
            Voice-Updates prüfen →
          </button>
        </div>
      )}

      <div
        className={`bg-white rounded-xl border p-5 ${
          allPresent
            ? 'border-status-fertig-border'
            : nonePresent
              ? 'border-status-fehler-border'
              : 'border-accent-200'
        }`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                allPresent
                  ? 'bg-status-fertig-bg'
                  : nonePresent
                    ? 'bg-status-fehler-bg'
                    : 'bg-accent-50'
              }`}
            >
              {allPresent ? (
                <CheckCircle2 className="w-5 h-5 text-status-fertig-text" />
              ) : nonePresent ? (
                <XCircle className="w-5 h-5 text-status-fehler-text" />
              ) : (
                <AlertCircle className="w-5 h-5 text-accent-500" />
              )}
            </div>
            <div>
              {allPresent && (
                <>
                  <p className="text-sm font-semibold text-ink">Voice-Profil aktiv</p>
                  {lastUpdated && (
                    <p className="text-xs text-ink-muted mt-0.5">
                      Zuletzt aktualisiert: {formatDate(lastUpdated)}
                    </p>
                  )}
                  <div className="flex gap-2 mt-2 flex-wrap">
                    {[
                      { label: 'Voice-Profil', v: voice_profile },
                      { label: 'Kundenkontext', v: customer_context },
                      { label: 'Avatar', v: audience_avatar },
                    ].map(({ label, v }) => (
                      <Badge key={label} color="fertig" border size="sm">
                        <CheckCircle2 className="w-3 h-3" />
                        {label}
                        {v?.version && <span className="opacity-60">v{v.version}</span>}
                      </Badge>
                    ))}
                  </div>
                </>
              )}
              {!allPresent && !nonePresent && (
                <>
                  <p className="text-sm font-semibold text-ink">Profil unvollständig</p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Noch fehlend: {missing.join(', ')}
                  </p>
                </>
              )}
              {nonePresent && (
                <>
                  <p className="text-sm font-semibold text-status-fehler-text">
                    Kein Brand Voice eingerichtet
                  </p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Lade eine Datei hoch oder importiere aus Nextcloud, um zu starten.
                  </p>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {allPresent && (
              <button
                onClick={onSetup}
                className="px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100"
              >
                Neu generieren
              </button>
            )}
            {!allPresent && !nonePresent && (
              <button
                onClick={onSetup}
                className="px-3 py-1.5 text-xs font-medium text-accent-700 bg-accent-50 border border-accent-200 rounded-lg hover:bg-accent-100"
              >
                Profil vervollständigen
              </button>
            )}
            {nonePresent && (
              <button
                onClick={onSetup}
                className="px-4 py-2 text-xs font-semibold text-white bg-status-fehler-bg rounded-lg hover:bg-status-fehler-bg flex items-center gap-1.5"
              >
                Jetzt einrichten <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={onRefresh}
              className="p-2 text-ink-muted hover:text-primary-600 rounded-lg hover:bg-surface-bg"
              title="Aktualisieren"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── UploadZone ───────────────────────────────────────────────────────────

const MAX_FILE_SIZE = 2 * 1024 * 1024 // 2 MB

function UploadZone({ onUploadSuccess }) {
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)
  const [fileError, setFileError] = useState(null)
  const [showColumnModal, setShowColumnModal] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const inputRef = useRef(null)
  const activeReaderRef = useRef(null)

  // FileReader-Cleanup bei Unmount
  useEffect(() => {
    return () => {
      if (activeReaderRef.current) activeReaderRef.current.abort()
    }
  }, [])

  function validateAndSetFile(f) {
    setFileError(null)
    setUploadError(null)
    setUploadSuccess(false)
    setFileContent(null)
    setFile(null)

    const ext = f.name.toLowerCase().split('.').pop()
    const allowed = ['md', 'json']
    if (!allowed.includes(ext)) {
      setFileError('Nur .md und .json Dateien erlaubt.')
      return
    }
    // MIME-Type-Check (Defense-in-Depth) — Browser setzt bei Drag-and-Drop ggf. leer
    const allowedMimes = ['application/json', 'text/markdown', 'text/plain', '']
    if (f.type && !allowedMimes.includes(f.type)) {
      setFileError('Ungültiger Dateityp. Nur .md und .json erlaubt.')
      return
    }
    if (f.size > MAX_FILE_SIZE) {
      setFileError('Datei zu groß (max. 2 MB).')
      return
    }

    const reader = new FileReader()
    activeReaderRef.current = reader
    reader.onload = (e) => {
      activeReaderRef.current = null
      const content = e.target.result
      setFile(f)
      setFileContent(content)

      if (ext === 'json') {
        const detected = detectProfileType(content)
        if (detected) {
          startUpload(f, detected)
        } else {
          setShowColumnModal(true)
        }
      } else {
        // .md always shows modal
        setShowColumnModal(true)
      }
    }
    reader.readAsText(f)
  }

  async function startUpload(f, profileType) {
    setUploading(true)
    setUploadError(null)
    try {
      const formData = new FormData()
      formData.append('file', f)
      formData.append('tenant_id', TENANT_ID)
      formData.append('profile_type', profileType)
      await uploadBrandVoiceFile(formData)
      setUploadSuccess(true)
      onUploadSuccess?.()
    } catch (e) {
      setUploadError('Upload fehlgeschlagen: ' + e.message)
    }
    setUploading(false)
  }

  function handleColumnConfirm(profileType) {
    setShowColumnModal(false)
    if (file) startUpload(file, profileType)
  }

  function handleDragOver(e) {
    e.preventDefault()
    setDragging(true)
  }

  function handleDragLeave() {
    setDragging(false)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) validateAndSetFile(dropped)
  }

  function handleFileChange(e) {
    const selected = e.target.files[0]
    if (selected) validateAndSetFile(selected)
    e.target.value = ''
  }

  const previewLines = fileContent ? fileContent.split('\n').slice(0, 30).join('\n') : null

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5">
      <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
        <Upload className="w-4 h-4 text-primary-600" />
        Datei hochladen
      </h2>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragging
            ? 'border-primary-500 bg-primary-50'
            : 'border-surface-border hover:border-primary-400 hover:bg-surface-bg'
        }`}
      >
        <Upload className="w-8 h-8 text-ink-light mx-auto mb-2" />
        <p className="text-sm text-ink-muted">
          Datei hier ablegen oder{' '}
          <span className="text-primary-700 font-medium">klicken zum Auswählen</span>
        </p>
        <p className="text-xs text-ink-light mt-1">Unterstützt: .md, .json — max. 2 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.json"
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {fileError && (
        <div className="mt-3 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
          {fileError}
        </div>
      )}

      {uploadError && (
        <div className="mt-3 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
          {uploadError}
        </div>
      )}

      {uploadSuccess && (
        <div className="mt-3 p-3 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-xs text-status-fertig-text flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          Datei erfolgreich hochgeladen.
        </div>
      )}

      {uploading && (
        <div className="mt-3 flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 className="w-4 h-4 animate-spin" /> Wird hochgeladen...
        </div>
      )}

      {file && !uploading && !uploadSuccess && (
        <p className="mt-2 text-xs text-ink-muted">
          Datei: <span className="font-medium text-ink">{file.name}</span>
        </p>
      )}

      {previewLines && (
        <div className="mt-4">
          <p className="text-xs font-medium text-ink-muted mb-1">Vorschau (erste 30 Zeilen):</p>
          <pre className="bg-surface-bg border border-surface-border rounded-lg p-3 text-[11px] text-ink leading-relaxed overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
            {previewLines}
          </pre>
        </div>
      )}

      <ColumnSelectModal
        open={showColumnModal}
        onClose={() => setShowColumnModal(false)}
        onConfirm={handleColumnConfirm}
      />
    </div>
  )
}

// ─── Main: BrandVoice ─────────────────────────────────────────────────────

export default function BrandVoice() {
  const navigate = useNavigate()
  const [statusData, setStatusData] = useState(undefined) // undefined = loading, null = error
  const [statusError, setStatusError] = useState(null)
  const [pipelineRunId, setPipelineRunId] = useState(null)
  const [showNCPicker, setShowNCPicker] = useState(false)
  const [reviewQueueCount, setReviewQueueCount] = useState(0)

  const loadStatus = useCallback(async () => {
    setStatusError(null)
    try {
      const data = await getBrandVoiceStatus(TENANT_ID, getActiveProjectId())
      setStatusData(data)
    } catch (e) {
      setStatusError(e.message)
      setStatusData(null)
    }
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  useEffect(() => {
    getReviewQueue('me', 'pending')
      .then((data) => {
        const list = data.items || data || []
        setReviewQueueCount(Array.isArray(list) ? list.length : 0)
      })
      .catch(() => {})
  }, [])

  async function handleNCImport(tenantId, path, sourceType) {
    const result = await importBrandVoiceFromNC(tenantId, path, sourceType)
    if (result?.run_id) {
      setPipelineRunId(result.run_id)
    }
    loadStatus()
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <Mic2 className="w-5 h-5 text-primary-600" />
            Brand Voice
          </h1>
          <p className="text-sm text-ink-light mt-0.5">
            Stimm-Profil, Kundenkontext und Zielgruppen-Avatar verwalten.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {statusData?.voice_profile && (
            <Link
              to="/brand-voice/wizard"
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-ink-muted bg-white border border-surface-border rounded-lg hover:bg-surface-bg"
            >
              <RotateCcw className="w-4 h-4" />
              Wizard erneut
            </Link>
          )}
          <button
            onClick={() => setShowNCPicker(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100"
          >
            <FolderOpen className="w-4 h-4" />
            Aus Nextcloud importieren
          </button>
        </div>
      </div>

      {/* Pipeline Banner */}
      {pipelineRunId && (
        <PipelineRunBanner
          runId={pipelineRunId}
          onDone={() => {
            loadStatus()
            setTimeout(() => setPipelineRunId(null), 4000)
          }}
        />
      )}

      {/* Status error */}
      {statusError && (
        <div className="mb-4 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-sm text-status-fehler-text flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          Fehler beim Laden des Status: {statusError}
        </div>
      )}

      {/* Review-Queue warning banner */}
      {reviewQueueCount > 0 && (
        <Link
          to="/brand-voice/review-queue"
          className="flex items-center gap-3 mb-4 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-sm text-status-fehler-text hover:bg-status-fehler-bg transition-colors"
        >
          <ShieldAlert className="w-4 h-4 shrink-0" />
          <span className="flex-1">
            <span className="font-semibold">
              {reviewQueueCount} {reviewQueueCount === 1 ? 'Post' : 'Posts'} in Review-Queue
            </span>{' '}
            — Sensible Themen warten auf Freigabe.
          </span>
          <span className="text-xs font-medium underline shrink-0">Jetzt prüfen →</span>
        </Link>
      )}

      {/* Status Tile — shows skeleton when statusData is undefined */}
      <StatusTile
        data={statusData}
        onRefresh={loadStatus}
        onDriftReview={() => navigate('/brand-voice/drift-review')}
        onSetup={() => navigate('/brand-voice/wizard')}
      />

      {/* Upload Zone */}
      <UploadZone onUploadSuccess={loadStatus} />

      {/* NC Picker Modal */}
      <NCPickerModal
        open={showNCPicker}
        onClose={() => setShowNCPicker(false)}
        onImport={handleNCImport}
        tenantSlug={statusData?.tenant_name || 'default'}
      />
    </div>
  )
}
