import { useState, useEffect, useMemo } from 'react'
import {
  DollarSign, BarChart3, Zap, Download, RefreshCw, TrendingUp, Cpu, Activity
} from 'lucide-react'
import {
  getLLMAnalyticsSummary,
  getLLMAnalyticsByTask,
  getLLMAnalyticsByModel,
  getLLMAnalyticsByDay,
  getLLMAnalyticsCSVUrl,
} from '../api'

function fmtTokens(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(0) + 'K'
  return String(n)
}

function toYYYYMMDD(date) {
  return date.toISOString().slice(0, 10)
}

function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <div className="bg-white rounded-xl border border-surface-border p-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-primary-50">
          <Icon className="w-4 h-4 text-primary-700" />
        </div>
        <div>
          <p className="text-2xl font-bold text-ink leading-none">{value ?? '—'}</p>
          <p className="text-xs text-ink-muted mt-0.5">{label}</p>
        </div>
      </div>
      {sub && <p className="text-[11px] text-ink-light mt-2 pl-12">{sub}</p>}
    </div>
  )
}

function HBar({ label, value, max, sub, color = 'bg-primary-500' }) {
  const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="w-36 text-xs text-ink-muted text-right shrink-0 truncate" title={label}>{label}</span>
      <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ink font-medium w-20 text-right shrink-0">{sub}</span>
    </div>
  )
}

