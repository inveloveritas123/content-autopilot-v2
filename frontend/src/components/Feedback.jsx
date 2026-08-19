// AUDITED-2026-08-14 (Welle D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState, useEffect } from 'react'
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  FileText,
  Percent,
  Hash,
  Send,
  AlertCircle,
  CheckCircle2,
  ArrowDownRight,
  ArrowUpRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts'
import { getFeedbackStats, submitPerformance, getContentList } from '../api'

const TREND_MAP = {
  improving: {
    label: 'Wird besser',
    icon: TrendingUp,
    color: 'text-status-fertig-text',
    bg: 'bg-status-fertig-bg',
  },
  declining: {
    label: 'Ruecklaeufig',
    icon: TrendingDown,
    color: 'text-status-fehler-text',
    bg: 'bg-status-fehler-bg',
  },
  stable: {
    label: 'Stabil',
    icon: Minus,
    color: 'text-status-aktiv-text',
    bg: 'bg-status-aktiv-bg',
  },
  no_data: {
    label: 'Noch keine Daten',
    icon: BarChart3,
    color: 'text-ink-light',
    bg: 'bg-surface-bg',
  },
}

// Status-Bedeutung: 'teal'/'amber' referenzieren bereits die Primitive-Basis
// (Standard-KPI); 'emerald'/'blue'/'red' markieren eine Bewertung der Kennzahl
// (gut/neutral/kritisch) und mappen deshalb auf die Status-Tokens.
function StatCard({ icon: Icon, label, value, sub, color = 'teal' }) {
  const bgMap = {
    teal: 'bg-primary-50',
    amber: 'bg-accent-50',
    emerald: 'bg-status-fertig-bg',
    blue: 'bg-status-neu-bg',
    red: 'bg-status-fehler-bg',
  }
  const textMap = {
    teal: 'text-primary-700',
    amber: 'text-accent-700',
    emerald: 'text-status-fertig-text',
    blue: 'text-status-neu-text',
    red: 'text-status-fehler-text',
  }
  return (
    <div className="bg-white rounded-xl border border-surface-border p-5">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${bgMap[color]}`}>
          <Icon className={`w-5 h-5 ${textMap[color]}`} />
        </div>
        <div>
          <p className="text-2xl font-bold text-ink">{value}</p>
          <p className="text-xs text-ink-muted">{label}</p>
          {sub && <p className="text-[11px] text-ink-muted mt-0.5">{sub}</p>}
        </div>
      </div>
    </div>
  )
}

function AnglesChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="text-center py-8">
        <BarChart3 className="w-8 h-8 text-ink-muted mx-auto mb-2" />
        <p className="text-sm text-ink-light">Noch keine Angle-Daten.</p>
      </div>
    )
  }

  const chartData = data.map((d) => ({
    name: d.angle.charAt(0).toUpperCase() + d.angle.slice(1),
    engagement: parseFloat(d.avg_engagement?.toFixed(1) || 0),
    anzahl: d.count,
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /* bewusst behalten: Chart-Farbe */ />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: '1px solid #e5e7eb' /* bewusst behalten: Chart-Farbe */,
          }}
          formatter={(value, name) => [
            name === 'engagement' ? `${value}%` : value,
            name === 'engagement' ? 'Engagement' : 'Anzahl',
          ]}
        />
        <Bar
          dataKey="engagement"
          fill="#0d9488"
          /* bewusst behalten: Chart-Farbe */ radius={[4, 4, 0, 0]}
          name="engagement"
        />
        <Bar
          dataKey="anzahl"
          fill="#f59e0b"
          /* bewusst behalten: Chart-Farbe */ radius={[4, 4, 0, 0]}
          name="anzahl"
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

function PerformanceForm({ onSubmitted }) {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)
  const [form, setForm] = useState({
    content_piece_id: '',
    impressions: '',
    reactions: '',
    comments: '',
    shares: '',
    clicks: '',
    posted_at: '',
  })

  useEffect(() => {
    loadPosts()
  }, [])

  async function loadPosts() {
    setLoading(true)
    try {
      const data = await getContentList({ status: 'approved' })
      const list = Array.isArray(data) ? data : data?.items || []
      setPosts(list)
    } catch {
      setPosts([])
    }
    setLoading(false)
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.content_piece_id) {
      setMessage({ type: 'error', text: 'Bitte waehle einen Post aus.' })
      return
    }
    setSubmitting(true)
    setMessage(null)
    try {
      const payload = {
        content_piece_id: form.content_piece_id,
        impressions: parseInt(form.impressions) || 0,
        reactions: parseInt(form.reactions) || 0,
        comments: parseInt(form.comments) || 0,
        shares: parseInt(form.shares) || 0,
        clicks: parseInt(form.clicks) || 0,
      }
      if (form.posted_at) payload.posted_at = new Date(form.posted_at).toISOString()

      const result = await submitPerformance(payload)
      setMessage({
        type: 'success',
        text: `Gespeichert! Engagement: ${result.engagement_rate?.toFixed(1) || 0}% — ${result.verdict || ''}`,
      })
      setForm({
        content_piece_id: '',
        impressions: '',
        reactions: '',
        comments: '',
        shares: '',
        clicks: '',
        posted_at: '',
      })
      if (onSubmitted) onSubmitted()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSubmitting(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-ink-light mb-1.5">Post auswaehlen</label>
        {loading ? (
          <p className="text-xs text-ink-muted">Lade Posts...</p>
        ) : posts.length === 0 ? (
          <p className="text-xs text-ink-muted">Keine freigegebenen Posts vorhanden.</p>
        ) : (
          <select
            value={form.content_piece_id}
            onChange={(e) => updateField('content_piece_id', e.target.value)}
            className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">— Post waehlen —</option>
            {posts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.content_text?.slice(0, 80) || p.title || p.id}...
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { key: 'impressions', label: 'Impressions' },
          { key: 'reactions', label: 'Reaktionen' },
          { key: 'comments', label: 'Kommentare' },
          { key: 'shares', label: 'Shares' },
          { key: 'clicks', label: 'Klicks' },
        ].map((f) => (
          <div key={f.key}>
            <label className="block text-xs font-medium text-ink-light mb-1">{f.label}</label>
            <input
              type="number"
              min="0"
              value={form[f.key]}
              onChange={(e) => updateField(f.key, e.target.value)}
              placeholder="0"
              className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        ))}
        <div>
          <label className="block text-xs font-medium text-ink-light mb-1">
            Veroeffentlicht am
          </label>
          <input
            type="datetime-local"
            value={form.posted_at}
            onChange={(e) => updateField('posted_at', e.target.value)}
            className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
      </div>

      {message && (
        <div
          className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
            message.type === 'error'
              ? 'bg-status-fehler-bg text-status-fehler-text'
              : 'bg-status-fertig-bg text-status-fertig-text'
          }`}
        >
          {message.type === 'error' ? (
            <AlertCircle className="w-4 h-4" />
          ) : (
            <CheckCircle2 className="w-4 h-4" />
          )}
          {message.text}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !form.content_piece_id}
        className="flex items-center gap-2 px-4 py-2.5 bg-primary-700 text-white rounded-lg text-sm font-medium hover:bg-primary-800 disabled:opacity-50 transition-colors"
      >
        <Send className="w-4 h-4" />
        {submitting ? 'Speichern...' : 'Performance eintragen'}
      </button>
    </form>
  )
}

