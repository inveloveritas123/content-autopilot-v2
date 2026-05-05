import { useState, useEffect, useMemo } from 'react'
import {
  DollarSign, BarChart3, Zap, Download, RefreshCw, TrendingUp, Cpu, Activity, AlertTriangle, Clock, Shield
} from 'lucide-react'
import {
  getLLMAnalyticsSummary,
  getLLMAnalyticsByTask,
  getLLMAnalyticsByModel,
  getLLMAnalyticsByDay,
  getLLMAnalyticsCSVUrl,
  getLLMAnalyticsByHour,
  getLLMAnalyticsAnomaly,
  getContentByCategory,
  getCostTrend,
  getCacheHitRate,
  getRunawayDetection,
} from '../api'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'

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

// -----------------------------------------------------------------------
// #155 Trends & Cache Sub-Components
// -----------------------------------------------------------------------

const HEATMAP_DAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']

function HeatmapCell({ count, alert }) {
  const intensity = Math.min(1, (count || 0) / 500)
  const bg = alert
    ? 'bg-red-500'
    : intensity > 0.7 ? 'bg-orange-400' : intensity > 0.3 ? 'bg-amber-300' : intensity > 0 ? 'bg-emerald-200' : 'bg-gray-100'
  return (
    <div
      className={`w-6 h-6 rounded-sm ${bg} flex items-center justify-center`}
      title={`${count} Calls${alert ? ' — ALERT >500' : ''}`}
    />
  )
}

