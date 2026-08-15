import { useState, useEffect, useRef } from 'react'
import { flushSync } from 'react-dom'
import { useToast } from './ui/Toast'
import { Button } from './ui/Button'
import {
  Lightbulb,
  MessageCircleQuestion,
  ChevronDown,
  ChevronUp,
  Send,
  Sparkles,
  Tag,
  Star,
  Clock,
  CheckCircle2,
  AlertCircle,
  Plus,
  Loader2,
  Trash2,
  LayoutList,
  Rows3,
  SkipForward,
  Zap,
} from 'lucide-react'
import {
  getIdeas,
  getIdea,
  submitAnswer,
  generatePost,
  updateIdea,
  getItems,
  generateIdeas,
  batchGenerateIdeas,
  refreshIdeasWithProfile,
  getSources,
  bulkArchiveIdeas,
  quickGeneratePost,
  bulkQuickGeneratePosts,
  getIdeasSourceBreakdown,
  createManualIdea,
} from '../api'
import TimeFilter from './TimeFilter'
import IdeaVariants from './IdeaVariants'

const STATUS_MAP = {
  new: { label: 'Neu', color: 'bg-status-neu-bg text-status-neu-text', icon: Lightbulb },
  questions_sent: {
    label: 'Fragen offen',
    color: 'bg-status-aktiv-bg text-status-aktiv-text',
    icon: MessageCircleQuestion,
  },
  answers_received: {
    label: 'Beantwortet',
    color: 'bg-status-fertig-bg text-status-fertig-text',
    icon: CheckCircle2,
  },
  content_generated: {
    label: 'Post erstellt',
    color: 'bg-primary-100 text-primary-700',
    icon: Sparkles,
  },
  dismissed: {
    label: 'Verworfen',
    color: 'bg-status-archiviert-bg text-status-archiviert-text',
    icon: AlertCircle,
  },
  skipped: {
    label: 'Übersprungen',
    color: 'bg-status-archiviert-bg text-status-archiviert-text',
    icon: SkipForward,
  },
  rejected: {
    label: 'Archiviert',
    color: 'bg-status-archiviert-bg text-status-archiviert-text',
    icon: Trash2,
  },
}

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] || { label: status, color: 'bg-surface-bg text-ink-light' }
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${s.color}`}
    >
      {s.icon && <s.icon className="w-3 h-3" />}
      {s.label}
    </span>
  )
}

function RelevanceBar({ score }) {
  const s = score ?? 0
  const pct = Math.min(s * 10, 100)
  const color =
    s >= 7 ? 'bg-status-fertig-border' : s >= 4 ? 'bg-status-aktiv-border' : 'bg-status-fehler-border'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-surface-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ink-muted">{s.toFixed(1)}</span>
    </div>
  )
}

function InlineQA({
  idea,
  answers,
  onChange,
  onSubmit,
  onGeneratePost,
  onQuickGenerate,
  submitting,
  generating,
  quickGenerating,
  message,
}) {
  if (!idea)
    return (
      <div className="py-3 flex items-center justify-center gap-2 text-xs text-ink-muted">
        <Loader2 className="animate-spin w-4 h-4" aria-hidden="true" />
        Lade Fragen…
      </div>
    )
  const questions = idea.entrepreneur_questions || []
  const existingAnswerIndices = new Set((idea.answers || []).map((a) => a.question_index))
  const allAnswered =
    questions.length > 0 && questions.every((_, i) => existingAnswerIndices.has(i))

  return (
    <div className="border-t border-surface-border mt-3 pt-4 space-y-3">
      {message && (
        <div
          className={`p-2 rounded-lg text-xs ${message.type === 'error' ? 'bg-status-fehler-bg text-status-fehler-text' : 'bg-status-fertig-bg text-status-fertig-text'}`}
        >
          {message.text}
        </div>
      )}
      {idea.hook_suggestion && (
        <div className="p-2.5 bg-accent-50 rounded-lg border border-accent-200">
          <p className="text-[11px] font-medium text-accent-600 mb-0.5">Hook-Vorschlag:</p>
          <p className="text-xs text-accent-900 italic">"{idea.hook_suggestion}"</p>
        </div>
      )}
      {questions.length === 0 && (
        <p className="text-xs text-ink-muted text-center py-2">Keine Fragen für diese Idee.</p>
      )}
      {questions.map((q, idx) => {
        const answered = existingAnswerIndices.has(idx)
        const existingText = idea.answers?.find((a) => a.question_index === idx)?.answer_text
        const qText = typeof q === 'string' ? q : q.question || q.text || JSON.stringify(q)
        return (
          <div
            key={idx}
            className={`p-3 rounded-lg border ${answered ? 'border-status-fertig-border bg-status-fertig-bg/40' : 'border-surface-border bg-surface-bg'}`}
          >
            <p className="text-xs font-medium text-ink mb-1.5">
              <span className="text-primary-600 mr-1">{idx + 1}.</span>
              {qText}
            </p>
            {answered ? (
              <div className="flex items-start gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-status-fertig-border mt-0.5 shrink-0" />
                <p className="text-xs text-ink-light">{existingText}</p>
              </div>
            ) : (
              <div className="flex gap-2">
                <textarea
                  className="flex-1 text-xs border border-surface-border rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                  rows={2}
                  placeholder="Deine Antwort (min. 10 Zeichen)..."
                  value={answers[idx] || ''}
                  onChange={(e) => onChange(idx, e.target.value)}
                />
                <button
                  onClick={() => onSubmit(idx, qText)}
                  disabled={submitting || !answers[idx] || answers[idx].length < 10}
                  className="shrink-0 px-2.5 py-1.5 bg-primary-700 text-white rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors"
                  title="Antwort speichern"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        )
      })}
      {allAnswered && idea.status !== 'content_generated' && (
        <button
          onClick={onGeneratePost}
          disabled={generating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent-500 text-white rounded-xl font-medium text-sm hover:bg-accent-600 disabled:opacity-50 transition-colors"
        >
          <Sparkles className="w-4 h-4" />
          {generating ? 'Posts werden erstellt...' : 'LinkedIn-Posts generieren'}
        </button>
      )}
      {!allAnswered && idea.status !== 'content_generated' && onQuickGenerate && (
        <button
          onClick={onQuickGenerate}
          disabled={quickGenerating || generating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-surface-bg border border-surface-border text-ink-light rounded-xl text-sm hover:bg-surface-border disabled:opacity-50 transition-colors"
          title="Post direkt aus Ideen-Metadaten generieren — ohne Fragen beantworten"
        >
          <Zap className="w-4 h-4 text-status-aktiv-text" />
          {quickGenerating ? 'Quick-Post wird erstellt...' : '⚡ Quick Post (ohne Q&A)'}
        </button>
      )}
      {idea.status === 'content_generated' && (
        <div className="p-3 bg-primary-50 rounded-lg border border-primary-100 text-center">
          <Sparkles className="w-4 h-4 text-primary-600 mx-auto mb-1" />
          <p className="text-xs font-medium text-primary-700">
            Posts erstellt — schau unter "Posts"
          </p>
        </div>
      )}
    </div>
  )
}

function IdeaCard({ idea, onToggle, isExpanded, inlineContent, isSelected, onSelect }) {
  const hasQuestions = (idea.questions_count || 0) > 0
  const actionLabel = isExpanded
    ? 'Einklappen'
    : hasQuestions && idea.status !== 'content_generated'
      ? 'Fragen beantworten'
      : 'Details'

  return (
    <div
      className={`bg-white rounded-xl border transition-colors ${isSelected ? 'border-status-fehler-border bg-status-fehler-bg/30' : isExpanded ? 'border-primary-300 shadow-sm' : 'border-surface-border hover:border-primary-300'}`}
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2 shrink-0 mt-0.5">
            <input
              type="checkbox"
              checked={isSelected}
              onChange={(e) => onSelect(idea.id, e.target.checked)}
              className="w-3.5 h-3.5 rounded border-surface-border text-status-fehler-text cursor-pointer mt-0.5"
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <StatusBadge status={idea.status} />
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-bg text-xs text-ink-light">
                <Tag className="w-3 h-3" />
                {idea.angle}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-ink leading-snug">{idea.title}</h3>
            {idea.description && (
              <p className="text-xs text-ink-light mt-1.5 line-clamp-2">{idea.description}</p>
            )}
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <RelevanceBar score={idea.relevance_score} />
            {hasQuestions && (
              <span className="text-[11px] text-ink-muted">{idea.questions_count} Fragen</span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-surface-border">
          <span className="text-[11px] text-ink-muted flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {idea.created_at ? new Date(idea.created_at).toLocaleDateString('de-DE') : '-'}
          </span>
          <button
            onClick={() => onToggle(idea.id)}
            className={`flex items-center gap-1 text-xs font-medium transition-colors ${
              hasQuestions && !isExpanded && idea.status !== 'content_generated'
                ? 'text-accent-700 hover:text-accent-800'
                : 'text-primary-700 hover:text-primary-800'
            }`}
          >
            {actionLabel}
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>

        {isExpanded && inlineContent}
        {isExpanded && <IdeaVariants ideaId={idea.id} />}
      </div>
    </div>
  )
}

function IdeaDetail({ ideaId, onClose }) {
  const [idea, setIdea] = useState(null)
  const [loading, setLoading] = useState(true)
  const [answers, setAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    loadIdea()
  }, [ideaId])

  async function loadIdea() {
    setLoading(true)
    try {
      const data = await getIdea(ideaId)
      setIdea(data)
      // Pre-fill answered questions
      const existing = {}
      ;(data.answers || []).forEach((a) => {
        existing[a.question_index] = a.answer_text
      })
      setAnswers(existing)
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setLoading(false)
  }

  async function handleSubmitAnswer(qIdx, qText) {
    if (!answers[qIdx] || answers[qIdx].length < 10) {
      setMessage({ type: 'error', text: 'Antwort muss mindestens 10 Zeichen lang sein.' })
      return
    }
    setSubmitting(true)
    try {
      await submitAnswer(ideaId, {
        question_index: qIdx,
        question_text: qText,
        answer_text: answers[qIdx],
        answer_source: 'web_ui',
      })
      setMessage({ type: 'success', text: 'Antwort gespeichert!' })
      await loadIdea()
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setSubmitting(false)
  }

  async function handleGeneratePost() {
    setGenerating(true)
    try {
      const result = await generatePost(ideaId)
      setMessage({ type: 'success', text: `${result.posts?.length || 0} Post-Varianten erstellt!` })
      await loadIdea()
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setGenerating(false)
  }

  if (loading) return <div className="p-6 text-center text-ink-muted">Lade...</div>
  if (!idea) return null

  const questions = idea.entrepreneur_questions || []
  const existingAnswerIndices = new Set((idea.answers || []).map((a) => a.question_index))
  const allAnswered =
    questions.length > 0 && questions.every((_, i) => existingAnswerIndices.has(i))

  return (
    <div className="bg-white rounded-xl border border-surface-border shadow-sm">
      <div className="p-6 border-b border-surface-border">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <StatusBadge status={idea.status} />
              <span className="px-2 py-0.5 rounded-md bg-surface-bg text-xs text-ink-light">
                {idea.angle}
              </span>
            </div>
            <h2 className="text-lg font-semibold text-ink">{idea.title}</h2>
            <p className="text-sm text-ink-light mt-1">{idea.description}</p>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-sm">
            Schliessen
          </button>
        </div>
        {idea.hook_suggestion && (
          <div className="mt-3 p-3 bg-accent-50 rounded-lg border border-accent-200">
            <p className="text-xs font-medium text-accent-700 mb-1">Hook-Vorschlag:</p>
            <p className="text-sm text-accent-900 italic">"{idea.hook_suggestion}"</p>
          </div>
        )}
      </div>

      {/* Questions + Answers */}
      <div className="p-6">
        <h3 className="text-sm font-semibold text-ink mb-4 flex items-center gap-2">
          <MessageCircleQuestion className="w-4 h-4 text-primary-600" />
          Deine Perspektive ({questions.length} Fragen)
        </h3>

        {message && (
          <div
            className={`mb-4 p-3 rounded-lg text-sm ${message.type === 'error' ? 'bg-status-fehler-bg text-status-fehler-text' : 'bg-status-fertig-bg text-status-fertig-text'}`}
          >
            {message.text}
          </div>
        )}

        <div className="space-y-4">
          {questions.map((q, idx) => {
            const answered = existingAnswerIndices.has(idx)
            const qText = typeof q === 'string' ? q : q.question || q.text || JSON.stringify(q)
            return (
              <div
                key={idx}
                className={`p-4 rounded-lg border ${answered ? 'border-status-fertig-border bg-status-fertig-bg/50' : 'border-surface-border bg-surface-bg'}`}
              >
                <p className="text-sm font-medium text-ink mb-2">
                  <span className="text-primary-600 mr-1">{idx + 1}.</span>
                  {qText}
                </p>
                {answered ? (
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-status-fertig-border mt-0.5 shrink-0" />
                    <p className="text-sm text-ink-light">{answers[idx]}</p>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <textarea
                      className="flex-1 text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                      rows={2}
                      placeholder="Deine Antwort..."
                      value={answers[idx] || ''}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [idx]: e.target.value }))}
                    />
                    <button
                      onClick={() => handleSubmitAnswer(idx, qText)}
                      disabled={submitting}
                      className="shrink-0 px-3 py-2 bg-primary-700 text-white rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Generate Post Button */}
        {allAnswered && idea.status !== 'content_generated' && (
          <div className="mt-6 pt-4 border-t border-surface-border">
            <button
              onClick={handleGeneratePost}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-accent-500 text-white rounded-xl font-medium hover:bg-accent-600 disabled:opacity-50 transition-colors"
            >
              <Sparkles className="w-5 h-5" />
              {generating ? 'Posts werden erstellt...' : 'LinkedIn-Posts generieren'}
            </button>
          </div>
        )}

        {idea.status === 'content_generated' && (
          <div className="mt-6 p-4 bg-primary-50 rounded-lg border border-primary-200 text-center">
            <Sparkles className="w-6 h-6 text-primary-600 mx-auto mb-2" />
            <p className="text-sm font-medium text-primary-700">Posts wurden erstellt!</p>
            <p className="text-xs text-primary-600 mt-1">
              Schau unter "Posts" nach deinen Varianten.
            </p>
          </div>
        )}
      </div>

      {/* Source Quotes */}
      {idea.source_quotes && idea.source_quotes.length > 0 && (
        <div className="px-6 pb-6">
          <h4 className="text-xs font-medium text-ink-muted mb-2">Zitate aus der Quelle:</h4>
          <div className="space-y-2">
            {idea.source_quotes.map((q, i) => (
              <blockquote
                key={i}
                className="pl-3 border-l-2 border-primary-300 text-xs text-ink-light italic"
              >
                {typeof q === 'string' ? q : q.text || JSON.stringify(q)}
              </blockquote>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TriageCard({ idea, onSkip, onGenerate, skipping, generating }) {
  const score = idea.relevance_score ?? 0
  const pct = Math.min(score * 10, 100)
  const scoreColor =
    score >= 7
      ? 'text-status-fertig-text'
      : score >= 4
        ? 'text-status-aktiv-text'
        : 'text-status-fehler-text'
  const barColor =
    score >= 7 ? 'bg-status-fertig-border' : score >= 4 ? 'bg-status-aktiv-border' : 'bg-status-fehler-border'

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-white border border-surface-border rounded-lg hover:border-primary-300 transition-colors group">
      {/* Score pill */}
      <div className="flex flex-col items-center gap-0.5 w-10 shrink-0">
        <span className={`text-sm font-bold tabular-nums ${scoreColor}`}>{score.toFixed(1)}</span>
        <div className="w-8 h-1 bg-surface-border rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Angle badge */}
      <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-bg text-ink-light w-20 truncate">
        {idea.angle || '—'}
      </span>

      {/* Title */}
      <p className="flex-1 text-sm text-ink font-medium leading-snug line-clamp-1 min-w-0">
        {idea.title}
      </p>

      {/* Source hint */}
      {idea.source_name && (
        <span className="hidden lg:inline-flex shrink-0 items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-bg text-ink-light max-w-[120px] truncate">
          {idea.source_name}
        </span>
      )}
      {!idea.source_name && idea.source_title && (
        <span className="hidden lg:block text-[11px] text-ink-muted truncate max-w-[140px] shrink-0">
          {idea.source_title}
        </span>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onGenerate(idea.id)}
          disabled={generating}
          title="Quick-Generate Post (ohne Q&A)"
          className="flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-accent-700 bg-accent-50 border border-accent-200 rounded-md hover:bg-accent-100 disabled:opacity-40 transition-colors"
        >
          {generating ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Sparkles className="w-3 h-3" />
          )}
          Generate
        </button>
        <button
          onClick={() => onSkip(idea.id)}
          disabled={skipping}
          title="Idee überspringen"
          className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-ink-light bg-surface-bg border border-surface-border rounded-md hover:bg-surface-border disabled:opacity-40 transition-colors"
        >
          {skipping ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <SkipForward className="w-3 h-3" />
          )}
          Skip
        </button>
      </div>
    </div>
  )
}

export default function Ideas() {
  const { toast } = useToast()
  const [ideas, setIdeas] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [expandedDetail, setExpandedDetail] = useState(null) // loaded idea detail for inline QA
  const [inlineAnswers, setInlineAnswers] = useState({}) // {[qIdx]: text}
  const [inlineSubmitting, setInlineSubmitting] = useState(false)
  const [inlineGenerating, setInlineGenerating] = useState(false)
  const [inlineQuickGenerating, setInlineQuickGenerating] = useState(false)
  const [inlineMessage, setInlineMessage] = useState(null)
  const [filter, setFilter] = useState('')
  const [timeFilter, setTimeFilter] = useState({ period: 'last_30d' })
  const [showGenerate, setShowGenerate] = useState(false)
  const [analyzedItems, setAnalyzedItems] = useState([])
  const [selectedItemId, setSelectedItemId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [batchMsg, setBatchMsg] = useState(null)
  const [minScore, setMinScore] = useState(0)
  const [sortBy, setSortBy] = useState('relevance')
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [archiving, setArchiving] = useState(false)
  const [archiveMsg, setArchiveMsg] = useState(null)
  const [angleFilter, setAngleFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sources, setSources] = useState([])
  const [quickGenerating, setQuickGenerating] = useState(false)
  const [quickGenProgress, setQuickGenProgress] = useState(null) // {done, total, errors}
  const [sourceBreakdown, setSourceBreakdown] = useState(null)
  const [showSourceBreakdown, setShowSourceBreakdown] = useState(false)
  const [viewMode, setViewMode] = useState('list') // 'list' | 'triage'
  const [triageSkipping, setTriageSkipping] = useState(null) // idea id being skipped
  const [triageGenerating, setTriageGenerating] = useState(null) // idea id being generated
  const [triageMsg, setTriageMsg] = useState(null)
  const [ideasTotal, setIdeasTotal] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const PAGE_SIZE = 100
  const [showManualIdea, setShowManualIdea] = useState(false)
  const [manualTitle, setManualTitle] = useState('')
  const [manualDesc, setManualDesc] = useState('')
  const [manualAngle, setManualAngle] = useState('manual')
  const [manualHook, setManualHook] = useState('')
  const [manualSaving, setManualSaving] = useState(false)
  const [manualMsg, setManualMsg] = useState(null)

  const autoRefreshRef = useRef(null)

  useEffect(() => {
    loadIdeas()
    autoRefreshRef.current = setInterval(() => loadIdeas(true), 15000)
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [filter, timeFilter, sourceFilter, searchQuery])

  useEffect(() => {
    getSources()
      .then((s) => setSources(Array.isArray(s) ? s.filter((x) => x.is_active) : []))
      .catch(() => {})
    getIdeasSourceBreakdown()
      .then((d) => setSourceBreakdown(d))
      .catch(() => {})
  }, [])

  async function loadIdeas(silent = false) {
    const savedScrollY = silent ? window.scrollY : 0
    if (!silent) setLoading(true)
    try {
      const params = { limit: 100, offset: 0 }
      if (filter) params.status = filter
      if (sourceFilter) params.source_id = sourceFilter
      if (searchQuery.trim()) params.search = searchQuery.trim()
      if (timeFilter.period && timeFilter.period !== 'all') params.period = timeFilter.period
      if (timeFilter.date_from) params.date_from = timeFilter.date_from
      if (timeFilter.date_to) params.date_to = timeFilter.date_to
      const data = await getIdeas(params)
      const items = data?.items ?? (Array.isArray(data) ? data : [])
      const total = data?.total ?? items.length
      // flushSync ensures React commits the DOM update synchronously before scroll restore
      flushSync(() => {
        setIdeas(items)
        setIdeasTotal(total)
      })
      if (silent && savedScrollY > 0) {
        window.scrollTo({ top: savedScrollY, behavior: 'instant' })
      }
    } catch (e) {
      if (!silent) setError(e.message)
    }
    if (!silent) setLoading(false)
  }

  async function loadMore() {
    if (loadingMore || ideas.length >= ideasTotal) return
    setLoadingMore(true)
    try {
      const params = { limit: PAGE_SIZE, offset: ideas.length }
      if (filter) params.status = filter
      if (sourceFilter) params.source_id = sourceFilter
      if (searchQuery.trim()) params.search = searchQuery.trim()
      if (timeFilter.period && timeFilter.period !== 'all') params.period = timeFilter.period
      if (timeFilter.date_from) params.date_from = timeFilter.date_from
      if (timeFilter.date_to) params.date_to = timeFilter.date_to
      const data = await getIdeas(params)
      const newItems = data?.items ?? (Array.isArray(data) ? data : [])
      setIdeas((prev) => [...prev, ...newItems])
      setIdeasTotal(data?.total ?? ideasTotal)
    } catch (e) {
      console.error('loadMore failed:', e)
    }
    setLoadingMore(false)
  }

  async function openGeneratePanel() {
    setShowGenerate(true)
    try {
      const items = await getItems({ status: 'analyzed' })
      setAnalyzedItems(Array.isArray(items) ? items : [])
    } catch (e) {
      setError('Konnte analysierte Videos nicht laden: ' + e.message)
    }
  }

  async function handleGenerateIdeas() {
    if (!selectedItemId) return
    setGenerating(true)
    try {
      await generateIdeas(selectedItemId)
      setShowGenerate(false)
      setSelectedItemId('')
      await loadIdeas()
    } catch (e) {
      setError('Ideen-Generierung fehlgeschlagen: ' + e.message)
    }
    setGenerating(false)
  }

  async function toggleExpand(id) {
    if (expandedId === id) {
      setExpandedId(null)
      setExpandedDetail(null)
      setInlineAnswers({})
      setInlineMessage(null)
      return
    }
    setExpandedId(id)
    setExpandedDetail(null)
    setInlineAnswers({})
    setInlineMessage(null)
    try {
      const detail = await getIdea(id)
      setExpandedDetail(detail)
    } catch (e) {
      setInlineMessage({ type: 'error', text: 'Konnte Idee nicht laden: ' + e.message })
    }
  }

  async function handleInlineSubmit(qIdx, qText) {
    const text = inlineAnswers[qIdx] || ''
    if (text.length < 10) {
      setInlineMessage({ type: 'error', text: 'Antwort muss mindestens 10 Zeichen lang sein.' })
      return
    }
    setInlineSubmitting(true)
    setInlineMessage(null)
    try {
      await submitAnswer(expandedId, {
        question_index: qIdx,
        question_text: qText,
        answer_text: text,
        answer_source: 'web_ui',
      })
      setInlineMessage({ type: 'success', text: 'Antwort gespeichert!' })
      // Reload detail to reflect new answer
      const detail = await getIdea(expandedId)
      setExpandedDetail(detail)
      await loadIdeas()
    } catch (e) {
      setInlineMessage({ type: 'error', text: e.message })
    }
    setInlineSubmitting(false)
  }

  async function handleInlineGenerate() {
    setInlineGenerating(true)
    setInlineMessage(null)
    try {
      const result = await generatePost(expandedId)
      setInlineMessage({
        type: 'success',
        text: `${result.posts?.length || 0} Post-Varianten erstellt! Schau unter "Posts".`,
      })
      const detail = await getIdea(expandedId)
      setExpandedDetail(detail)
      await loadIdeas()
    } catch (e) {
      setInlineMessage({ type: 'error', text: e.message })
    }
    setInlineGenerating(false)
  }

  async function handleInlineQuickGenerate() {
    if (!expandedId) return
    setInlineQuickGenerating(true)
    setInlineMessage(null)
    try {
      await quickGeneratePost(expandedId)
      setInlineMessage({
        type: 'success',
        text: 'Quick-Post erstellt — schau unter "Posts" → Entwürfe',
      })
      setIdeas((prev) =>
        prev.map((i) => (i.id === expandedId ? { ...i, status: 'content_generated' } : i))
      )
    } catch (e) {
      setInlineMessage({ type: 'error', text: 'Quick-Generate fehlgeschlagen: ' + e.message })
    }
    setInlineQuickGenerating(false)
  }

  function handleSelect(id, checked) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function handleSelectLowScore() {
    const lowIds = ideas.filter((i) => (i.relevance_score ?? 10) < 4).map((i) => i.id)
    setSelectedIds(new Set(lowIds))
  }

  async function handleBulkQuickGenerate() {
    if (!selectedIds.size) return
    const MAX_BATCH = 20
    const ids = [...selectedIds].slice(0, MAX_BATCH)
    if (
      !window.confirm(
        `${ids.length} Posts direkt generieren (ohne Q&A-Workflow)?\n\nDie KI generiert Posts direkt aus Ideen-Metadaten. Ergebnis erscheint unter "Posts" → Entwürfe.${ids.length < selectedIds.size ? `\n\n(${selectedIds.size - MAX_BATCH} übersprungen, max ${MAX_BATCH}/Batch)` : ''}`
      )
    )
      return
    setQuickGenerating(true)
    setQuickGenProgress({ done: 0, total: ids.length, errors: 0 })
    let done = 0,
      errors = 0
    for (const id of ids) {
      try {
        await quickGeneratePost(id)
        done++
      } catch (e) {
        errors++
        // Budget exhausted → stop immediately
        if (e.message?.includes('Budget') || e.message?.includes('503')) break
      }
      setQuickGenProgress({ done, total: ids.length, errors })
    }
    setSelectedIds(new Set())
    setQuickGenerating(false)
    setTimeout(() => {
      setQuickGenProgress(null)
      loadIdeas()
    }, 4000)
  }

  async function handleBulkArchive() {
    if (!selectedIds.size) return
    if (!window.confirm(`${selectedIds.size} Ideen archivieren?`)) return
    setArchiving(true)
    setArchiveMsg(null)
    let done = 0
    for (const id of selectedIds) {
      try {
        await updateIdea(id, { status: 'rejected' })
        done++
      } catch {}
    }
    setSelectedIds(new Set())
    setArchiveMsg(`🗑 ${done} Ideen archiviert`)
    setTimeout(() => {
      setArchiveMsg(null)
      loadIdeas()
    }, 3000)
    setArchiving(false)
  }

  async function handleTriageSkip(id) {
    setTriageSkipping(id)
    try {
      await updateIdea(id, { status: 'skipped' })
      setIdeas((prev) => prev.filter((i) => i.id !== id))
    } catch (e) {
      setTriageMsg({ type: 'error', text: 'Skip fehlgeschlagen: ' + e.message })
      setTimeout(() => setTriageMsg(null), 3000)
    }
    setTriageSkipping(null)
  }

  async function handleTriageGenerate(id) {
    setTriageGenerating(id)
    try {
      const result = await quickGeneratePost(id)
      setTriageMsg({ type: 'success', text: `Post erstellt — schau unter "Posts" → Entwürfe` })
      setIdeas((prev) => prev.map((i) => (i.id === id ? { ...i, status: 'content_generated' } : i)))
      setTimeout(() => setTriageMsg(null), 5000)
    } catch (e) {
      setTriageMsg({ type: 'error', text: 'Quick-Generate fehlgeschlagen: ' + e.message })
      setTimeout(() => setTriageMsg(null), 4000)
    }
    setTriageGenerating(null)
  }

  async function handleCreateManualIdea() {
    if (!manualTitle.trim() || manualTitle.trim().length < 5) {
      setManualMsg({ type: 'error', text: 'Titel muss mind. 5 Zeichen haben.' })
      return
    }
    setManualSaving(true)
    setManualMsg(null)
    try {
      const r = await createManualIdea({
        title: manualTitle.trim(),
        description: manualDesc.trim() || undefined,
        angle: manualAngle || 'manual',
        hook_suggestion: manualHook.trim() || undefined,
      })
      setManualMsg({ type: 'success', text: r.message || 'Idee erstellt!' })
      setManualTitle('')
      setManualDesc('')
      setManualAngle('manual')
      setManualHook('')
      setTimeout(() => {
        setShowManualIdea(false)
        setManualMsg(null)
        loadIdeas()
      }, 2000)
    } catch (e) {
      setManualMsg({ type: 'error', text: 'Fehler: ' + e.message })
    }
    setManualSaving(false)
  }

  const filters = [
    { value: '', label: 'Alle' },
    { value: 'new', label: 'Neu' },
    { value: 'questions_sent', label: 'Fragen offen' },
    { value: 'answers_received', label: 'Beantwortet' },
    { value: 'content_generated', label: 'Posts erstellt' },
    { value: 'skipped', label: 'Übersprungen' },
  ]

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div className="shrink-0">
          <h1 className="text-xl font-bold text-ink whitespace-nowrap">Content-Ideen</h1>
          <p className="text-sm text-ink-light mt-0.5">
            {ideasTotal > 0 ? (
              <>
                <strong>{ideasTotal.toLocaleString('de')}</strong> Ideen gesamt ·{' '}
              </>
            ) : (
              ''
            )}
            Beantworte die Fragen und lass daraus Posts erstellen.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {/* Eine Primäraktion (Neue Ideen), Rest einheitlich als Secondary —
              Owner-Entscheid 2026-08-15, analog Posts.jsx-Toolbar. */}
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={handleBulkQuickGenerate}
                disabled={quickGenerating}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-50 transition-colors"
                title="Posts direkt generieren ohne Q&A (max. 20)"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {quickGenerating
                  ? `${quickGenProgress?.done || 0}/${quickGenProgress?.total || 0} generiert...`
                  : `⚡ ${Math.min(selectedIds.size, 20)} Quick-Generate`}
              </button>
              <button
                onClick={handleBulkArchive}
                disabled={archiving}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-status-fehler-text bg-status-fehler-bg border border-status-fehler-border rounded-lg hover:bg-status-fehler-border disabled:opacity-50 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {archiving ? 'Archiviere...' : `${selectedIds.size} archivieren`}
              </button>
            </>
          )}
          <button
            onClick={async () => {
              setBatchGenerating(true)
              setBatchMsg(null)
              try {
                const r = await batchGenerateIdeas()
                setBatchMsg(`🚀 ${r.triggered} Items gestartet`)
                setTimeout(() => {
                  setBatchMsg(null)
                  loadIdeas()
                }, 4000)
              } catch (e) {
                setBatchMsg('❌ ' + e.message)
              }
              setBatchGenerating(false)
            }}
            disabled={batchGenerating}
            title="Generiert Ideen für alle content_ready Items ohne Ideen"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-50 transition-colors"
          >
            {batchGenerating ? '⏳' : '🚀'} Alle generieren
          </button>
          <button
            onClick={async () => {
              if (
                !confirm(
                  'Bestehende "neue" Ideen löschen und mit Unternehmer-Profil (Branche, Tonalität) neu generieren?\n\nDas behebt generische Themen (z.B. "CIO-Transformation") und ersetzt sie durch branchenspezifische Ideen.'
                )
              )
                return
              setBatchGenerating(true)
              setBatchMsg(null)
              try {
                const r = await refreshIdeasWithProfile(20)
                setBatchMsg(`✅ ${r.message || 'Ideen werden neu generiert'}`)
                setTimeout(() => {
                  setBatchMsg(null)
                  loadIdeas()
                }, 5000)
              } catch (e) {
                setBatchMsg('❌ ' + e.message)
              }
              setBatchGenerating(false)
            }}
            disabled={batchGenerating}
            title="Löscht generische Ideen und generiert neue mit deinem Branchenprofil — behebt CIO/Enterprise-Themen für Handwerker"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-50 transition-colors"
          >
            🎯 Mit Profil neu
          </button>
          <button
            onClick={() => {
              setShowManualIdea(true)
              setManualMsg(null)
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg transition-colors"
            title="Eigene Idee ohne LLM eintragen"
          >
            <Plus className="w-3.5 h-3.5" /> Manuelle Idee
          </button>
          <Button variant="primary" size="sm" onClick={openGeneratePanel}>
            <Plus className="w-4 h-4" /> Neue Ideen
          </Button>
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 mb-5 flex-wrap">
        <div className="flex items-center gap-1 bg-surface-bg rounded-lg p-1">
          {filters.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filter === f.value
                  ? 'bg-white text-ink shadow-sm'
                  : 'text-ink-light hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 bg-surface-bg rounded-lg p-1">
          {[
            { v: 0, l: 'Alle' },
            { v: 5, l: '5+' },
            { v: 7, l: '7+' },
            { v: 9, l: '9+' },
          ].map((s) => (
            <button
              key={s.v}
              onClick={() => setMinScore(s.v)}
              className={`px-2 py-1 text-xs font-medium rounded-md transition-colors ${
                minScore === s.v ? 'bg-white text-ink shadow-sm' : 'text-ink-light hover:text-ink'
              }`}
            >
              {s.l}
            </button>
          ))}
        </div>
        {/* Angle filter + select-all-by-angle */}
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="px-2 py-1.5 text-xs border border-surface-border rounded-lg bg-white text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value="">Alle Quellen</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {sourceFilter && (
            <button
              onClick={async () => {
                const sourceName =
                  sources.find((s) => s.id === sourceFilter)?.name || 'dieser Quelle'
                if (!window.confirm(`Alle neuen Ideen von "${sourceName}" archivieren?`)) return
                try {
                  const r = await bulkArchiveIdeas({ source_id: sourceFilter, status: 'new' })
                  setArchiveMsg(`🗑 ${r.archived} Ideen von "${sourceName}" archiviert`)
                  setTimeout(() => {
                    setArchiveMsg(null)
                    loadIdeas()
                  }, 3000)
                } catch (e) {
                  toast.error('Fehler: ' + e.message)
                }
              }}
              className="px-2 py-1 text-[10px] font-medium text-status-fehler-text bg-status-fehler-bg border border-status-fehler-border rounded-md hover:bg-status-fehler-border transition-colors"
              title="Alle neuen Ideen dieser Quelle archivieren"
            >
              <Trash2 className="w-3 h-3 inline mr-0.5" />
              Alle archivieren
            </button>
          )}
          <select
            value={angleFilter}
            onChange={(e) => setAngleFilter(e.target.value)}
            className="px-2 py-1.5 text-xs border border-surface-border rounded-lg bg-white text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value="">Alle Angles</option>
            {['meinung', 'howto', 'story', 'kontroverse', 'statistik', 'trend'].map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          {angleFilter && (
            <button
              onClick={() => {
                const ids = ideas
                  .filter((i) => i.angle === angleFilter && i.status === 'new')
                  .slice(0, 20)
                  .map((i) => i.id)
                setSelectedIds(new Set(ids))
              }}
              className="px-2.5 py-1.5 text-xs font-medium text-accent-700 bg-accent-50 border border-accent-200 rounded-lg hover:bg-accent-100 transition-colors"
              title={`Alle ${angleFilter}-Ideen auswählen (max 20)`}
            >
              Top 20 wählen
            </button>
          )}
          <button
            onClick={() => setSortBy((s) => (s === 'relevance' ? 'date' : 'relevance'))}
            title={sortBy === 'relevance' ? 'Sortiert nach Relevanz' : 'Sortiert nach Datum'}
            className="px-3 py-1.5 text-xs font-medium border border-surface-border rounded-lg bg-white text-ink-light hover:bg-surface-bg transition-colors"
          >
            {sortBy === 'relevance' ? '★ Relevanz' : '📅 Datum'}
          </button>
          <button
            onClick={handleSelectLowScore}
            title="Wählt alle Ideen mit Score < 4 aus"
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-status-fehler-text border border-status-fehler-border rounded-lg bg-white hover:bg-status-fehler-bg transition-colors"
          >
            <Trash2 className="w-3 h-3" /> Score&lt;4 wählen
          </button>
          {/* View mode toggle */}
          <div className="flex items-center gap-0.5 bg-surface-bg rounded-lg p-1">
            <button
              onClick={() => setViewMode('list')}
              title="Kartenansicht"
              className={`p-1.5 rounded-md transition-colors ${viewMode === 'list' ? 'bg-white shadow-sm text-ink' : 'text-ink-light hover:text-ink'}`}
            >
              <LayoutList className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('triage')}
              title="Triage-Queue (schnelles Durcharbeiten)"
              className={`p-1.5 rounded-md transition-colors ${viewMode === 'triage' ? 'bg-white shadow-sm text-primary-700' : 'text-ink-light hover:text-ink'}`}
            >
              <Rows3 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      <div className="mt-2">
        <TimeFilter

          value={timeFilter}
          onChange={setTimeFilter}
          count={ideasTotal}
          label="Zeitraum"
        />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Ideen durchsuchen (Titel, Beschreibung)…"
            className="w-full pl-8 pr-8 py-1.5 text-xs border border-surface-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 placeholder-gray-400"
          />
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted text-xs">
            🔍
          </span>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-light text-xs font-bold"
            >
              ✕
            </button>
          )}
        </div>
        {ideas.length > 0 && (
          <button
            onClick={() => {
              const visibleIds = ideas
                .filter((i) => {
                  if (minScore > 0 && (i.relevance_score == null || i.relevance_score < minScore))
                    return false
                  if (angleFilter && i.angle !== angleFilter) return false
                  return true
                })
                .map((i) => i.id)
              const allSelected = visibleIds.every((id) => selectedIds.has(id))
              if (allSelected) {
                setSelectedIds(new Set())
              } else {
                setSelectedIds(new Set(visibleIds))
              }
            }}
            className="whitespace-nowrap px-3 py-1.5 text-xs font-medium border border-surface-border rounded-lg bg-white text-ink-light hover:bg-surface-bg transition-colors"
          >
            {ideas
              .filter((i) => {
                if (minScore > 0 && (i.relevance_score == null || i.relevance_score < minScore))
                  return false
                if (angleFilter && i.angle !== angleFilter) return false
                return true
              })
              .every((i) => selectedIds.has(i.id)) && selectedIds.size > 0
              ? '☑ Alle abwählen'
              : `☐ Alle wählen (${
                  ideas.filter((i) => {
                    if (minScore > 0 && (i.relevance_score == null || i.relevance_score < minScore))
                      return false
                    if (angleFilter && i.angle !== angleFilter) return false
                    return true
                  }).length
                })`}
          </button>
        )}
      </div>

      {batchMsg && (
        <div className="mb-4 p-3 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-sm text-status-fertig-text font-medium">
          {batchMsg}
        </div>
      )}
      {archiveMsg && (
        <div className="mb-4 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-sm text-status-fehler-text font-medium">
          {archiveMsg}
        </div>
      )}
      {quickGenProgress && (
        <div
          className={`mb-4 p-3 rounded-xl border text-sm ${quickGenerating ? 'bg-accent-50 border-accent-200 text-accent-800' : quickGenProgress.errors === 0 ? 'bg-status-fertig-bg border-status-fertig-border text-status-fertig-text' : 'bg-status-aktiv-bg border-status-aktiv-border text-status-aktiv-text'}`}
        >
          <div className="flex items-center gap-3">
            <span className="font-semibold">
              {quickGenerating
                ? `⚡ Generiere Posts… ${quickGenProgress.done}/${quickGenProgress.total}`
                : `✓ ${quickGenProgress.done} Posts generiert${quickGenProgress.errors > 0 ? `, ${quickGenProgress.errors} Fehler` : ''}`}
            </span>
            {quickGenerating && (
              <div className="flex-1 h-1.5 bg-white/60 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-500 rounded-full transition-all"
                  style={{
                    width: `${quickGenProgress.total > 0 ? (quickGenProgress.done / quickGenProgress.total) * 100 : 0}%`,
                  }}
                />
              </div>
            )}
            {!quickGenerating && (
              <span className="text-xs opacity-70">→ Unter "Posts" sichtbar</span>
            )}
          </div>
        </div>
      )}

      {/* Source Breakdown Panel — shows idea count per source with cleanup actions */}
      {sourceBreakdown && sourceBreakdown.sources && sourceBreakdown.sources.length > 0 && (
        <div className="mb-4 rounded-xl border border-surface-border bg-surface-bg overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-surface-bg transition-colors"
            onClick={() => setShowSourceBreakdown((v) => !v)}
          >
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-ink">Ideen nach Quelle</span>
              <span className="text-xs text-ink-muted bg-white border border-surface-border px-1.5 py-0.5 rounded">
                {sourceBreakdown.total.toLocaleString('de')} gesamt ·{' '}
                {sourceBreakdown.sources.length} Quellen
              </span>
            </div>
            <span className="text-xs text-ink-muted">
              {showSourceBreakdown ? '▲ Einklappen' : '▼ Anzeigen'}
            </span>
          </button>
          {showSourceBreakdown && (
            <div className="border-t border-surface-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-bg border-b border-surface-border">
                    <th className="text-left px-4 py-2 font-medium text-ink-muted">Quelle</th>
                    <th className="text-right px-3 py-2 font-medium text-ink-muted">Ideen</th>
                    <th className="text-right px-3 py-2 font-medium text-ink-muted">Neu</th>
                    <th className="py-2 px-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {sourceBreakdown.sources.map((src) => (
                    <tr
                      key={src.source_id}
                      className="border-b border-surface-border last:border-0 hover:bg-white/60"
                    >
                      <td className="px-4 py-2 font-medium text-ink truncate max-w-[220px]">
                        {src.source_name}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-ink-muted">
                        {src.idea_count.toLocaleString('de')}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-status-aktiv-text">
                        {src.new_count.toLocaleString('de')}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setSourceFilter(src.source_id)}
                            className="px-2 py-0.5 text-[10px] text-primary-700 bg-primary-50 border border-primary-200 rounded hover:bg-primary-100 transition-colors"
                          >
                            Filtern
                          </button>
                          {src.new_count > 0 && (
                            <button
                              onClick={async () => {
                                if (
                                  !window.confirm(
                                    `${src.new_count} neue Ideen von "${src.source_name}" archivieren?`
                                  )
                                )
                                  return
                                try {
                                  const r = await bulkArchiveIdeas({
                                    source_id: src.source_id,
                                    status: 'new',
                                  })
                                  setArchiveMsg(`🗑 ${r.archived} Ideen archiviert`)
                                  setTimeout(() => {
                                    setArchiveMsg(null)
                                    loadIdeas()
                                    getIdeasSourceBreakdown()
                                      .then((d) => setSourceBreakdown(d))
                                      .catch(() => {})
                                  }, 3000)
                                } catch (e) {
                                  toast.error('Fehler: ' + e.message)
                                }
                              }}
                              className="px-2 py-0.5 text-[10px] text-status-fehler-text bg-status-fehler-bg border border-status-fehler-border rounded hover:bg-status-fehler-border transition-colors"
                            >
                              Archivieren
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {showGenerate && (
        <div className="mb-6 p-5 bg-white rounded-xl border border-primary-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary-600" />
              Ideen aus analysiertem Video generieren
            </h3>
            <button
              onClick={() => setShowGenerate(false)}
              className="text-xs text-ink-muted hover:text-ink"
            >
              Abbrechen
            </button>
          </div>
          {analyzedItems.length === 0 ? (
            <p className="text-sm text-ink-light">
              Keine analysierten Videos gefunden. Analysiere zuerst ein Video unter "Quellen".
            </p>
          ) : (
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs text-ink-muted mb-1">Video auswaehlen</label>
                <select
                  value={selectedItemId}
                  onChange={(e) => setSelectedItemId(e.target.value)}
                  className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">— Video waehlen —</option>
                  {analyzedItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleGenerateIdeas}
                disabled={!selectedItemId || generating}
                className="flex items-center gap-2 px-4 py-2 bg-accent-500 text-white rounded-lg font-medium hover:bg-accent-600 disabled:opacity-50 transition-colors"
              >
                {generating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                {generating ? 'Generiere...' : 'Ideen generieren'}
              </button>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-status-fehler-bg text-status-fehler-text rounded-lg text-sm">
          {error}
        </div>
      )}

      {triageMsg && (
        <div
          className={`mb-4 p-3 rounded-lg text-sm font-medium ${triageMsg.type === 'error' ? 'bg-status-fehler-bg text-status-fehler-text border border-status-fehler-border' : 'bg-status-fertig-bg text-status-fertig-text border border-status-fertig-border'}`}
        >
          {triageMsg.text}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-ink-muted">Lade Ideen...</div>
      ) : ideas.length === 0 ? (
        <div className="text-center py-12">
          <Lightbulb className="w-12 h-12 text-ink-muted mx-auto mb-3" />
          <p className="text-sm text-ink-light">Keine Ideen in diesem Zeitraum.</p>
          <p className="text-xs text-ink-muted mt-1">Probier einen größeren Zeitraum.</p>
          {timeFilter.period !== 'all' && (
            <button
              onClick={() => setTimeFilter({ period: 'all' })}
              className="mt-3 px-4 py-1.5 text-xs font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50"
            >
              Alle anzeigen
            </button>
          )}
        </div>
      ) : viewMode === 'triage' ? (
        <div>
          <div className="mb-3 flex items-center gap-2 p-3 bg-primary-50 border border-primary-100 rounded-xl">
            <Rows3 className="w-4 h-4 text-primary-600 shrink-0" />
            <p className="text-xs text-primary-700 font-medium">
              Triage-Queue — klicke <strong>Generate</strong> für sofortigen Post (ohne Q&A) oder{' '}
              <strong>Skip</strong> zum Überspringen.{' '}
              <span className="opacity-70">
                {
                  ideas.filter((i) => {
                    if (minScore > 0 && (i.relevance_score == null || i.relevance_score < minScore))
                      return false
                    if (angleFilter && i.angle !== angleFilter) return false
                    return true
                  }).length
                }{' '}
                Ideen
              </span>
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            {ideas
              .filter((idea) => {
                if (
                  minScore > 0 &&
                  (idea.relevance_score == null || idea.relevance_score < minScore)
                )
                  return false
                if (angleFilter && idea.angle !== angleFilter) return false
                return true
              })
              .sort((a, b) => {
                if (sortBy === 'relevance')
                  return (b.relevance_score || 0) - (a.relevance_score || 0)
                return new Date(b.created_at || 0) - new Date(a.created_at || 0)
              })
              .map((idea) => (
                <TriageCard
                  key={idea.id}
                  idea={idea}
                  onSkip={handleTriageSkip}
                  onGenerate={handleTriageGenerate}
                  skipping={triageSkipping === idea.id}
                  generating={triageGenerating === idea.id}
                />
              ))}
          </div>
        </div>
      ) : (
        <div className="grid gap-3">
          {ideas
            .filter((idea) => {
              if (minScore > 0 && (idea.relevance_score == null || idea.relevance_score < minScore))
                return false
              if (angleFilter && idea.angle !== angleFilter) return false
              return true
            })
            .sort((a, b) => {
              if (sortBy === 'relevance') return (b.relevance_score || 0) - (a.relevance_score || 0)
              return new Date(b.created_at || 0) - new Date(a.created_at || 0)
            })
            .map((idea) => (
              <IdeaCard
                key={idea.id}
                idea={idea}
                isExpanded={expandedId === idea.id}
                onToggle={toggleExpand}
                isSelected={selectedIds.has(idea.id)}
                onSelect={handleSelect}
                inlineContent={
                  expandedId === idea.id ? (
                    <InlineQA
                      idea={expandedDetail}
                      answers={inlineAnswers}
                      onChange={(idx, val) => setInlineAnswers((prev) => ({ ...prev, [idx]: val }))}
                      onSubmit={handleInlineSubmit}
                      onGeneratePost={handleInlineGenerate}
                      onQuickGenerate={handleInlineQuickGenerate}
                      submitting={inlineSubmitting}
                      generating={inlineGenerating}
                      quickGenerating={inlineQuickGenerating}
                      message={inlineMessage}
                    />
                  ) : null
                }
              />
            ))}
          {ideas.length < ideasTotal && (
            <div className="flex items-center justify-center gap-3 py-4 border-t border-surface-border">
              <span className="text-xs text-ink-muted">
                {ideas.length} von {ideasTotal.toLocaleString('de')} geladen
              </span>
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors disabled:opacity-50"
              >
                {loadingMore
                  ? 'Lade...'
                  : `Weitere ${Math.min(PAGE_SIZE, ideasTotal - ideas.length)} laden`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Manual Idea Modal */}
      {showManualIdea && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowManualIdea(false)
          }}
        >
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-ink">Manuelle Idee erstellen</h2>
              <button
                onClick={() => setShowManualIdea(false)}
                className="text-ink-muted hover:text-ink-light text-lg font-bold"
              >
                ✕
              </button>
            </div>
            <p className="text-xs text-ink-muted">
              Trage eine eigene Idee ein — ohne LLM-Budget. Sobald Budget verfügbar, kannst du
              Quick-Generate nutzen.
            </p>
            {manualMsg && (
              <div
                className={`p-3 rounded-lg text-xs font-medium ${manualMsg.type === 'error' ? 'bg-status-fehler-bg text-status-fehler-text border border-status-fehler-border' : 'bg-status-fertig-bg text-status-fertig-text border border-status-fertig-border'}`}
              >
                {manualMsg.text}
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-ink mb-1">
                Titel <span className="text-status-fehler-text">*</span>
              </label>
              <input
                type="text"
                value={manualTitle}
                onChange={(e) => setManualTitle(e.target.value)}
                placeholder="z.B. Heizungsoptimierung im Winter: 5 Tipps für SHK-Kunden"
                className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                maxLength={200}
              />
              <p className="text-[10px] text-ink-muted mt-0.5">{manualTitle.length}/200</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-ink mb-1">
                Beschreibung (optional)
              </label>
              <textarea
                value={manualDesc}
                onChange={(e) => setManualDesc(e.target.value)}
                placeholder="Kurze Beschreibung des Themas..."
                className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                rows={3}
                maxLength={1000}
              />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink mb-1">Content-Angle</label>
                <select
                  value={manualAngle}
                  onChange={(e) => setManualAngle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {['manual', 'howto', 'meinung', 'story', 'kontroverse', 'statistik', 'trend'].map(
                    (a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    )
                  )}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-ink mb-1">
                Hook-Vorschlag (optional)
              </label>
              <input
                type="text"
                value={manualHook}
                onChange={(e) => setManualHook(e.target.value)}
                placeholder="z.B. 'Die meisten Hausbesitzer wissen nicht, dass...'"
                className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                maxLength={300}
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowManualIdea(false)}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-ink-light border border-surface-border rounded-xl hover:bg-surface-bg transition-colors"
              >
                Abbrechen
              </button>
              <button
                onClick={handleCreateManualIdea}
                disabled={manualSaving || manualTitle.trim().length < 5}
                className="flex-1 px-4 py-2.5 text-sm font-semibold text-white bg-status-fertig-border hover:bg-status-fertig-text rounded-xl disabled:opacity-50 transition-colors"
              >
                {manualSaving ? '⏳ Speichern...' : '✓ Idee erstellen'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
