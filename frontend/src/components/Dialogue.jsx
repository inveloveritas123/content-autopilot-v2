// AUDITED-2026-08-14 (D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState, useEffect } from 'react'
import {
  MessageSquare,
  ChevronRight,
  Copy,
  Check,
  Loader2,
  BookOpen,
  Lightbulb,
  ArrowRight,
} from 'lucide-react'
import {
  getDialogueItems,
  getDialogueContext,
  submitDialogueAnswers,
  generateDialoguePostPrompt,
} from '../api'

// Local aliases
const submitAnswers = submitDialogueAnswers
const generatePostPrompt = generateDialoguePostPrompt

const STATUS_LABELS = {
  no_questions_yet: {
    label: 'Fragen ausstehend',
    color: 'bg-surface-bg text-ink-light',
    dot: 'bg-surface-card',
  },
  waiting_for_answers: {
    label: 'Antworten fehlen',
    color: 'bg-accent-100 text-accent-700',
    dot: 'bg-accent-500',
  },
  answers_given: {
    label: 'Bereit für Post',
    color: 'bg-status-fertig-bg text-status-fertig-text',
    dot: 'bg-status-fertig-bg',
  },
}

const FORMAT_OPTIONS = [
  {
    key: 'story',
    emoji: '📖',
    label: 'Story',
    desc: 'Persönliche Geschichte mit Erkenntnismoment',
  },
  { key: 'opinion', emoji: '💡', label: 'Meinung', desc: 'Provokante These, klare Haltung' },
  { key: 'how_to', emoji: '🛠', label: 'How-To', desc: 'Konkrete Schritte aus eigener Erfahrung' },
  { key: 'question', emoji: '❓', label: 'Frage', desc: 'Öffnet Diskussion in der Community' },
]

const ANGLE_COLORS = {
  story: 'text-accent-600 bg-accent-50',
  meinung: 'text-primary-600 bg-primary-50',
  howto: 'text-status-fertig-text bg-status-fertig-bg',
  frage: 'text-accent-600 bg-accent-50',
}

function ItemCard({ item, isActive, onClick }) {
  const st = STATUS_LABELS[item.dialogue_status] || STATUS_LABELS.no_questions_yet
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border transition-all ${
        isActive
          ? 'border-primary-400 bg-primary-50 shadow-sm'
          : 'border-surface-border bg-white hover:border-surface-border hover:bg-surface-bg'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-xs font-medium text-ink leading-snug line-clamp-2 flex-1">
          {item.title}
        </span>
        <ChevronRight
          className={`w-4 h-4 shrink-0 mt-0.5 transition-transform ${isActive ? 'text-primary-600 rotate-90' : 'text-ink-light'}`}
        />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium ${st.color}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
          {st.label}
        </span>
        {item.question_count > 0 && (
          <span className="text-[10px] text-ink-muted">
            {item.answered_count}/{item.question_count} Fragen beantwortet
          </span>
        )}
        <span className="text-[10px] text-ink-muted ml-auto">{item.source_name}</span>
      </div>
      {item.summary_1sentence && (
        <p className="text-[11px] text-ink-muted mt-2 line-clamp-2 leading-relaxed">
          {item.summary_1sentence}
        </p>
      )}
    </button>
  )
}

