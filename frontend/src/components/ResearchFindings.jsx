/**
 * Phase 6.1 — Research-Findings (Vorschläge der Woche).
 * Im Dashboard sichtbar; jeder Befund zeigt 3 Hook-Vorschläge mit "Als Idee".
 */
import { useState, useEffect } from 'react'
import { Sparkles, ExternalLink, X, Plus } from 'lucide-react'
import { listResearchFindings, dismissResearchFinding, convertFindingToIdea } from '../api'

const CATEGORY_LABELS = {
  rules_constraints: { de: 'Regulierung', color: 'bg-rose-100 text-rose-700' },
  demand_behavior: { de: 'Marktnachfrage', color: 'bg-amber-100 text-amber-700' },
  tools_methods: { de: 'Tools & Methoden', color: 'bg-emerald-100 text-emerald-700' },
  competition_market: { de: 'Wettbewerb', color: 'bg-violet-100 text-violet-700' },
  costs_resources: { de: 'Kosten & Ressourcen', color: 'bg-blue-100 text-blue-700' },
  emerging_topics: { de: 'Trend-Themen', color: 'bg-teal-100 text-teal-700' },
}

const IMPACT_ICONS = {
  positive: '🟢',
  neutral: '🟡',
  negative: '🔴',
}

export default function ResearchFindings({ limit = 8 }) {
  const [findings, setFindings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await listResearchFindings({ status_filter: 'active', limit })
      setFindings(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load() /* eslint-disable-next-line */
  }, [limit])

  async function handleDismiss(id) {
    try {
      await dismissResearchFinding(id)
      setFindings((prev) => prev.filter((f) => f.id !== id))
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleUseAsIdea(id, hookIdx) {
    try {
      const r = await convertFindingToIdea(id, hookIdx)
      setFindings((prev) => prev.filter((f) => f.id !== id))
      // Optional: navigate(`/ideas#${r.idea_id}`) — leave to Robert preference
    } catch (e) {
      setError(e.message)
    }
  }

  if (loading) return <p className="text-xs text-ink-muted">Lade Research-Vorschläge…</p>
  if (error) return <p className="text-xs text-red-700">{error}</p>
  if (findings.length === 0) {
    return (
      <p className="text-xs text-ink-muted">
        Noch keine Research-Vorschläge. Der nächste Auto-Run ist Dienstag und Freitag morgens.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {findings.map((f) => {
        const cat = CATEGORY_LABELS[f.category] || {
          de: f.category,
          color: 'bg-gray-100 text-gray-700',
        }
        return (
          <div
            key={f.id}
            className="bg-white rounded-xl border border-surface-border p-4 hover:border-primary-300 transition-colors"
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className={`text-[11px] px-2 py-0.5 rounded-full ${cat.color}`}>
                    {cat.de}
                  </span>
                  <span className="text-[11px] text-ink-muted">
                    {IMPACT_ICONS[f.impact_rating] || '🟡'}
                  </span>
                  {f.source_publisher && (
                    <span className="text-[11px] text-ink-muted">· {f.source_publisher}</span>
                  )}
                  {f.source_date && (
                    <span className="text-[11px] text-ink-muted">
                      · {new Date(f.source_date).toLocaleDateString('de-DE')}
                    </span>
                  )}
                </div>
                <h3 className="text-sm font-semibold text-ink leading-snug">
                  {f.title}
                  {f.source_url && (
                    <a
                      href={f.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-1.5 text-primary-600 hover:text-primary-800"
                    >
                      <ExternalLink className="w-3 h-3 inline" />
                    </a>
                  )}
                </h3>
                {f.summary && (
                  <p className="text-xs text-ink-muted mt-1 line-clamp-2">{f.summary}</p>
                )}
              </div>
              <button
                onClick={() => handleDismiss(f.id)}
                className="p-1 rounded text-ink-muted hover:bg-gray-100"
                title="Verwerfen"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {f.hooks && f.hooks.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10px] uppercase tracking-wide text-ink-muted font-semibold">
                  3 Hook-Vorschläge
                </p>
                {f.hooks.slice(0, 3).map((hook, i) => (
                  <div key={i} className="flex items-start gap-2 group">
                    <p className="flex-1 text-xs text-ink leading-snug pt-1">{hook}</p>
                    <button
                      onClick={() => handleUseAsIdea(f.id, i)}
                      className="flex items-center gap-1 px-2 py-1 text-[11px] bg-primary-50 hover:bg-primary-100 text-primary-700 rounded border border-primary-200 transition-colors flex-shrink-0"
                    >
                      <Plus className="w-3 h-3" />
                      Als Idee
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
