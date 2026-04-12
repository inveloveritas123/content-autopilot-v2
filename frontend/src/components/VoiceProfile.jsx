import { useState, useEffect } from 'react'
import { Fingerprint, RefreshCw, TrendingUp, AlertCircle, Mic, BookOpen } from 'lucide-react'
import { getVoiceProfile, getFeedbackStats } from '../api'

const VOICE_DIMENSIONS = [
  { key: 'directness', label: 'Direktheit', desc: 'Klartext statt Drumherumreden' },
  { key: 'competence', label: 'Kompetenz', desc: 'Fachlich fundiert, ohne Belehrung' },
  { key: 'warmth', label: 'Warmherzigkeit', desc: 'Menschlich, nahbar, auf Augenhoehe' },
  { key: 'pragmatism', label: 'Pragmatismus', desc: 'Loesungen statt Theorie' },
  { key: 'confidence', label: 'Selbstbewusstsein', desc: 'Klare Haltung, ohne Arroganz' },
  { key: 'humor', label: 'Humor', desc: 'Eine Prise, nie albern' },
  { key: 'storytelling', label: 'Storytelling', desc: 'Echte Geschichten, keine Floskeln' },
  { key: 'formality', label: 'Formalitaet', desc: 'du-Form, professionell aber locker' },
  { key: 'emotion', label: 'Emotion', desc: 'Leidenschaft zeigen, nicht aufsetzen' },
  { key: 'technical_depth', label: 'Fachtiefe', desc: 'Praxis-Wissen, keine Buzzwords' },
  { key: 'call_to_action', label: 'CTA-Stil', desc: 'Klar, direkt, ohne Druck' },
  { key: 'authenticity', label: 'Authentizitaet', desc: 'Echt bleiben, nie kuenstlich' },
]

function DimensionBar({ label, desc, value }) {
  const pct = Math.min(Math.max((value || 5) * 10, 0), 100)
  return (
    <div className="group">
      <div className="flex items-center justify-between mb-1">
        <div>
          <span className="text-sm font-medium text-ink">{label}</span>
          <span className="text-xs text-ink-muted ml-2 hidden group-hover:inline">{desc}</span>
        </div>
        <span className="text-xs font-medium text-primary-700">{value ? value.toFixed(1) : '-'}/10</span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-600 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
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

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [p, s] = await Promise.all([
        getVoiceProfile(),
        getFeedbackStats(),
      ])
      setProfile(p)
      setStats(s)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const trendLabels = { improving: 'Wird besser', stable: 'Stabil', declining: 'Wird schlechter', no_data: 'Noch keine Daten' }
  const trendColors = { improving: 'text-emerald-600', stable: 'text-primary-600', declining: 'text-red-600', no_data: 'text-ink-muted' }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Voice-Profil...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Voice-Profil</h1>
          <p className="text-sm text-ink-light mt-0.5">Dein Schreibstil in 12 Dimensionen. Lernt mit jedem Post dazu.</p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50"
        >
          <RefreshCw className="w-4 h-4" /> Aktualisieren
        </button>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>}

      {/* KPI Cards */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <StatCard
            icon={BookOpen}
            label="Posts insgesamt"
            value={stats.total_posts}
            color="text-primary-600"
          />
          <StatCard
            icon={TrendingUp}
            label="Avg. Engagement"
            value={stats.avg_engagement_rate ? `${stats.avg_engagement_rate}%` : '-'}
            color="text-emerald-600"
          />
          <StatCard
            icon={Mic}
            label="Lernfortschritt"
            value={trendLabels[stats.improvement_trend] || 'Unbekannt'}
            sub={stats.avg_edit_distance > 0 ? `Edit-Distanz: ${stats.avg_edit_distance}` : null}
            color="text-amber-600"
          />
        </div>
      )}

      {/* Voice Dimensions */}
      <div className="bg-white rounded-xl border border-surface-border p-6">
        <h2 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
          <Fingerprint className="w-4 h-4 text-primary-600" />
          Die 12 Voice-Dimensionen
        </h2>
        <p className="text-xs text-ink-muted mb-5">
          Basierend auf der Zukunftsbund-Brandvoice: Direkt, Kompetent, Warmherzig, Pragmatisch, Selbstbewusst.
        </p>

        {profile && profile.dimensions ? (
          <div className="space-y-4">
            {VOICE_DIMENSIONS.map(dim => (
              <DimensionBar
                key={dim.key}
                label={dim.label}
                desc={dim.desc}
                value={profile.dimensions?.[dim.key]}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <AlertCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-ink-light">Voice-Profil noch nicht erstellt.</p>
            <p className="text-xs text-ink-muted mt-1">Das Profil wird automatisch beim ersten Onboarding oder nach dem ersten Post-Feedback erstellt.</p>
          </div>
        )}
      </div>

      {/* Top Angles */}
      {stats && stats.top_angles && stats.top_angles.length > 0 && (
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
