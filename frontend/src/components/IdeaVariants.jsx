/**
 * Phase 4.2 — IdeaVariants UI-Section
 *
 * Zeigt die 3 Aufhänger-Varianten (hook/story/these) für eine Idee
 * mit Wahl-/Regenerate-Buttons. Wird in IdeaCard im expanded-Mode
 * eingebettet.
 */
import { useState, useEffect } from 'react'
import { Sparkles, RefreshCw, Check, Loader2 } from 'lucide-react'
import { listIdeaVariants, regenerateIdeaVariants, chooseIdeaVariant } from '../api'

const TYPE_META = {
  hook:  { label: 'Hook',     desc: 'provokant',  color: 'bg-rose-100 text-rose-700 border-rose-200' },
  story: { label: 'Story',    desc: 'persönlich', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  these: { label: 'These',    desc: 'sachlich',   color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
}

export default function IdeaVariants({ ideaId }) {
  const [variants, setVariants] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await listIdeaVariants(ideaId)
      setVariants(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() /* eslint-disable-next-line */ }, [ideaId])

  async function handleRegenerate() {
    setGenerating(true)
    setError(null)
    try {
      await regenerateIdeaVariants(ideaId)
      // Pollen statt blocken — Variants entstehen via Celery-Task.
      // Pragmatisch: 3s warten, dann load. Bei nicht-fertig: User klickt "Aktualisieren".
      await new Promise(r => setTimeout(r, 3000))
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  async function handleChoose(variantId) {
    setError(null)
    try {
      await chooseIdeaVariant(ideaId, variantId)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const hasVariants = variants.length > 0

  return (
    <div className="border-t border-surface-border bg-surface-50/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-ink flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" /> 3 Aufhänger
          {hasVariants && variants.find(v => v.is_chosen) && (
            <span className="ml-1 text-[10px] text-emerald-700 px-1.5 py-0.5 bg-emerald-50 rounded-full">
              ✓ ausgewählt
            </span>
          )}
        </h4>
        <button
          onClick={handleRegenerate}
          disabled={generating}
          className="flex items-center gap-1 text-[11px] text-primary-700 hover:text-primary-900 disabled:opacity-50"
        >
          {generating ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          {hasVariants ? 'Neu generieren' : 'Generieren'}
        </button>
      </div>

      {error && (
        <p className="text-[11px] text-red-700">{error}</p>
      )}

      {loading ? (
        <p className="text-xs text-ink-muted">Lade Varianten…</p>
      ) : !hasVariants ? (
        <p className="text-xs text-ink-muted">
          Noch keine Varianten generiert — klick „Generieren" für 3 Aufhänger (Hook/Story/These).
        </p>
      ) : (
        <div className="space-y-2">
          {variants.map(v => {
            const meta = TYPE_META[v.variant_type] || { label: v.variant_type, desc: '', color: 'bg-gray-100 text-gray-700 border-gray-200' }
            const ringClass = v.is_chosen ? 'ring-2 ring-primary-500' : 'hover:border-primary-300'
            return (
              <div key={v.id} className={`rounded-lg border bg-white p-3 transition-all ${ringClass}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${meta.color}`}>
                        {meta.label}
                      </span>
                      <span className="text-[10px] text-ink-muted">{meta.desc}</span>
                    </div>
                    <p className="text-sm font-medium text-ink mb-1">{v.hook_text}</p>
                    <p className="text-xs text-ink-muted line-clamp-3">{v.body_outline}</p>
                  </div>
                  <button
                    onClick={() => handleChoose(v.id)}
                    disabled={v.is_chosen}
                    className={`text-[11px] px-2.5 py-1 rounded-lg flex-shrink-0 transition-colors ${
                      v.is_chosen ? 'bg-primary-100 text-primary-700 cursor-default'
                                  : 'bg-white border border-primary-200 text-primary-700 hover:bg-primary-50'
                    }`}
                  >
                    {v.is_chosen ? (<><Check className="w-3 h-3 inline mr-0.5" />gewählt</>) : 'Wählen'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