export default function Feedback() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    setLoading(true)
    try {
      const data = await getFeedbackStats()
      setStats(data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Feedback-Daten...</div>

  const trend = TREND_MAP[stats?.improvement_trend] || TREND_MAP.no_data
  const TrendIcon = trend.icon

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">Feedback & Lernsystem</h1>
        <p className="text-sm text-ink-light mt-0.5">
          So lernt das System aus deinem Feedback — Edit-Distanzen, Engagement und
          Angle-Performance.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-status-fehler-bg text-status-fehler-text rounded-lg text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          icon={FileText}
          label="Bewertete Posts"
          value={stats?.total_posts || 0}
          color="teal"
        />
        <StatCard
          icon={Hash}
          label="Avg. Edit-Distanz"
          value={stats?.avg_edit_distance?.toFixed(0) || '0'}
          sub="Zeichen Aenderung im Schnitt"
          color={stats?.avg_edit_distance > 100 ? 'amber' : 'emerald'}
        />
        <StatCard
          icon={Percent}
          label="Avg. Engagement"
          value={`${stats?.avg_engagement_rate?.toFixed(1) || '0'}%`}
          sub={stats?.avg_engagement_rate >= 3 ? 'Ueber Durchschnitt' : 'Noch aufbauend'}
          color={stats?.avg_engagement_rate >= 3 ? 'emerald' : 'blue'}
        />
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${trend.bg}`}>
              <TrendIcon className={`w-5 h-5 ${trend.color}`} />
            </div>
            <div>
              <p className="text-lg font-bold text-ink">{trend.label}</p>
              <p className="text-xs text-ink-muted">Lernkurve</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Angles Chart */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary-600" />
            Engagement nach Angle
          </h2>
          <AnglesChart data={stats?.top_angles} />
        </div>

        {/* Interpretation */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-status-fertig-text" />
            Einordnung
          </h2>

          {!stats || stats.total_posts === 0 ? (
            <div className="text-center py-8">
              <BarChart3 className="w-8 h-8 text-ink-muted mx-auto mb-2" />
              <p className="text-sm text-ink-light">Noch keine Daten vorhanden.</p>
              <p className="text-xs text-ink-muted mt-1">
                Gib unten LinkedIn-Performance ein, damit das Lernsystem starten kann.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-surface-bg">
                <p className="text-xs font-medium text-ink mb-1">Edit-Distanz</p>
                <p className="text-sm text-ink-light">
                  {stats.avg_edit_distance < 50
                    ? 'Sehr nah an deiner Sprache — das System trifft den Ton gut.'
                    : stats.avg_edit_distance < 150
                      ? 'Moderate Anpassungen — das System lernt noch deine Vorlieben.'
                      : 'Groessere Korrekturen noetig — mehr Feedback hilft dem System.'}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-surface-bg">
                <p className="text-xs font-medium text-ink mb-1">Engagement-Rate</p>
                <p className="text-sm text-ink-light">
                  {stats.avg_engagement_rate >= 5
                    ? 'Exzellent! Deine Posts performen ueberdurchschnittlich.'
                    : stats.avg_engagement_rate >= 3
                      ? 'Gute Performance — ueber dem LinkedIn-Durchschnitt.'
                      : stats.avg_engagement_rate >= 1.5
                        ? 'Durchschnittlich — weiter optimieren.'
                        : 'Noch im Aufbau — mehr Posts und Feedback bringen Daten.'}
                </p>
              </div>

              {stats.top_angles?.length > 0 && (
                <div className="p-3 rounded-lg bg-surface-bg">
                  <p className="text-xs font-medium text-ink mb-1">Bester Angle</p>
                  <p className="text-sm text-ink-light">
                    <span className="font-medium text-primary-700">
                      {stats.top_angles[0].angle.charAt(0).toUpperCase() +
                        stats.top_angles[0].angle.slice(1)}
                    </span>{' '}
                    mit {stats.top_angles[0].avg_engagement?.toFixed(1)}% Engagement
                    {stats.top_angles[0].count > 1 ? ` (${stats.top_angles[0].count} Posts)` : ''}.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Performance Entry Form */}
      <div className="bg-white rounded-xl border border-surface-border p-5">
        <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
          <ArrowUpRight className="w-4 h-4 text-accent-600" />
          LinkedIn-Performance eintragen
        </h2>
        <p className="text-xs text-ink-light mb-4">
          Trage die Zahlen deines LinkedIn-Posts ein (nach 48h fuer stabile Werte). Das System lernt
          daraus, welche Angles und Stile am besten ankommen.
        </p>
        <PerformanceForm onSubmitted={loadStats} />
      </div>
    </div>
  )
}