function TrendsCacheTab({ loading, error, costTrend, cacheHitRate, runaway, onReload }) {
  if (loading) {
    return (
      <div className="py-12 text-center text-ink-muted text-sm">Lade Trend-Daten...</div>
    )
  }
  if (error) {
    return (
      <div className="py-8 flex flex-col items-center gap-3">
        <p className="text-red-600 text-sm">{error}</p>
        <button
          onClick={onReload}
          className="min-h-[44px] px-4 py-2 text-xs bg-surface-100 border border-surface-border rounded-lg hover:bg-gray-50"
        >
          Erneut laden
        </button>
      </div>
    )
  }

  // --- Cache-Hit-Rate KPI Card ---
  const avg7d = cacheHitRate?.avg_7d
  const cacheAlert = cacheHitRate?.alert === true

  // --- Cost-Trend Recharts data ---
  const trendDays = costTrend?.days || []
  const deployMarkers = costTrend?.deploy_markers || []

  // Flatten to recharts format: [{date, total_cost_cents, total_input_tokens, total_output_tokens}]
  const chartData = trendDays.map(d => ({
    date: d.date,
    cost: d.total?.total_cost_cents ?? 0,
    input: d.total?.total_input_tokens ?? 0,
    output: d.total?.total_output_tokens ?? 0,
  }))

  // --- Top Killers ---
  const topKillers = runaway?.top_killers || []

  // --- Heatmap ---
  const heatmapRaw = runaway?.heatmap || []
  // Build 7x24 grid keyed by (day_of_week, hour_of_day)
  const heatmapGrid = {}
  for (const cell of heatmapRaw) {
    const key = `${cell.day_of_week}_${cell.hour_of_day}`
    heatmapGrid[key] = cell
  }

  async function downloadCSV(endpoint, filename) {
    const key = localStorage.getItem('apiKey') || ''
    try {
      const res = await fetch(`/api/analytics/${endpoint}?format=csv`, {
        headers: { 'X-API-Key': key },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('CSV-Download fehlgeschlagen:', err)
    }
  }

  const hasTrendData = chartData.length > 0

  return (
    <div className="space-y-6 pt-2">
      {/* 1. Cache-Hit-Rate KPI */}
      <div className={`rounded-xl border p-4 ${cacheAlert ? 'bg-amber-50 border-amber-300' : 'bg-white border-surface-border'}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <Zap className="w-4 h-4" /> Cache-Hit-Rate (7-Tage-Avg)
          </h3>
          <button
            onClick={() => downloadCSV('cache-hit-rate', 'cache-hit-rate.csv')}
            className="text-xs px-3 py-2 min-h-[44px] flex items-center bg-surface-100 border border-surface-border rounded-lg hover:bg-gray-50"
          >
            <Download className="w-3 h-3 mr-1" /> CSV
          </button>
        </div>
        {avg7d === null || avg7d === undefined ? (
          <p className="text-sm text-ink-muted">Noch keine Daten (mindestens 7 Tage nötig).</p>
        ) : (
          <div className="flex items-baseline gap-3">
            <span className={`text-4xl font-bold ${cacheAlert ? 'text-amber-700' : 'text-emerald-600'}`}>
              {(avg7d * 100).toFixed(1)}%
            </span>
            <span className="text-xs text-ink-muted">7-Tage-Durchschnitt</span>
          </div>
        )}
        {cacheAlert && (
          <div className="mt-2 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 font-medium">
              Cache-Hit-Rate unter 30% — #127 Auto-Caching prüfen!
            </p>
          </div>
        )}
      </div>

      {/* 2. Cost-Trend Line Chart */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <TrendingUp className="w-4 h-4" /> Cost-Trend (30 Tage, Cent)
          </h3>
          <button
            onClick={() => downloadCSV('cost-trend', 'cost-trend.csv')}
            className="text-xs px-3 py-2 min-h-[44px] flex items-center bg-surface-100 border border-surface-border rounded-lg hover:bg-gray-50"
          >
            <Download className="w-3 h-3 mr-1" /> CSV
          </button>
        </div>
        {!hasTrendData ? (
          <p className="text-sm text-ink-muted text-center py-6">Keine Daten in den letzten 30 Tagen.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 10 }} width={40} />
              <Tooltip formatter={(v) => [`${v}¢`, 'Cost']} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              {deployMarkers.map(m => (
                <ReferenceLine
                  key={m.label}
                  x={m.date.slice(0, 10)}
                  stroke="#6366f1"
                  strokeDasharray="4 2"
                  label={{ value: m.label, position: 'top', fontSize: 9, fill: '#6366f1' }}
                />
              ))}
              <Line type="monotone" dataKey="cost" stroke="#f59e0b" strokeWidth={2} dot={false} name="Cost (¢)" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* 3. Token-Volumen-Trend */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2 mb-4">
          <BarChart3 className="w-4 h-4" /> Token-Volumen-Trend (30 Tage)
        </h3>
        {!hasTrendData ? (
          <p className="text-sm text-ink-muted text-center py-6">Keine Daten.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={v => fmtTokens(v)} />
              <Tooltip formatter={(v) => [fmtTokens(v), '']} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              {deployMarkers.map(m => (
                <ReferenceLine
                  key={m.label}
                  x={m.date.slice(0, 10)}
                  stroke="#6366f1"
                  strokeDasharray="4 2"
                />
              ))}
              <Line type="monotone" dataKey="input" stroke="#3b82f6" strokeWidth={2} dot={false} name="Input Tokens" />
              <Line type="monotone" dataKey="output" stroke="#10b981" strokeWidth={2} dot={false} name="Output Tokens" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* 4. Top-N Token-Killer */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Top-20 Token-Killer (7 Tage)
          </h3>
          <button
            onClick={() => downloadCSV('runaway-detection', 'runaway-detection.csv')}
            className="text-xs px-3 py-2 min-h-[44px] flex items-center bg-surface-100 border border-surface-border rounded-lg hover:bg-gray-50"
          >
            <Download className="w-3 h-3 mr-1" /> CSV
          </button>
        </div>
        {topKillers.length === 0 ? (
          <p className="text-sm text-ink-muted text-center py-4">Keine Daten.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left min-w-[400px]">
              <thead>
                <tr className="border-b border-surface-border text-[10px] text-ink-muted uppercase tracking-wide">
                  <th className="pb-2 pr-3">Task</th>
                  <th className="pb-2 pr-3">Modell</th>
                  <th className="pb-2 pr-3 text-right">Kosten (¢)</th>
                  <th className="pb-2 text-right">Calls</th>
                </tr>
              </thead>
              <tbody>
                {topKillers.map((k, i) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-1.5 pr-3 font-medium text-ink">{k.task_name}</td>
                    <td className="py-1.5 pr-3 text-ink-muted font-mono">{k.model}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{k.total_cost_cents.toFixed(2)}</td>
                    <td className="py-1.5 text-right text-ink-muted">{k.total_calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 5. Calls-Heatmap: Tenant x Hour-of-Day */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2 mb-3">
          <Clock className="w-4 h-4" /> Calls-Heatmap: Tag x Stunde (7 Tage)
          <span className="text-[10px] font-normal text-ink-muted">rot = &gt;500/h</span>
        </h3>
        {heatmapRaw.length === 0 ? (
          <p className="text-sm text-ink-muted text-center py-4">Keine Daten.</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="flex gap-1 min-w-[560px]">
              {/* Y-Achse: Wochentage */}
              <div className="flex flex-col gap-1 pt-6">
                {HEATMAP_DAYS.map(d => (
                  <div key={d} className="h-6 text-[10px] text-ink-muted flex items-center w-7 justify-end pr-1">{d}</div>
                ))}
              </div>
              {/* Grid: 24 Spalten (Stunden) x 7 Zeilen (Tage) */}
              <div className="flex flex-col gap-1">
                {/* Header: Stunden */}
                <div className="flex gap-1 mb-1">
                  {Array.from({ length: 24 }, (_, h) => (
                    <div key={h} className="w-6 text-[8px] text-ink-muted text-center">{h}</div>
                  ))}
                </div>
                {HEATMAP_DAYS.map((_, dow) => (
                  <div key={dow} className="flex gap-1">
                    {Array.from({ length: 24 }, (_, hour) => {
                      const key = `${dow}_${hour}`
                      const cell = heatmapGrid[key]
                      return (
                        <HeatmapCell
                          key={hour}
                          count={cell?.call_count || 0}
                          alert={cell?.alert || false}
                        />
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// -----------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------

export default function LLMAnalytics() {
  const [summary, setSummary] = useState(null)
  const [byTask, setByTask] = useState([])
  const [byModel, setByModel] = useState([])
  const [byDay, setByDay] = useState([])
  const [byHour, setByHour] = useState([])
  const [byCategory, setByCategory] = useState([])
  const [anomaly, setAnomaly] = useState(null)
  // #128 B-5: Provider-Reconciliation (manuelle Requesty-Side-Werte)
  const [manualRequestyCost, setManualRequestyCost] = useState(() => localStorage.getItem('reconcile_requesty_usd') || '')
  const [manualRequestyTokens, setManualRequestyTokens] = useState(() => localStorage.getItem('reconcile_requesty_tokens') || '')
  const [manualReconcileDate, setManualReconcileDate] = useState(() => localStorage.getItem('reconcile_date') || toYYYYMMDD(new Date()))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [dateRange, setDateRange] = useState(() => {
    const to = new Date()
    const from = new Date()
    from.setDate(from.getDate() - 6)
    return { from: toYYYYMMDD(from), to: toYYYYMMDD(to) }
  })
  const [activeTab, setActiveTab] = useState('task')
  // #155 Trend & Cache
  const [costTrend, setCostTrend] = useState(null)
  const [cacheHitRate, setCacheHitRate] = useState(null)
  const [runaway, setRunaway] = useState(null)
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError, setTrendError] = useState(null)

  const apiParams = useMemo(() => ({
    from_date: dateRange.from || undefined,
    to_date: dateRange.to || undefined,
  }), [dateRange.from, dateRange.to])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [sum, task, model, day, hourly, anom, categories] = await Promise.all([
        getLLMAnalyticsSummary(apiParams),
        getLLMAnalyticsByTask(apiParams),
        getLLMAnalyticsByModel(apiParams),
        getLLMAnalyticsByDay(apiParams),
        getLLMAnalyticsByHour({ hours: 24 }).catch(() => []),
        getLLMAnalyticsAnomaly({ threshold_factor: 2.0 }).catch(() => null),
        getContentByCategory({ days: 30 }).catch(() => []),
      ])
      setSummary(sum)
      setByTask(Array.isArray(task) ? task : [])
      setByModel(Array.isArray(model) ? model : [])
      setByDay(Array.isArray(day) ? day : [])
      setByHour(Array.isArray(hourly) ? hourly : [])
      setAnomaly(anom)
      setByCategory(Array.isArray(categories) ? categories : [])
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

  async function loadTrendData() {
    setTrendLoading(true)
    setTrendError(null)
    try {
      const [trend, cache, rwd] = await Promise.all([
        getCostTrend({ days: 30 }),
        getCacheHitRate({ days: 30 }),
        getRunawayDetection({}),
      ])
      setCostTrend(trend)
      setCacheHitRate(cache)
      setRunaway(rwd)
    } catch (e) {
      setTrendError(e.message)
    } finally {
      setTrendLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'trends') {
      loadTrendData()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  useEffect(() => {
    if (manualRequestyCost) localStorage.setItem('reconcile_requesty_usd', manualRequestyCost)
    if (manualRequestyTokens) localStorage.setItem('reconcile_requesty_tokens', manualRequestyTokens)
    if (manualReconcileDate) localStorage.setItem('reconcile_date', manualReconcileDate)
  }, [manualRequestyCost, manualRequestyTokens, manualReconcileDate])

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
  const maxHourCost = useMemo(() => Math.max(1, ...byHour.map(r => r.total_cost_cents || 0)), [byHour])

  const tabs = [
    { id: 'task', label: 'Nach Task', icon: TrendingUp },
    { id: 'model', label: 'Nach Modell', icon: Cpu },
    { id: 'day', label: 'Nach Tag', icon: BarChart3 },
    { id: 'trends', label: 'Trends & Cache', icon: Shield },
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
              className="px-3 py-1.5 min-h-[44px] text-xs bg-surface-100 hover:bg-primary-50 hover:text-primary-700 text-ink rounded-lg border border-surface-border transition-colors"
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

      {/* #128 E: Anomalie-Banner (Cost-Spike-Detector) */}
      {anomaly?.anomaly && (
        <div className="bg-red-50 border-2 border-red-300 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-900">
              Cost-Spike erkannt — aktuelle Stunde {(anomaly.factor || 0).toFixed(1)}× höher als Median
            </p>
            <p className="text-xs text-red-700 mt-0.5">
              Aktuell: ${(anomaly.current_hour_cost_cents / 100).toFixed(4)} · Median 24h: ${(anomaly.median_24h_cost_cents / 100).toFixed(4)} · Schwelle: {anomaly.threshold_factor}×
            </p>
            <p className="text-[11px] text-red-600 mt-1">
              Verdacht auf Burst (z.B. Cron-Job-Schleife) — bitte Logs / by-task prüfen.
            </p>
          </div>
        </div>
      )}

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

          {activeTab === 'trends' && (
            <TrendsCacheTab
              loading={trendLoading}
              error={trendError}
              costTrend={costTrend}
              cacheHitRate={cacheHitRate}
              runaway={runaway}
              onReload={loadTrendData}
            />
          )}
        </div>
      </div>

      {/* #145 Phase 4.1: Kategorie-Verteilung (letzte 30 Tage) */}
      {byCategory.length > 0 && (
        <div className="bg-white rounded-xl border border-surface-border p-4">
          <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> Posts nach Kategorie (30 Tage)
          </h3>
          <div className="space-y-2">
            {(() => {
              const max = Math.max(1, ...byCategory.map(r => r.count || 0))
              const colors = {
                news: 'bg-blue-500', persoenlich: 'bg-amber-500',
                trust: 'bg-emerald-500', praxis: 'bg-violet-500',
                unkategorisiert: 'bg-gray-400',
              }
              const labels = {
                news: 'News', persoenlich: 'Persönlich',
                trust: 'Trust', praxis: 'Praxis',
                unkategorisiert: 'Unkategorisiert',
              }
              return byCategory.map(r => (
                <HBar
                  key={r.category}
                  label={labels[r.category] || r.category}
                  value={r.count || 0}
                  max={max}
                  sub={`${r.count} Posts`}
                  color={colors[r.category] || 'bg-gray-400'}
                />
              ))
            })()}
          </div>
        </div>
      )}

      {/* #128 D: Stündliche Cost-Verteilung (Cost-Spike-Debug) */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Clock className="w-4 h-4" /> Stündlich (letzte 24h)
        </h3>
        {byHour.length === 0 ? (
          <p className="text-xs text-ink-muted">Keine Daten in den letzten 24h</p>
        ) : (
          <div className="space-y-1">
            {byHour.map(r => {
              const t = r.hour ? new Date(r.hour) : null
              const label = t ? t.toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : ''
              return (
                <HBar
                  key={r.hour}
                  label={label}
                  value={r.total_cost_cents || 0}
                  max={maxHourCost}
                  sub={`${r.calls || 0} calls · ${fmtTokens(r.total_tokens || 0)} Tokens`}
                  color="bg-violet-500"
                />
              )
            })}
          </div>
        )}
      </div>

      {/* #128 B-5: Provider-Reconciliation — intern vs Requesty.ai-Dashboard */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4" /> Provider-Vergleich
          <span className="text-[11px] font-normal text-ink-muted">— Intern vs Requesty.ai-Dashboard</span>
        </h3>
        <p className="text-[11px] text-ink-muted mb-3">
          Trage hier die Werte aus deinem Requesty.ai-Dashboard ein, um Abweichungen zu erkennen.
          Eingabe wird lokal im Browser gespeichert (kein Server).
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Datum</label>
            <input
              type="date"
              value={manualReconcileDate}
              onChange={e => setManualReconcileDate(e.target.value)}
              className="w-full text-xs border border-surface-border rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Cost laut Requesty (USD)</label>
            <input
              type="number"
              step="0.001"
              min="0"
              value={manualRequestyCost}
              onChange={e => setManualRequestyCost(e.target.value)}
              placeholder="z.B. 7.42"
              className="w-full text-xs border border-surface-border rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Tokens laut Requesty</label>
            <input
              type="number"
              step="1"
              min="0"
              value={manualRequestyTokens}
              onChange={e => setManualRequestyTokens(e.target.value)}
              placeholder="z.B. 1234567"
              className="w-full text-xs border border-surface-border rounded-lg px-2 py-1.5"
            />
          </div>
        </div>

        {/* Diff-Tabelle */}
        {(() => {
          const dayRow = byDay.find(d => d.day === manualReconcileDate || (d.day || '').slice(0, 10) === manualReconcileDate)
          const internCostUsd = dayRow ? (dayRow.total_cost_cents / 100) : 0
          const internTokens = dayRow ? (dayRow.total_tokens || 0) : 0
          const reqCostUsd = parseFloat(manualRequestyCost || '0') || 0
          const reqTokens = parseFloat(manualRequestyTokens || '0') || 0
          const costDiff = reqCostUsd - internCostUsd
          const tokenDiff = reqTokens - internTokens
          const costDiffPct = internCostUsd > 0 ? (costDiff / internCostUsd) * 100 : null
          const significant = costDiffPct !== null && Math.abs(costDiffPct) > 10
          if (!manualRequestyCost && !manualRequestyTokens && !dayRow) return null
          return (
            <div className={`rounded-lg p-3 text-xs ${significant ? 'bg-amber-50 border border-amber-200' : 'bg-gray-50 border border-gray-200'}`}>
              <table className="w-full text-left">
                <thead className="text-[10px] text-ink-muted uppercase tracking-wide">
                  <tr>
                    <th className="pb-1">Metrik</th>
                    <th className="pb-1 text-right">Intern (uns)</th>
                    <th className="pb-1 text-right">Requesty</th>
                    <th className="pb-1 text-right">Diff</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  <tr>
                    <td className="py-1">Cost (USD)</td>
                    <td className="py-1 text-right">${internCostUsd.toFixed(4)}</td>
                    <td className="py-1 text-right">${reqCostUsd.toFixed(4)}</td>
                    <td className={`py-1 text-right ${significant ? 'text-amber-700 font-semibold' : 'text-ink-muted'}`}>
                      {costDiff >= 0 ? '+' : ''}{costDiff.toFixed(4)}
                      {costDiffPct !== null ? ` (${costDiffPct >= 0 ? '+' : ''}${costDiffPct.toFixed(1)}%)` : ''}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1">Tokens</td>
                    <td className="py-1 text-right">{fmtTokens(internTokens)}</td>
                    <td className="py-1 text-right">{fmtTokens(reqTokens)}</td>
                    <td className="py-1 text-right text-ink-muted">
                      {tokenDiff >= 0 ? '+' : ''}{fmtTokens(Math.abs(tokenDiff))}
                    </td>
                  </tr>
                </tbody>
              </table>
              {significant && (
                <p className="mt-2 text-[11px] text-amber-700">
                  ⚠ Abweichung &gt; 10% — bitte Requesty.ai-Dashboard prüfen ggf. Cache-Tracking-Drift.
                </p>
              )}
            </div>
          )
        })()}
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
