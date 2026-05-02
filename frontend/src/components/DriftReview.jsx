import { useState, useEffect, useCallback } from 'react'
import { Check, X, Edit2, ChevronDown, ChevronUp, AlertCircle, Loader2, CheckCircle2 } from 'lucide-react'
import { getDriftObservations, decideDriftObservation } from '../api'

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

function triggerLabel(obs) {
  const trigger = obs?.suggested_changes?.[0]?.trigger || obs?.trigger
  if (trigger === 'user_feedback') return 'User-Feedback'
  if (trigger === 'auto') return 'Automatisch'
  if (typeof trigger === 'string' && trigger) return trigger
  const count = obs?.post_count
  if (count) return `nach ${count} Posts`
  return 'nach 10 Posts'
}

function statusBadge(status) {
  switch (status) {
    case 'pending_review':
      return 'bg-yellow-50 text-yellow-700 border-yellow-200'
    case 'accepted':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200'
    case 'rejected':
      return 'bg-red-50 text-red-700 border-red-200'
    case 'partial':
      return 'bg-blue-50 text-blue-700 border-blue-200'
    default:
      return 'bg-gray-50 text-gray-600 border-gray-200'
  }
}

function statusLabel(status) {
  switch (status) {
    case 'pending_review': return 'Ausstehend'
    case 'accepted': return 'Übernommen'
    case 'rejected': return 'Abgelehnt'
    case 'partial': return 'Teilweise'
    default: return status
  }
}

function displayValue(val) {
  if (val === null || val === undefined) return '—'
  if (Array.isArray(val)) return val.join(', ')
  return String(val)
}

// ─── ChangeItem ───────────────────────────────────────────────────────────────

