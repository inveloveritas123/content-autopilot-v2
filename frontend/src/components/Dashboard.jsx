import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from './ui/Toast'
import {
  Radio,
  FileText,
  Lightbulb,
  CheckCircle2,
  TrendingUp,
  Clock,
  ArrowRight,
  Sparkles,
  AlertCircle,
  Zap,
  BarChart3,
  CalendarDays,
  Flame,
  Play,
  Pause,
  Target,
  Award,
  TrendingDown,
  Loader2,
} from 'lucide-react'
import {
  getDashboard,
  getIdeas,
  getFeedbackStats,
  triggerAutoPipeline,
  getScheduledPosts,
  getSourceFunnel,
  getContentList,
  getTodayBrief,
  autoSchedulePosts,
  resetBudgetFlag,
  getSettings,
  bulkArchiveIdeas,
  getIdeasSourceBreakdown,
  getBrandVoiceStatus,
  getAutomationStatus,
  pauseAutomation,
  resumeAutomation,
} from '../api'
import ResearchFindings from './ResearchFindings'

function FrequencyAdvisor({ approved, drafts }) {
  const [freq, setFreq] = useState(5)
  const total = (approved || 0) + (drafts || 0)
  const weeks = freq > 0 ? Math.floor((approved || 0) / freq) : 0
  const totalWeeks = freq > 0 ? Math.floor(total / freq) : 0
  const color = weeks >= 8 ? 'text-emerald-600' : weeks >= 4 ? 'text-amber-600' : 'text-red-500'
  const barPct = Math.min(100, (weeks / 12) * 100)
  return (
    <div className="bg-white rounded-xl border border-surface-border p-5">
      <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
        <Flame className="w-4 h-4 text-accent-500" /> Posting-Frequenz
      </h2>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-ink-muted">Posts/Woche:</span>
        {[3, 5, 7].map((f) => (
          <button
            key={f}
            onClick={() => setFreq(f)}
            className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${freq === f ? 'bg-primary-600 text-white' : 'bg-gray-100 text-ink-muted hover:bg-gray-200'}`}
          >
            {f}×
          </button>
        ))}
      </div>
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-ink-muted">{approved} freigegeben</span>
          <span className={`font-bold ${color}`}>{weeks} Wochen</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${weeks >= 8 ? 'bg-emerald-500' : weeks >= 4 ? 'bg-amber-400' : 'bg-red-400'}`}
            style={{ width: `${barPct}%` }}
          />
        </div>
      </div>
      <p className="text-[11px] text-ink-light leading-relaxed">
        {approved > 0
          ? `${freq}×/Woche → ${weeks}W freigegebener Content${drafts > 0 ? ` (inkl. Entwürfe: ${totalWeeks}W)` : ''}`
          : 'Noch keine freigegebenen Posts — Entwürfe freigeben'}
      </p>
    </div>
  )
}

function KpiCard({ icon: Icon, label, value, sub, color, onClick }) {
  const bgMap = {
    teal: 'bg-primary-50',
    amber: 'bg-accent-50',
    emerald: 'bg-emerald-50',
    blue: 'bg-blue-50',
    purple: 'bg-purple-50',
    red: 'bg-red-50',
  }
  const textMap = {
    teal: 'text-primary-700',
    amber: 'text-accent-700',
    emerald: 'text-emerald-700',
    blue: 'text-blue-700',
    purple: 'text-purple-700',
    red: 'text-red-600',
  }
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-xl border border-surface-border p-4 ${onClick ? 'cursor-pointer hover:border-primary-300 hover:shadow-sm transition-all' : ''}`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center ${bgMap[color] || bgMap.teal}`}
        >
          <Icon className={`w-4.5 h-4.5 ${textMap[color] || textMap.teal}`} />
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

function PipelineBar({ pipeline }) {
  const order = [
    'content_ready',
    'analyzed',
    'transcribed',
    'transcribing',
    'analyzing',
    'generating',
    'transcription_failed',
  ]
  const colors = {
    content_ready: 'bg-emerald-500',
    analyzed: 'bg-teal-500',
    transcribed: 'bg-blue-400',
    transcribing: 'bg-yellow-400',
    analyzing: 'bg-yellow-400',
    generating: 'bg-yellow-400',
    transcription_failed: 'bg-red-400',
  }
  const labels = {
    content_ready: 'Content bereit',
    analyzed: 'Analysiert',
    transcribed: 'Transkribiert',
    transcribing: 'Transkribiert...',
    analyzing: 'Analysiert...',
    generating: 'Generiert...',
    transcription_failed: 'Fehler',
  }
  const total = Object.values(pipeline).reduce((a, b) => a + b, 0)
  if (!total) return null

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5">
      <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
        <Zap className="w-4 h-4 text-accent-500" /> Pipeline-Übersicht
      </h2>
      <div className="flex rounded-full overflow-hidden h-3 mb-3">
        {order.map((status) => {
          const count = pipeline[status] || 0
          if (!count) return null
          const pct = ((count / total) * 100).toFixed(1)
          return (
            <div
              key={status}
              className={`${colors[status]} transition-all`}
              style={{ width: `${pct}%` }}
              title={`${labels[status]}: ${count}`}
            />
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {order.map((status) => {
          const count = pipeline[status] || 0
          if (!count) return null
          return (
            <div key={status} className="flex items-center gap-1.5">
              <span className={`w-2.5 h-2.5 rounded-full ${colors[status]}`} />
              <span className="text-xs text-ink-muted">{labels[status]}</span>
              <span className="text-xs font-semibold text-ink">{count}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Today's Content Brief ─────────────────────────────────────────────────
const PILLAR_EMOJIS = {
  thought_leadership: '💡',
  how_to: '🛠',
  personal_story: '📖',
  industry_news: '📰',
  product_service: '🎯',
}

function TodayBrief({ brief, navigate }) {
  if (!brief) return null
  const { today, queue, pillar_gap, recommended_post, momentum_score } = brief

  const scoreColor =
    momentum_score >= 70
      ? 'text-emerald-600'
      : momentum_score >= 40
        ? 'text-amber-600'
        : 'text-red-500'
  const scoreBar =
    momentum_score >= 70 ? 'bg-emerald-500' : momentum_score >= 40 ? 'bg-amber-400' : 'bg-red-400'

  return (
    <div className="bg-gradient-to-r from-primary-50 to-indigo-50 rounded-xl border border-primary-200 p-5 mb-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary-600" />
          <span className="text-sm font-semibold text-ink">Heute — {today.day_name}</span>
          {today.is_good_posting_day ? (
            <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full text-[10px] font-medium">
              Guter Post-Tag
            </span>
          ) : (
            <span className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full text-[10px]">
              Wochenende
            </span>
          )}
        </div>
        {/* Momentum Score */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-ink-muted">Momentum</span>
          <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${scoreBar}`}
              style={{ width: `${momentum_score}%` }}
            />
          </div>
          <span className={`text-xs font-bold tabular-nums ${scoreColor}`}>{momentum_score}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Optimal post time */}
        <div className="bg-white rounded-lg p-3 border border-white/80 shadow-sm">
          <p className="text-[10px] font-semibold text-ink-muted uppercase tracking-wide mb-1.5 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Optimale Zeit
          </p>
          {today.next_optimal_slot ? (
            <>
              <p className="text-xl font-bold text-ink">{today.next_optimal_slot} Uhr</p>
              <p className="text-[10px] text-ink-muted mt-0.5">
                Beste Stunden: {today.best_hours.map((h) => `${h}:00`).join(' · ')}
              </p>
            </>
          ) : (
            <p className="text-sm text-ink-muted">Kein Slot mehr heute</p>
          )}
        </div>

        {/* Pillar gap */}
        <div className="bg-white rounded-lg p-3 border border-white/80 shadow-sm">
          <p className="text-[10px] font-semibold text-ink-muted uppercase tracking-wide mb-1.5 flex items-center gap-1">
            <Target className="w-3 h-3" /> Pillar-Lücke
          </p>
          <p className="text-sm font-semibold text-ink">
            {PILLAR_EMOJIS[pillar_gap?.key]} {pillar_gap?.label}
          </p>
          <p className="text-[10px] text-ink-muted mt-0.5 leading-relaxed">
            {pillar_gap?.writing_prompt}
          </p>
        </div>

        {/* Queue status + recommended action */}
        <div className="bg-white rounded-lg p-3 border border-white/80 shadow-sm">
          <p className="text-[10px] font-semibold text-ink-muted uppercase tracking-wide mb-1.5 flex items-center gap-1">
            <Zap className="w-3 h-3" /> Empfehlung
          </p>
          {recommended_post ? (
            <>
              <p className="text-xs font-medium text-ink line-clamp-2 leading-relaxed">
                {recommended_post.preview}…
              </p>
              <button
                onClick={() => navigate('/posts')}
                className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-primary-600 hover:text-primary-700"
              >
                <ArrowRight className="w-3 h-3" /> Post öffnen & einplanen
              </button>
            </>
          ) : (
            <div>
              <p className="text-xs text-ink-muted">
                {queue.approved} freigegeben · {queue.drafts} Entwürfe
              </p>
              <button
                onClick={() => navigate('/posts')}
                className="mt-2 text-[10px] font-semibold text-primary-600 hover:underline"
              >
                → Posts freigeben
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const PILLAR_LABELS = {
  thought_leadership: { label: 'Thought Leadership', emoji: '💡' },
  how_to: { label: 'How-To', emoji: '🛠' },
  personal_story: { label: 'Story', emoji: '📖' },
  industry_news: { label: 'News', emoji: '📰' },
  product_service: { label: 'Produkt', emoji: '🎯' },
}

function SmartInsights({ sourceFunnel, recentPosts, scheduled }) {
  // 1. Best source by approval_rate (min 2 items)
  const bestSource = sourceFunnel
    .filter((s) => (s.items_count || 0) >= 2 && (s.approval_rate || 0) > 0)
    .sort((a, b) => (b.approval_rate || 0) - (a.approval_rate || 0))[0]

  // 2. Pillar gap: which pillar has fewest posts
  const pillarCounts = {}
  Object.keys(PILLAR_LABELS).forEach((k) => {
    pillarCounts[k] = 0
  })
  recentPosts.forEach((p) => {
    const pillar = p.content_metadata?.pillar
    if (pillar && pillarCounts[pillar] !== undefined) pillarCounts[pillar]++
  })
  const gapPillar = Object.entries(pillarCounts).sort((a, b) => a[1] - b[1])[0]

  // 3. Velocity: posts created in last 7 days vs previous 7 days
  const now = Date.now()
  const DAY = 86400000
  const last7 = recentPosts.filter(
    (p) => p.created_at && now - new Date(p.created_at) < 7 * DAY
  ).length
  const prev7 = recentPosts.filter(
    (p) =>
      p.created_at &&
      now - new Date(p.created_at) >= 7 * DAY &&
      now - new Date(p.created_at) < 14 * DAY
  ).length
  const velocityDelta = last7 - prev7
  const velocityUp = velocityDelta >= 0

  // 4. Next scheduled post countdown
  const nextPost = scheduled?.[0]
  let countdownText = null
  if (nextPost?.scheduled_at) {
    const diffMs = new Date(nextPost.scheduled_at) - new Date()
    if (diffMs > 0) {
      const diffH = Math.floor(diffMs / 3600000)
      const diffM = Math.floor((diffMs % 3600000) / 60000)
      countdownText = diffH > 0 ? `in ${diffH}h ${diffM}min` : `in ${diffM}min`
    }
  }

  const insights = [
    bestSource && {
      icon: Award,
      color: 'text-emerald-700 bg-emerald-50 border-emerald-200',
      iconColor: 'text-emerald-600',
      title: 'Beste Quelle',
      body: `${bestSource.name} — ${Math.round(bestSource.approval_rate * 100)}% Freigaberate (${bestSource.approved_count}/${bestSource.posts_count} Posts)`,
    },
    gapPillar && {
      icon: Target,
      color: 'text-amber-700 bg-amber-50 border-amber-200',
      iconColor: 'text-amber-600',
      title: 'Pillar-Lücke',
      body: `${PILLAR_LABELS[gapPillar[0]]?.emoji} ${PILLAR_LABELS[gapPillar[0]]?.label} fehlt — nur ${gapPillar[1]} Posts bisher`,
    },
    {
      icon: velocityUp ? TrendingUp : TrendingDown,
      color: velocityUp
        ? 'text-blue-700 bg-blue-50 border-blue-200'
        : 'text-red-700 bg-red-50 border-red-200',
      iconColor: velocityUp ? 'text-blue-600' : 'text-red-500',
      title: 'Content-Velocity',
      body: `${last7} Posts letzte 7 Tage (${velocityUp ? '+' : ''}${velocityDelta} vs. Vorwoche)`,
    },
    countdownText && {
      icon: CalendarDays,
      color: 'text-violet-700 bg-violet-50 border-violet-200',
      iconColor: 'text-violet-600',
      title: 'Nächster Post',
      body: `${countdownText} — ${new Date(nextPost.scheduled_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} Uhr`,
    },
  ].filter(Boolean)

  if (insights.length === 0) return null

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5 mb-5">
      <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-accent-500" /> Smart Insights
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {insights.map((ins, i) => (
          <div
            key={i}
            className={`flex items-start gap-2.5 p-3 rounded-lg border text-xs ${ins.color}`}
          >
            <ins.icon className={`w-4 h-4 shrink-0 mt-0.5 ${ins.iconColor}`} />
            <div>
              <p className="font-semibold leading-tight">{ins.title}</p>
              <p className="mt-0.5 leading-relaxed opacity-90">{ins.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── This Week Schedule Widget (Cycle 44) ────────────────────────────────────
function WeekScheduleWidget({ scheduled, approved, navigate }) {
  const [filling, setFilling] = useState(false)
  const [fillResult, setFillResult] = useState(null)

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const dow = (today.getDay() + 6) % 7 // 0=Mon
  const weekStart = new Date(today.getTime() - dow * 86400000)

  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart.getTime() + i * 86400000)
    const iso = d.toISOString().slice(0, 10)
    const posts = (scheduled || []).filter((p) => (p.scheduled_at || '').startsWith(iso))
    const isToday = i === dow
    const isPast = d < today
    const isWeekend = i >= 5
    return {
      d,
      iso,
      posts,
      isToday,
      isPast,
      isWeekend,
      label: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][i],
    }
  })

  const workdays = days.filter((d) => !d.isWeekend)
  const gapDays = workdays.filter((d) => !d.isPast && d.posts.length === 0).length
  const totalScheduled = days.reduce((a, d) => a + d.posts.length, 0)

  async function handleFillGaps() {
    if (!window.confirm(`${gapDays} freie Werktage mit genehmigten Posts füllen?`)) return
    setFilling(true)
    setFillResult(null)
    try {
      const r = await autoSchedulePosts({ posts_per_day: 1, weeks: 1 })
      setFillResult({ ok: true, text: `✅ ${r.scheduled || 0} Posts eingeplant` })
      setTimeout(() => setFillResult(null), 4000)
    } catch (e) {
      setFillResult({ ok: false, text: e.message })
    }
    setFilling(false)
  }

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5 mb-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-primary-600" /> Diese Woche
          <span className="text-xs font-normal text-ink-muted ml-1">
            {totalScheduled > 0 ? `${totalScheduled} Posts eingeplant` : 'Noch nichts geplant'}
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {gapDays > 0 && approved > 0 && (
            <button
              onClick={handleFillGaps}
              disabled={filling}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 disabled:opacity-50 transition-colors"
            >
              <Zap className="w-3 h-3" />
              {filling ? 'Fülle...' : `${gapDays} Lücken füllen`}
            </button>
          )}
          <button
            onClick={() => navigate('/calendar')}
            className="text-xs text-ink-muted hover:text-primary-600 flex items-center gap-1"
          >
            Kalender <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {fillResult && (
        <div
          className={`mb-3 px-3 py-2 rounded-lg text-xs font-medium ${fillResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}
        >
          {fillResult.text}
        </div>
      )}

      <div className="grid grid-cols-7 gap-1.5">
        {days.map((day, i) => {
          const hasPost = day.posts.length > 0
          const isGap = !day.isPast && !hasPost && !day.isWeekend
          return (
            <div
              key={i}
              onClick={() => navigate('/calendar')}
              className={`rounded-xl p-2.5 text-center cursor-pointer transition-all border
                ${
                  day.isToday
                    ? 'border-primary-400 bg-primary-50 shadow-sm'
                    : hasPost
                      ? 'border-emerald-300 bg-emerald-50 hover:bg-emerald-100'
                      : isGap
                        ? 'border-amber-200 bg-amber-50 hover:bg-amber-100'
                        : day.isPast
                          ? 'border-gray-100 bg-gray-50'
                          : 'border-gray-200 bg-gray-50 hover:bg-gray-100'
                }`}
            >
              <p
                className={`text-[10px] font-semibold mb-1 ${day.isToday ? 'text-primary-700' : 'text-ink-muted'}`}
              >
                {day.label}
              </p>
              <p
                className={`text-base font-bold leading-none mb-1.5 ${day.isToday ? 'text-primary-700' : day.isPast ? 'text-gray-400' : 'text-ink'}`}
              >
                {day.d.getDate()}
              </p>
              {hasPost ? (
                <div className="space-y-0.5">
                  {day.posts.slice(0, 2).map((p, j) => (
                    <div
                      key={j}
                      className="w-full h-1.5 rounded-full bg-emerald-500"
                      title={`${new Date(p.scheduled_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} Uhr`}
                    />
                  ))}
                  {day.posts.length > 2 && (
                    <p className="text-[9px] text-emerald-600">+{day.posts.length - 2}</p>
                  )}
                </div>
              ) : isGap ? (
                <div className="text-amber-400 text-xs leading-none">!</div>
              ) : day.isWeekend ? (
                <div className="text-gray-300 text-xs leading-none">—</div>
              ) : null}
            </div>
          )
        })}
      </div>

      {gapDays > 0 && approved === 0 && (
        <p className="text-[11px] text-amber-600 mt-3 text-center">
          ⚠️ {gapDays} freie Werktage — erst Posts freigeben, dann einplanen
        </p>
      )}
    </div>
  )
}

// ── 12-Week Content Activity Calendar (Cycle 41) ─────────────────────────────
const DAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function ContentStreakCalendar({ posts }) {
  const DAY_MS = 86400000
  const WEEKS = 12
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // Build activity map: dateStr → { approved, draft, published, scheduled }
  const actMap = {}
  posts.forEach((p) => {
    const dates = [p.created_at, p.approved_at].filter(Boolean)
    dates.forEach((d) => {
      const day = new Date(d)
      day.setHours(0, 0, 0, 0)
      const key = day.toISOString().slice(0, 10)
      if (!actMap[key]) actMap[key] = { approved: 0, draft: 0, published: 0, total: 0 }
      if (p.status === 'published') actMap[key].published++
      else if (p.status === 'approved' || p.status === 'scheduled') actMap[key].approved++
      else actMap[key].draft++
      actMap[key].total++
    })
  })

  // Build 84-day grid starting from Monday 12 weeks ago
  // Find the Monday 12 weeks before today
  const startDate = new Date(today)
  const dayOfWeek = (startDate.getDay() + 6) % 7 // 0=Mon, 6=Sun
  startDate.setDate(startDate.getDate() - dayOfWeek - (WEEKS - 1) * 7)

  const days = []
  for (let i = 0; i < WEEKS * 7; i++) {
    const d = new Date(startDate.getTime() + i * DAY_MS)
    const key = d.toISOString().slice(0, 10)
    const act = actMap[key] || { approved: 0, draft: 0, published: 0, total: 0 }
    const isToday = d.getTime() === today.getTime()
    const isFuture = d.getTime() > today.getTime()
    days.push({ date: d, key, act, isToday, isFuture })
  }

  // Streak calculation (consecutive days back from today with >= 1 approved/published)
  let streak = 0
  let bestStreak = 0
  let cur = 0
  for (let i = days.length - 1; i >= 0; i--) {
    const d = days[i]
    if (d.isFuture) continue
    const active = d.act.approved + d.act.published > 0
    if (active) {
      if (
        streak === 0 ||
        i === days.length - 1 ||
        days[i + 1].act.approved + days[i + 1].act.published > 0 ||
        days[i + 1].isFuture
      )
        streak++
    } else if (streak > 0) break
  }
  // Best streak scan
  for (const d of days) {
    if (!d.isFuture && d.act.approved + d.act.published > 0) {
      cur++
    } else {
      bestStreak = Math.max(bestStreak, cur)
      cur = 0
    }
  }
  bestStreak = Math.max(bestStreak, cur)

  // Posts this week (Mon–Sun of current week)
  const weekStart = new Date(today)
  weekStart.setDate(today.getDate() - dayOfWeek)
  const postsThisWeek = days.filter(
    (d) => d.date >= weekStart && !d.isFuture && d.act.total > 0
  ).length

  // Month labels (show month name at first day of each month in grid)
  const weekGroups = []
  for (let w = 0; w < WEEKS; w++) {
    weekGroups.push(days.slice(w * 7, w * 7 + 7))
  }
  const monthLabels = weekGroups.map((wk) => {
    const first = wk[0]
    const isNewMonth = first.date.getDate() <= 7
    return isNewMonth ? first.date.toLocaleDateString('de-DE', { month: 'short' }) : ''
  })

  function cellColor(d) {
    if (d.isFuture) return 'bg-gray-100'
    if (d.act.published > 0) return 'bg-emerald-600'
    if (d.act.approved > 0) return 'bg-emerald-300'
    if (d.act.draft > 0) return 'bg-amber-200'
    return 'bg-gray-100'
  }

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5 mb-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
          <Flame className="w-4 h-4 text-orange-500" /> Content-Aktivität — 12 Wochen
        </h2>
        <div className="flex items-center gap-4 text-[11px] text-ink-muted">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-emerald-600 inline-block" /> Veröffentlicht
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-emerald-300 inline-block" /> Freigegeben
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-amber-200 inline-block" /> Entwurf
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-6 mb-4">
        <div className="text-center">
          <div className="text-2xl font-black text-orange-500 leading-none">{streak}</div>
          <div className="text-[10px] text-ink-muted mt-0.5">Streak (Tage)</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-black text-emerald-600 leading-none">{bestStreak}</div>
          <div className="text-[10px] text-ink-muted mt-0.5">Bester Streak</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-black text-blue-600 leading-none">{postsThisWeek}</div>
          <div className="text-[10px] text-ink-muted mt-0.5">Diese Woche</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-black text-ink leading-none">
            {Object.values(actMap).reduce((a, v) => a + v.total, 0)}
          </div>
          <div className="text-[10px] text-ink-muted mt-0.5">Gesamt aktiv</div>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="overflow-x-auto">
        <div className="inline-flex flex-col gap-1" style={{ minWidth: 'max-content' }}>
          {/* Month labels row */}
          <div className="flex gap-1 mb-0.5 pl-8">
            {weekGroups.map((_, w) => (
              <div key={w} className="w-4 text-[9px] text-ink-muted text-center">
                {monthLabels[w]}
              </div>
            ))}
          </div>
          {/* Day rows */}
          {[0, 1, 2, 3, 4, 5, 6].map((dayIdx) => (
            <div key={dayIdx} className="flex items-center gap-1">
              <span className="text-[9px] text-ink-muted w-6 text-right shrink-0 pr-1">
                {DAY_LABELS[dayIdx]}
              </span>
              {weekGroups.map((wk, w) => {
                const d = wk[dayIdx]
                return (
                  <div
                    key={w}
                    title={`${d.key}: ${d.act.published}pub ${d.act.approved}approved ${d.act.draft}draft`}
                    className={`w-4 h-4 rounded-sm ${cellColor(d)} ${d.isToday ? 'ring-2 ring-offset-1 ring-primary-500' : ''} transition-colors`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [data, setData] = useState(null)
  const [ideas, setIdeas] = useState([])
  const [stats, setStats] = useState(null)
  const [scheduled, setScheduled] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sourceFunnel, setSourceFunnel] = useState([])
  const [recentPosts, setRecentPosts] = useState([])
  const [todayBrief, setTodayBrief] = useState(null)
  const [autoPumping, setAutoPumping] = useState(false)
  const [pumpResult, setPumpResult] = useState(null)
  const [profileSettings, setProfileSettings] = useState(null)
  const [brandVoiceData, setBrandVoiceData] = useState(null)
  const [ideaBreakdown, setIdeaBreakdown] = useState(null)
  const [cleaningUp, setCleaningUp] = useState(false)
  const [cleanupMsg, setCleanupMsg] = useState(null)
  const [automationStatus, setAutomationStatus] = useState(null)
  const [automationToggling, setAutomationToggling] = useState(false)

  useEffect(() => {
    loadAll()
    loadAutomationStatus()
    // Auto-refresh every 30 seconds to pick up pipeline changes
    const interval = setInterval(() => loadAll(), 30000)
    return () => clearInterval(interval)
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [
        dash,
        ideasData,
        fbStats,
        sched,
        funnel,
        posts,
        brief,
        settingsData,
        breakdown,
        bvData,
      ] = await Promise.all([
        getDashboard().catch(() => null),
        getIdeas({ status: '' }).catch(() => []),
        getFeedbackStats().catch(() => null),
        getScheduledPosts('scheduled').catch(() => []),
        getSourceFunnel().catch(() => []),
        getContentList({ limit: 200 }).catch(() => []),
        getTodayBrief().catch(() => null),
        getSettings().catch(() => null),
        getIdeasSourceBreakdown().catch(() => null),
        getBrandVoiceStatus('me').catch(() => null),
      ])
      if (breakdown) setIdeaBreakdown(breakdown)
      setData(dash)
      setIdeas(Array.isArray(ideasData) ? ideasData : [])
      setStats(fbStats)
      setScheduled(Array.isArray(sched) ? sched : [])
      setSourceFunnel(Array.isArray(funnel) ? funnel : [])
      setRecentPosts(Array.isArray(posts) ? posts : posts?.items || [])
      setTodayBrief(brief || null)
      setProfileSettings(settingsData?.settings || null)
      setBrandVoiceData(bvData || null)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  async function loadAutomationStatus() {
    try {
      const s = await getAutomationStatus()
      setAutomationStatus(s)
    } catch {
      // ignore — endpoint may not be deployed yet
    }
  }

  async function handleAutomationToggle() {
    if (!automationStatus) return
    setAutomationToggling(true)
    try {
      const isPaused = automationStatus.paused
      const result = isPaused ? await resumeAutomation() : await pauseAutomation()
      setAutomationStatus({
        enabled: result.enabled,
        paused: !result.enabled,
        disabled_at: result.disabled_at ?? null,
        disabled_reason: result.disabled_reason ?? null,
      })
      if (isPaused) {
        toast.success('Automatik wieder aktiv — Pipeline läuft.')
      } else {
        toast.warning('Automatik pausiert — Pipeline gestoppt.')
      }
    } catch (e) {
      toast.error(e.message || 'Fehler beim Umschalten der Automatik')
    }
    setAutomationToggling(false)
  }

  async function handleAutoPump() {
    setAutoPumping(true)
    setPumpResult(null)
    try {
      const r = await triggerAutoPipeline()
      setPumpResult({
        ok: true,
        text: `▶ ${r.analyze_triggered} analysieren · ${r.generate_triggered} generieren · ${r.ideation_triggered} ideation`,
      })
      setTimeout(() => {
        setPumpResult(null)
        loadAll()
      }, 5000)
    } catch (e) {
      setPumpResult({ ok: false, text: e.message })
    }
    setAutoPumping(false)
  }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Dashboard...</div>

  const s = data?.stats || {}
  const pipeline = data?.pipeline || {}
  const openIdeas = ideas.filter((i) => i.status === 'new' || i.status === 'questions_sent').length
  const answeredIdeas = ideas.filter((i) => i.status === 'answers_received').length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Dashboard</h1>
          <p className="text-sm text-ink-light mt-0.5">
            Content Autopilot — dein LinkedIn auf Kurs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Automation Kill-Switch (Issue #89) */}
          {automationStatus !== null && (
            <button
              onClick={handleAutomationToggle}
              disabled={automationToggling}
              title={
                automationStatus.paused
                  ? `Automatik pausiert seit ${automationStatus.disabled_at ? new Date(automationStatus.disabled_at).toLocaleString('de-DE') : '—'} — klicken zum Reaktivieren`
                  : 'Tägliche LLM-Automatik pausieren'
              }
              className={`flex items-center gap-1.5 text-xs font-medium rounded-lg px-3 py-1.5 border transition-colors disabled:opacity-60 ${
                automationStatus.paused
                  ? 'text-white bg-amber-500 border-amber-600 hover:bg-amber-600'
                  : 'text-gray-700 bg-white border-gray-300 hover:bg-gray-50'
              }`}
            >
              {automationToggling ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
              ) : automationStatus.paused ? (
                <Play className="w-3.5 h-3.5" />
              ) : (
                <Pause className="w-3.5 h-3.5" />
              )}
              {automationToggling
                ? '…'
                : automationStatus.paused
                  ? 'Automatik starten'
                  : 'Automatik pausieren'}
            </button>
          )}
          <button
            onClick={handleAutoPump}
            disabled={autoPumping}
            className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 hover:bg-emerald-100 disabled:opacity-60 transition-colors"
            title="Analysieren + Generieren + Ideation für alle wartenden Items"
          >
            {autoPumping ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            {autoPumping ? 'Pumpt…' : 'Auto-Pipeline'}
          </button>
          <button
            onClick={loadAll}
            className="text-xs text-ink-muted hover:text-primary-600 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50"
          >
            Aktualisieren
          </button>
        </div>
      </div>

      {pumpResult && (
        <div
          className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${pumpResult.ok ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700'}`}
        >
          {pumpResult.ok ? (
            <Zap className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          {pumpResult.text}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Setup Checklist — shown when profile is incomplete */}
      {(() => {
        // v2 Brand Voice check: all 3 pillars must be active
        const bvContext = brandVoiceData?.customer_context
        const bvVoice = brandVoiceData?.voice_profile
        const bvAvatar = brandVoiceData?.audience_avatar
        const bvPillarsCount = [bvContext, bvVoice, bvAvatar].filter(Boolean).length
        const hasBrandVoice = bvPillarsCount === 3
        const hasSources = (data?.active_sources?.length || 0) > 0
        const hasIdeas = ideas.length > 0
        const hasContent = (data?.stats?.drafts || 0) + (data?.stats?.approved || 0) > 0
        const allDone = hasBrandVoice && hasSources && hasIdeas && hasContent
        if (allDone) return null

        // Check for old v1 profile data (migration hint)
        const ent = profileSettings?.entrepreneur || {}
        const hasOldProfile = !!(ent.name || ent.industry)

        const steps = [
          {
            done: hasBrandVoice,
            title: 'Brand Voice einrichten',
            desc: hasBrandVoice
              ? `${bvContext?.payload?.person?.name || brandVoiceData?.tenant_name || ''} · Brand Voice vollständig`
              : bvPillarsCount > 0
                ? `${bvPillarsCount}/3 Säulen fertig — Wizard fortsetzen`
                : hasOldProfile
                  ? `Altes Profil gefunden (${ent.name || ent.industry}) — Brand Voice Wizard starten`
                  : 'Branche, Tonalität, Zielgruppe — KI-Basis für alle Posts',
            action: () => navigate('/brand-voice'),
            actionLabel: 'Brand Voice einrichten →',
            urgent: true,
          },
          {
            done: hasSources,
            title: 'Inhaltsquellen hinzufügen',
            desc: hasSources
              ? `${data.active_sources.length} aktive Quellen`
              : 'YouTube-Kanäle oder RSS-Feeds als Rohmaterial für Posts',
            action: () => navigate('/sources'),
            actionLabel: 'Quellen hinzufügen →',
          },
          {
            done: hasIdeas,
            title: 'Ideen generieren',
            desc: hasIdeas
              ? `${ideas.length.toLocaleString('de')} Ideen verfügbar`
              : 'Aus analysierten Inhalten werden 5-8 Post-Ideen pro Video erstellt',
            action: () => navigate('/ideas'),
            actionLabel: 'Zur Ideen-Pipeline →',
          },
          {
            done: hasContent,
            title: 'Ersten Post erstellen & freigeben',
            desc: hasContent
              ? `${(data?.stats?.drafts || 0) + (data?.stats?.approved || 0)} Posts vorhanden`
              : 'Quick-Generate: Posts aus Ideen ohne Q&A erstellen',
            action: () => navigate('/posts'),
            actionLabel: 'Posts ansehen →',
          },
        ]
        const completedCount = steps.filter((s) => s.done).length
        return (
          <div className="mb-5 rounded-xl border border-primary-200 bg-gradient-to-r from-primary-50 to-blue-50 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-primary-600" />
                <span className="font-semibold text-sm text-primary-900">Setup-Checkliste</span>
                <span className="text-xs text-primary-600 bg-primary-100 px-2 py-0.5 rounded-full font-medium">
                  {completedCount}/{steps.length}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 bg-primary-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-600 rounded-full transition-all"
                    style={{ width: `${(completedCount / steps.length) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-primary-600 font-medium">
                  {Math.round((completedCount / steps.length) * 100)}%
                </span>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {steps.map((step, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2.5 p-3 rounded-lg border transition-all cursor-pointer ${
                    step.done
                      ? 'bg-white/70 border-emerald-200 opacity-70'
                      : step.urgent
                        ? 'bg-white border-amber-300 shadow-sm hover:shadow-md'
                        : 'bg-white/80 border-primary-100 hover:border-primary-300'
                  }`}
                  onClick={step.done ? undefined : step.action}
                >
                  <div
                    className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${step.done ? 'bg-emerald-500' : step.urgent ? 'bg-amber-400' : 'bg-gray-200'}`}
                  >
                    {step.done ? (
                      <CheckCircle2 className="w-3 h-3 text-white" />
                    ) : (
                      <span className="text-[10px] font-bold text-white">{i + 1}</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className={`text-xs font-semibold leading-snug ${step.done ? 'text-emerald-800 line-through decoration-emerald-400' : step.urgent ? 'text-amber-900' : 'text-ink'}`}
                    >
                      {step.title}
                    </p>
                    <p className="text-[11px] text-ink-muted mt-0.5 leading-tight">{step.desc}</p>
                    {!step.done && (
                      <button
                        onClick={step.action}
                        className={`mt-1.5 text-[10px] font-semibold ${step.urgent ? 'text-amber-700 hover:text-amber-900' : 'text-primary-600 hover:text-primary-800'}`}
                      >
                        {step.actionLabel}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {!hasBrandVoice && (
              <div className="mt-3 px-3 py-2 bg-amber-100 border border-amber-200 rounded-lg text-xs text-amber-800">
                ⚠️ <strong>Brand Voice nicht eingerichtet</strong> — die KI generiert generische
                Inhalte ohne Branchenbezug. Bitte Brand Voice Wizard starten.
              </div>
            )}
          </div>
        )
      })()}

      {/* KPI Grid — 6 cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
        <KpiCard
          icon={Radio}
          label="Quellen aktiv"
          value={data?.active_sources?.length || 0}
          color="blue"
          onClick={() => navigate('/sources')}
        />
        <KpiCard
          icon={Zap}
          label="Items gesamt"
          value={s.total_items}
          color="teal"
          onClick={() => navigate('/pipeline')}
        />
        <KpiCard
          icon={CheckCircle2}
          label="Content bereit"
          value={pipeline.content_ready || 0}
          color="emerald"
          onClick={() => navigate('/pipeline')}
        />
        <KpiCard
          icon={FileText}
          label="Entwürfe"
          value={s.drafts || 0}
          color="purple"
          onClick={() => navigate('/posts')}
          sub={s.approved > 0 ? `${s.approved} freigegeben` : null}
        />
        <KpiCard
          icon={CalendarDays}
          label="Eingeplant"
          value={scheduled.length}
          color="teal"
          onClick={() => navigate('/calendar')}
          sub={
            scheduled.length > 0
              ? `nächster: ${new Date(scheduled[0].scheduled_at).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}`
              : 'noch nichts geplant'
          }
        />
        <KpiCard
          icon={AlertCircle}
          label="Fehler"
          value={pipeline.transcription_failed || 0}
          color="red"
          onClick={() => navigate('/pipeline')}
        />
      </div>

      {/* Today's Brief */}
      <TodayBrief brief={todayBrief} navigate={navigate} />

      {/* This Week Schedule */}
      <WeekScheduleWidget scheduled={scheduled} approved={s.approved || 0} navigate={navigate} />

      {/* Pipeline budget exceeded warning */}
      {data?.llm_budget_exceeded && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold text-red-800">
              🔴 KI-Pipeline pausiert: Requesty.ai Portal-Budget erschöpft.
            </span>
            <span className="text-red-700 ml-1">
              Bitte bei{' '}
              <a
                href="https://requesty.ai"
                target="_blank"
                rel="noopener"
                className="underline font-medium"
              >
                requesty.ai
              </a>{' '}
              Guthaben aufladen.
            </span>
            {(() => {
              const waiting = (pipeline.transcribed || 0) + (pipeline.analyzed || 0)
              if (!waiting) return null
              const minCost = (waiting * 0.0005).toFixed(2)
              const maxCost = (waiting * 0.003).toFixed(2)
              return (
                <div className="mt-1 text-red-700">
                  <span className="font-medium">{waiting.toLocaleString('de-DE')} Artikel</span>{' '}
                  warten — ca.{' '}
                  <span className="font-medium">
                    ${minCost}–${maxCost}
                  </span>{' '}
                  zum Verarbeiten.
                </div>
              )
            })()}
          </div>
          <button
            className="shrink-0 px-3 py-1 bg-red-700 hover:bg-red-800 text-white text-xs font-semibold rounded-lg transition-colors"
            title="Erst Guthaben bei requesty.ai aufladen, dann diesen Button klicken"
            onClick={async () => {
              if (
                !window.confirm(
                  'Hast du das Guthaben bei requesty.ai bereits aufgeladen?\n\nDer Button funktioniert nur wenn tatsächlich Budget vorhanden ist.'
                )
              )
                return
              try {
                await resetBudgetFlag()
                await triggerAutoPipeline()
                loadAll()
              } catch (e) {
                toast.error(e.message)
              }
            }}
          >
            ✓ Budget aufgeladen → Fortsetzen
          </button>
        </div>
      )}
      {/* Pipeline stuck warning — only show for very large backlogs to avoid false alarms */}
      {!data?.llm_budget_exceeded &&
        (pipeline.transcribed || 0) > 500 &&
        (pipeline.analyzing || 0) === 0 && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-amber-800">
                {(pipeline.transcribed || 0).toLocaleString('de')} Items warten auf Analyse —
                Pipeline möglicherweise blockiert.
              </span>
              <span className="text-amber-700 ml-1">
                Falls KI-Aufrufe fehlschlagen: Guthaben bei{' '}
                <a
                  href="https://requesty.ai"
                  target="_blank"
                  rel="noopener"
                  className="underline font-medium"
                >
                  requesty.ai
                </a>{' '}
                prüfen und ggf. aufladen.
              </span>
            </div>
          </div>
        )}

      {/* Pipeline bar */}
      {Object.keys(pipeline).length > 0 && (
        <div className="mb-5">
          <PipelineBar pipeline={pipeline} />
        </div>
      )}

      {/* Cleanup Widget — shown when there are irrelevant ideas */}
      {(() => {
        const SHK_KW = [
          'shk',
          'handwerk',
          'haustechnik',
          'sanitär',
          'heizung',
          'profi',
          'fachmagazin',
        ]
        const isSHK = (name) => SHK_KW.some((k) => (name || '').toLowerCase().includes(k))
        const irrelevantSources = (ideaBreakdown?.sources || []).filter(
          (s) => !isSHK(s.source_name) && s.new_count > 0
        )
        const totalIrrelevant = irrelevantSources.reduce((sum, s) => sum + s.new_count, 0)
        if (totalIrrelevant === 0) return null
        return (
          <div className="mb-5 rounded-xl border border-orange-200 bg-orange-50 overflow-hidden">
            <div className="px-4 py-2.5 bg-orange-100 border-b border-orange-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-orange-600">🧹</span>
                <span className="text-sm font-semibold text-orange-900">Bereinigung empfohlen</span>
                <span className="px-2 py-0.5 text-[10px] bg-orange-200 text-orange-800 rounded-full font-medium">
                  {totalIrrelevant.toLocaleString('de')} irrelevante Ideen
                </span>
              </div>
              {cleanupMsg ? (
                <span className="text-xs font-semibold text-emerald-700">{cleanupMsg}</span>
              ) : (
                <button
                  onClick={async () => {
                    if (
                      !window.confirm(
                        `${totalIrrelevant} neue Ideen aus nicht-SHK-Quellen archivieren?\n\nBetroffen: ${irrelevantSources.map((s) => s.source_name).join(', ')}`
                      )
                    )
                      return
                    setCleaningUp(true)
                    try {
                      const r = await bulkArchiveIdeas({ status: 'new' })
                      setCleanupMsg(`✓ ${r.archived} Ideen archiviert`)
                      setTimeout(() => {
                        setCleanupMsg(null)
                        loadAll()
                      }, 4000)
                    } catch (e) {
                      toast.error('Fehler: ' + e.message)
                    }
                    setCleaningUp(false)
                  }}
                  disabled={cleaningUp}
                  className="px-3 py-1 text-xs font-semibold bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {cleaningUp
                    ? 'Archiviere...'
                    : `Alle ${totalIrrelevant.toLocaleString('de')} archivieren`}
                </button>
              )}
            </div>
            <div className="px-4 py-2.5">
              <p className="text-xs text-orange-800 mb-2">
                Diese Quellen produzieren Ideen ohne SHK/Handwerk-Bezug — archiviere sie, um Platz
                für relevante Inhalte zu schaffen:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {irrelevantSources.slice(0, 6).map((src) => (
                  <span
                    key={src.source_id}
                    className="px-2 py-0.5 text-[10px] bg-white border border-orange-200 text-orange-700 rounded-full"
                  >
                    {src.source_name.length > 30
                      ? src.source_name.slice(0, 28) + '…'
                      : src.source_name}{' '}
                    · {src.new_count}
                  </span>
                ))}
                {irrelevantSources.length > 6 && (
                  <span className="px-2 py-0.5 text-[10px] text-orange-600">
                    +{irrelevantSources.length - 6} weitere
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })()}

      {/* SHK Analysis Progress Widget */}
      {(() => {
        const SHK_KW = [
          'shk',
          'handwerk',
          'haustechnik',
          'sanitär',
          'heizung',
          'profi',
          'ikz',
          'zvshk',
          'zdh',
          'wärmepumpen',
        ]
        const isSHK = (name) => SHK_KW.some((k) => (name || '').toLowerCase().includes(k))
        const shkWithItems = (sourceFunnel || []).filter((s) => isSHK(s.source_name) && s.items > 0)
        if (shkWithItems.length === 0 || data?.llm_budget_exceeded) return null
        const totalShkIdeas = shkWithItems.reduce((sum, s) => sum + (s.ideas || 0), 0)
        const allHaveIdeas = shkWithItems.every((s) => (s.ideas || 0) > 0)
        return (
          <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 overflow-hidden">
            <div className="px-4 py-2.5 bg-blue-100 border-b border-blue-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-600" />
                <span className="text-sm font-semibold text-blue-900">
                  {allHaveIdeas ? '✅ SHK-Quellen aktiv' : '🔄 SHK-Analyse läuft'}
                </span>
                {totalShkIdeas > 0 && (
                  <span className="px-2 py-0.5 text-[10px] bg-blue-200 text-blue-800 rounded-full font-medium">
                    {totalShkIdeas} Ideen verfügbar
                  </span>
                )}
              </div>
              {totalShkIdeas > 0 && (
                <button
                  onClick={() => navigate('/ideas')}
                  className="text-xs font-medium text-blue-700 hover:text-blue-900 flex items-center gap-1"
                >
                  Ideen ansehen <ArrowRight className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="px-4 py-3 space-y-2">
              {shkWithItems.map((s) => {
                const ideaCount = s.ideas || 0
                const pct = s.items > 0 ? Math.min(100, Math.round((ideaCount / s.items) * 100)) : 0
                return (
                  <div key={s.source_id} className="flex items-center gap-3">
                    <span className="text-xs text-blue-800 font-medium truncate flex-1 min-w-0">
                      {s.source_name}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-16 h-1.5 bg-blue-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-blue-600 w-16 text-right">
                        {s.items} →{' '}
                        <span
                          className={`font-semibold ${ideaCount > 0 ? 'text-emerald-700' : 'text-blue-400'}`}
                        >
                          {ideaCount}
                        </span>
                      </span>
                    </div>
                  </div>
                )
              })}
              {!allHaveIdeas && (
                <p className="text-[11px] text-blue-600 mt-1">
                  Ideen werden im Hintergrund generiert — Seite aktualisiert sich automatisch alle
                  30 Sek.
                </p>
              )}
            </div>
          </div>
        )
      })()}

      {/* Smart Insights */}
      <SmartInsights sourceFunnel={sourceFunnel} recentPosts={recentPosts} scheduled={scheduled} />

      {/* 12-Week Content Activity Calendar */}
      <ContentStreakCalendar posts={recentPosts} />

      {/* Phase 6.1 — Research-Vorschläge der Woche */}
      <div className="bg-white rounded-xl border border-surface-border p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-violet-500" /> Vorschläge der Woche
            <span className="text-[10px] font-normal text-ink-muted">— P07 Themen-Research</span>
          </h2>
        </div>
        <ResearchFindings limit={5} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Recent Ideas */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-accent-500" /> Neueste Content-Ideen
            </h2>
            <button
              onClick={() => navigate('/ideas')}
              className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
            >
              Alle <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {ideas.length === 0 ? (
            <div className="text-center py-8">
              <Lightbulb className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-ink-light">Noch keine Ideen.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {ideas.slice(0, 6).map((idea) => {
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
                    className="py-2.5 flex items-center justify-between cursor-pointer hover:bg-gray-50 -mx-2 px-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-medium ${statusInfo.color}`}
                      >
                        {statusInfo.label}
                      </span>
                      <span className="text-sm text-ink truncate">{idea.title}</span>
                    </div>
                    <span className="text-xs text-ink-muted shrink-0 ml-2">{idea.angle}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* System status + recent content */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-surface-border p-5">
            <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-ink-light" /> System-Status
            </h2>
            <div className="space-y-2.5">
              {[
                {
                  label: 'Quellen',
                  value: data?.active_sources?.length || 0,
                  color: 'text-blue-700 bg-blue-50',
                },
                {
                  label: 'In Verarbeitung',
                  value: s.processing || 0,
                  color: 'text-yellow-700 bg-yellow-50',
                },
                {
                  label: 'Posts (Entwurf)',
                  value: s.drafts || 0,
                  color: 'text-primary-700 bg-primary-50',
                },
                {
                  label: 'Posts (Freigegeben)',
                  value: s.approved || 0,
                  color: 'text-emerald-700 bg-emerald-50',
                },
                {
                  label: 'Posts (Eingeplant)',
                  value: scheduled.length,
                  color: 'text-teal-700 bg-teal-50',
                },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between">
                  <span className="text-xs text-ink-muted">{row.label}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${row.color}`}>
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Upcoming scheduled posts */}
          <div className="bg-white rounded-xl border border-surface-border p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold text-ink flex items-center gap-2">
                <CalendarDays className="w-3.5 h-3.5 text-primary-600" /> Nächste Posts
              </h2>
              <button
                onClick={() => navigate('/calendar')}
                className="text-[11px] text-primary-600 hover:underline"
              >
                Kalender →
              </button>
            </div>
            {scheduled.length === 0 ? (
              <p className="text-[11px] text-ink-muted py-2">Noch keine Posts eingeplant.</p>
            ) : (
              <div className="space-y-1.5">
                {scheduled.slice(0, 4).map((sp, i) => {
                  const dt = new Date(sp.scheduled_at)
                  const isToday = dt.toDateString() === new Date().toDateString()
                  return (
                    <div
                      key={sp.id || i}
                      className={`flex items-center gap-2 p-1.5 rounded-lg ${isToday ? 'bg-emerald-50' : 'hover:bg-gray-50'}`}
                    >
                      <span
                        className={`text-[10px] font-mono font-semibold shrink-0 ${isToday ? 'text-emerald-700' : 'text-ink-muted'}`}
                      >
                        {dt.toLocaleDateString('de-DE', {
                          weekday: 'short',
                          day: '2-digit',
                          month: '2-digit',
                        })}{' '}
                        {dt.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {isToday && (
                        <span className="text-[10px] bg-emerald-200 text-emerald-800 px-1 rounded shrink-0">
                          Heute
                        </span>
                      )}
                    </div>
                  )
                })}
                {scheduled.length > 4 && (
                  <p className="text-[10px] text-ink-muted pl-1.5">
                    + {scheduled.length - 4} weitere bis{' '}
                    {new Date(scheduled[scheduled.length - 1].scheduled_at).toLocaleDateString(
                      'de-DE',
                      { day: '2-digit', month: '2-digit' }
                    )}
                  </p>
                )}
              </div>
            )}
          </div>

          <FrequencyAdvisor approved={s.approved} drafts={s.drafts} />

          {/* Trending Keywords */}
          {data?.trending_keywords?.length > 0 && (
            <div className="bg-white rounded-xl border border-surface-border p-5">
              <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-primary-500" /> Trending Themen (30 Tage)
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {data.trending_keywords.slice(0, 20).map((kw, i) => {
                  const maxCount = data.trending_keywords[0]?.count || 1
                  const opacity = 0.4 + 0.6 * (kw.count / maxCount)
                  const size =
                    kw.count >= maxCount * 0.7
                      ? 'text-xs font-semibold'
                      : kw.count >= maxCount * 0.4
                        ? 'text-[11px] font-medium'
                        : 'text-[10px]'
                  return (
                    <span
                      key={i}
                      className={`px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 border border-primary-100 ${size} transition-opacity`}
                      style={{ opacity }}
                      title={`${kw.count}× erwähnt`}
                    >
                      {kw.keyword}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          <div className="p-3 bg-primary-50 rounded-xl border border-primary-100 flex items-start gap-2">
            <CalendarDays className="w-4 h-4 text-primary-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-primary-800">Nächster Schritt</p>
              <p className="text-[11px] text-primary-600 mt-0.5 leading-relaxed">
                {scheduled.length > 0
                  ? `${scheduled.length} Posts eingeplant — nächster am ${new Date(scheduled[0].scheduled_at).toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' })} um ${new Date(scheduled[0].scheduled_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} Uhr`
                  : s.approved > 0
                    ? `${s.approved} Posts freigegeben → Auto-Einplanen in Posts`
                    : s.drafts > 0
                      ? `${s.drafts} Entwürfe → Triage-Modus in Posts öffnen`
                      : 'Pipeline läuft — bald neue Posts verfügbar'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