export default function LLMAnalytics() {
  const [summary, setSummary] = useState(null)
  const [byTask, setByTask] = useState([])
  const [byModel, setByModel] = useState([])
  const [byDay, setByDay] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [dateRange, setDateRange] = useState(() => {
    const to = new Date()
    const from = new Date()
    from.setDate(from.getDate() - 6)
    return { from: toYYYYMMDD(from), to: toYYYYMMDD(to) }
  })
  const [activeTab, setActiveTab] = useState('task')

  const apiParams = useMemo(() => ({
    from_date: dateRange.from || undefined,
    to_date: dateRange.to || undefined,
  }), [dateRange.from, dateRange.to])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [sum, task, model, day] = await Promise.all([
        getLLMAnalyticsSummary(apiParams),
        getLLMAnalyticsByTask(apiParams),
        getLLMAnalyticsByModel(apiParams),
        getLLMAnalyticsByDay(apiParams),
      ])
      setSummary(sum)
      setByTask(Array.isArray(task) ? task : [])
      setByModel(Array.isArray(model) ? model : [])
      setByDay(Array.isArray(day) ? day : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange])

  function applyPreset(days) {
    const to = new Date()
    const from = new Date()
    if (days === 0) {
      // Heute
      setDateRange({ from: toYYYYMMDD(to), to: toYYYYMMDD(to) })
    } else if (days === -1) {
      // Gestern
      const yesterday = new Date()
      yesterday.setDate(yesterday.getDate() - 1)
      setDateRange({ from: toYYYYMMDD(yesterday), to: toYYYYMMDD(yesterday) })
    } else {
      from.setDate(from.getDate() - (days - 1))
      setDateRange({ from: toYYYYMMDD(from), to: toYYYYMMDD(to) })
    }
  }

  const maxTaskCost = useMemo(() => Math.max(1, ...byTask.map(r => r.total_cost_cents || 0)), [byTask])
  const maxModelCost = useMemo(() => Math.max(1, ...byModel.map(r => r.total_cost_cents || 0)), [byModel])
  const maxDayCost = useMemo(() => Math.max(1, ...byDay.map(r => r.total_cost_cents || 0)), [byDay])

  const tabs = [
    { id: 'task', label: 'Nach Task', icon: TrendingUp },
    { id: 'model', label: 'Nach Modell', icon: Cpu },
    { id: 'day', label: 'Nach Tag', icon: BarChart3 },
  ]

  const presets = [
    { label: 'Heute', days: 0 },
    { label: 'Gestern', days: -1 },
    { label: '7 Tage', days: 7 },
    { label: '30 Tage', days: 30 },
  ]

  if (loading) {
    return <div className="p-6 text-ink-muted">Lade Daten...</div>
  }

  if (error) {
    return <div className="text-red-600 p-4">{error}</div>
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">LLM Cost Analytics</h1>
          <p className="text-sm text-ink-muted mt-0.5">Kosten und Token-Verbrauch nach Zeitraum</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {presets.map(p => (
            <button
              key={p.label}
              onClick={() => applyPreset(p.days)}
              className="px-3 py-1.5 text-xs bg-surface-100 hover:bg-primary-50 hover:text-primary-700 text-ink rounded-lg border border-surface-border transition-colors"
            >
              {p.label}
            </button>
          ))}
          <input
            type="date"
            value={dateRange.from}
            onChange={e => setDateRange(r => ({ ...r, from: e.target.value }))}
            className="text-xs border border-surface-border rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <span className="text-xs text-ink-muted">bis</span>
          <input
            type="date"
            value={dateRange.to}
            onChange={e => setDateRange(r => ({ ...r, to: e.target.value }))}
            className="text-xs border border-surface-border rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <button
            onClick={loadData}
            className="p-1.5 rounded-lg border border-surface-border hover:bg-gray-50 transition-colors"
            title="Aktualisieren"
          >
            <RefreshCw className="w-4 h-4 text-ink-muted" />
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={DollarSign}
          label="Gesamtkosten"
          value={`${((summary?.total_cost_cents || 0) / 100).toFixed(4)} €`}
          sub={`${((summary?.total_cost_cents || 0) / 100).toFixed(6)} USD-Cent-Basis`}
        />
        <StatCard
          icon={Activity}
          label="API-Calls"
          value={summary?.total_calls ?? 0}
        />
        <StatCard
          icon={Zap}
          label="Tokens (In+Out)"
          value={fmtTokens((summary?.total_input_tokens || 0) + (summary?.total_output_tokens || 0))}
          sub={`${fmtTokens(summary?.total_input_tokens)} in / ${fmtTokens(summary?.total_output_tokens)} out`}
        />
        <StatCard
          icon={BarChart3}
          label="Cache-Hit-Rate"
          value={`${Math.round((summary?.cache_hit_rate || 0) * 100)}%`}
          sub={`${fmtTokens(summary?.total_cache_read_tokens)} cached`}
        />
      </div>

      {/* Tab Navigation + Content */}
      <div className="bg-white rounded-xl border border-surface-border overflow-hidden">
        <div className="flex border-b border-surface-border">
          {tabs.map(tab => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'border-primary-700 text-primary-700 bg-primary-50'
                    : 'border-transparent text-ink-muted hover:text-ink hover:bg-gray-50'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            )
          })}
        </div>

        <div className="p-5 space-y-1">
          {activeTab === 'task' && (
            byTask.length === 0
              ? <p className="text-sm text-ink-muted py-4 text-center">Keine Daten im gewaehlten Zeitraum.</p>
              : byTask.map(r => (
                <HBar
                  key={r.task_type}
                  label={r.task_type}
                  value={r.total_cost_cents || 0}
                  max={maxTaskCost}
                  sub={`${((r.total_cost_cents || 0) / 100).toFixed(4)}€`}
                />
              ))
          )}

          {activeTab === 'model' && (
            byModel.length === 0
              ? <p className="text-sm text-ink-muted py-4 text-center">Keine Daten im gewaehlten Zeitraum.</p>
              : byModel.map(r => (
                <div key={r.model}>
                  <HBar
                    label={r.model}
                    value={r.total_cost_cents || 0}
                    max={maxModelCost}
                    sub={`${((r.total_cost_cents || 0) / 100).toFixed(4)}€`}
                    color="bg-primary-500"
                  />
                  {r.cache_hit_rate != null && (
                    <HBar
                      label=""
                      value={r.cache_hit_rate}
                      max={1}
                      sub={`Cache ${Math.round(r.cache_hit_rate * 100)}%`}
                      color="bg-emerald-400"
                    />
                  )}
                </div>
              ))
          )}

          {activeTab === 'day' && (
            byDay.length === 0
              ? <p className="text-sm text-ink-muted py-4 text-center">Keine Daten im gewaehlten Zeitraum.</p>
              : byDay.map(r => (
                <HBar
                  key={r.date}
                  label={r.date}
                  value={r.total_cost_cents || 0}
                  max={maxDayCost}
                  sub={`${r.calls || 0} calls`}
                  color="bg-accent-500"
                />
              ))
          )}
        </div>
      </div>

      {/* CSV Export */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Download className="w-4 h-4" /> CSV-Export
        </h3>
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Raw (alle Calls)', agg: undefined },
            { label: 'Nach Task', agg: 'task' },
            { label: 'Nach Modell', agg: 'model' },
            { label: 'Nach Tag', agg: 'day' },
          ].map(({ label, agg }) => (
            <a
              key={label}
              href={getLLMAnalyticsCSVUrl({
                from_date: dateRange.from || undefined,
                to_date: dateRange.to || undefined,
                aggregate: agg,
              })}
              download
              className="px-3 py-1.5 text-xs bg-surface-100 hover:bg-surface-200 text-ink rounded-lg border border-surface-border transition-colors"
            >
              {label} ↓
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}