function QuestionForm({ context, itemId, onDone }) {
  const [answers, setAnswers] = useState(() => {
    const init = {}
    context.smart_questions.forEach((q) => {
      init[q.id] = q.answer || ''
    })
    return init
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const payload = Object.entries(answers)
        .filter(([, v]) => v.trim())
        .map(([question_id, answer_text]) => ({ question_id, answer_text }))
      if (!payload.length) {
        setError('Bitte mindestens eine Frage beantworten.')
        setSaving(false)
        return
      }
      const result = await submitAnswers(itemId, payload)
      setSaved(true)
      setTimeout(() => {
        setSaved(false)
        onDone()
      }, 1200)
    } catch (e) {
      setError(e.message || 'Fehler beim Speichern')
    }
    setSaving(false)
  }

  return (
    <div className="space-y-4">
      <div className="bg-accent-50 border border-accent-200 rounded-xl p-4">
        <p className="text-xs text-accent-800 font-medium mb-1">
          💬 Deine persönliche Erfahrung ist der Schlüssel
        </p>
        <p className="text-[11px] text-accent-700 leading-relaxed">
          Beantworte diese Fragen aus deiner Perspektive als{' '}
          {context.entrepreneur?.name || 'Unternehmer'}. Deine Antworten werden zu einem
          authentischen LinkedIn-Post — kein KI-Blubber, deine echten Erlebnisse.
        </p>
      </div>

      {context.smart_questions.map((q, i) => (
        <div key={q.id} className="bg-white rounded-xl border border-surface-border p-4">
          <div className="flex items-start gap-3 mb-3">
            <span className="w-6 h-6 rounded-full bg-primary-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
              {i + 1}
            </span>
            <div className="flex-1">
              <p className="text-sm font-medium text-ink">{q.question}</p>
              {q.transcript_reference && (
                <p className="text-[11px] text-ink-muted mt-1 italic border-l-2 border-surface-border pl-2">
                  Bezug: „{q.transcript_reference.slice(0, 120)}…"
                </p>
              )}
              {q.why_relevant && (
                <p className="text-[10px] text-primary-600 mt-1">💡 {q.why_relevant}</p>
              )}
            </div>
          </div>
          <textarea
            value={answers[q.id] || ''}
            onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
            placeholder={q.answered ? '(bereits beantwortet)' : 'Deine Antwort...'}
            rows={3}
            className="w-full text-sm border border-surface-border rounded-lg p-3 resize-y focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-surface-bg placeholder-gray-400"
          />
        </div>
      ))}

      {error && (
        <p className="text-sm text-status-fehler-text bg-status-fehler-bg rounded-lg p-3">
          {error}
        </p>
      )}

      <button
        onClick={handleSave}
        disabled={saving || saved}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary-600 text-white rounded-xl font-medium text-sm hover:bg-primary-700 disabled:opacity-60 transition-colors"
      >
        {saving ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : saved ? (
          <Check className="w-4 h-4" />
        ) : (
          <ArrowRight className="w-4 h-4" />
        )}
        {saving ? 'Speichern…' : saved ? 'Gespeichert! ✓' : 'Antworten speichern'}
      </button>
    </div>
  )
}