function ChangeItem({ change, decision, editedValue, onDecide, onEditChange }) {
  const { field_path, current_value, new_value, reason } = change

  return (
    <div className="border border-surface-border rounded-xl p-4 bg-white">
      {/* Field label */}
      <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide mb-3">
        {field_path}
      </p>

      {/* Old → New diff */}
      <div className="flex flex-col md:flex-row gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-medium text-ink-muted mb-1">Alt</p>
          <p className="text-sm text-ink bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 leading-relaxed break-words whitespace-pre-wrap">
            {displayValue(current_value)}
          </p>
        </div>
        <div className="hidden md:flex items-center text-gray-400 text-sm shrink-0 pt-5">→</div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-medium text-ink-muted mb-1">Neu</p>
          <p className="text-sm text-ink bg-blue-50 border border-blue-100 rounded-lg px-3 py-2 leading-relaxed break-words whitespace-pre-wrap">
            {displayValue(new_value)}
          </p>
        </div>
      </div>

      {/* Reason */}
      {reason && (
        <p className="text-xs text-ink-muted mb-3 leading-relaxed">
          <span className="font-medium text-ink">Begründung:</span> {reason}
        </p>
      )}

      {/* Edit textarea */}
      {decision === 'edit' && (
        <div className="mb-3">
          <p className="text-xs font-medium text-ink mb-1">Angepasster Wert</p>
          <textarea
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-y min-h-[80px]"
            value={editedValue}
            onChange={(e) => onEditChange(e.target.value)}
          />
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => onDecide('accept')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
            decision === 'accept'
              ? 'bg-emerald-600 text-white border-emerald-600'
              : 'bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50'
          }`}
        >
          <Check className="w-3.5 h-3.5" />
          Übernehmen
        </button>
        <button
          onClick={() => onDecide('reject')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
            decision === 'reject'
              ? 'bg-red-600 text-white border-red-600'
              : 'bg-white text-red-700 border-red-200 hover:bg-red-50'
          }`}
        >
          <X className="w-3.5 h-3.5" />
          Ablehnen
        </button>
        <button
          onClick={() => onDecide('edit')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
            decision === 'edit'
              ? 'bg-primary-600 text-white border-primary-600'
              : 'bg-white text-primary-700 border-primary-200 hover:bg-primary-50'
          }`}
        >
          <Edit2 className="w-3.5 h-3.5" />
          Anpassen
        </button>
      </div>
    </div>
  )
}

// ─── ObservationCard ──────────────────────────────────────────────────────────

function ObservationCard({ obs, onDecided }) {
  const changes = obs.suggested_changes || []

  // Per-change local state: { decision: 'accept'|'reject'|'edit'|null, editedValue: string }
  const [changeStates, setChangeStates] = useState(() =>
    changes.map((c) => ({
      decision: null,
      editedValue: displayValue(c.new_value),
    }))
  )
  const [expanded, setExpanded] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const allDecided = changeStates.length > 0 && changeStates.every((s) => s.decision !== null)

  function handleDecide(idx, decision) {
    setChangeStates((prev) => {
      const next = [...prev]
      next[idx] = {
        ...next[idx],
        decision,
        // pre-fill editedValue when switching to edit
        editedValue:
          decision === 'edit'
            ? next[idx].editedValue
            : displayValue(changes[idx]?.new_value),
      }
      return next
    })
  }

  function handleEditChange(idx, value) {
    setChangeStates((prev) => {
      const next = [...prev]
      next[idx] = { ...next[idx], editedValue: value }
      return next
    })
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const payload = changeStates.map((s, i) => ({
        field_path: changes[i].field_path,
        accepted: s.decision === 'accept' || s.decision === 'edit',
        modified_value: s.decision === 'edit' ? s.editedValue : null,
      }))
      const result = await decideDriftObservation(obs.id, payload)
      onDecided(obs.id, result?.status || 'accepted')
    } catch (e) {
      setSubmitError(e.message || 'Fehler beim Speichern')
    } finally {
      setSubmitting(false)
    }
  }

  const isPending = obs.status === 'pending_review'

  return (
    <div className="bg-white rounded-xl border border-surface-border overflow-hidden">
      {/* Card header */}
      <div
        className="flex items-center justify-between px-5 py-3.5 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-ink-muted">{formatDate(obs.created_at)}</span>
          <span className="text-xs text-ink-muted">{triggerLabel(obs)}</span>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-medium ${statusBadge(obs.status)}`}
          >
            {statusLabel(obs.status)}
          </span>
          {changes.length > 0 && (
            <span className="text-xs text-ink-muted">
              {changes.length} {changes.length === 1 ? 'Änderung' : 'Änderungen'}
            </span>
          )}
        </div>
        <div className="shrink-0 text-ink-muted">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Card body */}
      {expanded && (
        <div className="px-5 pb-5 space-y-3 border-t border-surface-border pt-4">
          {changes.length === 0 ? (
            <p className="text-sm text-ink-muted italic">Keine Änderungsvorschläge.</p>
          ) : (
            changes.map((change, idx) => (
              <ChangeItem
                key={change.field_path + idx}
                change={change}
                decision={changeStates[idx]?.decision ?? null}
                editedValue={changeStates[idx]?.editedValue ?? ''}
                onDecide={(d) => handleDecide(idx, d)}
                onEditChange={(v) => handleEditChange(idx, v)}
              />
            ))
          )}

          {/* Submit error */}
          {submitError && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {submitError}
            </div>
          )}

          {/* Submit button — only show when pending */}
          {isPending && (
            <div className="flex justify-end pt-1">
              <button
                onClick={handleSubmit}
                disabled={!allDecided || submitting}
                className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Übernehmen
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main: DriftReview ────────────────────────────────────────────────────────

export default function DriftReview() {
  const [observations, setObservations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getDriftObservations('me', 'pending_review')
      .then((data) => setObservations(data.observations || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function handleDecided(obsId, newStatus) {
    setObservations((prev) =>
      prev.map((o) => (o.id === obsId ? { ...o, status: newStatus } : o))
    )
  }

  const pendingCount = observations.filter((o) => o.status === 'pending_review').length

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            Voice-Updates prüfen
          </h1>
          <p className="text-sm text-ink-light mt-0.5">
            Vom System erkannte Voice-Änderungen überprüfen und bestätigen oder ablehnen.
          </p>
        </div>
        {!loading && !error && pendingCount > 0 && (
          <span className="inline-flex items-center px-3 py-1 rounded-full bg-yellow-50 border border-yellow-200 text-yellow-700 text-xs font-medium">
            {pendingCount} ausstehend
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
          Lade Voice-Updates...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && observations.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mb-3" />
          <p className="text-sm font-medium">Keine ausstehenden Voice-Anpassungen</p>
          <p className="text-xs text-ink-light mt-1">Alles erledigt.</p>
        </div>
      )}

      {/* Observation cards */}
      {!loading && !error && observations.length > 0 && (
        <div className="space-y-4">
          {observations.map((obs) => (
            <ObservationCard key={obs.id} obs={obs} onDecided={handleDecided} />
          ))}
        </div>
      )}
    </div>
  )
}
