import { useState, useEffect } from 'react'
import { Lightbulb, MessageCircleQuestion, ChevronDown, ChevronUp, Send, Sparkles, Tag, Star, Clock, CheckCircle2, AlertCircle } from 'lucide-react'
import { getIdeas, getIdea, submitAnswer, generatePost, updateIdea } from '../api'

const STATUS_MAP = {
  new: { label: 'Neu', color: 'bg-blue-100 text-blue-700', icon: Lightbulb },
  questions_sent: { label: 'Fragen offen', color: 'bg-amber-100 text-amber-700', icon: MessageCircleQuestion },
  answers_received: { label: 'Beantwortet', color: 'bg-emerald-100 text-emerald-700', icon: CheckCircle2 },
  content_generated: { label: 'Post erstellt', color: 'bg-primary-100 text-primary-700', icon: Sparkles },
  dismissed: { label: 'Verworfen', color: 'bg-gray-100 text-gray-500', icon: AlertCircle },
}

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] || { label: status, color: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${s.color}`}>
      {s.icon && <s.icon className="w-3 h-3" />}
      {s.label}
    </span>
  )
}

function RelevanceBar({ score }) {
  const s = score ?? 0
  const pct = Math.min(s * 10, 100)
  const color = s >= 7 ? 'bg-emerald-500' : s >= 4 ? 'bg-amber-500' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ink-muted">{s.toFixed(1)}</span>
    </div>
  )
}

function IdeaCard({ idea, onExpand, isExpanded }) {
  return (
    <div className="bg-white rounded-xl border border-surface-border hover:border-primary-300 transition-colors">
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <StatusBadge status={idea.status} />
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-100 text-xs text-ink-light">
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
            {idea.questions_count > 0 && (
              <span className="text-[11px] text-ink-muted">
                {idea.questions_count} Fragen
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
          <span className="text-[11px] text-ink-muted flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {idea.created_at ? new Date(idea.created_at).toLocaleDateString('de-DE') : '-'}
          </span>
          <button
            onClick={() => onExpand(idea.id)}
            className="flex items-center gap-1 text-xs text-primary-700 hover:text-primary-800 font-medium"
          >
            {isExpanded ? 'Einklappen' : 'Details'}
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
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
      ;(data.answers || []).forEach(a => { existing[a.question_index] = a.answer_text })
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
  const existingAnswerIndices = new Set((idea.answers || []).map(a => a.question_index))
  const allAnswered = questions.length > 0 && questions.every((_, i) => existingAnswerIndices.has(i))

  return (
    <div className="bg-white rounded-xl border border-surface-border shadow-sm">
      <div className="p-6 border-b border-surface-border">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <StatusBadge status={idea.status} />
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-xs text-ink-light">{idea.angle}</span>
            </div>
            <h2 className="text-lg font-semibold text-ink">{idea.title}</h2>
            <p className="text-sm text-ink-light mt-1">{idea.description}</p>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-sm">Schliessen</button>
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
          <div className={`mb-4 p-3 rounded-lg text-sm ${message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
            {message.text}
          </div>
        )}

        <div className="space-y-4">
          {questions.map((q, idx) => {
            const answered = existingAnswerIndices.has(idx)
            const qText = typeof q === 'string' ? q : q.question || q.text || JSON.stringify(q)
            return (
              <div key={idx} className={`p-4 rounded-lg border ${answered ? 'border-emerald-200 bg-emerald-50/50' : 'border-gray-200 bg-gray-50'}`}>
                <p className="text-sm font-medium text-ink mb-2">
                  <span className="text-primary-600 mr-1">{idx + 1}.</span>
                  {qText}
                </p>
                {answered ? (
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                    <p className="text-sm text-ink-light">{answers[idx]}</p>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <textarea
                      className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                      rows={2}
                      placeholder="Deine Antwort..."
                      value={answers[idx] || ''}
                      onChange={e => setAnswers(prev => ({ ...prev, [idx]: e.target.value }))}
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
          <div className="mt-6 pt-4 border-t border-gray-100">
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
            <p className="text-xs text-primary-600 mt-1">Schau unter "Posts" nach deinen Varianten.</p>
          </div>
        )}
      </div>

      {/* Source Quotes */}
      {idea.source_quotes && idea.source_quotes.length > 0 && (
        <div className="px-6 pb-6">
          <h4 className="text-xs font-medium text-ink-muted mb-2">Zitate aus der Quelle:</h4>
          <div className="space-y-2">
            {idea.source_quotes.map((q, i) => (
              <blockquote key={i} className="pl-3 border-l-2 border-primary-300 text-xs text-ink-light italic">
                {typeof q === 'string' ? q : q.text || JSON.stringify(q)}
              </blockquote>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Ideas() {
  const [ideas, setIdeas] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [filter, setFilter] = useState('')

  useEffect(() => { loadIdeas() }, [filter])

  async function loadIdeas() {
    setLoading(true)
    try {
      const params = {}
      if (filter) params.status = filter
      const data = await getIdeas(params)
      setIdeas(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const filters = [
    { value: '', label: 'Alle' },
    { value: 'new', label: 'Neu' },
    { value: 'questions_sent', label: 'Fragen offen' },
    { value: 'answers_received', label: 'Beantwortet' },
    { value: 'content_generated', label: 'Posts erstellt' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Content-Ideen</h1>
          <p className="text-sm text-ink-light mt-0.5">Beantworte die Fragen und lass daraus Posts erstellen.</p>
        </div>
        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
          {filters.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filter === f.value ? 'bg-white text-ink shadow-sm' : 'text-ink-light hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>
      )}

      {expandedId ? (
        <IdeaDetail ideaId={expandedId} onClose={() => { setExpandedId(null); loadIdeas() }} />
      ) : loading ? (
        <div className="text-center py-12 text-ink-muted">Lade Ideen...</div>
      ) : ideas.length === 0 ? (
        <div className="text-center py-12">
          <Lightbulb className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-ink-light">Noch keine Ideen vorhanden.</p>
          <p className="text-xs text-ink-muted mt-1">Analysiere ein Video, um Content-Ideen zu generieren.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {ideas.map(idea => (
            <IdeaCard
              key={idea.id}
              idea={idea}
              isExpanded={false}
              onExpand={setExpandedId}
            />
          ))}
        </div>
      )}
    </div>
  )
}
