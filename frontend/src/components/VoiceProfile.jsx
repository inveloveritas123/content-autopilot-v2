import { useState, useEffect, useCallback } from 'react'
import { Fingerprint, RefreshCw, TrendingUp, AlertCircle, Mic, BookOpen, RotateCcw, Save, Check } from 'lucide-react'
import { getVoiceProfile, getFeedbackStats, updateVoiceProfile } from '../api'

const VOICE_DIMENSIONS = [
  { key: 'directness', label: 'Direktheit', desc: 'Klartext statt Drumherumreden', low: 'Diplomatisch', high: 'Klartext' },
  { key: 'competence', label: 'Kompetenz', desc: 'Fachlich fundiert, ohne Belehrung', low: 'Allgemein', high: 'Expertenlevel' },
  { key: 'warmth', label: 'Warmherzigkeit', desc: 'Menschlich, nahbar, auf Augenhoehe', low: 'Sachlich', high: 'Herzlich' },
  { key: 'pragmatism', label: 'Pragmatismus', desc: 'Loesungen statt Theorie', low: 'Theoretisch', high: 'Hands-on' },
  { key: 'confidence', label: 'Selbstbewusstsein', desc: 'Klare Haltung, ohne Arroganz', low: 'Zurueckhaltend', high: 'Selbstsicher' },
  { key: 'humor', label: 'Humor', desc: 'Eine Prise, nie albern', low: 'Ernst', high: 'Humorvoll' },
  { key: 'storytelling', label: 'Storytelling', desc: 'Echte Geschichten, keine Floskeln', low: 'Faktenbasiert', high: 'Geschichtenerzaehler' },
  { key: 'formality', label: 'Formalitaet', desc: 'du-Form, professionell aber locker', low: 'Locker/du', high: 'Formell/Sie' },
  { key: 'emotion', label: 'Emotion', desc: 'Leidenschaft zeigen, nicht aufsetzen', low: 'Nuechtern', high: 'Leidenschaftlich' },
  { key: 'technical_depth', label: 'Fachtiefe', desc: 'Praxis-Wissen, keine Buzzwords', low: 'Einfach', high: 'Technisch tief' },
  { key: 'call_to_action', label: 'CTA-Stil', desc: 'Klar, direkt, ohne Druck', low: 'Subtil', high: 'Direkt' },
  { key: 'authenticity', label: 'Authentizitaet', desc: 'Echt bleiben, nie kuenstlich', low: 'Poliert', high: 'Roh & echt' },
]

