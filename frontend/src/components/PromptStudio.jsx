/**
 * Prompt-Studio (P3) — Seite zum Durchsehen, Bearbeiten, Validieren und
 * Speichern von content-truth-Dateien (Prompts, Rules, Schemas).
 *
 * Muster: Memory.jsx / CompanyProfile.jsx (einfache Fetch-on-Mount-Seiten)
 * UI-Bausteine: Card/CardHeader/CardTitle/CardContent, Button, Badge, useToast
 */
import { useState, useEffect, useCallback } from 'react'
import { FileCode, AlertTriangle, RefreshCw, CheckCircle, XCircle, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { useToast } from './ui/Toast'
import {
  getPromptFiles,
  getPromptFile,
  validatePromptFile,
  savePromptFile,
  revertPromptFile,
} from '../api'

// ─── Helper-Funktionen (pure, auch in Tests genutzt) ─────────────────────────

/**
 * Leitet die Gruppe (Prompts / Rules / Schemas) aus kind ab.
 * kind: "prompt" | "rule" | "schema"
 */
export function kindToGroup(kind) {
  if (kind === 'prompt') return 'Prompts'
  if (kind === 'rule') return 'Rules'
  if (kind === 'schema') return 'Schemas'
  return 'Sonstige'
}

/**
 * Liefert Badge-Farbe für source ("base" | "overlay").
 */
export function sourceBadgeColor(source) {
  return source === 'overlay' ? 'yellow' : 'gray'
}

/**
 * Prüft ob die Base-Version neuer ist als das Overlay (Warnung).
 * base_mtime und mtime sind ISO-Strings.
 */
export function isBaseNewerThanOverlay(file) {
  if (!file.has_overlay || !file.base_mtime) return false
  const baseMtime = new Date(file.base_mtime).getTime()
  const effectiveMtime = new Date(file.mtime).getTime()
  return baseMtime > effectiveMtime
}

/**
 * Erkennt ob aktueller Inhalt sich vom geladenen Stand unterscheidet (dirty).
 */
export function isDirty(current, loaded) {
  return current !== loaded
}

// ─── FileList-Unterkomponente ─────────────────────────────────────────────────

function FileList({ files, selectedPath, onSelect }) {
  const [collapsed, setCollapsed] = useState({})

  const grouped = {}
  for (const f of files) {
    const g = kindToGroup(f.kind)
    if (!grouped[g]) grouped[g] = []
    grouped[g].push(f)
  }

  const groupOrder = ['Prompts', 'Rules', 'Schemas', 'Sonstige']
  const sortedGroups = groupOrder.filter(g => grouped[g])

  function toggleGroup(g) {
    setCollapsed(prev => ({ ...prev, [g]: !prev[g] }))
  }

  return (
    <div className="space-y-2">
      {sortedGroups.map(group => (
        <div key={group}>
          <button
            onClick={() => toggleGroup(group)}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors"
          >
            {collapsed[group]
              ? <ChevronRight className="w-3 h-3 flex-shrink-0" />
              : <ChevronDown className="w-3 h-3 flex-shrink-0" />
            }
            {group}
            <span className="ml-auto font-normal normal-case tracking-normal">
              {grouped[group].length}
            </span>
          </button>

          {!collapsed[group] && (
            <div className="space-y-0.5 ml-1">
              {grouped[group].map(f => {
                const isSelected = f.path === selectedPath
                const warnBaseNewer = isBaseNewerThanOverlay(f)
                return (
                  <button
                    key={f.path}
                    onClick={() => onSelect(f.path)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-start gap-2 min-h-[44px] ${
                      isSelected
                        ? 'bg-primary-50 text-primary-700 border-l-2 border-primary-700'
                        : 'text-ink-light hover:bg-gray-50 hover:text-ink'
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="truncate font-medium text-xs">{f.name}</span>
                        {f.prompt_key && (
                          <span className="text-[10px] text-ink-muted shrink-0">{f.prompt_key}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Badge color={sourceBadgeColor(f.source)} className="text-[10px] py-0 px-1.5">
                          {f.source}
                        </Badge>
                        {warnBaseNewer && (
                          <span title="Base ist neuer als dein Overlay">
                            <AlertTriangle className="w-3 h-3 text-amber-500" />
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── ValidationPanel-Unterkomponente ─────────────────────────────────────────

function ValidationPanel({ result }) {
  if (!result) return null

  const ok = result.valid
  return (
    <div className={`rounded-lg border p-3 text-sm ${
      ok
        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
        : 'bg-amber-50 border-amber-200 text-amber-800'
    }`}>
      <div className="flex items-center gap-2 font-medium mb-1">
        {ok
          ? <CheckCircle className="w-4 h-4 text-emerald-600" />
          : <XCircle className="w-4 h-4 text-amber-600" />
        }
        {ok ? 'Validierung OK' : 'Validierung: Probleme gefunden'}
      </div>

      {result.health && (
        <div className="text-xs space-y-0.5">
          <div>System: {result.health.system_chars} Zeichen · User: {result.health.user_chars} Zeichen</div>
          {result.health.issues.length > 0 && (
            <ul className="list-disc list-inside">
              {result.health.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {result.schema_errors && result.schema_errors.length > 0 && (
        <ul className="text-xs list-disc list-inside mt-1">
          {result.schema_errors.map((err, i) => (
            <li key={i}>{err}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── SectionPreview-Unterkomponente ──────────────────────────────────────────

function SectionPreview({ fileContent }) {
  const [open, setOpen] = useState(false)
  if (!fileContent) return null
  const { system_prompt, user_prompt } = fileContent
  if (!system_prompt && !user_prompt) return null

  return (
    <div className="border border-surface-border rounded-lg text-xs">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-ink-muted hover:text-ink transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        Extrahierte Sektionen (Loader-Vorschau)
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {system_prompt != null && (
            <div>
              <p className="font-semibold text-ink mb-0.5">System-Prompt</p>
              <pre className="bg-gray-50 rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap break-words text-ink-muted">
                {system_prompt || '(leer)'}
              </pre>
            </div>
          )}
          {user_prompt != null && (
            <div>
              <p className="font-semibold text-ink mb-0.5">User-Prompt</p>
              <pre className="bg-gray-50 rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap break-words text-ink-muted">
                {user_prompt || '(leer)'}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Haupt-Komponente ─────────────────────────────────────────────────────────

export default function PromptStudio() {
  const { success, error: toastError, warning, info } = useToast()

  // Datei-Liste
  const [files, setFiles] = useState([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState(null)

  // Ausgewählte Datei
  const [selectedPath, setSelectedPath] = useState(null)
  const [fileContent, setFileContent] = useState(null)  // PromptFileContentResponse
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState(null)

  // Editor-State
  const [editorText, setEditorText] = useState('')
  const [loadedText, setLoadedText] = useState('')  // Stand beim Laden (für dirty-Erkennung)
  const [loadedSha, setLoadedSha] = useState(null)  // base_sha256 für optimistisches Locking

  // Aktions-States
  const [validating, setValidating] = useState(false)
  const [validateResult, setValidateResult] = useState(null)
  const [saving, setSaving] = useState(false)
  const [reverting, setReverting] = useState(false)

  // ─── Datei-Liste laden ───────────────────────────────────────────────────

  const loadFileList = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const data = await getPromptFiles()
      setFiles(data.files || [])
    } catch (e) {
      setListError(e.message)
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => { loadFileList() }, [loadFileList])

  // ─── Datei öffnen ────────────────────────────────────────────────────────

  const loadFile = useCallback(async (path) => {
    setSelectedPath(path)
    setFileLoading(true)
    setFileError(null)
    setFileContent(null)
    setValidateResult(null)
    try {
      const data = await getPromptFile(path)
      setFileContent(data)
      setEditorText(data.content)
      setLoadedText(data.content)
      setLoadedSha(data.sha256)
    } catch (e) {
      setFileError(e.message)
    } finally {
      setFileLoading(false)
    }
  }, [])

  // ─── Validieren ──────────────────────────────────────────────────────────

  async function handleValidate() {
    if (!selectedPath) return
    setValidating(true)
    setValidateResult(null)
    try {
      const result = await validatePromptFile(selectedPath, editorText)
      setValidateResult(result)
      if (result.valid) {
        info('Validierung erfolgreich')
      } else {
        warning('Validierung: Probleme gefunden')
      }
    } catch (e) {
      toastError('Validierung fehlgeschlagen: ' + e.message)
    } finally {
      setValidating(false)
    }
  }

  // ─── Speichern ───────────────────────────────────────────────────────────

  async function handleSave() {
    if (!selectedPath) return
    setSaving(true)
    try {
      const result = await savePromptFile(selectedPath, editorText, loadedSha)
      // Antwort enthält neue sha256 + mtime
      setLoadedText(editorText)
      setLoadedSha(result.sha256)
      setValidateResult(result.validation || null)
      success('Gespeichert (Overlay)')
      // Liste und Datei neu laden für aktuellen source/mtime-Stand
      await loadFileList()
      await loadFile(selectedPath)
    } catch (e) {
      if (e.status === 409 || (e.message && e.message.includes('Konflikt'))) {
        toastError('Konflikt — Datei wurde extern geändert. Bitte neu laden.')
      } else if (e.status === 422) {
        const errs = e.detail && Array.isArray(e.detail.schema_errors)
          ? e.detail.schema_errors.join('; ')
          : e.message
        toastError('Ungültiges Schema — Speichern blockiert: ' + errs)
      } else {
        toastError('Speichern fehlgeschlagen: ' + e.message)
      }
    } finally {
      setSaving(false)
    }
  }

  // ─── Auf Base zurücksetzen ───────────────────────────────────────────────

  async function handleRevert() {
    if (!selectedPath) return
    if (!window.confirm('Overlay löschen und zur Base-Version zurückkehren?')) return
    setReverting(true)
    try {
      const result = await revertPromptFile(selectedPath)
      if (result.reverted) {
        success('Overlay entfernt — Base-Version wiederhergestellt')
      } else {
        info('Kein Overlay vorhanden — bereits auf Base-Stand')
      }
      setValidateResult(null)
      await loadFileList()
      await loadFile(selectedPath)
    } catch (e) {
      toastError('Zurücksetzen fehlgeschlagen: ' + e.message)
    } finally {
      setReverting(false)
    }
  }

  // ─── Aktueller Dateizustand ──────────────────────────────────────────────

  const dirty = fileContent ? isDirty(editorText, loadedText) : false
  const currentFileInfo = files.find(f => f.path === selectedPath)
  const showRevert = fileContent?.has_overlay || currentFileInfo?.has_overlay

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-ink flex items-center gap-2">
          <FileCode className="w-6 h-6 text-primary-600" />
          Prompt-Studio
        </h1>
        <p className="text-sm text-ink-muted mt-1">
          Prompts, Rules und Schemas durchsehen, bearbeiten und validieren — ohne Container-Rebuild.
          Änderungen landen im beschreibbaren Overlay (<code className="text-xs bg-gray-100 px-1 rounded">data/prompts-custom/</code>).
        </p>
      </div>

      {/* Fehler beim Laden der Liste */}
      {listError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-center gap-2">
          <XCircle className="w-4 h-4 flex-shrink-0" />
          Fehler beim Laden: {listError}
          <Button variant="ghost" size="sm" onClick={loadFileList} className="ml-auto">
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Neu laden
          </Button>
        </div>
      )}

      {/* Zweispalten-Layout */}
      <div className="flex gap-6 items-start">

        {/* Linke Spalte: Datei-Liste */}
        <div className="w-64 shrink-0">
          <Card>
            <CardHeader className="py-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Dateien</CardTitle>
                <button
                  onClick={loadFileList}
                  className="p-1 rounded hover:bg-gray-100 text-ink-muted hover:text-ink transition-colors"
                  title="Liste neu laden"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${listLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </CardHeader>
            <CardContent className="py-2 px-3">
              {listLoading && files.length === 0 ? (
                <p className="text-xs text-ink-muted py-4 text-center">Lade…</p>
              ) : files.length === 0 ? (
                <p className="text-xs text-ink-muted py-4 text-center">Keine Dateien gefunden.</p>
              ) : (
                <FileList
                  files={files}
                  selectedPath={selectedPath}
                  onSelect={loadFile}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Rechte Spalte: Editor */}
        <div className="flex-1 min-w-0 space-y-4">
          {!selectedPath && (
            <Card>
              <CardContent className="py-16 text-center">
                <FileCode className="w-10 h-10 text-ink-muted mx-auto mb-3" />
                <p className="text-sm text-ink-muted">Wähle eine Datei aus der Liste.</p>
              </CardContent>
            </Card>
          )}

          {selectedPath && (
            <>
              {/* Datei-Header */}
              {fileContent && (
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-base font-semibold text-ink">{fileContent.path}</h2>
                  <Badge color={sourceBadgeColor(fileContent.source)}>
                    {fileContent.source}
                  </Badge>
                  {fileContent.prompt_key && (
                    <Badge color="blue">{fileContent.prompt_key}</Badge>
                  )}
                  {isBaseNewerThanOverlay(fileContent) && (
                    <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      Base ist neuer als dein Overlay
                    </span>
                  )}
                  {dirty && (
                    <span className="text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
                      Ungespeicherte Änderungen
                    </span>
                  )}
                </div>
              )}

              {/* Lade-Fehler Editor */}
              {fileError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                  {fileError}
                </div>
              )}

              {/* Textarea */}
              <Card>
                <CardContent className="p-0">
                  {fileLoading ? (
                    <div className="py-16 text-center text-sm text-ink-muted">Lade Datei…</div>
                  ) : (
                    <textarea
                      value={editorText}
                      onChange={e => setEditorText(e.target.value)}
                      spellCheck={false}
                      className="w-full font-mono text-sm p-4 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 min-h-[480px] bg-white text-ink leading-relaxed"
                      style={{ height: 'clamp(480px, 60vh, 900px)' }}
                      placeholder="Datei-Inhalt erscheint hier…"
                    />
                  )}
                </CardContent>
              </Card>

              {/* Aktions-Buttons */}
              {!fileLoading && fileContent && (
                <div className="flex items-center gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleValidate}
                    disabled={validating}
                  >
                    <CheckCircle className="w-3.5 h-3.5" />
                    {validating ? 'Validiere…' : 'Validieren'}
                  </Button>

                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSave}
                    disabled={saving || !dirty}
                  >
                    {saving ? 'Speichere…' : 'Speichern'}
                  </Button>

                  {showRevert && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={handleRevert}
                      disabled={reverting}
                    >
                      {reverting ? 'Setze zurück…' : 'Auf Base zurücksetzen'}
                    </Button>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => loadFile(selectedPath)}
                    disabled={fileLoading}
                    className="ml-auto"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Neu laden
                  </Button>
                </div>
              )}

              {/* Validierungs-Ergebnis */}
              <ValidationPanel result={validateResult} />

              {/* Extrahierte Sektionen */}
              {fileContent && <SectionPreview fileContent={fileContent} />}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
