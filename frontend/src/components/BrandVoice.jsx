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
} from 'lucide-react'
import { Dialog } from './ui/Dialog'
import {
  getBrandVoiceStatus,
  uploadBrandVoiceFile,
  importBrandVoiceFromNC,
  getBrandVoicePipelineStatus,
  getReviewQueue,
} from '../api'

const TENANT_ID = 'me'

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
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
      <p className="text-sm text-ink-muted mb-4">
        Welchem Brand-Voice-Bereich gehört diese Datei?
      </p>
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
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${isSelected ? 'text-primary-600' : 'text-gray-400'}`} />
              <div>
                <span className="text-sm font-semibold text-ink block">{opt.label}</span>
                <span className="text-xs text-ink-muted">{opt.desc}</span>
                <span className="text-xs text-primary-600 block mt-1 cursor-default">Vorlage anzeigen</span>
              </div>
            </button>
          )
        })}
      </div>
      <div className="flex justify-end gap-2 mt-6">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50"
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
            <button onClick={() => onNavigate(partPath)} className="hover:text-primary-700 font-medium">
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
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    if (open) {
      setCurrentPath(defaultPath)
      setSelectedFile(null)
    }
  }, [open, defaultPath])

  useEffect(() => {
    if (open) {
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
      const resp = await fetch(
        `${API_BASE}/nc/list?path=${encodeURIComponent(path)}`,
        { headers: { 'X-API-Key': apiKey } }
      )
      if (!resp.ok) {
        if (resp.status === 404) {
          setError('Pfad nicht gefunden. Bitte navigieren Sie zu den Vorlagen.')
          setItems([])
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
    <Dialog open={open} onClose={onClose} title="Datei aus Nextcloud importieren" className="max-w-xl">
      <div className="mb-3">
        <Breadcrumb path={currentPath} onNavigate={setCurrentPath} />
      </div>

      {error && (
        <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          {error}
          <div className="mt-1 text-ink-muted">
            Vorlagen: /zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/
          </div>
        </div>
      )}

      <div className="border border-gray-200 rounded-xl overflow-hidden min-h-[200px] max-h-64 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-ink-muted text-sm">
            <Loader2 className="w-4 h-4 animate-spin mr-2" /> Lade...
          </div>
        ) : items.length === 0 && !error ? (
          <div className="flex flex-col items-center justify-center py-12 text-ink-muted text-sm">
            <FolderOpen className="w-8 h-8 mb-2 text-gray-300" />
            Kein Inhalt gefunden
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
                className={`w-full text-left px-4 py-2.5 flex items-center gap-2 text-sm border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors ${
                  isSelected ? 'bg-primary-50 text-primary-700' : 'text-ink'
                }`}
              >
                {isDir ? (
                  <FolderOpen className="w-4 h-4 text-amber-500 shrink-0" />
                ) : (
                  <div className="w-4 h-4 shrink-0 rounded border border-gray-300 flex items-center justify-center">
                    {isSelected && <div className="w-2 h-2 rounded-sm bg-primary-600" />}
                  </div>
                )}
                <span className="truncate">{name}</span>
                {isDir && <ChevronRight className="w-3 h-3 text-gray-400 ml-auto shrink-0" />}
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
          className="px-4 py-2 text-sm text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50"
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
        onSelect={handleNCImportWithType}
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
          ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
          : isError
          ? 'bg-red-50 border-red-200 text-red-700'
          : 'bg-blue-50 border-blue-200 text-blue-700'
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

function StatusTile({ data, onRefresh, onDriftReview }) {
  if (!data) {
    return (
      <div className="bg-white rounded-xl border border-surface-border p-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gray-100 animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gray-100 rounded animate-pulse w-1/2" />
            <div className="h-3 bg-gray-100 rounded animate-pulse w-1/3" />
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

  return (
    <div className="space-y-3 mb-6">
      {drift_available && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-3 text-sm text-blue-700">
          <Info className="w-4 h-4 shrink-0" />
          <span className="flex-1">Voice-Update verfügbar — Drift erkannt.</span>
          <button
            onClick={onDriftReview}
            className="text-xs font-medium text-blue-700 underline hover:no-underline"
          >
            Voice-Updates prüfen →
          </button>
        </div>
      )}

      <div
        className={`bg-white rounded-xl border p-5 ${
          allPresent
            ? 'border-emerald-200'
            : nonePresent
            ? 'border-red-200'
            : 'border-amber-200'
        }`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                allPresent
                  ? 'bg-emerald-50'
                  : nonePresent
                  ? 'bg-red-50'
                  : 'bg-amber-50'
              }`}
            >
              {allPresent ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              ) : nonePresent ? (
                <XCircle className="w-5 h-5 text-red-500" />
              ) : (
                <AlertCircle className="w-5 h-5 text-amber-500" />
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
                      <span
                        key={label}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-medium border border-emerald-100"
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        {label}
                        {v?.version && <span className="opacity-60">v{v.version}</span>}
                      </span>
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
                  <p className="text-sm font-semibold text-red-700">Kein Brand Voice eingerichtet</p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Lade eine Datei hoch oder importiere aus Nextcloud, um zu starten.
                  </p>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {allPresent && (
              <button className="px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100">
                Neu generieren
              </button>
            )}
            {!allPresent && !nonePresent && (
              <button className="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100">
                Profil vervollständigen
              </button>
            )}
            {nonePresent && (
              <button className="px-4 py-2 text-xs font-semibold text-white bg-red-500 rounded-lg hover:bg-red-600 flex items-center gap-1.5">
                Jetzt einrichten <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={onRefresh}
              className="p-2 text-ink-muted hover:text-primary-600 rounded-lg hover:bg-gray-50"
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
    return () => { if (activeReaderRef.current) activeReaderRef.current.abort() }
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

  const previewLines = fileContent
    ? fileContent.split('\n').slice(0, 30).join('\n')
    : null

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
            : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        }`}
      >
        <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
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
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          {fileError}
        </div>
      )}

      {uploadError && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          {uploadError}
        </div>
      )}

      {uploadSuccess && (
        <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700 flex items-center gap-2">
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
          <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-[11px] text-ink leading-relaxed overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
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
      const data = await getBrandVoiceStatus(TENANT_ID)
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
        <button
          onClick={() => setShowNCPicker(true)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100"
        >
          <FolderOpen className="w-4 h-4" />
          Aus Nextcloud importieren
        </button>
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
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          Fehler beim Laden des Status: {statusError}
        </div>
      )}

      {/* Review-Queue warning banner */}
      {reviewQueueCount > 0 && (
        <Link
          to="/brand-voice/review-queue"
          className="flex items-center gap-3 mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 hover:bg-red-100 transition-colors"
        >
          <ShieldAlert className="w-4 h-4 shrink-0" />
          <span className="flex-1">
            <span className="font-semibold">{reviewQueueCount} {reviewQueueCount === 1 ? 'Post' : 'Posts'} in Review-Queue</span>
            {' '}— Sensible Themen warten auf Freigabe.
          </span>
          <span className="text-xs font-medium underline shrink-0">Jetzt prüfen →</span>
        </Link>
      )}

      {/* Status Tile — shows skeleton when statusData is undefined */}
      <StatusTile data={statusData} onRefresh={loadStatus} onDriftReview={() => navigate('/brand-voice/drift-review')} />

      {/* Upload Zone */}
      <UploadZone onUploadSuccess={loadStatus} />

      {/* NC Picker Modal */}
      <NCPickerModal
        open={showNCPicker}
        onClose={() => setShowNCPicker(false)}
        onImport={handleNCImport}
        tenantSlug="zfb"
      />
    </div>
  )
}