function DimensionSlider({ dim, value, defaultValue, onChange, onReset }) {
  const val = value ?? 5
  const isCustom = defaultValue !== undefined && Math.abs(val - defaultValue) > 0.1
  return (
    <div className="group">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink">{dim.label}</span>
          {isCustom && (
            <button onClick={onReset} className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-gray-100" title="Zuruecksetzen">
              <RotateCcw className="w-3 h-3 text-ink-muted" />
            </button>
          )}
        </div>
        <span className={`text-xs font-medium ${isCustom ? 'text-accent-600' : 'text-primary-700'}`}>{val.toFixed(1)}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-[10px] text-ink-muted w-20 text-right shrink-0">{dim.low}</span>
        <div className="flex-1 relative">
          <input
            type="range" min="0" max="10" step="0.5" value={val}
            onChange={e => onChange(parseFloat(e.target.value))}
            className="w-full h-2 rounded-full appearance-none cursor-pointer accent-primary-600
              [&::-webkit-slider-runnable-track]:bg-gradient-to-r [&::-webkit-slider-runnable-track]:from-gray-200 [&::-webkit-slider-runnable-track]:to-primary-200 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:h-2
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary-600 [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:-mt-1
              [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary-600 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white
              [&::-moz-range-track]:bg-gradient-to-r [&::-moz-range-track]:from-gray-200 [&::-moz-range-track]:to-primary-200 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:h-2"
          />
        </div>
        <span className="text-[10px] text-ink-muted w-24 shrink-0">{dim.high}</span>
      </div>
      <p className="text-[10px] text-ink-muted mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">{dim.desc}</p>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color = 'text-primary-600' }) {
  return (
    <div className="bg-white rounded-xl border border-surface-border p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color === 'text-primary-600' ? 'bg-primary-50' : color === 'text-emerald-600' ? 'bg-emerald-50' : 'bg-amber-50'}`}>
          <Icon className={`w-5 h-5 ${color}`} />
        </div>
        <div>
          <p className="text-lg font-bold text-ink">{value}</p>
          <p className="text-xs text-ink-muted">{label}</p>
        </div>
      </div>
      {sub && <p className="text-xs text-ink-light mt-2 pl-[52px]">{sub}</p>}
    </div>
  )
}

export default function VoiceProfile() {
  const [profile, setProfile] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dimensions, setDimensions] = useState({})
  const [defaults, setDefaults] = useState({})
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [p, s] = await Promise.all([getVoiceProfile(), getFeedbackStats()])
      setProfile(p)
      setStats(s)
      if (p?.dimensions) {
        setDimensions({ ...p.dimensions })
        setDefaults(p.defaults || {})
      }
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const handleChange = useCallback((key, value) => {
    setDimensions(prev => ({ ...prev, [key]: value }))
    setDirty(true)
    setSaved(false)
  }, [])

  const handleReset = useCallback((key) => {
    if (defaults[key] !== undefined) {
      setDimensions(prev => ({ ...prev, [key]: defaults[key] }))
      setDirty(true)
      setSaved(false)
    }
  }, [defaults])

  const handleResetAll = () => {
    setDimensions({ ...defaults })
    setDirty(true)
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateVoiceProfile(dimensions)
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError('Speichern fehlgeschlagen: ' + e.message)
    }
    setSaving(false)
  }

  const trendLabels = { improving: 'Wird besser', stable: 'Stabil', declining: 'Wird schlechter', no_data: 'Noch keine Daten' }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Voice-Profil...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Voice-Profil</h1>
          <p className="text-sm text-ink-light mt-0.5">Dein Schreibstil in 12 Dimensionen. Schiebe die Regler oder lass die KI lernen.</p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <>
              <button onClick={handleResetAll} className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50">
                <RotateCcw className="w-3.5 h-3.5" /> Alle zuruecksetzen
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50">
                {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? 'Speichern...' : 'Speichern'}
              </button>
            </>
          )}
          {saved && (
            <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <Check className="w-3.5 h-3.5" /> Gespeichert
            </span>
          )}
          <button onClick={loadData} className="p-2 text-ink-muted hover:text-primary-600 rounded-lg hover:bg-gray-50">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>}

      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <StatCard icon={BookOpen} label="Posts insgesamt" value={stats.total_posts} color="text-primary-600" />
          <StatCard icon={TrendingUp} label="Avg. Engagement" value={stats.avg_engagement_rate ? `${stats.avg_engagement_rate}%` : '-'} color="text-emerald-600" />
          <StatCard icon={Mic} label="Lernfortschritt" value={trendLabels[stats.improvement_trend] || 'Unbekannt'}
            sub={stats.avg_edit_distance > 0 ? `Edit-Distanz: ${stats.avg_edit_distance}` : null} color="text-amber-600" />
        </div>
      )}

      <div className="bg-white rounded-xl border border-surface-border p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Fingerprint className="w-4 h-4 text-primary-600" />
              Die 12 Voice-Dimensionen
            </h2>
            <p className="text-xs text-ink-muted mt-0.5">Schiebe die Regler um dein Profil anzupassen. Hover fuer Details.</p>
          </div>
        </div>

        {Object.keys(dimensions).length > 0 ? (
          <div className="space-y-5">
            {VOICE_DIMENSIONS.map(dim => (
              <DimensionSlider
                key={dim.key}
                dim={dim}
                value={dimensions[dim.key]}
                defaultValue={defaults[dim.key]}
                onChange={v => handleChange(dim.key, v)}
                onReset={() => handleReset(dim.key)}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <AlertCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-ink-light">Voice-Profil noch nicht erstellt.</p>
          </div>
        )}
      </div>

      {stats?.top_angles?.length > 0 && (
        <div className="mt-6 bg-white rounded-xl border border-surface-border p-6">
          <h2 className="text-sm font-semibold text-ink mb-4">Deine besten Angles</h2>
          <div className="space-y-3">
            {stats.top_angles.map((a, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-primary-50 text-primary-700 text-xs font-bold flex items-center justify-center">{i + 1}</span>
                  <span className="text-sm text-ink">{a.angle}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-ink-muted">{a.count} Posts</span>
                  <span className="text-xs font-medium text-emerald-600">{((a.avg_engagement ?? 0) * 100).toFixed(1)}% Engagement</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
