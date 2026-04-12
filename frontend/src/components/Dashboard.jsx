import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Radio, FileText, Lightbulb, CheckCircle2, TrendingUp, Clock, ArrowRight, Sparkles, AlertCircle } from 'lucide-react'
import { getDashboard, getIdeas, getFeedbackStats } from '../api'

function KpiCard({ icon: Icon, label, value, color, onClick }) {
  const bgMap = { teal: 'bg-primary-50', amber: 'bg-accent-50', emerald: 'bg-emerald-50', blue: 'bg-blue-50' }
  const textMap = { teal: 'text-primary-700', amber: 'text-accent-700', emerald: 'text-emerald-700', blue: 'text-blue-700' }
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-xl border border-surface-border p-5 ${onClick ? 'cursor-pointer hover:border-primary-300 hover:shadow-sm transition-all' : ''}`}
    >
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${bgMap[color] || bgMap.teal}`}>
          <Icon className={`w-5 h-5 ${textMap[color] || textMap.teal}`} />
        </div>
        <div>
          <p className="text-2xl font-bold text-ink">{value}</p>
          <p className="text-xs text-ink-muted">{label}</p>
        </div>
      </div>
    </div>
  )
}

function ActivityItem({ icon: Icon, text, time, color }) {
  const colorMap = { teal: 'text-primary-600 bg-primary-50', amber: 'text-accent-600 bg-accent-50', emerald: 'text-emerald-600 bg-emerald-50' }
  return (
    <div className="flex items-start gap-3 py-3">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colorMap[color] || colorMap.teal}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-ink">{text}</p>
        {time && <p className="text-xs text-ink-muted mt-0.5">{time}</p>}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [ideas, setIdeas] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [dash, ideasData, fbStats] = await Promise.all([
        getDashboard().catch(() => null),
        getIdeas({ status: '' }).catch(() => []),
        getFeedbackStats().catch(() => null),
      ])
      setData(dash)
      setIdeas(Array.isArray(ideasData) ? ideasData : [])
      setStats(fbStats)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Dashboard...</div>

  const s = data?.stats || {}
  const openIdeas = ideas.filter(i => i.status === 'new' || i.status === 'questions_sent').length
  const answeredIdeas = ideas.filter(i => i.status === 'answers_received').length

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">Dashboard</h1>
        <p className="text-sm text-ink-light mt-0.5">Content Autopilot — dein LinkedIn auf Kurs.</p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard icon={Radio} label="Aktive Quellen" value={data?.active_sources?.length || 0} color="blue" onClick={() => navigate('/sources')} />
        <KpiCard icon={Lightbulb} label="Offene Ideen" value={openIdeas} color="amber" onClick={() => navigate('/ideas')} />
        <KpiCard icon={FileText} label="Post-Entwuerfe" value={s.content_suggestions || 0} color="teal" onClick={() => navigate('/posts')} />
        <KpiCard icon={CheckCircle2} label="Freigegeben" value={s.approved || 0} color="emerald" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Recent Ideas */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-accent-500" />
              Neueste Content-Ideen
            </h2>
            <button
              onClick={() => navigate('/ideas')}
              className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
            >
              Alle anzeigen <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {ideas.length === 0 ? (
            <div className="text-center py-8">
              <Lightbulb className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-ink-light">Noch keine Ideen.</p>
              <p className="text-xs text-ink-muted">Fuege eine Quelle hinzu und lass ein Video analysieren.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {ideas.slice(0, 5).map(idea => {
                const statusInfo = {
                  new: { label: 'Neu', color: 'bg-blue-100 text-blue-700' },
                  questions_sent: { label: 'Fragen offen', color: 'bg-amber-100 text-amber-700' },
                  answers_received: { label: 'Bereit', color: 'bg-emerald-100 text-emerald-700' },
                  content_generated: { label: 'Post da', color: 'bg-primary-100 text-primary-700' },
                }[idea.status] || { label: idea.status, color: 'bg-gray-100 text-gray-600' }

                return (
                  <div
                    key={idea.id}
                    onClick={() => navigate('/ideas')}
                    className="py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 -mx-2 px-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-medium ${statusInfo.color}`}>
                        {statusInfo.label}
                      </span>
                      <span className="text-sm text-ink truncate">{idea.title}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-3">
                      <span className="text-xs text-ink-muted">{idea.angle}</span>
                      <ArrowRight className="w-3 h-3 text-ink-muted" />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right: Activity */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-ink-light" />
            System-Status
          </h2>

          <div className="divide-y divide-gray-100">
            <ActivityItem
              icon={Radio}
              text={`${data?.active_sources?.length || 0} Quellen aktiv`}
              color="teal"
            />
            <ActivityItem
              icon={Lightbulb}
              text={`${ideas.length} Ideen insgesamt`}
              time={answeredIdeas > 0 ? `${answeredIdeas} bereit fuer Post-Generierung` : null}
              color="amber"
            />
            <ActivityItem
              icon={Sparkles}
              text={`${s.content_suggestions || 0} Post-Entwuerfe`}
              time={s.approved > 0 ? `${s.approved} davon freigegeben` : null}
              color="emerald"
            />
            {stats && stats.total_posts > 0 && (
              <ActivityItem
                icon={TrendingUp}
                text={`Lernsystem: ${stats.improvement_trend === 'improving' ? 'Wird besser' : stats.improvement_trend === 'stable' ? 'Stabil' : 'Noch zu wenig Daten'}`}
                time={stats.avg_engagement_rate > 0 ? `${stats.avg_engagement_rate}% Engagement` : null}
                color="emerald"
              />
            )}
          </div>

          {/* Quick hint */}
          <div className="mt-4 p-3 bg-primary-50 rounded-lg">
            <p className="text-xs text-primary-700 font-medium">Tipp: MCP nutzen</p>
            <p className="text-[11px] text-primary-600 mt-0.5">
              Oeffne Claude und sag: "Zeig mir was Neues gibt" — der Content Autopilot antwortet direkt.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
