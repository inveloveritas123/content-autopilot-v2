import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPipelineModels, setPipelineModelOverride } from '../api'

/**
 * Pipeline-Modell-Hoheit (SOLL-IST-2026-06-12-wiring.md §5).
 *
 * Zeigt pro Pipeline-Phase das OFFIZIELLE Default-Modell (im Code/ADR-0008
 * verankert) und erlaubt einen globalen TEST-Override mit einer beliebigen
 * Requesty-Modell-ID (z.B. gemini-flash-lite). Default bleibt unangetastet —
 * der Override ist jederzeit rücksetzbar.
 */
export default function PipelineModels() {
  const [phases, setPhases] = useState([])
  const [catalog, setCatalog] = useState([])
  const [drafts, setDrafts] = useState({}) // phase -> input value
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [savingPhase, setSavingPhase] = useState(null)
  const [notice, setNotice] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await getPipelineModels()
      setPhases(data.phases || [])
      setCatalog(data.tier_catalog || [])
      const d = {}
      ;(data.phases || []).forEach((p) => {
        d[p.phase] = p.override || ''
      })
      setDrafts(d)
    } catch (e) {
      setError(e.message || 'Laden fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function save(phase, modelId) {
    setSavingPhase(phase)
    setError(null)
    setNotice(null)
    try {
      const data = await setPipelineModelOverride(phase, modelId)
      setPhases(data.phases || [])
      const d = {}
      ;(data.phases || []).forEach((p) => {
        d[p.phase] = p.override || ''
      })
      setDrafts(d)
      setNotice(
        modelId
          ? `${phase}: Test-Override gesetzt → ${modelId}`
          : `${phase}: Override entfernt (zurück auf Default)`
      )
    } catch (e) {
      setError(e.message || 'Speichern fehlgeschlagen')
    } finally {
      setSavingPhase(null)
    }
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="mb-4">
        <Link to="/settings" className="text-sm text-primary-700 hover:underline">
          ← Einstellungen
        </Link>
      </div>
      <h1 className="text-2xl font-semibold text-ink">Modell-Hoheit · Pipeline-Phasen</h1>
      <p className="mt-2 text-sm text-ink-light">
        Pro Phase ist das <strong>offizielle</strong> Modell im Code verankert (Tier-Default,
        ADR-0008). Für Experimente kannst du einen <strong>globalen Test-Override</strong> mit einer
        beliebigen Requesty-Modell-ID setzen — der Default bleibt erhalten und ist jederzeit
        rücksetzbar.
      </p>

      {error && (
        <div className="mt-4 rounded-lg bg-status-fehler-bg border border-status-fehler-border px-4 py-3 text-sm text-status-fehler-text">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-4 rounded-lg bg-status-fertig-bg border border-status-fertig-border px-4 py-3 text-sm text-status-fertig-text">
          {notice}
        </div>
      )}

      <datalist id="model-catalog">
        {catalog.map((c) => (
          <option key={c.tier} value={c.model_id}>
            {c.tier} · {c.model_id}
          </option>
        ))}
      </datalist>

      {loading ? (
        <div className="mt-6 text-sm text-ink-light">Lädt…</div>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-ink-light border-b">
                <th className="py-2 pr-4">Phase</th>
                <th className="py-2 pr-4">Offiziell (Default)</th>
                <th className="py-2 pr-4">Effektiv</th>
                <th className="py-2 pr-4">Test-Override (Requesty-Modell-ID)</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {phases.map((p) => {
                const overridden = p.source !== 'default'
                return (
                  <tr key={p.phase} className="border-b last:border-0 align-top">
                    <td className="py-3 pr-4 font-medium text-ink">{p.phase}</td>
                    <td className="py-3 pr-4 text-ink-light">
                      <span className="inline-flex items-center gap-1">
                        <span className="px-1.5 py-0.5 rounded bg-surface-bg text-ink-light text-xs font-mono">
                          {p.default_tier}
                        </span>
                        <span className="font-mono text-xs">{p.default_model}</span>
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      {overridden ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="px-1.5 py-0.5 rounded bg-status-aktiv-bg text-status-aktiv-text text-xs font-medium">
                            TEST
                          </span>
                          <span className="font-mono text-xs text-status-aktiv-text">
                            {p.effective_model}
                          </span>
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-status-fertig-bg text-status-fertig-text text-xs font-medium">
                          offiziell
                        </span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <input
                        list="model-catalog"
                        value={drafts[p.phase] ?? ''}
                        onChange={(e) => setDrafts({ ...drafts, [p.phase]: e.target.value })}
                        placeholder={p.default_model}
                        className="w-72 px-2 py-1 border border-surface-border rounded font-mono text-xs focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      />
                    </td>
                    <td className="py-3 whitespace-nowrap">
                      <button
                        onClick={() => save(p.phase, (drafts[p.phase] || '').trim())}
                        disabled={savingPhase === p.phase}
                        className="px-3 py-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-medium rounded"
                      >
                        {savingPhase === p.phase ? '…' : 'Speichern'}
                      </button>
                      {overridden && (
                        <button
                          onClick={() => save(p.phase, null)}
                          disabled={savingPhase === p.phase}
                          className="ml-2 px-3 py-1 bg-surface-bg hover:bg-surface-border disabled:opacity-50 text-ink-light text-xs font-medium rounded"
                        >
                          Reset
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-4 text-xs text-ink-muted">
            Übersteuerung gilt global und sofort (hot-reload, kein Neustart). Quelle der Defaults:
            <code className="mx-1">services/pipeline_llm.py</code> (MODEL_PER_PROMPT / TIER_MODELS).
          </p>
        </div>
      )}
    </div>
  )
}
