import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Database,
  Play,
  RefreshCw,
  CheckCircle,
  XCircle,
  Send,
  Settings,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import {
  listAdminModels,
  startBacktest,
  getBacktest,
  notifyTenantModel,
  applyTenantModel,
} from '../api'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function scoreBannerClass(score) {
  if (score >= 80) return 'bg-emerald-50 border-emerald-200 text-emerald-800'
  if (score >= 60) return 'bg-yellow-50 border-yellow-200 text-yellow-800'
  return 'bg-red-50 border-red-200 text-red-800'
}

function truncateId(id, len = 20) {
  if (!id) return '—'
  const s = String(id)
  return s.length > len ? s.slice(0, len) + '…' : s
}

// ─── ModelList ────────────────────────────────────────────────────────────────

function ModelList({ models, loading, error, onRefresh }) {
  const now = Date.now()

  return (
    <div className="bg-white rounded-xl border border-surface-border overflow-hidden flex flex-col">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-surface-border">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
          <Database className="w-4 h-4 text-primary-600" strokeWidth={1.75} />
          Verfügbare Modelle
        </h2>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-surface-border hover:bg-gray-50 text-ink-muted transition-colors disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="flex items-center justify-center py-12 text-ink-muted text-sm gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Lade Modelle…
          </div>
        )}

        {!loading && error && (
          <div className="m-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {error}
          </div>
        )}

        {!loading && !error && models.length === 0 && (
          <p className="py-12 text-center text-sm text-ink-muted">Keine Modelle gefunden.</p>
        )}

        {!loading && !error && models.length > 0 && (
          <ul className="divide-y divide-surface-border">
            {models.map((m) => {
              const firstSeenMs = m.first_seen_at ? new Date(m.first_seen_at).getTime() : null
              const isNew = firstSeenMs && now - firstSeenMs < 7 * 24 * 60 * 60 * 1000
              return (
                <li key={m.model_id} className="px-5 py-3 flex items-start gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary-400 mt-1.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink truncate">
                      {m.display_name || m.model_id}
                    </p>
                    <p className="text-xs text-ink-muted truncate">{m.provider} · {m.model_id}</p>
                  </div>
                  {isNew && (
                    <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-full bg-blue-50 border border-blue-200 text-[10px] font-medium text-blue-700">
                      Neu
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

// ─── BacktestResults ──────────────────────────────────────────────────────────

function BacktestResults({ result, tenantId, adminToken, onReset }) {
  const [notifying, setNotifying] = useState(false)
  const [notified, setNotified] = useState(false)
  const [notifyError, setNotifyError] = useState(null)
  const [applying, setApplying] = useState(false)
  const [applied, setApplied] = useState(false)
  const [applyError, setApplyError] = useState(null)

  const posts = result.results || []
  const passCount = posts.filter((p) => p.quality_pass === true).length
  const total = posts.length
  const score = total > 0 ? Math.round((passCount / total) * 100) : 0
  const canNotify = score >= 60

  async function handleNotify() {
    setNotifying(true)
    setNotifyError(null)
    try {
      await notifyTenantModel(adminToken, tenantId, result.run_id)
      setNotified(true)
    } catch (e) {
      setNotifyError(e.message || 'Benachrichtigung fehlgeschlagen')
    } finally {
      setNotifying(false)
    }
  }

  async function handleApply() {
    setApplying(true)
    setApplyError(null)
    try {
      await applyTenantModel(adminToken, tenantId, result.candidate_model_id || result.model_id)
      setApplied(true)
    } catch (e) {
      setApplyError(e.message || 'Fehler beim Übernehmen')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Score banner */}
      <div className={`p-4 rounded-xl border font-medium text-sm ${scoreBannerClass(score)}`}>
        {passCount}/{total} Posts PASS · Score: {score}%
      </div>

      {/* Per-post list */}
      <ul className="space-y-2">
        {posts.map((p, idx) => {
          const pass = p.quality_pass === true
          return (
            <li
              key={idx}
              className={`flex items-start gap-3 p-3 rounded-lg border text-xs ${
                pass
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-red-50 border-red-200'
              }`}
            >
              {pass ? (
                <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              )}
              <div className="flex-1 min-w-0">
                <p className="font-medium text-ink truncate">{truncateId(p.post_id || p.id, 28)}</p>
                {pass && (p.original_length != null || p.new_length != null) && (
                  <p className="text-ink-muted mt-0.5">
                    Original: {p.original_length ?? '—'} Zeichen · Neu: {p.new_length ?? '—'} Zeichen
                  </p>
                )}
                {!pass && p.issues && p.issues.length > 0 && (
                  <ul className="mt-1 space-y-0.5">
                    {p.issues.map((issue, i) => (
                      <li key={i} className="text-red-700">{issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3 pt-1">
        {canNotify && !notified && (
          <button
            onClick={handleNotify}
            disabled={notifying}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-primary-200 text-primary-700 hover:bg-primary-50 disabled:opacity-40 transition-colors"
          >
            {notifying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            Tenant benachrichtigen
          </button>
        )}
        {notified && (
          <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700">
            <CheckCircle className="w-3.5 h-3.5" />
            Benachrichtigung gesendet
          </span>
        )}

        {(notified || !canNotify) && !applied && (
          <button
            onClick={handleApply}
            disabled={applying}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40 transition-colors"
          >
            {applying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Settings className="w-4 h-4" />
            )}
            Modell übernehmen
          </button>
        )}
        {applied && (
          <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700">
            <CheckCircle className="w-3.5 h-3.5" />
            Modell-Konfiguration aktualisiert
          </span>
        )}

        <button
          onClick={onReset}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-gray-50 transition-colors"
        >
          Neuer Backtest
        </button>
      </div>

      {notifyError && (
        <p className="text-xs text-red-700 mt-1">{notifyError}</p>
      )}
      {applyError && (
        <p className="text-xs text-red-700 mt-1">{applyError}</p>
      )}
    </div>
  )
}

// ─── BacktestPanel ────────────────────────────────────────────────────────────

function BacktestPanel({ models, adminToken }) {
  const [tenantId, setTenantId] = useState('me')
  const [candidateModelId, setCandidateModelId] = useState('')
  const [postCount, setPostCount] = useState(10)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState(null)

  // polling state
  const [runId, setRunId] = useState(null)
  const [pollData, setPollData] = useState(null)
  const [pollError, setPollError] = useState(null)
  const pollRef = useRef(null)

  // result state
  const [result, setResult] = useState(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  async function handleStart() {
    if (!candidateModelId.trim()) return
    setStarting(true)
    setStartError(null)
    setRunId(null)
    setPollData(null)
    setPollError(null)
    setResult(null)
    try {
      const res = await startBacktest(adminToken, tenantId.trim(), candidateModelId.trim(), postCount)
      const id = res.backtest_run_id
      setRunId(id)
      // kick off polling
      const poll = async () => {
        try {
          const data = await getBacktest(adminToken, id)
          setPollData(data)
          if (data.status !== 'running' && data.status !== 'pending') {
            stopPolling()
            if (data.status === 'completed') {
              setResult(data)
            } else {
              setPollError(`Backtest fehlgeschlagen: ${data.error || data.status}`)
            }
          }
        } catch (e) {
          stopPolling()
          setPollError(e.message || 'Fehler beim Abrufen des Backtests')
        }
      }
      poll()
      pollRef.current = setInterval(poll, 3000)
    } catch (e) {
      setStartError(e.message || 'Backtest konnte nicht gestartet werden')
    } finally {
      setStarting(false)
    }
  }

  function handleReset() {
    stopPolling()
    setRunId(null)
    setPollData(null)
    setPollError(null)
    setResult(null)
    setStartError(null)
  }

  const isRunning = runId && pollData && (pollData.status === 'running' || pollData.status === 'pending')
  const testedCount = pollData?.tested_count ?? null
  const totalCount = pollData?.total_count ?? postCount

  return (
    <div className="bg-white rounded-xl border border-surface-border overflow-hidden flex flex-col">
      {/* Panel header */}
      <div className="px-5 py-3.5 border-b border-surface-border">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
          <Play className="w-4 h-4 text-primary-600" strokeWidth={1.75} />
          Backtest
        </h2>
      </div>

      <div className="p-5 flex-1 space-y-4">
        {/* Form — only show when not running and no result */}
        {!isRunning && !result && (
          <div className="space-y-4">
            {/* Tenant-ID */}
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">Tenant-ID</label>
              <input
                type="text"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                placeholder="me"
              />
            </div>

            {/* Kandidat-Modell */}
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">Kandidat-Modell</label>
              {models.length > 0 ? (
                <select
                  value={candidateModelId}
                  onChange={(e) => setCandidateModelId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white"
                >
                  <option value="">— Modell wählen —</option>
                  {models.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.display_name || m.model_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={candidateModelId}
                  onChange={(e) => setCandidateModelId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  placeholder="z.B. gpt-4o-mini"
                />
              )}
            </div>

            {/* Anzahl Posts */}
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">Anzahl Posts</label>
              <input
                type="number"
                value={postCount}
                min={1}
                max={20}
                onChange={(e) => setPostCount(Math.min(20, Math.max(1, Number(e.target.value))))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            {/* Start button */}
            <button
              onClick={handleStart}
              disabled={starting || !candidateModelId.trim() || !tenantId.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {starting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Backtest starten
            </button>

            {startError && (
              <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {startError}
              </div>
            )}
          </div>
        )}

        {/* Running state */}
        {isRunning && (
          <div className="flex flex-col items-center justify-center py-8 gap-3 text-ink-muted">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
            <p className="text-sm font-medium text-ink">
              Läuft…{testedCount != null ? ` (${testedCount}/${totalCount} Posts getestet)` : ''}
            </p>
            <p className="text-xs text-ink-muted">Run-ID: {runId}</p>
          </div>
        )}

        {/* Poll error */}
        {pollError && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {pollError}
            </div>
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-gray-50 transition-colors"
            >
              Zurücksetzen
            </button>
          </div>
        )}

        {/* Results */}
        {result && (
          <BacktestResults result={result} tenantId={tenantId} adminToken={adminToken} onReset={handleReset} />
        )}
      </div>
    </div>
  )
}

// ─── Main: AdminModels ────────────────────────────────────────────────────────

export default function AdminModels() {
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem('admin_token') || '')
  const [tokenInput, setTokenInput] = useState('')

  const [models, setModels] = useState([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState(null)

  const loadModels = useCallback(() => {
    if (!adminToken) return
    setModelsLoading(true)
    setModelsError(null)
    listAdminModels(adminToken)
      .then((data) => setModels(data.models || data || []))
      .catch((e) => setModelsError(e.message || 'Fehler beim Laden der Modelle'))
      .finally(() => setModelsLoading(false))
  }, [adminToken])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  if (!adminToken) {
    return (
      <div className="max-w-sm mx-auto mt-20 p-6 border rounded-lg">
        <h2 className="text-lg font-semibold mb-4">Admin-Zugang</h2>
        <input
          type="password"
          className="w-full border rounded px-3 py-2 mb-3 text-sm"
          placeholder="Admin-Token eingeben"
          value={tokenInput}
          onChange={e => setTokenInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              localStorage.setItem('admin_token', tokenInput)
              setAdminToken(tokenInput)
            }
          }}
        />
        <button
          className="w-full bg-gray-800 text-white rounded py-2 text-sm"
          onClick={() => {
            localStorage.setItem('admin_token', tokenInput)
            setAdminToken(tokenInput)
          }}
        >
          Anmelden
        </button>
        <p className="mt-3 text-xs text-gray-500">
          Admin-Token steht in <code className="bg-gray-100 px-1 rounded">.env</code> unter <code className="bg-gray-100 px-1 rounded">ADMIN_TOKEN=...</code>.<br/>
          Standard (falls nicht gesetzt): <code className="bg-gray-100 px-1 rounded">admin_backtest_2026</code>
        </p>
      </div>
    )
  }

  return (
    <div>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink flex items-center gap-2">
          <Settings className="w-5 h-5 text-primary-600" strokeWidth={1.75} />
          Admin — Modelle
        </h1>
        <p className="text-sm text-ink-light mt-0.5">
          Verfügbare LLM-Modelle verwalten und Backtests gegen Tenant-Daten ausführen.
        </p>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ModelList
          models={models}
          loading={modelsLoading}
          error={modelsError}
          onRefresh={loadModels}
        />
        <BacktestPanel models={models} adminToken={adminToken} />
      </div>
    </div>
  )
}