function GeneratePostPanel({ context, itemId }) {
  const [format, setFormat] = useState('story')
  const [generating, setGenerating] = useState(false)
  const [promptData, setPromptData] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    setPromptData(null)
    try {
      const result = await generatePostPrompt(itemId, format)
      setPromptData(result)
    } catch (e) {
      setError(e.message || 'Fehler')
    }
    setGenerating(false)
  }

  function handleCopy() {
    if (promptData?.prompt_for_claude) {
      navigator.clipboard.writeText(promptData.prompt_for_claude)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-status-fertig-bg border border-status-fertig-border rounded-xl p-4">
        <p className="text-xs text-status-fertig-text font-medium mb-1">
          🎯 {context.answered_count} Frage{context.answered_count !== 1 ? 'n' : ''} beantwortet —
          bereit für Post-Generierung
        </p>
        <p className="text-[11px] text-status-fertig-text">
          Wähle ein Format und kopiere den Claude-Prompt. Claude generiert deinen Post direkt — ohne
          KI-Guthaben (kostenlos).
        </p>
      </div>

      {/* Format selection */}
      <div>
        <p className="text-xs font-medium text-ink mb-2">Post-Format wählen:</p>
        <div className="grid grid-cols-2 gap-2">
          {FORMAT_OPTIONS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFormat(f.key)}
              className={`p-3 rounded-xl border-2 text-left transition-all ${
                format === f.key
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-surface-border hover:border-surface-border bg-white'
              }`}
            >
              <span className="text-base block mb-0.5">{f.emoji}</span>
              <span className="text-xs font-medium text-ink">{f.label}</span>
              <span className="text-[10px] text-ink-muted block mt-0.5">{f.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={handleGenerate}
        disabled={generating}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary-600 text-white rounded-xl font-medium text-sm hover:bg-primary-700 disabled:opacity-60 transition-colors"
      >
        {generating ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Lightbulb className="w-4 h-4" />
        )}
        {generating ? 'Generiere Prompt…' : 'Claude-Prompt generieren'}
      </button>

      {error && (
        <p className="text-sm text-status-fehler-text bg-status-fehler-bg rounded-lg p-3">
          {error}
        </p>
      )}

      {promptData && (
        <div className="bg-surface-card rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-ink-light font-medium">
              Claude-Prompt bereit — in Claude einfügen:
            </span>
            <button
              onClick={handleCopy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                copied
                  ? 'bg-status-fertig-bg text-white'
                  : 'bg-surface-card text-ink-muted hover:bg-surface-card'
              }`}
            >
              {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Kopiert!' : 'Kopieren'}
            </button>
          </div>
          <pre className="text-xs text-ink-muted whitespace-pre-wrap leading-relaxed font-mono max-h-64 overflow-y-auto">
            {promptData.prompt_for_claude}
          </pre>
          <p className="text-[10px] text-ink-light mt-3">
            💡 Tipp: Kopiere diesen Prompt und füge ihn in ein neues Claude-Gespräch ein. Claude
            schreibt den Post direkt — kein API-Budget nötig.
          </p>
        </div>
      )}
    </div>
  )
}

function ItemDetail({ item, onBack }) {
  const [context, setContext] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('questions') // 'questions' | 'generate' | 'analysis'
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getDialogueContext(item.id)
      .then((d) => {
        setContext(d)
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }, [item.id, refreshKey])

  if (loading)
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
      </div>
    )
  if (error)
    return (
      <div className="p-4 bg-status-fehler-bg text-status-fehler-text rounded-xl text-sm">
        {error}
      </div>
    )
  if (!context) return null

  const hasQuestions = context.smart_questions.length > 0
  const hasAnswers = context.answered_count > 0

  // Determine active tab
  const effectiveTab = !hasQuestions ? 'analysis' : tab

  return (
    <div className="space-y-4">
      {/* Item header */}
      <div className="bg-white rounded-xl border border-surface-border p-4">
        <h2 className="text-sm font-semibold text-ink mb-1 line-clamp-2">{context.item.title}</h2>
        <div className="flex items-center gap-2 text-[11px] text-ink-muted flex-wrap">
          <span>{context.source?.name}</span>
          {context.analysis.main_topic && (
            <span className="px-2 py-0.5 bg-surface-bg text-ink-light rounded-full">
              {context.analysis.main_topic}
            </span>
          )}
          {context.item.url && (
            <a
              href={context.item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline ml-auto"
            >
              Quelle ↗
            </a>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-bg rounded-xl p-1">
        {hasQuestions && (
          <button
            onClick={() => setTab('questions')}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
              effectiveTab === 'questions'
                ? 'bg-white shadow-sm text-ink'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            💬 Fragen{' '}
            {hasAnswers
              ? `(${context.answered_count}/${context.question_count} ✓)`
              : `(${context.question_count})`}
          </button>
        )}
        {hasAnswers && (
          <button
            onClick={() => setTab('generate')}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
              effectiveTab === 'generate'
                ? 'bg-white shadow-sm text-ink'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            🚀 Post generieren
          </button>
        )}
        <button
          onClick={() => setTab('analysis')}
          className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
            effectiveTab === 'analysis'
              ? 'bg-white shadow-sm text-ink'
              : 'text-ink-muted hover:text-ink'
          }`}
        >
          📋 Analyse
        </button>
      </div>

      {/* Tab content */}
      {effectiveTab === 'questions' && hasQuestions && (
        <QuestionForm
          context={context}
          itemId={item.id}
          onDone={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {effectiveTab === 'generate' && <GeneratePostPanel context={context} itemId={item.id} />}

      {effectiveTab === 'analysis' && (
        <div className="space-y-3">
          {!hasQuestions && (
            <div className="bg-surface-bg border border-surface-border rounded-xl p-4">
              <p className="text-xs font-medium text-ink mb-1">
                ⏳ Smarte Fragen werden noch generiert
              </p>
              <p className="text-[11px] text-ink-muted">
                Sobald wieder KI-Guthaben verfügbar ist, generiert die Pipeline automatisch 3-5
                personalisierte Fragen aus diesem Content — basierend auf deinem Unternehmer-Profil.
              </p>
            </div>
          )}

          {context.analysis.summary && (
            <div className="bg-white rounded-xl border border-surface-border p-4">
              <p className="text-xs font-semibold text-ink mb-2 flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-primary-600" /> Zusammenfassung
              </p>
              <p className="text-xs text-ink-muted leading-relaxed">{context.analysis.summary}</p>
            </div>
          )}

          {context.analysis.key_insights?.length > 0 && (
            <div className="bg-white rounded-xl border border-surface-border p-4">
              <p className="text-xs font-semibold text-ink mb-2">💡 Key Insights</p>
              <ul className="space-y-1.5">
                {context.analysis.key_insights.slice(0, 5).map((ins, i) => (
                  <li key={i} className="text-xs text-ink-muted flex items-start gap-2">
                    <span className="w-4 h-4 rounded-full bg-primary-100 text-primary-700 text-[10px] flex items-center justify-center shrink-0 mt-0.5 font-bold">
                      {i + 1}
                    </span>
                    {typeof ins === 'string' ? ins : ins.text || JSON.stringify(ins)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {context.content.key_quotes?.length > 0 && (
            <div className="bg-white rounded-xl border border-surface-border p-4">
              <p className="text-xs font-semibold text-ink mb-2">💬 Zitate aus dem Transkript</p>
              <div className="space-y-2">
                {context.content.key_quotes.map((q, i) => (
                  <blockquote
                    key={i}
                    className="text-xs text-ink-muted italic border-l-2 border-primary-200 pl-3 py-0.5"
                  >
                    „{q}"
                  </blockquote>
                ))}
              </div>
            </div>
          )}

          {context.content.transcript_excerpt && (
            <div className="bg-white rounded-xl border border-surface-border p-4">
              <p className="text-xs font-semibold text-ink mb-2">📝 Transkript-Auszug</p>
              <p className="text-xs text-ink-muted leading-relaxed line-clamp-6">
                {context.content.transcript_excerpt}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Dialogue() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeItem, setActiveItem] = useState(null)
  const [filter, setFilter] = useState('all') // 'all' | 'ready' | 'answers'

  useEffect(() => {
    setLoading(true)
    getDialogueItems(50, false)
      .then((d) => {
        setItems(d)
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  const filtered = items.filter((item) => {
    if (filter === 'ready') return item.dialogue_status === 'waiting_for_answers'
    if (filter === 'answers') return item.dialogue_status === 'answers_given'
    return true
  })

  const stats = {
    total: items.length,
    withQuestions: items.filter((i) => i.question_count > 0).length,
    ready: items.filter((i) => i.dialogue_status === 'answers_given').length,
  }

  return (
    <div className="flex h-full gap-0">
      {/* Left panel — item list */}
      <div className="w-80 shrink-0 border-r border-surface-border flex flex-col">
        <div className="p-4 border-b border-surface-border">
          <h1 className="text-base font-bold text-ink flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary-600" />
            Dialogue-Workflow
          </h1>
          <p className="text-[11px] text-ink-muted mt-0.5">
            Deine Erfahrungen → authentische LinkedIn-Posts
          </p>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2 mt-3">
            <div className="bg-surface-bg rounded-lg p-2 text-center">
              <p className="text-base font-bold text-ink">{stats.total}</p>
              <p className="text-[10px] text-ink-muted">Items</p>
            </div>
            <div className="bg-accent-50 rounded-lg p-2 text-center">
              <p className="text-base font-bold text-accent-700">{stats.withQuestions}</p>
              <p className="text-[10px] text-ink-muted">mit Fragen</p>
            </div>
            <div className="bg-status-fertig-bg rounded-lg p-2 text-center">
              <p className="text-base font-bold text-status-fertig-text">{stats.ready}</p>
              <p className="text-[10px] text-ink-muted">bereit</p>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-1 mt-3 bg-surface-bg rounded-lg p-1">
            {[
              ['all', 'Alle'],
              ['ready', 'Fragen'],
              ['answers', 'Bereit'],
            ].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all ${filter === key ? 'bg-white shadow-sm text-ink' : 'text-ink-muted'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {loading && (
            <div className="flex items-center justify-center h-20">
              <Loader2 className="w-5 h-5 animate-spin text-primary-600" />
            </div>
          )}
          {error && <p className="text-xs text-status-fehler-text p-2">{error}</p>}
          {!loading && filtered.length === 0 && (
            <div className="text-center py-8">
              <MessageSquare className="w-8 h-8 text-ink-muted mx-auto mb-2" />
              <p className="text-xs text-ink-muted">Keine Items mit diesem Filter</p>
            </div>
          )}
          {filtered.map((item) => (
            <ItemCard
              key={item.id}
              item={item}
              isActive={activeItem?.id === item.id}
              onClick={() => setActiveItem(item)}
            />
          ))}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 overflow-y-auto p-5">
        {!activeItem ? (
          <div className="flex flex-col items-center justify-center h-full text-center max-w-md mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-primary-100 flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8 text-primary-600" />
            </div>
            <h2 className="text-base font-semibold text-ink mb-2">Dialogue-Workflow</h2>
            <p className="text-sm text-ink-muted leading-relaxed mb-4">
              Wähle ein Item aus der Liste. Beantworte die Fragen zu deinen persönlichen
              Erfahrungen. Lass Claude daraus einen authentischen LinkedIn-Post schreiben —
              kostenlos, ohne LLM-Budget.
            </p>
            <div className="bg-surface-bg rounded-xl p-4 text-left w-full space-y-3">
              <p className="text-xs font-semibold text-ink">So funktioniert's:</p>
              {[
                ['1', '💡', 'Item wählen', 'Wähle einen analysierten Content-Beitrag'],
                ['2', '💬', 'Fragen beantworten', 'Beantworte 3-5 smarte Fragen aus deiner Sicht'],
                [
                  '3',
                  '🚀',
                  'Post generieren',
                  'Kopiere den Claude-Prompt → Post wird direkt geschrieben',
                ],
              ].map(([n, emoji, title, desc]) => (
                <div key={n} className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-full bg-primary-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {n}
                  </span>
                  <div>
                    <p className="text-xs font-medium text-ink">
                      {emoji} {title}
                    </p>
                    <p className="text-[11px] text-ink-muted">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
            {stats.withQuestions === 0 && (
              <div className="mt-4 bg-accent-50 border border-accent-200 rounded-xl p-4 text-left w-full">
                <p className="text-xs font-medium text-accent-800 mb-1">
                  ⏳ Noch keine Fragen generiert
                </p>
                <p className="text-[11px] text-accent-700">
                  Sobald wieder KI-Guthaben verfügbar ist, generiert die Pipeline automatisch smarte
                  Fragen für alle {stats.total} analysierten Items.
                </p>
              </div>
            )}
          </div>
        ) : (
          <ItemDetail item={activeItem} onBack={() => setActiveItem(null)} />
        )}
      </div>
    </div>
  )
}
