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
      <h1 className="text-2xl font-semibold text-gray-900">Modell-Hoheit · Pipeline-Phasen</h1>
      <p className="mt-2 text-sm text-gray-600">
        Pro Phase ist das <strong>offizielle</strong> Modell im Code verankert (Tier-Default,
        ADR-0008). Für Experimente kannst du einen <strong>globalen Test-Override</strong> mit einer
        beliebigen Requesty-Modell-ID setzen — der Default bleibt erhalten und ist jederzeit
        rücksetzbar.
      </p>

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
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
        <div className="mt-6 text-sm text-gray-500">Lädt…</div>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
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
                    <td className="py-3 pr-4 font-medium text-gray-900">{p.phase}</td>
                    <td className="py-3 pr-4 text-gray-600">
                      <span className="inline-flex items-center gap-1">
                        <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 text-xs font-mono">
                          {p.default_tier}
                        </span>
                        <span className="font-mono text-xs">{p.default_model}</span>
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      {overridden ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-xs font-medium">
                            TEST
                          </span>
                          <span className="font-mono text-xs text-amber-900">
                            {p.effective_model}
                          </span>
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-xs font-medium">
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
                        className="w-72 px-2 py-1 border border-gray-300 rounded font-mono text-xs focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
                          className="ml-2 px-3 py-1 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-700 text-xs font-medium rounded"
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
          <p className="mt-4 text-xs text-gray-400">
            Übersteuerung gilt global und sofort (hot-reload, kein Neustart). Quelle der Defaults:
            <code className="mx-1">services/pipeline_llm.py</code> (MODEL_PER_PROMPT / TIER_MODELS).
          </p>
        </div>
      )}
    </div>
  )
}
