/**
 * Phase 6.1 — Research-Findings (Vorschläge der Woche).
 * Im Dashboard sichtbar; jeder Befund zeigt 3 Hook-Vorschläge mit "Als Idee".
 */
import { useState, useEffect } from 'react'
import { Sparkles, ExternalLink, Plus } from 'lucide-react'
import { CloseButton } from './ui/CloseButton'
import { listResearchFindings, dismissResearchFinding, markFindingAsIdea } from '../api'

// 6 Kategorien, 5 Status-Tokens — keine 1:1-Bedeutung, Zuordnung nach Farbcharakter
// (rose/amber/emerald→fehler/aktiv/fertig wie im übrigen Codebase üblich).
// competition_market (violet) hat keine Status-Entsprechung → accent (dekorativ).
// costs_resources (blue) → status-neu (deckt sich mit dessen Blauton).
// emerging_topics (teal) → primary (liegt in der primären Markenfarbfamilie).
const CATEGORY_LABELS = {
  rules_constraints: { de: 'Regulierung', color: 'bg-status-fehler-bg text-status-fehler-text' },
  demand_behavior: { de: 'Marktnachfrage', color: 'bg-status-aktiv-bg text-status-aktiv-text' },
  tools_methods: { de: 'Tools & Methoden', color: 'bg-status-fertig-bg text-status-fertig-text' },
  competition_market: { de: 'Wettbewerb', color: 'bg-accent-100 text-accent-700' },
  costs_resources: { de: 'Kosten & Ressourcen', color: 'bg-status-neu-bg text-status-neu-text' },
  emerging_topics: { de: 'Trend-Themen', color: 'bg-primary-100 text-primary-700' },
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
      const r = await markFindingAsIdea(id, hookIdx)
      setFindings((prev) => prev.filter((f) => f.id !== id))
      // Optional: navigate(`/ideas#${r.idea_id}`) — leave to Robert preference
    } catch (e) {
      setError(e.message)
    }
  }

  if (loading) return <p className="text-xs text-ink-muted">Lade Research-Vorschläge…</p>
  if (error) return <p className="text-xs text-status-fehler-text">{error}</p>
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
          color: 'bg-surface-bg text-ink-light',
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
              <CloseButton onClick={() => handleDismiss(f.id)} size="sm" label="Verwerfen" />
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
