import { useState, useEffect, useMemo } from 'react'
import {
  BarChart3,
  TrendingUp,
  FileText,
  CheckCircle2,
  Hash,
  Calendar,
  Clock,
  Radio,
  Award,
  Cpu,
} from 'lucide-react'
import {
  getContentList,
  getBestPostingTimes,
  getSourceFunnel,
  getLLMCostHistory,
  getLLMProviders,
  getQualitySummary,
  getProductionHeatmap,
  getIdeasStats,
  getQualityByModel,
  getQualityRecent,
} from '../api'

// Minimal quality scorer (mirrors Posts.jsx postScore)
function quickScore(text) {
  if (!text || text.length < 30) return { score: 0, grade: 'F' }
  let pts = 0
  const len = text.length
  if (len >= 600 && len <= 1500) pts += 5
  else if (len >= 400) pts += 3
  else if (len >= 200) pts += 1
  if (/\?/.test(text.slice(0, 210))) pts += 1
  if (text.length > 30 && !text.slice(0, 210).startsWith(' ')) pts += 1
  if (text.split(/\n\n+/).length >= 3) pts += 1
  const emojiCount = [...text].filter((c) => /\p{Emoji}/u.test(c) && c !== ' ').length
  if (emojiCount >= 1 && emojiCount <= 8) pts += 1
  if (/\?/.test(text.slice(-200))) pts += 1
  const score = Math.min(10, Math.round(pts))
  const grade = score >= 8 ? 'A' : score >= 6 ? 'B' : score >= 4 ? 'C' : score >= 2 ? 'D' : 'F'
  return { score, grade }
}

function StatCard({ icon: Icon, label, value, sub, color = 'teal' }) {
  // purple bewusst behalten: 4. KPI-Kachel-Farbe (Kanäle) neben den 3 migrierten
  // (teal/emerald/amber -> primary/status-fertig/accent), kein 1:1-Primitive-Äquivalent.
  const bg = {
    teal: 'bg-primary-50',
    emerald: 'bg-status-fertig-bg',
    amber: 'bg-accent-50',
    purple: 'bg-purple-50',
  }[color]
  const text = {
    teal: 'text-primary-700',
    emerald: 'text-status-fertig-text',
    amber: 'text-accent-700',
    purple: 'text-purple-700',
  }[color]
  return (
    <div className="bg-white rounded-xl border border-surface-border p-4">
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${bg}`}>
          <Icon className={`w-4.5 h-4.5 ${text}`} />
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

function HBar({ label, count, max, color = 'bg-primary-500', badge }) {
  const pct = max > 0 ? Math.max(4, (count / max) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 text-xs text-ink-muted text-right shrink-0 truncate">{label}</span>
      <div className="flex-1 h-5 bg-surface-bg rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-xs font-semibold text-ink text-right shrink-0">{count}</span>
      {badge && <span className="text-[10px] text-ink-muted shrink-0">{badge}</span>}
    </div>
  )
}

// Get ISO week string "YYYY-Www" for grouping
function isoWeek(dateStr) {
  const d = new Date(dateStr)
  const jan4 = new Date(d.getFullYear(), 0, 4)
  const startOfWeek1 = new Date(jan4)
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7))
  const diff = d - startOfWeek1
  const week = Math.floor(diff / (7 * 86400000)) + 1
  return `${d.getFullYear()}-W${String(week).padStart(2, '0')}`
}

// Last N weeks labels
function lastNWeeks(n) {
  const weeks = []
  const now = new Date()
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i * 7)
    weeks.push(isoWeek(d.toISOString()))
  }
  return weeks
}

const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const DAY_NAMES_LONG = [
  'Montag',
  'Dienstag',
  'Mittwoch',
  'Donnerstag',
  'Freitag',
  'Samstag',
  'Sonntag',
]
const HEAT_HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

function heatColor(v, max) {
  if (!v || !max) return 'bg-surface-bg'
  const t = v / max
  // Zwischentöne bewusst behalten: 5-stufige Heatmap-Intensitätsskala, status-fertig-
  // Token deckt nur die dunkelste Stufe exakt ab.
  if (t >= 0.9) return 'bg-emerald-600'
  if (t >= 0.7) return 'bg-status-fertig-border'
  if (t >= 0.5) return 'bg-emerald-400'
  if (t >= 0.3) return 'bg-emerald-300'
  if (t > 0) return 'bg-status-fertig-bg'
  return 'bg-surface-bg'
}

function PostingHeatmap({ data }) {
  const { heatmap, recommendations, tip } = data
  const allVals = Object.values(heatmap).flat()
  const maxVal = Math.max(...allVals, 1)

  return (
    <div className="bg-white rounded-xl border border-surface-border p-5">
      <h2 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
        <Clock className="w-4 h-4 text-primary-600" /> Beste Posting-Zeiten
      </h2>
      {tip && <p className="text-[11px] text-ink-muted mb-4">{tip}</p>}

      {/* Heatmap grid */}
      <div className="overflow-x-auto">
        <div className="min-w-[420px]">
          {/* Hour labels */}
          <div className="flex mb-1 ml-8">
            {HEAT_HOURS.map((h) => (
              <div key={h} className="flex-1 text-center text-[9px] text-ink-muted">
                {h}
              </div>
            ))}
          </div>
          {/* Rows */}
          {[0, 1, 2, 3, 4, 5, 6].map((day) => {
            const dayVals = heatmap[String(day)] || []
            return (
              <div key={day} className="flex items-center mb-1">
                <span className="w-8 text-[10px] text-ink-muted text-right pr-2 shrink-0">
                  {DAY_NAMES[day]}
                </span>
                {HEAT_HOURS.map((h) => {
                  const v = dayVals[h] || 0
                  return (
                    <div
                      key={h}
                      className={`flex-1 h-5 mx-0.5 rounded-sm ${heatColor(v, maxVal)} cursor-default`}
                      title={`${DAY_NAMES_LONG[day]} ${h}:00 — Score: ${v}`}
                    />
                  )
                })}
              </div>
            )
          })}
          {/* Legend */}
          <div className="flex items-center gap-2 mt-2 ml-8">
            <span className="text-[9px] text-ink-muted">Wenig</span>
            {/* Zwischentöne bewusst behalten: siehe heatColor() oben */}
            {[
              'bg-status-fertig-bg',
              'bg-emerald-300',
              'bg-emerald-400',
              'bg-status-fertig-border',
              'bg-emerald-600',
            ].map((c) => (
              <div key={c} className={`w-4 h-3 rounded-sm ${c}`} />
            ))}
            <span className="text-[9px] text-ink-muted">Viel</span>
          </div>
        </div>
      </div>

      {/* Top recommendations */}
      {recommendations?.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-[11px] font-semibold text-ink-muted uppercase tracking-wide">
            Top Empfehlungen
          </p>
          {recommendations.slice(0, 3).map((r) => (
            <div
              key={r.day}
              className="flex items-center gap-3 bg-status-fertig-bg rounded-lg px-3 py-2"
            >
              <span className="w-20 text-xs font-semibold text-status-fertig-text shrink-0">
                {r.day_name}
              </span>
              <div className="flex gap-1 flex-wrap">
                {(r.hours || []).map((h) => (
                  <span
                    key={h}
                    className="px-1.5 py-0.5 bg-status-fertig-border/40 text-status-fertig-text rounded text-[10px] font-mono"
                  >
                    {h}:00
                  </span>
                ))}
              </div>
              {r.note && (
                <span className="text-[10px] text-status-fertig-text ml-auto shrink-0">
                  {r.note}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Model Recommendations Panel ────────────────────────────────────────────
const STEP_LABELS = {
  transcription: 'Transkription',
  analysis: 'Analyse',
  ideation: 'Ideation',
  post_generation: 'Post-Generierung',
  smart_questions: 'Smarte Fragen',
}
const KNOWN_COSTS = {
  'gemini-2.0-flash': 0.075,
  'gemini-2.5-flash': 0.15,
  'gemini-2.5-flash-lite': 0.075,
  'mistral-medium-latest': 0.4,
  'mistral-small-latest': 0.1,
  'gpt-4.1-mini': 0.4,
  'claude-haiku-4-5': 0.8,
  'claude-sonnet-4': 3.0,
}

function ModelRecommendationsPanel({ models }) {
  // Group by step, find best model per step
  const byStep = {}
  models.forEach((row) => {
    if (!byStep[row.step]) byStep[row.step] = []
    byStep[row.step].push(row)
  })

  const recommendations = Object.entries(byStep).map(([step, rows]) => {
    const best = rows.reduce((a, b) => (a.avg_quality >= b.avg_quality ? a : b))
    const shortModel = best.model ? best.model.split('/').pop() : '?'
    const cost = KNOWN_COSTS[shortModel] ?? null
    const conf = { high: '🟢', medium: '🟡', low: '🔴' }[best.confidence] || '🔴'
    return { step, best, shortModel, cost, conf }
  })

  if (recommendations.length === 0) return null

  return (
    <div className="bg-white rounded-xl border border-surface-border shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-4 h-4 text-status-fertig-text" />
        <h2 className="text-base font-semibold text-ink">Modell-Empfehlungen</h2>
        <span className="text-xs text-ink-muted ml-1">
          Basierend auf gesammelten Qualitätsdaten
        </span>
      </div>
      <div className="space-y-2 mb-4">
        {recommendations.map(({ step, best, shortModel, cost, conf }) => (
          <div
            key={step}
            className="flex items-center gap-3 py-2 border-b border-surface-border last:border-0"
          >
            <div className="w-28 text-xs text-ink-muted shrink-0">{STEP_LABELS[step] || step}</div>
            <div className="flex-1 flex items-center gap-2 min-w-0">
              <span className="font-mono text-xs text-status-neu-text truncate">{shortModel}</span>
              <span
                className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                  best.avg_quality >= 80
                    ? 'bg-status-fertig-bg text-status-fertig-text'
                    : best.avg_quality >= 60
                      ? 'bg-status-aktiv-bg text-status-aktiv-text'
                      : 'bg-status-fehler-bg text-status-fehler-text'
                }`}
              >
                {best.avg_quality.toFixed(0)}/100
              </span>
              {cost != null && <span className="text-[10px] text-ink-muted">${cost}/1M</span>}
            </div>
            <span className="text-[11px] shrink-0">
              {conf} {best.count} Tests
            </span>
          </div>
        ))}
      </div>

      {/* Cost optimization tip */}
      <div className="bg-status-aktiv-bg border border-status-aktiv-border rounded-lg p-3 text-xs text-status-aktiv-text">
        <span className="font-semibold">💡 Kosten-Tipp:</span> Gemini Flash (0.075$/1M) liefert{' '}
        {recommendations
          .find((r) => r.shortModel.includes('gemini'))
          ?.best.avg_quality.toFixed(0) || '~97'}
        /100 Qualität bei Analyse — 10× günstiger als Claude Haiku (0.80$/1M). Routing-Konfiguration
        unter <strong>Einstellungen → KI-Provider → Live Routing Override</strong>.
      </div>

      <p className="text-[10px] text-ink-muted mt-2">
        🟢 verlässlich (n≥30) · 🟡 vorläufig (n≥5) · 🔴 wenig Daten · Daten wachsen mit jedem
        Pipeline-Lauf
      </p>
    </div>
  )
}

