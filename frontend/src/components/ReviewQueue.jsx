import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, Check, X, ChevronDown, ChevronUp, Loader2, ShieldAlert, Tag, AlertCircle, CheckCircle2 } from 'lucide-react'
import { getReviewQueue, decideReviewQueueItem } from '../api'

// ─── Helpers ──────────────────────────────────────────────────────────────────

const CATEGORY_LABELS = {
  politics: 'Politik',
  religion: 'Religion',
  hate: 'Hassrede',
  health_claims: 'Gesundheitsversprechen',
  financial_advice: 'Finanzberatung',
  legal_advice: 'Rechtsberatung',
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const yyyy = d.getFullYear()
    const hh = String(d.getHours()).padStart(2, '0')
    const min = String(d.getMinutes()).padStart(2, '0')
    return `${dd}.${mm}.${yyyy} ${hh}:${min}`
  } catch {
    return iso
  }
}

function severityClasses(severity) {
  switch (severity) {
    case 'high':
      return 'bg-red-100 text-red-700 border-red-200'
    case 'medium':
      return 'bg-yellow-100 text-yellow-700 border-yellow-200'
    default:
      return 'bg-gray-100 text-gray-600 border-gray-200'
  }
}

function severityLabel(severity) {
  switch (severity) {
    case 'high': return 'Hoch'
    case 'medium': return 'Mittel'
    default: return 'Niedrig'
  }
}

function categoryLabel(cat) {
  return CATEGORY_LABELS[cat] || cat
}

// ─── QueueItemCard ─────────────────────────────────────────────────────────────

function QueueItemCard({ item, onRemoved }) {
  const [expanded, setExpanded] = useState(true)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const postText = item.post_text || item.content || item.text || ''
  const truncated = postText.length > 400
  const displayText = truncated ? postText.slice(0, 400) + '...' : postText
  const phrases = item.flagged_phrases || []
  const categories = item.categories || []
  const severity = item.severity || 'low'

  async function handleDecide(action) {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await decideReviewQueueItem(item.id, action, note)
      onRemoved(item.id)
    } catch (e) {
      setSubmitError(e.message || 'Fehler beim Speichern')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-surface-border overflow-hidden">
      {/* Card header */}
      <div
        className="flex items-center justify-between px-5 py-3.5 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-ink-muted">{formatDate(item.created_at)}</span>

          {/* Severity badge */}
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-medium ${severityClasses(severity)}`}
          >
            {severityLabel(severity)}
          </span>

          {/* Category tags */}
          {categories.map((cat) => (
            <span
              key={cat}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-[11px] border border-gray-200"
            >
              <Tag className="w-2.5 h-2.5" />
              {categoryLabel(cat)}
            </span>
          ))}
        </div>

        <div className="shrink-0 text-ink-muted">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Card body */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-surface-border pt-4">

          {/* Post text */}
          {displayText && (
            <div>
              <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide mb-2">Post-Text</p>
              <p className="text-sm text-ink bg-gray-50 border border-gray-200 rounded-lg px-3 py-3 leading-relaxed whitespace-pre-wrap break-words">
                {displayText}
              </p>
            </div>
          )}

          {/* Matched phrases */}
          {phrases.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide mb-2">
                Erkannte Phrasen
              </p>
              <div className="space-y-1.5">
                {phrases.map((phrase, idx) => {
                  const phraseText = typeof phrase === 'string' ? phrase : phrase.text || phrase.phrase || String(phrase)
                  const phraseCategory = typeof phrase === 'object' ? phrase.category : null
                  return (
                    <div
                      key={idx}
                      className="flex items-start gap-2 text-sm"
                    >
                      {phraseCategory && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-[11px] border border-gray-200 shrink-0 mt-0.5">
                          <Tag className="w-2.5 h-2.5" />
                          {categoryLabel(phraseCategory)}
                        </span>
                      )}
                      <span className="text-ink leading-relaxed">{phraseText}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Note textarea */}
          <div>
            <label className="block text-xs font-semibold text-ink-muted uppercase tracking-wide mb-1.5">
              Notiz (optional)
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Interne Notiz zur Entscheidung..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-y min-h-[70px]"
              disabled={submitting}
            />
          </div>

          {/* Error */}
          {submitError && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {submitError}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={() => handleDecide('approved')}
              disabled={submitting}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm font-medium transition-colors bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              Freigeben
            </button>
            <button
              onClick={() => handleDecide('rejected')}
              disabled={submitting}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm font-medium transition-colors bg-white text-red-700 border-red-200 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <X className="w-4 h-4" />
              )}
              Ablehnen
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main: ReviewQueue ────────────────────────────────────────────────────────

export default function ReviewQueue() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getReviewQueue('me', 'pending')
      .then((data) => setItems(data.items || data || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function handleRemoved(id) {
    setItems((prev) => prev.filter((item) => item.id !== id))
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-red-600" />
            Review-Queue — Sensible Themen
          </h1>
          <p className="text-sm text-ink-light mt-0.5">
            Posts die vor Veröffentlichung geprüft werden müssen
          </p>
        </div>
        {!loading && !error && items.length > 0 && (
          <span className="inline-flex items-center px-3 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-medium">
            {items.length} ausstehend
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
          <button
            onClick={load}
            className="ml-auto text-xs underline hover:no-underline shrink-0"
          >
            Erneut laden
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-ink-muted text-sm gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Lade Review-Queue...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mb-3" />
          <p className="text-sm font-medium">Keine ausstehenden Reviews</p>
          <p className="text-xs text-ink-light mt-1">Alle Posts freigegeben oder noch keine Einträge.</p>
        </div>
      )}

      {/* Item cards */}
      {!loading && !error && items.length > 0 && (
        <div className="space-y-4">
          {items.map((item) => (
            <QueueItemCard key={item.id} item={item} onRemoved={handleRemoved} />
          ))}
        </div>
      )}
    </div>
  )
}
