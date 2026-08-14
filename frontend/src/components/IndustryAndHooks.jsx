/**
 * Industry-Setup + Hook-Library — kombinierte Settings-Sektion (Phase 4.4 + 7.4).
 */
import { useState, useEffect } from 'react'
import { Briefcase, RefreshCw, Loader2, Sparkles, Plus, Trash2, Download } from 'lucide-react'
import { Button } from './ui/Button'
import {
  getTenantIndustry,
  setTenantIndustry,
  refreshIndustry,
  listHooks,
  importHooks,
  addManualHook,
  deleteHook,
} from '../api'

export default function IndustryAndHooks() {
  // Industry
  const [industry, setIndustry] = useState('')
  const [industryInput, setIndustryInput] = useState('')
  const [industryContext, setIndustryContext] = useState({})
  const [savingIndustry, setSavingIndustry] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  // Hooks
  const [hooks, setHooks] = useState([])
  const [newHook, setNewHook] = useState('')
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState(null)

  async function loadIndustry() {
    try {
      const d = await getTenantIndustry()
      setIndustry(d.industry || '')
      setIndustryInput(d.industry || '')
      setIndustryContext(d.industry_context || {})
    } catch (e) {
      setError(e.message)
    }
  }
  async function loadHooks() {
    try {
      const d = await listHooks({ limit: 30, sort: 'performance' })
      setHooks(Array.isArray(d) ? d : [])
    } catch (e) {
      setError(e.message)
    }
  }
  useEffect(() => {
    loadIndustry()
    loadHooks()
  }, [])

  async function handleSetIndustry(e) {
    e?.preventDefault()
    if (!industryInput.trim()) return
    setSavingIndustry(true)
    setError(null)
    try {
      await setTenantIndustry(industryInput.trim())
      setTimeout(() => loadIndustry(), 5000) // nach Refresh-Task
      await loadIndustry()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingIndustry(false)
    }
  }
  async function handleRefreshIndustry() {
    setRefreshing(true)
    try {
      await refreshIndustry()
      setTimeout(() => loadIndustry(), 5000)
    } catch (e) {
      setError(e.message)
    } finally {
      setRefreshing(false)
    }
  }
  async function handleImportHooks() {
    setImporting(true)
    try {
      const r = await importHooks(20)
      await loadHooks()
      if (r.imported === 0) setError(`Keine neuen Hooks zum Importieren (${r.scanned} gescannt).`)
    } catch (e) {
      setError(e.message)
    } finally {
      setImporting(false)
    }
  }
  async function handleAddManualHook(e) {
    e?.preventDefault()
    if (!newHook.trim() || newHook.trim().length < 5) return
    try {
      await addManualHook(newHook.trim())
      setNewHook('')
      await loadHooks()
    } catch (e) {
      setError(e.message)
    }
  }
  async function handleDeleteHook(id) {
    try {
      await deleteHook(id)
      await loadHooks()
    } catch (e) {
      setError(e.message)
    }
  }

  const themen = industryContext.top_themen || []
  const trigger = industryContext.trigger_woerter || []
  const fragen = industryContext.typische_kundenfragen || []

  return (
    <div className="space-y-6">
      {/* Industry */}
      <div className="bg-white rounded-xl border border-surface-border p-5">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-primary-600" />
          Branche & Industry-Profil
          <span className="ml-auto text-[10px] text-ink-muted font-normal">(Phase 4.4)</span>
        </h3>
        <p className="text-xs text-ink-muted mb-3">
          Setze die Branche, damit Ideas branchen-spezifischen Relevanz-Boost bekommen (bis +2.5
          Punkte bei 5+ Trigger-Wort-Treffern).
        </p>
        <form onSubmit={handleSetIndustry} className="flex gap-2 mb-4">
          <input
            type="text"
            value={industryInput}
            onChange={(e) => setIndustryInput(e.target.value)}
            placeholder="z.B. Coaching für Selbstständige im Mittelstand"
            className="flex-1 px-3 py-2 min-h-[44px] text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <Button type="submit" disabled={savingIndustry || !industryInput.trim()}>
            {savingIndustry ? 'Speichere…' : 'Speichern'}
          </Button>
          {industry && (
            <button
              type="button"
              onClick={handleRefreshIndustry}
              disabled={refreshing}
              className="px-3 text-xs text-primary-700 hover:text-primary-900 disabled:opacity-50 flex items-center gap-1"
              title="Industry-Context neu generieren"
            >
              {refreshing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
              Neu generieren
            </button>
          )}
        </form>

        {industry && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted font-semibold mb-1.5">
                Top-Themen
              </p>
              <ul className="space-y-1">
                {themen.length ? (
                  themen.slice(0, 6).map((t, i) => (
                    <li key={i} className="text-xs text-ink">
                      • {t}
                    </li>
                  ))
                ) : (
                  <li className="text-xs text-ink-muted">— wird generiert —</li>
                )}
              </ul>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted font-semibold mb-1.5">
                Trigger-Wörter
              </p>
              <div className="flex flex-wrap gap-1">
                {trigger.length ? (
                  trigger.map((w, i) => (
                    <span
                      key={i}
                      className="text-[11px] px-1.5 py-0.5 bg-primary-50 text-primary-700 rounded-full"
                    >
                      {w}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-ink-muted">— wird generiert —</span>
                )}
              </div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted font-semibold mb-1.5">
                Typische Kundenfragen
              </p>
              <ul className="space-y-1">
                {fragen.length ? (
                  fragen.slice(0, 5).map((q, i) => (
                    <li key={i} className="text-xs text-ink-muted italic">
                      „{q}"
                    </li>
                  ))
                ) : (
                  <li className="text-xs text-ink-muted">— wird generiert —</li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Hooks */}
      <div className="bg-white rounded-xl border border-surface-border p-5">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-accent-500" />
          Hook-Bibliothek
          <span className="ml-auto text-[10px] text-ink-muted font-normal">
            (Phase 7.4 — {hooks.length} Hooks)
          </span>
        </h3>
        <p className="text-xs text-ink-muted mb-3">
          Sammlung gut performter Hooks. P12 kann sie als Allow-List beim Generieren nutzen.
        </p>
        <div className="flex gap-2 mb-3">
          <button
            onClick={handleImportHooks}
            disabled={importing}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-primary-50 hover:bg-primary-100 text-primary-700 border border-primary-200 rounded-lg disabled:opacity-50"
          >
            {importing ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Download className="w-3 h-3" />
            )}
            Aus Posts importieren
          </button>
        </div>

        <form onSubmit={handleAddManualHook} className="flex gap-2 mb-4">
          <input
            type="text"
            value={newHook}
            onChange={(e) => setNewHook(e.target.value)}
            placeholder={
              'Neuer Hook (z.B. „Vertrauen entsteht in 5 Minuten — nicht in 5 Monaten.")'
            }
            className="flex-1 px-3 py-2 min-h-[44px] text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <Button type="submit" disabled={!newHook.trim() || newHook.trim().length < 5}>
            <Plus className="w-3.5 h-3.5 mr-1 inline" />
            Hinzufügen
          </Button>
        </form>

        {error && <p className="text-xs text-status-fehler-text mb-2">{error}</p>}

        <div className="space-y-1.5 max-h-96 overflow-y-auto">
          {hooks.length === 0 ? (
            <p className="text-xs text-ink-muted">
              Noch keine Hooks. Importiere aus deinen Posts oder füge manuell hinzu.
            </p>
          ) : (
            hooks.map((h) => (
              <div
                key={h.id}
                className="flex items-start justify-between gap-2 p-2 bg-surface-bg rounded-lg group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-ink leading-snug">{h.hook_text}</p>
                  <p className="text-[10px] text-ink-muted mt-0.5">
                    [{h.hook_type}] · perf={h.performance_score.toFixed(2)} · used {h.used_count}×
                  </p>
                </div>
                <button
                  onClick={() => handleDeleteHook(h.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-status-fehler-text hover:bg-status-fehler-bg"
                  title="Löschen"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