export default function Analytics() {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [bestTimes, setBestTimes] = useState(null)
  const [sourceFunnel, setSourceFunnel] = useState(null)
  const [llmCostHistory, setLlmCostHistory] = useState(null)
  const [llmProviders, setLlmProviders] = useState([])
  const [costDays, setCostDays] = useState(7)
  const [qualitySummary, setQualitySummary] = useState(null)
  const [modelData, setModelData] = useState(null)
  const [modelStep, setModelStep] = useState('')
  const [heatmap, setHeatmap] = useState(null)
  const [ideasStats, setIdeasStats] = useState(null)
  const [qualityRecent, setQualityRecent] = useState(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [
          page1,
          page2,
          times,
          funnel,
          costHist,
          providers,
          qualSum,
          heatmapData,
          ideaSt,
          modelComp,
          qualRecent,
        ] = await Promise.all([
          getContentList({ limit: 200, offset: 0 }),
          getContentList({ limit: 200, offset: 200 }),
          getBestPostingTimes().catch(() => null),
          getSourceFunnel().catch(() => null),
          getLLMCostHistory(costDays).catch(() => null),
          getLLMProviders().catch(() => []),
          getQualitySummary(30).catch(() => null),
          getProductionHeatmap(90).catch(() => null),
          getIdeasStats().catch(() => null),
          getQualityByModel(30, modelStep || undefined).catch(() => null),
          getQualityRecent(30).catch(() => null),
        ])
        setPosts([...(page1 || []), ...(page2 || [])])
        setBestTimes(times)
        setSourceFunnel(funnel)
        setLlmCostHistory(costHist)
        setLlmProviders(Array.isArray(providers) ? providers : [])
        setHeatmap(heatmapData)
        setQualitySummary(qualSum)
        setIdeasStats(ideaSt)
        setModelData(modelComp)
        setQualityRecent(Array.isArray(qualRecent) ? qualRecent : null)
      } catch (e) {
        setError(e.message)
      }
      setLoading(false)
    }
    load()
  }, [costDays, modelStep])

  const stats = useMemo(() => {
    if (!posts.length) return null

    // Status breakdown
    const byStatus = {}
    posts.forEach((p) => {
      byStatus[p.status] = (byStatus[p.status] || 0) + 1
    })

    // Channel breakdown
    const byChannel = {}
    posts.forEach((p) => {
      const ch = p.channel || 'unbekannt'
      byChannel[ch] = (byChannel[ch] || 0) + 1
    })

    // Angle breakdown (from metadata)
    const byAngle = {}
    posts.forEach((p) => {
      const angle = p.content_metadata?.angle
      if (angle) byAngle[angle] = (byAngle[angle] || 0) + 1
    })

    // Weekly volume (last 8 weeks)
    const weeks = lastNWeeks(8)
    const byWeek = {}
    weeks.forEach((w) => {
      byWeek[w] = 0
    })
    posts.forEach((p) => {
      if (p.created_at) {
        const w = isoWeek(p.created_at)
        if (byWeek[w] !== undefined) byWeek[w]++
      }
    })

    // Avg char count
    const withText = posts.filter((p) => p.content_text)
    const avgChars = withText.length
      ? Math.round(withText.reduce((a, p) => a + p.content_text.length, 0) / withText.length)
      : 0

    // Avg chars by channel (approved only)
    const approvedByChannel = {}
    posts
      .filter((p) => p.status === 'approved')
      .forEach((p) => {
        const ch = p.channel || 'unbekannt'
        if (!approvedByChannel[ch]) approvedByChannel[ch] = { total: 0, count: 0 }
        approvedByChannel[ch].total += (p.content_text || '').length
        approvedByChannel[ch].count++
      })

    // Pillar distribution
    // violet/sky/pink bewusst behalten: 5 unterscheidbare Content-Säulen-Badges ohne
    // Status-Bedeutung (analog Posts.jsx Content-Säulen); teal/amber sind primitive-
    // identisch zu primary-*/accent-* und deshalb migriert.
    const PILLAR_CFG = {
      thought_leadership: { label: 'Thought Leadership', emoji: '💡', bar: 'bg-violet-400' },
      how_to: { label: 'How-To / Anleitung', emoji: '🛠', bar: 'bg-primary-400' },
      personal_story: { label: 'Persönliche Story', emoji: '📖', bar: 'bg-accent-400' },
      industry_news: { label: 'Branchennews', emoji: '📰', bar: 'bg-sky-400' },
      product_service: { label: 'Produkt / Service', emoji: '🎯', bar: 'bg-pink-400' },
    }
    const byPillar = {}
    let pillarAssigned = 0
    posts.forEach((p) => {
      const pillar = p.content_metadata?.pillar
      if (pillar) {
        byPillar[pillar] = (byPillar[pillar] || 0) + 1
        pillarAssigned++
      }
    })

    // Quality distribution across all drafts (Cycle 42)
    const gradeDist = { A: 0, B: 0, C: 0, D: 0, F: 0 }
    const scoreHist = { '0-2': 0, '3-4': 0, '5-6': 0, '7-8': 0, '9-10': 0 }
    const draftScores = []
    posts
      .filter((p) => p.status === 'draft' && p.content_text)
      .forEach((p) => {
        const { score, grade } = quickScore(p.content_text)
        gradeDist[grade] = (gradeDist[grade] || 0) + 1
        if (score <= 2) scoreHist['0-2']++
        else if (score <= 4) scoreHist['3-4']++
        else if (score <= 6) scoreHist['5-6']++
        else if (score <= 8) scoreHist['7-8']++
        else scoreHist['9-10']++
        draftScores.push({ id: p.id, score, grade, preview: (p.content_text || '').slice(0, 120) })
      })
    const topPosts = draftScores.sort((a, b) => b.score - a.score).slice(0, 5)
    const readyToApprove = (gradeDist['A'] || 0) + (gradeDist['B'] || 0)

    // Draft aging (Cycle 45)
    const now = Date.now()
    const ageBuckets = { fresh: 0, week: 0, twoweeks: 0, month: 0, old: 0 }
    const oldestDrafts = []
    posts
      .filter((p) => p.status === 'draft' && p.created_at)
      .forEach((p) => {
        const ageDays = Math.floor((now - new Date(p.created_at)) / 86400000)
        if (ageDays < 7) ageBuckets.fresh++
        else if (ageDays < 14) ageBuckets.week++
        else if (ageDays < 30) ageBuckets.twoweeks++
        else if (ageDays < 90) ageBuckets.month++
        else ageBuckets.old++
        oldestDrafts.push({ id: p.id, ageDays, preview: (p.content_text || '').slice(0, 100) })
      })
    oldestDrafts.sort((a, b) => b.ageDays - a.ageDays)
    const top5Oldest = oldestDrafts.slice(0, 5)

    return {
      byStatus,
      byChannel,
      byAngle,
      byWeek,
      weeks,
      avgChars,
      approvedByChannel,
      byPillar,
      pillarAssigned,
      PILLAR_CFG,
      gradeDist,
      scoreHist,
      topPosts,
      readyToApprove,
      ageBuckets,
      top5Oldest,
    }
  }, [posts])

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Analytics...</div>
  if (error)
    return (
      <div className="p-4 bg-status-fehler-bg text-status-fehler-text rounded-lg text-sm">
        {error}
      </div>
    )
  // Empty-State mit AUSWEG. Ein nacktes "Keine Daten vorhanden." sagt dem
  // Betreiber nicht, ob etwas kaputt ist oder er nur noch nichts angelegt hat —
  // und schon gar nicht, was er tun soll. Analytics wertet Content aus; ohne
  // Quellen gibt es keinen Content und damit nichts auszuwerten. Genau das
  // steht jetzt da, samt Weg zur Ursache.
  if (!stats)
    return (
      <div className="text-center py-16 px-4">
        <BarChart3 className="w-10 h-10 mx-auto mb-3 text-ink-muted opacity-40" />
        <p className="text-sm font-medium text-ink mb-1">Noch keine Auswertung möglich</p>
        <p className="text-xs text-ink-muted max-w-md mx-auto">
          Analytics wertet generierte Posts aus. Sobald die Pipeline aus deinen Quellen den ersten
          Content erzeugt hat, erscheinen hier Kennzahlen zu Kanälen, Formaten und
          Veröffentlichungen.
        </p>
        <p className="text-xs text-ink-muted mt-3">
          Noch keine Quellen angelegt? Unter <strong>Quellen</strong> hinzufügen — der Rest läuft
          automatisch.
        </p>
      </div>
    )

  const {
    byStatus,
    byChannel,
    byAngle,
    byWeek,
    weeks,
    avgChars,
    approvedByChannel,
    byPillar,
    pillarAssigned,
    PILLAR_CFG,
    gradeDist,
    scoreHist,
    topPosts,
    readyToApprove,
    ageBuckets,
    top5Oldest,
  } = stats

  const totalPosts = posts.length
  const approved = byStatus.approved || 0
  const drafts = byStatus.draft || 0
  const published = byStatus.published || 0
  const channels = Object.keys(byChannel).length

  const maxWeekCount = Math.max(...Object.values(byWeek), 1)
  const maxChannel = Math.max(...Object.values(byChannel), 1)
  const maxAngle = Math.max(...Object.values(byAngle), 1)

  // purple bewusst behalten: 6. unterscheidbare Kanal-Kategoriefarbe neben den 5
  // migrierten, kein 1:1-Primitive-Äquivalent im Tier-1-System.
  const channelColors = [
    'bg-primary-500',
    'bg-primary-500',
    'bg-status-neu-border',
    'bg-purple-400',
    'bg-accent-400',
    'bg-status-fertig-border',
  ]
  const weekColors = 'bg-primary-400'

  // bar-Feld ergänzt: die Badge-Farbe (color) ist die helle bg-*-Variante, das
  // Balkendiagramm darunter braucht den kräftigeren Ton — vorher per String-Replace
  // aus 'color' abgeleitet (Annahme: Klassenname endet auf "-100"), das funktioniert
  // mit Tier-2-Token-Namen nicht mehr, deshalb jetzt explizit gepflegt.
  const statusLabels = {
    draft: {
      label: 'Entwurf',
      color: 'bg-status-aktiv-bg text-status-aktiv-text',
      bar: 'bg-status-aktiv-border',
    },
    approved: {
      label: 'Freigegeben',
      color: 'bg-status-fertig-bg text-status-fertig-text',
      bar: 'bg-status-fertig-border',
    },
    published: {
      label: 'Veröffentlicht',
      color: 'bg-primary-100 text-primary-700',
      bar: 'bg-primary-400',
    },
    rejected: {
      label: 'Verworfen',
      color: 'bg-status-fehler-bg text-status-fehler-text',
      bar: 'bg-status-fehler-border',
    },
    scheduled: {
      label: 'Geplant',
      color: 'bg-status-neu-bg text-status-neu-text',
      bar: 'bg-status-neu-border',
    },
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Analytics</h1>
          <p className="text-sm text-ink-light mt-0.5">
            Content-Volumen & Zusammensetzung — {totalPosts} Posts analysiert
          </p>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard
          icon={FileText}
          label="Posts gesamt"
          value={totalPosts}
          color="teal"
          sub={`Ø ${avgChars} Zeichen`}
        />
        <StatCard
          icon={CheckCircle2}
          label="Freigegeben"
          value={approved}
          color="emerald"
          sub={totalPosts > 0 ? `${Math.round((approved / totalPosts) * 100)}% der Posts` : null}
        />
        <StatCard
          icon={TrendingUp}
          label="Entwürfe"
          value={drafts}
          color="amber"
          sub={published > 0 ? `${published} veröffentlicht` : 'Noch nichts publiziert'}
        />
        <StatCard
          icon={Hash}
          label="Kanäle"
          value={channels}
          color="purple"
          sub={Object.keys(byChannel).slice(0, 2).join(', ')}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        {/* Weekly Volume */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary-600" /> Posts pro Woche (letzte 8 Wochen)
          </h2>
          <div className="flex items-end gap-2 h-32">
            {weeks.map((w) => {
              const count = byWeek[w] || 0
              const pct = maxWeekCount > 0 ? (count / maxWeekCount) * 100 : 0
              const label = w.split('-W')[1] ? `KW${w.split('-W')[1]}` : w
              return (
                <div key={w} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-[10px] font-semibold text-ink-muted">
                    {count > 0 ? count : ''}
                  </span>
                  <div className="w-full flex items-end" style={{ height: '80px' }}>
                    <div
                      className={`w-full rounded-t-md ${weekColors} transition-all`}
                      style={{ height: `${Math.max(pct, count > 0 ? 5 : 0)}%` }}
                      title={`${label}: ${count} Posts`}
                    />
                  </div>
                  <span className="text-[9px] text-ink-muted">{label}</span>
                </div>
              )
            })}
          </div>
          <p className="text-[11px] text-ink-muted mt-2 text-center">
            Ø {Math.round(Object.values(byWeek).reduce((a, b) => a + b, 0) / weeks.length)}{' '}
            Posts/Woche
          </p>
        </div>

        {/* Status Breakdown */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary-600" /> Status-Verteilung
          </h2>
          <div className="space-y-2.5 mb-4">
            {Object.entries(byStatus)
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => {
                const pct = totalPosts > 0 ? Math.round((count / totalPosts) * 100) : 0
                const info = statusLabels[status] || {
                  label: status,
                  color: 'bg-surface-bg text-ink-light',
                  bar: 'bg-ink-muted',
                }
                return (
                  <div key={status} className="flex items-center gap-3">
                    <span
                      className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium ${info.color}`}
                    >
                      {info.label}
                    </span>
                    <div className="flex-1 h-4 bg-surface-bg rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${info.bar}`}
                        style={{ width: `${Math.max(pct, 3)}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold text-ink w-8 text-right">{count}</span>
                    <span className="text-[10px] text-ink-muted w-8">{pct}%</span>
                  </div>
                )
              })}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        {/* Channel Breakdown */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <Hash className="w-4 h-4 text-primary-600" /> Kanal-Verteilung
          </h2>
          <div className="space-y-2.5">
            {Object.entries(byChannel)
              .sort((a, b) => b[1] - a[1])
              .map(([ch, count], i) => {
                const avgCh = approvedByChannel[ch]
                const avgStr =
                  avgCh?.count > 0 ? `Ø ${Math.round(avgCh.total / avgCh.count)} Z.` : null
                return (
                  <HBar
                    key={ch}
                    label={ch}
                    count={count}
                    max={maxChannel}
                    color={channelColors[i % channelColors.length]}
                    badge={avgStr}
                  />
                )
              })}
          </div>
        </div>

        {/* Angle Breakdown */}
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary-600" /> Post-Winkel (Angle)
          </h2>
          {Object.keys(byAngle).length === 0 ? (
            <p className="text-sm text-ink-muted py-4 text-center">
              Kein Angle-Metadaten vorhanden
            </p>
          ) : (
            <div className="space-y-2.5">
              {Object.entries(byAngle)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([angle, count]) => (
                  <HBar
                    key={angle}
                    label={angle}
                    count={count}
                    max={maxAngle}
                    color="bg-accent-400"
                  />
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Content Pillar Distribution */}
      <div className="bg-white rounded-xl border border-surface-border p-5 mb-5">
        <h2 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
          {/* violet bewusst behalten: Panel-Icon, passend zu den violet-Content-Säulen oben */}
          <BarChart3 className="w-4 h-4 text-violet-600" /> Content-Säulen Verteilung
        </h2>
        <p className="text-[11px] text-ink-muted mb-4">
          {pillarAssigned > 0
            ? `${pillarAssigned} von ${posts.length} Posts haben eine Content-Säule zugewiesen (${Math.round((pillarAssigned / posts.length) * 100)}%)`
            : 'Noch keine Content-Säulen zugewiesen — öffne einen Post und weise eine Säule zu.'}
        </p>
        {pillarAssigned > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2.5">
            {Object.entries(PILLAR_CFG).map(([key, cfg]) => {
              const count = byPillar[key] || 0
              const pct = pillarAssigned > 0 ? Math.round((count / pillarAssigned) * 100) : 0
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="w-6 text-base shrink-0 text-center">{cfg.emoji}</span>
                  <span className="w-36 text-xs text-ink-muted shrink-0 truncate">{cfg.label}</span>
                  <div className="flex-1 h-4 bg-surface-bg rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${cfg.bar}`}
                      style={{ width: `${Math.max(count > 0 ? 4 : 0, pct)}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-ink w-6 text-right shrink-0">
                    {count}
                  </span>
                  <span className="text-[10px] text-ink-muted w-8 shrink-0">{pct}%</span>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(PILLAR_CFG).map(([key, cfg]) => (
              <div
                key={key}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-bg border border-surface-border text-xs text-ink-muted"
              >
                <span>{cfg.emoji}</span>
                <span>{cfg.label}</span>
                <span className="text-ink-muted">—</span>
                <span className="font-semibold">0</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Source Productivity Funnel */}
      {sourceFunnel && sourceFunnel.length > 0 && (
        <div className="bg-white rounded-xl border border-surface-border p-5 mb-5">
          <h2 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
            <Radio className="w-4 h-4 text-primary-600" /> Quellen-Produktivität
          </h2>
          <p className="text-[11px] text-ink-muted mb-4">
            Funnel pro Quelle: Gescraped → Ideen → Posts → Freigegeben → Veröffentlicht
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border">
                  <th className="text-left py-2 pr-4 text-ink-muted font-medium">Quelle</th>
                  <th className="text-right py-2 px-2 text-ink-muted font-medium">Items</th>
                  <th className="text-right py-2 px-2 text-ink-muted font-medium">Ideen</th>
                  <th className="text-right py-2 px-2 text-ink-muted font-medium">Posts</th>
                  <th className="text-right py-2 px-2 text-ink-muted font-medium">Freigeg.</th>
                  <th className="text-right py-2 px-2 text-ink-muted font-medium">Publik.</th>
                  <th className="text-right py-2 pl-2 text-ink-muted font-medium">Approval-Rate</th>
                </tr>
              </thead>
              <tbody>
                {sourceFunnel.slice(0, 12).map((s, i) => {
                  const typeIcon =
                    s.source_type === 'youtube'
                      ? '▶'
                      : s.source_type === 'rss'
                        ? '📡'
                        : s.source_type === 'podcast'
                          ? '🎙'
                          : '🌐'
                  const approvalPct = s.approval_rate
                  const barColor =
                    approvalPct >= 50
                      ? 'bg-status-fertig-border'
                      : approvalPct >= 20
                        ? 'bg-status-aktiv-border'
                        : 'bg-status-fehler-border'
                  return (
                    <tr
                      key={s.source_id}
                      className={`border-b border-surface-border ${i % 2 === 0 ? '' : 'bg-surface-bg/50'} hover:bg-primary-50/30`}
                    >
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-1.5 max-w-[220px]">
                          <span className="text-[10px]">{typeIcon}</span>
                          <span className="truncate font-medium text-ink" title={s.source_name}>
                            {s.source_name}
                          </span>
                        </div>
                      </td>
                      <td className="text-right py-2 px-2 font-semibold text-ink tabular-nums">
                        {s.items.toLocaleString('de')}
                      </td>
                      <td className="text-right py-2 px-2 text-ink-muted tabular-nums">
                        {s.ideas.toLocaleString('de')}
                      </td>
                      <td className="text-right py-2 px-2 text-ink-muted tabular-nums">
                        {s.posts.toLocaleString('de')}
                      </td>
                      <td className="text-right py-2 px-2 text-status-fertig-text font-medium tabular-nums">
                        {s.approved.toLocaleString('de')}
                      </td>
                      <td className="text-right py-2 px-2 text-primary-700 font-semibold tabular-nums">
                        {s.published.toLocaleString('de')}
                      </td>
                      <td className="py-2 pl-2">
                        <div className="flex items-center gap-2 justify-end">
                          <div className="w-16 h-2 bg-surface-bg rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${barColor}`}
                              style={{ width: `${Math.max(approvalPct, s.approved > 0 ? 4 : 0)}%` }}
                            />
                          </div>
                          <span
                            className={`tabular-nums font-medium ${approvalPct >= 50 ? 'text-status-fertig-text' : approvalPct >= 20 ? 'text-status-aktiv-text' : 'text-status-fehler-text'}`}
                          >
                            {approvalPct}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {sourceFunnel.length > 12 && (
            <p className="text-[11px] text-ink-muted mt-3 text-center">
              Top 12 von {sourceFunnel.length} Quellen
            </p>
          )}
        </div>
      )}

      {/* Draft Aging Report (Cycle 45) */}
      {Object.values(ageBuckets).some((v) => v > 0) && (
        <div className="bg-white rounded-xl border border-surface-border p-5 mb-6">
          <h2 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-accent-500" /> Entwurfs-Alter — Backlog-Übersicht
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Age distribution bars */}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-3">
                Altersverteilung der Entwürfe
              </p>
              {[
                {
                  key: 'fresh',
                  label: '< 7 Tage',
                  color: 'bg-status-fertig-bg',
                  textColor: 'text-status-fertig-text',
                },
                {
                  key: 'week',
                  label: '7–14 Tage',
                  color: 'bg-status-aktiv-bg',
                  textColor: 'text-status-aktiv-text',
                },
                {
                  key: 'twoweeks',
                  label: '14–30 Tage',
                  // orange bewusst behalten: 5. Alters-Stufe zwischen aktiv(week)/fehler(month,old),
                  // kein eigener Status-Token für diese Zwischenstufe (analog Posts.jsx Notenstufe D).
                  color: 'bg-orange-400',
                  textColor: 'text-orange-700',
                },
                {
                  key: 'month',
                  label: '1–3 Monate',
                  color: 'bg-status-fehler-border',
                  textColor: 'text-status-fehler-text',
                },
                {
                  key: 'old',
                  label: '> 3 Monate',
                  color: 'bg-red-700',
                  // rot bewusst behalten: dunklerer roter Ton für die älteste Alters-Stufe,
                  // kein eigener (noch dunklerer) status-fehler-Ton vorhanden.
                  textColor: 'text-red-700',
                },
              ].map(({ key, label, color, textColor }) => {
                const count = ageBuckets[key] || 0
                const total = Object.values(ageBuckets).reduce((a, v) => a + v, 0)
                const pct = total > 0 ? Math.round((count / total) * 100) : 0
                return (
                  <div key={key} className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] text-ink-muted w-20 shrink-0 text-right">
                      {label}
                    </span>
                    <div className="flex-1 h-5 bg-surface-bg rounded-md overflow-hidden">
                      <div
                        className={`h-full ${color} rounded-md flex items-center pl-2`}
                        style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%` }}
                      >
                        {pct >= 10 && (
                          <span className="text-[10px] text-white font-semibold">{count}</span>
                        )}
                      </div>
                    </div>
                    <span
                      className={`text-[11px] tabular-nums font-medium w-12 text-right shrink-0 ${textColor}`}
                    >
                      {count} ({pct}%)
                    </span>
                  </div>
                )
              })}
              {ageBuckets.old > 0 && (
                <p className="text-[11px] text-status-fehler-text mt-2">
                  ⚠️ {ageBuckets.old + ageBuckets.month} Entwürfe älter als 1 Monat — Review
                  empfohlen
                </p>
              )}
            </div>
            {/* Oldest drafts */}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-3">🕰 Älteste Entwürfe</p>
              <div className="space-y-2">
                {top5Oldest.length === 0 && (
                  <p className="text-xs text-ink-muted italic">Keine Entwürfe mit Datum</p>
                )}
                {top5Oldest.map((p, i) => {
                  const ageColor =
                    p.ageDays >= 90
                      ? 'text-status-fehler-text bg-status-fehler-bg border-status-fehler-border'
                      : p.ageDays >= 30
                        ? // orange bewusst behalten: Zwischenstufe, siehe Altersverteilung oben
                          'text-orange-700 bg-orange-50 border-orange-200'
                        : 'text-status-aktiv-text bg-status-aktiv-bg border-status-aktiv-border'
                  return (
                    <div
                      key={p.id}
                      className={`flex items-start gap-2 p-2 rounded-lg border ${ageColor}`}
                    >
                      <span className="text-[10px] font-black shrink-0 mt-0.5 w-4">#{i + 1}</span>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/60 shrink-0">
                        {p.ageDays}d
                      </span>
                      <p className="text-[11px] leading-relaxed line-clamp-2 flex-1">{p.preview}</p>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Content Quality Distribution Report (Cycle 42) */}
      {Object.values(gradeDist).some((v) => v > 0) && (
        <div className="bg-white rounded-xl border border-surface-border p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Award className="w-4 h-4 text-accent-500" /> Content-Qualitätsbericht — Entwürfe
            </h2>
            {readyToApprove > 0 && (
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-status-fertig-bg text-status-fertig-text border border-status-fertig-border">
                ✅ {readyToApprove} bereit zur Freigabe (Note A/B)
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Grade distribution */}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-3">Notenverteilung</p>
              <div className="space-y-2">
                {[
                  {
                    grade: 'A',
                    label: 'Hervorragend (9-10)',
                    color: 'bg-status-fertig-border',
                    textColor: 'text-status-fertig-text',
                  },
                  {
                    grade: 'B',
                    label: 'Gut (7-8)',
                    color: 'bg-status-neu-border',
                    textColor: 'text-status-neu-text',
                  },
                  {
                    grade: 'C',
                    label: 'Okay (5-6)',
                    color: 'bg-status-aktiv-bg',
                    textColor: 'text-status-aktiv-text',
                  },
                  {
                    grade: 'D',
                    label: 'Schwach (3-4)',
                    // orange bewusst behalten: eigene Notenstufe "D" zwischen aktiv(C)/fehler(F),
                    // kein Status-Token für diese Zwischenstufe (analog Posts.jsx).
                    color: 'bg-orange-400',
                    textColor: 'text-orange-700',
                  },
                  {
                    grade: 'F',
                    label: 'Ungenügend (0-2)',
                    color: 'bg-status-fehler-border',
                    textColor: 'text-status-fehler-text',
                  },
                ].map(({ grade, label, color, textColor }) => {
                  const count = gradeDist[grade] || 0
                  const total = Object.values(gradeDist).reduce((a, v) => a + v, 0)
                  const pct = total > 0 ? Math.round((count / total) * 100) : 0
                  return (
                    <div key={grade} className="flex items-center gap-2">
                      <span className={`w-5 text-xs font-black shrink-0 ${textColor}`}>
                        {grade}
                      </span>
                      <div className="flex-1 h-5 bg-surface-bg rounded-md overflow-hidden">
                        <div
                          className={`h-full ${color} rounded-md transition-all flex items-center pl-2`}
                          style={{ width: `${Math.max(pct, count > 0 ? 4 : 0)}%` }}
                        >
                          {pct >= 12 && (
                            <span className="text-[10px] text-white font-semibold">{count}</span>
                          )}
                        </div>
                      </div>
                      <span className="text-[11px] text-ink-muted tabular-nums w-12 text-right">
                        {count} ({pct}%)
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Score histogram */}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-3">Score-Verteilung</p>
              <div className="space-y-2">
                {Object.entries(scoreHist).map(([range, count]) => {
                  const maxHist = Math.max(...Object.values(scoreHist), 1)
                  const pct = Math.round((count / maxHist) * 100)
                  const barColor =
                    range === '9-10'
                      ? 'bg-status-fertig-border'
                      : range === '7-8'
                        ? 'bg-status-neu-border'
                        : range === '5-6'
                          ? 'bg-status-aktiv-border'
                          : range === '3-4'
                            ? // orange bewusst behalten: siehe Notenverteilung oben (Stufe D)
                              'bg-orange-300'
                            : 'bg-red-300'
                  return (
                    <div key={range} className="flex items-center gap-2">
                      <span className="text-[10px] text-ink-muted w-10 text-right shrink-0">
                        {range}
                      </span>
                      <div className="flex-1 h-5 bg-surface-bg rounded-md overflow-hidden">
                        <div
                          className={`h-full ${barColor} rounded-md`}
                          style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-ink-muted tabular-nums w-8 text-right">
                        {count}
                      </span>
                    </div>
                  )
                })}
              </div>
              <p className="text-[10px] text-ink-muted mt-3">
                Ø Score:{' '}
                <span className="font-semibold text-ink">
                  {topPosts.length > 0
                    ? ((topPosts.reduce((a, p) => a + p.score, 0) / topPosts.length) * 2).toFixed(1)
                    : '–'}
                </span>{' '}
                / 10 (Top 5 Ø)
              </p>
            </div>

            {/* Top 5 posts preview */}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-3">🏆 Top 5 Entwürfe</p>
              <div className="space-y-2">
                {topPosts.length === 0 && (
                  <p className="text-xs text-ink-muted italic">Keine Entwürfe</p>
                )}
                {topPosts.map((p, i) => {
                  const gradeColor = {
                    A: 'bg-status-fertig-bg text-status-fertig-text',
                    B: 'bg-status-neu-bg text-status-neu-text',
                    C: 'bg-status-aktiv-bg text-status-aktiv-text',
                    // orange bewusst behalten: Notenstufe D, siehe oben
                    D: 'bg-orange-100 text-orange-800',
                    F: 'bg-status-fehler-bg text-status-fehler-text',
                  }[p.grade]
                  return (
                    <div
                      key={p.id}
                      className="flex items-start gap-2 p-2 rounded-lg border border-surface-border hover:border-ink-muted bg-surface-bg"
                    >
                      <span className="text-[10px] font-black text-ink-muted shrink-0 mt-0.5">
                        #{i + 1}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${gradeColor}`}
                      >
                        {p.grade}
                      </span>
                      <p className="text-[11px] text-ink leading-relaxed line-clamp-2 flex-1">
                        {p.preview}
                      </p>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* LLM Cost & Usage Panel */}
      {(llmCostHistory || llmProviders.length > 0) && (
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <span className="text-lg">🤖</span> KI-Kosten &amp; Nutzung
            </h3>
            <div className="flex gap-1">
              {[7, 14, 30].map((d) => (
                <button
                  key={d}
                  onClick={() => setCostDays(d)}
                  className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${costDays === d ? 'bg-primary-700 text-white border-primary-700' : 'bg-white text-ink-muted border-surface-border hover:border-primary-300'}`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {llmCostHistory &&
            llmCostHistory.length > 0 &&
            (() => {
              const history = [...llmCostHistory].reverse()
              const maxCents = Math.max(...history.map((d) => d.total_cents), 1)
              const totalCents = history.reduce((s, d) => s + d.total_cents, 0)
              const totalCalls = history.reduce((s, d) => s + d.calls, 0)
              const totalTokensIn = history.reduce((s, d) => s + (d.input_tokens || 0), 0)
              const totalTokensOut = history.reduce((s, d) => s + (d.output_tokens || 0), 0)
              const avgPerDay = totalCents / history.length
              return (
                <div className="space-y-4">
                  {/* Summary stats */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                      {
                        label: `Gesamt (${costDays}d)`,
                        value: `${(totalCents / 100).toFixed(2)} €`,
                        sub: `${totalCalls} Aufrufe`,
                        // purple bewusst behalten: 4. KPI-Kachel-Farbe neben den 3 migrierten,
                        // kein 1:1-Primitive-Äquivalent im Tier-1-System.
                        color: 'bg-purple-50 text-purple-700',
                      },
                      {
                        label: 'Ø pro Tag',
                        value: `${(avgPerDay / 100).toFixed(3)} €`,
                        sub: `${Math.round(totalCalls / history.length)} Aufrufe/Tag`,
                        color: 'bg-status-neu-bg text-status-neu-text',
                      },
                      {
                        label: 'Input Tokens',
                        value: (totalTokensIn / 1000).toFixed(0) + 'K',
                        sub: 'Prompt-Tokens gesamt',
                        color: 'bg-accent-50 text-accent-700',
                      },
                      {
                        label: 'Output Tokens',
                        value: (totalTokensOut / 1000).toFixed(0) + 'K',
                        sub: 'Antwort-Tokens gesamt',
                        color: 'bg-status-fertig-bg text-status-fertig-text',
                      },
                    ].map((s) => (
                      <div key={s.label} className={`rounded-lg p-3 ${s.color.split(' ')[0]}`}>
                        <p className={`text-xs font-medium ${s.color.split(' ')[1]}`}>{s.label}</p>
                        <p className={`text-lg font-bold ${s.color.split(' ')[1]}`}>{s.value}</p>
                        <p className="text-[10px] opacity-70">{s.sub}</p>
                      </div>
                    ))}
                  </div>

                  {/* Bar chart */}
                  <div>
                    <p className="text-xs font-medium text-ink-muted mb-2">Tageskosten (Cent)</p>
                    <div className="flex items-end gap-1 h-20">
                      {history.map((day, i) => {
                        const h = Math.max(4, Math.round((day.total_cents / maxCents) * 72))
                        const isToday = i === history.length - 1
                        return (
                          <div
                            key={day.date}
                            className="flex-1 flex flex-col items-center gap-0.5 group relative"
                          >
                            <div
                              className={`w-full rounded-t transition-colors ${isToday ? 'bg-primary-600' : 'bg-primary-200 group-hover:bg-primary-400'}`}
                              style={{ height: `${h}px` }}
                            />
                            <span className="text-[9px] text-ink-muted">{day.date.slice(5)}</span>
                            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-10">
                              {day.date}: {day.total_cents.toFixed(1)}¢ / {day.calls} Calls
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })()}

          {/* Provider budget status */}
          {llmProviders.filter((p) => p.is_active).length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-medium text-ink-muted">Provider Budget-Status</p>
              {llmProviders
                .filter((p) => p.is_active)
                .map((p) => {
                  const limit = p.cost_limit_daily_cents || 0
                  const spent = p.cost_spent_today_cents || 0
                  const pct = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : null
                  const barColor =
                    pct == null
                      ? 'bg-surface-border'
                      : pct >= 90
                        ? 'bg-status-fehler-border'
                        : pct >= 70
                          ? 'bg-status-aktiv-border'
                          : 'bg-status-fertig-border'
                  return (
                    <div key={p.id} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-ink">
                          {p.name}{' '}
                          <span className="text-[10px] text-ink-muted font-mono">
                            {p.model_name?.split('/').pop()}
                          </span>
                        </span>
                        <span className="text-xs font-mono text-ink-muted">
                          {spent.toFixed(1)}¢ {limit > 0 ? `/ ${limit}¢` : ''}
                          {pct != null && (
                            <span
                              className={`ml-1 font-semibold ${pct >= 90 ? 'text-status-fehler-text' : pct >= 70 ? 'text-status-aktiv-text' : 'text-status-fertig-text'}`}
                            >
                              {pct}%
                            </span>
                          )}
                        </span>
                      </div>
                      {limit > 0 && (
                        <div className="h-1.5 bg-surface-bg rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${barColor}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      )}
                      <p className="text-[10px] text-ink-muted">
                        {p.last_test_status === 'ok' ? '🟢 Verbunden' : '🔴 Fehler'} ·{' '}
                        {p.task_assignment === 'all' ? 'Alle Aufgaben' : p.task_assignment}
                      </p>
                    </div>
                  )
                })}
            </div>
          )}
        </div>
      )}

      {/* Quality Tracking Panel */}
      {qualitySummary && (
        <div className="bg-white rounded-xl border border-surface-border shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            {/* purple bewusst behalten: Panel-Icon-Farbe, kein 1:1-Primitive-Äquivalent */}
            <Award className="w-4 h-4 text-purple-600" />
            <h2 className="text-base font-semibold text-ink">Pipeline-Qualität</h2>
            <span className="ml-auto text-xs text-ink-muted">
              {qualitySummary.total_quality_checks} Messungen · letzte 30d
            </span>
          </div>

          {/* Overall score */}
          {/* purple bewusst behalten: passend zum Panel-Icon oben */}
          <div className="flex items-center gap-3 mb-4 p-3 bg-purple-50 rounded-lg">
            <div className="text-3xl font-bold text-purple-700">
              {qualitySummary.avg_overall_score}
            </div>
            <div>
              <div className="text-sm font-medium text-ink">Gesamt-Score</div>
              <div className="text-xs text-ink-muted">Durchschnitt aller Pipeline-Schritte</div>
            </div>
            <div className="ml-auto">
              <div
                className={`text-lg font-bold ${
                  qualitySummary.avg_overall_score >= 80
                    ? 'text-status-fertig-text'
                    : qualitySummary.avg_overall_score >= 60
                      ? 'text-status-aktiv-text'
                      : 'text-status-fehler-text'
                }`}
              >
                {qualitySummary.avg_overall_score >= 80
                  ? 'A'
                  : qualitySummary.avg_overall_score >= 60
                    ? 'B'
                    : qualitySummary.avg_overall_score >= 40
                      ? 'C'
                      : 'D'}
              </div>
            </div>
          </div>

          {/* Per-step breakdown */}
          <div className="space-y-2">
            {(qualitySummary.steps || [])
              .filter((s) => s.count > 0)
              .map((step) => {
                const stepLabels = {
                  transcription: 'Transkription',
                  analysis: 'Analyse',
                  ideation: 'Ideation',
                  post_generation: 'Post-Generierung',
                  smart_questions: 'Smarte Fragen',
                }
                const score = step.avg_overall
                const barColor =
                  score >= 80
                    ? 'bg-status-fertig-border'
                    : score >= 60
                      ? 'bg-status-aktiv-border'
                      : score >= 40
                        ? // orange bewusst behalten: 4. Score-Stufe zwischen aktiv/fehler, siehe
                          // Notenverteilung oben (Stufe D/C)
                          'bg-orange-500'
                        : 'bg-status-fehler-border'
                return (
                  <div key={step.step}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-ink-muted">
                        {stepLabels[step.step] || step.step}
                      </span>
                      <span className="text-xs font-medium text-ink">{score}/100</span>
                      <span className="text-[10px] text-ink-muted ml-1">({step.count})</span>
                    </div>
                    <div className="h-1.5 bg-surface-bg rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${barColor}`}
                        style={{ width: `${score}%` }}
                      />
                    </div>
                  </div>
                )
              })}
          </div>

          {qualitySummary.total_quality_checks === 0 && (
            <p className="text-xs text-ink-muted text-center py-3">
              Noch keine Qualitätsdaten — wird bei neuen Pipeline-Läufen automatisch befüllt.
            </p>
          )}
        </div>
      )}

      {/* Model Comparison Panel */}
      <div className="bg-white rounded-xl border border-surface-border shadow-sm p-5">
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <Cpu className="w-4 h-4 text-status-neu-text" />
          <h2 className="text-base font-semibold text-ink">Modell-Vergleich</h2>
          <span className="text-xs text-ink-muted ml-1">Qualität · Kosten · Latenz</span>
          <div className="ml-auto flex gap-1 flex-wrap">
            {['', 'transcription', 'analysis', 'ideation', 'post_generation'].map((s) => {
              const labels = {
                '': 'Alle',
                transcription: 'Transkription',
                analysis: 'Analyse',
                ideation: 'Ideation',
                post_generation: 'Post',
              }
              return (
                <button
                  key={s}
                  onClick={() => setModelStep(s)}
                  className={`px-2 py-0.5 text-xs rounded border transition-colors ${modelStep === s ? 'bg-status-neu-text text-white border-status-neu-text' : 'bg-white text-ink-muted border-surface-border hover:border-status-neu-border'}`}
                >
                  {labels[s]}
                </button>
              )
            })}
          </div>
        </div>

        {!modelData || !modelData.models || modelData.models.length === 0 ? (
          <p className="text-xs text-ink-muted text-center py-6">
            Noch keine Modell-Vergleichsdaten — werden automatisch gesammelt wenn die Pipeline
            läuft.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border">
                  <th className="text-left py-2 pr-3 text-ink-muted font-medium">Modell</th>
                  <th className="text-left py-2 pr-3 text-ink-muted font-medium">Schritt</th>
                  <th className="text-right py-2 pr-3 text-ink-muted font-medium">Qualität</th>
                  <th className="text-right py-2 pr-3 text-ink-muted font-medium">Kosten/Aufruf</th>
                  <th className="text-right py-2 pr-3 text-ink-muted font-medium">Latenz</th>
                  <th className="text-right py-2 pr-3 text-ink-muted font-medium">Effizienz</th>
                  <th className="text-right py-2 text-ink-muted font-medium">n</th>
                </tr>
              </thead>
              <tbody>
                {modelData.models.map((row, i) => {
                  const stepLabels = {
                    transcription: 'Transkr.',
                    analysis: 'Analyse',
                    ideation: 'Ideation',
                    post_generation: 'Post',
                    smart_questions: 'Fragen',
                  }
                  const shortModel = row.model ? row.model.split('/').pop() : '?'
                  const qualColor =
                    row.avg_quality >= 80
                      ? 'text-status-fertig-text font-semibold'
                      : row.avg_quality >= 60
                        ? 'text-status-aktiv-text'
                        : 'text-status-fehler-text'
                  const confIcon = { high: '🟢', medium: '🟡', low: '🔴' }[row.confidence] || ''
                  const efficiencyLabel = row.quality_per_cent
                    ? `${row.quality_per_cent.toFixed(1)} Q/ct`
                    : '—'
                  return (
                    <tr
                      key={i}
                      className="border-b border-surface-border hover:bg-surface-bg transition-colors"
                    >
                      <td
                        className="py-2 pr-3 font-mono text-status-neu-text truncate max-w-[180px]"
                        title={row.model}
                      >
                        {shortModel}
                      </td>
                      <td className="py-2 pr-3 text-ink-muted">
                        {stepLabels[row.step] || row.step}
                      </td>
                      <td className={`py-2 pr-3 text-right ${qualColor}`}>{row.avg_quality}/100</td>
                      <td className="py-2 pr-3 text-right text-ink">
                        {row.avg_cost_cents ? `${(row.avg_cost_cents / 100).toFixed(4)} €` : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right text-ink-muted">
                        {row.avg_latency_ms ? `${(row.avg_latency_ms / 1000).toFixed(1)}s` : '—'}
                      </td>
                      {/* purple bewusst behalten: Effizienz-Spalte, kein 1:1-Primitive-Äquivalent */}
                      <td className="py-2 pr-3 text-right text-purple-700">{efficiencyLabel}</td>
                      <td className="py-2 text-right text-ink-muted">
                        {confIcon} {row.count}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="text-[10px] text-ink-muted mt-2">
              🟢 = verlässlich (n≥30) · 🟡 = vorläufig (n≥5) · 🔴 = wenig Daten (n&lt;5) · Effizienz
              = Qualität pro Eurocent
            </p>
          </div>
        )}
      </div>

      {/* Recent Pipeline Quality Feed */}
      {qualityRecent && qualityRecent.length > 0 && (
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center gap-2 mb-4">
            {/* indigo bewusst behalten: Panel-Icon-Farbe, kein 1:1-Primitive-Äquivalent */}
            <Award className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-semibold text-ink">Letzte Pipeline-Qualitätsmessungen</h2>
            <span className="ml-auto text-[11px] text-ink-muted">
              {qualityRecent.length} Einträge
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border">
                  <th className="text-left py-1.5 pr-3 text-ink-muted font-medium">Schritt</th>
                  <th className="text-left py-1.5 pr-3 text-ink-muted font-medium">Modell</th>
                  <th className="text-right py-1.5 pr-3 text-ink-muted font-medium">Gesamt</th>
                  <th className="text-right py-1.5 pr-3 text-ink-muted font-medium">Vollst.</th>
                  <th className="text-right py-1.5 text-ink-muted font-medium">Zeit</th>
                </tr>
              </thead>
              <tbody>
                {qualityRecent.slice(0, 20).map((row, i) => {
                  const stepLabels = {
                    transcription: 'Transkr.',
                    analysis: 'Analyse',
                    ideation: 'Ideation',
                    post_generation: 'Post',
                    smart_questions: 'Fragen',
                  }
                  const score = row.overall_score || 0
                  const scoreColor =
                    score >= 80
                      ? 'text-status-fertig-text font-semibold'
                      : score >= 60
                        ? 'text-status-aktiv-text'
                        : 'text-status-fehler-text'
                  const shortModel = (row.model || '?').split('/').pop()
                  const timeAgo = row.created_at
                    ? (() => {
                        const diff = (Date.now() - new Date(row.created_at).getTime()) / 1000
                        if (diff < 3600) return `${Math.round(diff / 60)}m`
                        if (diff < 86400) return `${Math.round(diff / 3600)}h`
                        return `${Math.round(diff / 86400)}d`
                      })()
                    : '?'
                  return (
                    <tr
                      key={i}
                      className={`border-b border-surface-border ${i % 2 === 0 ? '' : 'bg-surface-bg/50'}`}
                    >
                      <td className="py-1.5 pr-3 text-ink-muted">
                        {stepLabels[row.step] || row.step}
                      </td>
                      <td
                        className="py-1.5 pr-3 font-mono text-status-neu-text text-[10px] truncate max-w-[120px]"
                        title={row.model}
                      >
                        {shortModel}
                      </td>
                      <td className={`py-1.5 pr-3 text-right tabular-nums ${scoreColor}`}>
                        {score.toFixed(0)}/100
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-ink-muted">
                        {(row.completeness_score || 0).toFixed(0)}
                      </td>
                      <td className="py-1.5 text-right text-ink-muted">{timeAgo}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-ink-muted mt-2">
            Automatisch erfasst nach jedem Pipeline-Schritt · regelbasiert (kein LLM-Budget nötig)
          </p>
        </div>
      )}

      {/* Best Posting Times Heatmap */}
      {bestTimes && <PostingHeatmap data={bestTimes} />}

      {/* Content Production Heatmap */}
      {heatmap && heatmap.calendar && (
        <div className="bg-white rounded-xl border border-surface-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <span className="w-4 h-4 text-status-fertig-text font-bold text-base">▦</span>
              Content-Produktion (letzte 90 Tage)
            </h2>
            <div className="flex items-center gap-4 text-[11px] text-ink-muted">
              <span>
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-status-neu-border mr-1 align-middle" />
                Transkribiert: {heatmap.total_transcribed}
              </span>
              <span>
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-status-fertig-border mr-1 align-middle" />
                Posts: {heatmap.total_content}
              </span>
            </div>
          </div>
          <div className="flex gap-[3px] flex-wrap">
            {heatmap.calendar.map((day) => {
              const intensity = heatmap.peak > 0 ? day.total / heatmap.peak : 0
              const bg =
                day.total === 0
                  ? 'bg-surface-bg'
                  : intensity >= 0.7
                    ? 'bg-emerald-500'
                    : intensity >= 0.4
                      ? 'bg-emerald-400'
                      : intensity >= 0.2
                        ? 'bg-emerald-300'
                        : 'bg-status-fertig-bg'
              const isMonday = new Date(day.date).getDay() === 1
              return (
                <div
                  key={day.date}
                  className={`w-[10px] h-[10px] rounded-sm ${bg} ${isMonday ? 'ml-[2px]' : ''}`}
                  title={`${day.date}: ${day.transcribed} transkribiert, ${day.content_pieces} Posts`}
                />
              )
            })}
          </div>
          <div className="flex items-center gap-1 mt-2 justify-end">
            <span className="text-[10px] text-ink-muted mr-1">Wenig</span>
            {/* emerald-Zwischentöne bewusst behalten: 5-stufige Heatmap-Intensitätsskala,
                status-fertig-Token deckt nur 2 der 5 Stufen exakt ab. */}
            {[
              'bg-surface-bg',
              'bg-status-fertig-bg',
              'bg-emerald-300',
              'bg-emerald-400',
              'bg-emerald-500',
            ].map((c) => (
              <div key={c} className={`w-[10px] h-[10px] rounded-sm ${c}`} />
            ))}
            <span className="text-[10px] text-ink-muted ml-1">Viel</span>
          </div>
        </div>
      )}

      {/* Ideas Pipeline Panel */}
      {ideasStats && (
        <div className="bg-white rounded-xl border border-surface-border p-5 mt-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <span className="text-base">💡</span> Ideen-Pipeline
            </h2>
            <div className="flex gap-3 text-[11px] text-ink-muted">
              <span className="font-semibold text-ink">
                {ideasStats.total.toLocaleString('de')} Ideen
              </span>
              {ideasStats.with_posts > 0 && (
                <span className="text-status-fertig-text">
                  {ideasStats.with_posts} Posts generiert
                </span>
              )}
            </div>
          </div>

          {/* Status breakdown */}
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(ideasStats.by_status).map(([status, count]) => {
              const cfg = {
                new: {
                  label: 'Neu / Wartend',
                  color: 'bg-status-aktiv-bg text-status-aktiv-text border-status-aktiv-border',
                },
                answered: {
                  label: 'Beantwortet',
                  color: 'bg-status-neu-bg text-status-neu-text border-status-neu-border',
                },
                post_generated: {
                  label: 'Post erstellt',
                  color: 'bg-status-fertig-bg text-status-fertig-text border-status-fertig-border',
                },
                skipped: {
                  label: 'Übersprungen',
                  color: 'bg-surface-bg text-ink-light border-surface-border',
                },
              }[status] || {
                label: status,
                color: 'bg-surface-bg text-ink-light border-surface-border',
              }
              return (
                <span
                  key={status}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.color}`}
                >
                  {cfg.label}: {count.toLocaleString('de')}
                </span>
              )
            })}
            {ideasStats.by_status.new > 0 && (
              <span className="px-2.5 py-1 rounded-full text-xs text-status-aktiv-text bg-status-aktiv-bg border border-status-aktiv-border">
                ⏳ {ideasStats.by_status.new.toLocaleString('de')} warten auf LLM-Budget
              </span>
            )}
          </div>

          {/* Angle distribution */}
          {ideasStats.by_angle.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-ink-muted uppercase tracking-wide mb-2">
                Post-Winkel (Angle)
              </p>
              <div className="space-y-1.5">
                {(() => {
                  const maxAngle = Math.max(...ideasStats.by_angle.map((a) => a.count), 1)
                  // violet/sky/red/pink bewusst behalten: 7 unterscheidbare Angle-Kategorien
                  // ohne Status-Bedeutung (analog Posts.jsx Content-Säulen-Badges); teal/amber/
                  // emerald sind primitive-identisch zu primary-*/accent-*/status-fertig-* und
                  // deshalb migriert.
                  const ANGLE_LABELS = {
                    howto: { label: 'How-To / Anleitung', color: 'bg-primary-400' },
                    meinung: { label: 'Meinung / Perspektive', color: 'bg-violet-400' },
                    trend: { label: 'Trend / Entwicklung', color: 'bg-sky-400' },
                    kontroverse: { label: 'Kontroverse', color: 'bg-red-400' },
                    statistik: { label: 'Statistik / Daten', color: 'bg-accent-400' },
                    story: { label: 'Story / Erfahrung', color: 'bg-pink-400' },
                    checkliste: { label: 'Checkliste', color: 'bg-status-fertig-border' },
                  }
                  return ideasStats.by_angle.slice(0, 8).map(({ angle, count }) => {
                    const cfg = ANGLE_LABELS[angle] || { label: angle, color: 'bg-ink-muted' }
                    const pct = Math.max(4, (count / maxAngle) * 100)
                    return (
                      <div key={angle} className="flex items-center gap-3">
                        <span className="w-36 text-xs text-ink-muted shrink-0 truncate">
                          {cfg.label}
                        </span>
                        <div className="flex-1 h-4 bg-surface-bg rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${cfg.color} transition-all`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs font-semibold text-ink w-10 text-right shrink-0">
                          {count}
                        </span>
                      </div>
                    )
                  })
                })()}
              </div>
            </div>
          )}

          {ideasStats.total > 0 && (
            <p className="text-[11px] text-ink-muted mt-3 pt-3 border-t border-surface-border">
              Durchschnittlich ~
              {Math.round(ideasStats.total / Math.max(ideasStats.by_angle.length, 1))} Ideen pro
              Angle · Potenzial: {ideasStats.total.toLocaleString('de')} Posts ausstehend
            </p>
          )}
        </div>
      )}

      {/* Model Recommendations Panel */}
      {modelData && modelData.models && modelData.models.length > 0 && (
        <ModelRecommendationsPanel models={modelData.models} />
      )}
    </div>
  )
}
