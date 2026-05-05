import { useState, useEffect, useMemo } from 'react'
import { useToast } from './ui/Toast'
import { CheckCircle2, Copy, Check, Clock, CalendarDays, Linkedin, ArrowUpRight, Flame } from 'lucide-react'
import { getScheduledPosts, markPublished } from '../api'

const PILLAR_EMOJI = {
  thought_leadership: '💡',
  how_to: '🛠',
  personal_story: '📖',
  industry_news: '📰',
  product_service: '🎯',
}

function dayLabel(dateStr) {
  const d = new Date(dateStr)
  const today = new Date()
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1)
  const toStr = (x) => x.toDateString()
  if (toStr(d) === toStr(today)) return 'Heute'
  if (toStr(d) === toStr(tomorrow)) return 'Morgen'
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

function timeLabel(dateStr) {
  return new Date(dateStr).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

function PostQueueCard({ post, onPublished }) {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [done, setDone] = useState(false)
  const pillarEmoji = PILLAR_EMOJI[post.angle] || ''
  const day = dayLabel(post.scheduled_at)
  const isOverdue = new Date(post.scheduled_at) < new Date() && !done
  const isToday = day === 'Heute'

  async function handlePublish() {
    if (!post.content_piece_id) return
    setPublishing(true)
    try {
      await markPublished(post.content_piece_id)
      setDone(true)
      onPublished(post.id)
    } catch(e) {
      const detail = e?.detail || e?.message || ''
      if (typeof detail === 'object' && detail?.error === 'unapproved_post') {
        toast.warning('Dieser Post muss zuerst in der App freigegeben werden, bevor er veröffentlicht werden kann.')
      } else {
        console.error(e)
      }
    }
    setPublishing(false)
  }

  function handleCopy() {
    navigator.clipboard.writeText(post.content_text || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`bg-white rounded-xl border p-4 transition-all ${done ? 'opacity-50 border-gray-200' : isOverdue ? 'border-orange-300 bg-orange-50' : isToday ? 'border-teal-300' : 'border-surface-border'}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
            isOverdue && !done ? 'bg-orange-100 text-orange-700' :
            isToday ? 'bg-teal-100 text-teal-700' :
            'bg-gray-100 text-gray-600'
          }`}>
            {isOverdue && !done ? '🔴 Überfällig' : isToday ? '🟢 Heute' : day}
          </span>
          <span className="flex items-center gap-1 text-[11px] text-ink-muted">
            <Clock className="w-3 h-3" />
            {timeLabel(post.scheduled_at)} Uhr
          </span>
          {post.angle && (
            <span className="text-[11px] text-ink-muted">{pillarEmoji} {post.angle}</span>
          )}
          {done && <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700">✓ Gepostet</span>}
        </div>
        {!done && (
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={handleCopy}
              title="Kopieren für LinkedIn"
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border transition-colors ${copied ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-gray-50 border-gray-200 text-ink-muted hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700'}`}
            >
              {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Kopiert!' : 'Kopieren'}
            </button>
            <button
              onClick={handlePublish}
              disabled={publishing}
              title="Als veröffentlicht markieren"
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg border bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
            >
              <CheckCircle2 className="w-3 h-3" />
              {publishing ? '...' : 'Gepostet ✓'}
            </button>
          </div>
        )}
      </div>

      <p className="text-sm text-ink leading-relaxed line-clamp-3 whitespace-pre-line mb-2">
        {post.content_text || post.content_preview || '(kein Text)'}
      </p>

      {post.content_text && post.content_text.length > 210 && (
        <p className="text-[10px] text-ink-muted">{post.content_text.length} Zeichen</p>
      )}
    </div>
  )
}

export default function PublishQueue() {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [publishedIds, setPublishedIds] = useState(new Set())
  const [viewDays, setViewDays] = useState(7)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const data = await getScheduledPosts({ status: 'scheduled' })
        // Sort by scheduled_at ascending
        const sorted = (Array.isArray(data) ? data : []).sort((a, b) =>
          new Date(a.scheduled_at) - new Date(b.scheduled_at)
        )
        setPosts(sorted)
      } catch(e) {
        console.error(e)
      }
      setLoading(false)
    }
    load()
  }, [])

  function handlePublished(postId) {
    setPublishedIds(prev => new Set([...prev, postId]))
  }

  const now = new Date()
  const cutoff = new Date(now); cutoff.setDate(cutoff.getDate() + viewDays)

  const visiblePosts = useMemo(() => {
    return posts.filter(p => new Date(p.scheduled_at) <= cutoff)
  }, [posts, viewDays])

  // Group by day
  const grouped = useMemo(() => {
    const groups = {}
    visiblePosts.forEach(p => {
      const day = p.scheduled_at.slice(0, 10)
      if (!groups[day]) groups[day] = []
      groups[day].push(p)
    })
    return groups
  }, [visiblePosts])

  const overdueCount = posts.filter(p => new Date(p.scheduled_at) < now && !publishedIds.has(p.id)).length
  const todayCount = posts.filter(p => p.scheduled_at.slice(0, 10) === now.toISOString().slice(0, 10)).length
  const publishedThisSession = publishedIds.size

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Publishing Queue...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <Linkedin className="w-5 h-5 text-blue-600" />
            Publishing Queue
          </h1>
          <p className="text-sm text-ink-light mt-0.5">
            Posts für LinkedIn vorbereiten, kopieren und als veröffentlicht markieren.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {publishedThisSession > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg">
              <Flame className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs font-semibold text-emerald-700">{publishedThisSession} heute gepostet</span>
            </div>
          )}
          <select
            value={viewDays}
            onChange={e => setViewDays(Number(e.target.value))}
            className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-primary-400"
          >
            <option value={1}>Heute</option>
            <option value={3}>Nächste 3 Tage</option>
            <option value={7}>Nächste 7 Tage</option>
            <option value={14}>Nächste 14 Tage</option>
          </select>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className={`rounded-xl border p-4 ${overdueCount > 0 ? 'bg-orange-50 border-orange-200' : 'bg-white border-surface-border'}`}>
          <p className={`text-2xl font-bold tabular-nums ${overdueCount > 0 ? 'text-orange-700' : 'text-ink'}`}>{overdueCount}</p>
          <p className="text-xs text-ink-muted mt-0.5">Überfällig</p>
        </div>
        <div className={`rounded-xl border p-4 ${todayCount > 0 ? 'bg-teal-50 border-teal-200' : 'bg-white border-surface-border'}`}>
          <p className={`text-2xl font-bold tabular-nums ${todayCount > 0 ? 'text-teal-700' : 'text-ink'}`}>{todayCount}</p>
          <p className="text-xs text-ink-muted mt-0.5">Heute geplant</p>
        </div>
        <div className="rounded-xl border border-surface-border bg-white p-4">
          <p className="text-2xl font-bold tabular-nums text-ink">{posts.length}</p>
          <p className="text-xs text-ink-muted mt-0.5">Gesamt eingeplant</p>
        </div>
      </div>

      {/* Approval requirement notice */}
      <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-2">
        <span className="text-amber-600 text-sm shrink-0">!</span>
        <p className="text-xs text-amber-800">
          <strong>Freigabe erforderlich:</strong> Posts müssen zuerst in der Freigabe-Ansicht genehmigt werden (status: freigegeben) bevor sie als veröffentlicht markiert werden können.
        </p>
      </div>

      {/* Workflow hint */}
      {(overdueCount > 0 || todayCount > 0) && (
        <div className="mb-5 p-4 bg-blue-50 border border-blue-200 rounded-xl flex items-start gap-3">
          <Linkedin className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-blue-900">So funktioniert's:</p>
            <ol className="text-xs text-blue-700 mt-1 space-y-0.5 list-decimal list-inside">
              <li>„Kopieren" klicken → Post-Text ist in der Zwischenablage</li>
              <li>LinkedIn öffnen → neuen Post erstellen → einfügen → veröffentlichen</li>
              <li>Zurückkommen → „Gepostet ✓" klicken → Status wird aktualisiert</li>
            </ol>
            <a href="https://www.linkedin.com/feed/" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 mt-2 text-xs font-semibold text-blue-700 hover:text-blue-900">
              LinkedIn öffnen <ArrowUpRight className="w-3 h-3" />
            </a>
          </div>
        </div>
      )}

      {Object.keys(grouped).length === 0 ? (
        <div className="text-center py-12 bg-white rounded-xl border border-surface-border">
          <CalendarDays className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-ink-muted">Keine geplanten Posts in diesem Zeitraum.</p>
          <p className="text-xs text-ink-muted mt-1">Gehe zu „Posts" → „Auto-Einplanen" um Posts einzuplanen.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([day, dayPosts]) => {
            const label = dayLabel(day + 'T00:00:00')
            const isToday = label === 'Heute'
            const allDone = dayPosts.every(p => publishedIds.has(p.id))
            return (
              <div key={day}>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className={`text-sm font-bold ${isToday ? 'text-teal-700' : 'text-ink'}`}>
                    {label}
                  </h2>
                  <span className="text-xs text-ink-muted">
                    {new Date(day + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long' })}
                  </span>
                  {allDone && <span className="ml-auto text-[11px] font-semibold text-emerald-600">✓ Alle gepostet</span>}
                </div>
                <div className="space-y-3">
                  {dayPosts.map(p => (
                    <PostQueueCard key={p.id} post={p} onPublished={handlePublished} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
