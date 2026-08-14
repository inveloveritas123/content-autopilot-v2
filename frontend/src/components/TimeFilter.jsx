import { useState } from 'react'
import { Clock } from 'lucide-react'

const QUICK_FILTERS = [
  { label: '1h', value: 'last_hour' },
  { label: '24h', value: 'last_24h' },
  { label: '7 Tage', value: 'last_7d' },
  { label: '30 Tage', value: 'last_30d' },
  { label: '2026', value: 'this_year' },
  { label: '2025', value: 'last_year' },
  { label: 'Alle', value: 'all' },
]

/**
 * TimeFilter — reusable time range picker
 *
 * Props:
 *   value: { period, date_from, date_to }  — current filter state
 *   onChange(newValue)                      — called when filter changes
 *   count: number | null                    — result count to display (optional)
 *   label: string                           — label prefix (optional)
 */
export default function TimeFilter({ value = {}, onChange, count = null, label = 'Zeitraum' }) {
  const [showCustom, setShowCustom] = useState(false)
  const [dateFrom, setDateFrom] = useState(value.date_from || '')
  const [dateTo, setDateTo] = useState(value.date_to || '')

  const activePeriod = value.period || 'last_30d'

  function selectPeriod(p) {
    setShowCustom(false)
    onChange({ period: p, date_from: undefined, date_to: undefined })
  }

  function applyCustom() {
    if (!dateFrom && !dateTo) return
    onChange({ period: null, date_from: dateFrom || undefined, date_to: dateTo || undefined })
    setShowCustom(false)
  }

  function labelFor(p) {
    const f = QUICK_FILTERS.find((f) => f.value === p)
    return f ? f.label : p
  }

  const isCustomActive = !value.period && (value.date_from || value.date_to)

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 text-xs text-ink-muted">
        <Clock className="w-3.5 h-3.5" />
        <span>{label}:</span>
      </div>

      {/* Quick-filter buttons — horizontally scrollable on mobile */}
      <div className="flex items-center gap-1 overflow-x-auto pb-0.5 scrollbar-hide">
        {QUICK_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => selectPeriod(f.value)}
            className={`whitespace-nowrap px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
              activePeriod === f.value && !isCustomActive
                ? 'bg-primary-700 text-white border-primary-700'
                : 'bg-white text-ink-muted border-surface-border hover:border-primary-300 hover:text-primary-700'
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={() => setShowCustom((v) => !v)}
          className={`whitespace-nowrap px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
            isCustomActive || showCustom
              ? 'bg-primary-700 text-white border-primary-700'
              : 'bg-white text-ink-muted border-surface-border hover:border-primary-300 hover:text-primary-700'
          }`}
        >
          {isCustomActive
            ? `${value.date_from || '…'} → ${value.date_to || '…'}`
            : '📅 Benutzerdefiniert'}
        </button>
      </div>

      {/* Result counter */}
      {count !== null && (
        <span className="text-xs text-ink-muted ml-1">
          — <span className="font-semibold text-ink">{count}</span> Ergebnis
          {count !== 1 ? 'se' : ''}
        </span>
      )}

      {/* Custom date range picker */}
      {showCustom && (
        <div className="w-full flex items-center gap-2 mt-1 pl-1">
          <span className="text-xs text-ink-muted">Von</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="text-xs border border-surface-border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-400"
          />
          <span className="text-xs text-ink-muted">Bis</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="text-xs border border-surface-border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-400"
          />
          <button
            onClick={applyCustom}
            className="px-3 py-1 text-xs font-semibold text-white bg-primary-700 rounded hover:bg-primary-800"
          >
            Anwenden
          </button>
          <button
            onClick={() => setShowCustom(false)}
            className="text-xs text-ink-muted hover:text-ink"
          >
            Abbrechen
          </button>
        </div>
      )}
    </div>
  )
}
