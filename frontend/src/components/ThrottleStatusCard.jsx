// AUDITED-2026-08-14 (Welle D6): Tiefen-Audit, Datei vollstaendig gelesen.
/**
 * ThrottleStatusCard — Issue 156: Pipeline-Pump-Throttle UI
 *
 * Displays:
 *  - Calls letzte Stunde: X / 200 (per tenant)
 *  - Throttled in den letzten 24h: N
 *  - Red banner when currently_throttled = true
 *
 * Mobile-first: touch targets >= 44x44px, responsive >= 375px
 */
import { useState, useEffect, useCallback } from 'react'
import { Activity, AlertTriangle, RefreshCw } from 'lucide-react'
import { getThrottleStatus } from '../api'

function UsageBar({ current, limit, label }) {
  const pct = limit > 0 ? Math.min(100, Math.round((current / limit) * 100)) : 0
  const isWarn = pct >= 80
  const isCrit = pct >= 100
  const barColor = isCrit ? 'bg-red-500' : isWarn ? 'bg-amber-400' : 'bg-primary-500'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink-muted">{label}</span>
        <span
          className={`font-semibold ${isCrit ? 'text-red-700' : isWarn ? 'text-amber-600' : 'text-ink'}`}
        >
          {current.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <div className="h-3 bg-gray-100 rounded-full overflow-hidden min-w-0">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={current}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-label={label}
        />
      </div>
    </div>
  )
}

export default function ThrottleStatusCard({ adminToken, tenantId, className = '' }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!adminToken) return
    setLoading(true)
    setError(null)
    try {
      const result = await getThrottleStatus(adminToken, tenantId || undefined)
      setData(result)
    } catch (e) {
      setError(e?.message || 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [adminToken, tenantId])

  useEffect(() => {
    load()
    // Auto-refresh every 60s
    const id = setInterval(load, 60_000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className={`bg-white rounded-xl border border-surface-border ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 pb-2">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-primary-50">
            <Activity className="w-4 h-4 text-primary-700" aria-hidden="true" />
          </div>
          <span className="font-semibold text-ink text-sm">Pipeline-Throttle</span>
        </div>
        {/* Refresh — min 44x44 touch target */}
        <button
          onClick={load}
          disabled={loading}
          aria-label="Throttle-Status aktualisieren"
          className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg
                     text-ink-muted hover:text-ink hover:bg-gray-100
                     disabled:opacity-40 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {/* Red alert banner — only when throttled */}
      {data?.currently_throttled && (
        <div
          role="alert"
          className="mx-4 mb-2 flex items-start gap-2 rounded-lg px-3 py-2
                     text-red-700 bg-red-50 border border-red-200 text-sm"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            <strong>Pipeline pausiert</strong> — Rate-Limit erreicht. Neue Calls werden erst nach
            Ablauf des Stunden-Fensters zugelassen.
          </span>
        </div>
      )}

      {/* Content */}
      <div className="p-4 pt-2 space-y-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!data && !loading && !error && (
          <p className="text-sm text-ink-muted">Kein Admin-Token konfiguriert.</p>
        )}

        {data && (
          <>
            {/* Per-Tenant Bar (only shown when tenantId provided) */}
            {tenantId && (
              <UsageBar
                current={data.tenant_count_1h}
                limit={data.tenant_limit}
                label="Calls letzte Stunde (Tenant)"
              />
            )}

            {/* Global Bar */}
            <UsageBar
              current={data.global_count_1h}
              limit={data.global_limit}
              label="Calls letzte Stunde (Global)"
            />

            {/* 24h throttle counter */}
            <div className="flex items-center justify-between pt-1 border-t border-surface-border">
              <span className="text-sm text-ink-muted">Throttled (letzte 24 h)</span>
              <span
                className={`text-sm font-semibold min-w-[44px] min-h-[44px] flex items-center justify-end
                  ${data.throttled_24h > 0 ? 'text-amber-600' : 'text-ink-muted'}`}
              >
                {data.throttled_24h}
              </span>
            </div>
          </>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center py-4">
            <RefreshCw className="w-5 h-5 animate-spin text-ink-muted" aria-hidden="true" />
          </div>
        )}
      </div>
    </div>
  )
}
