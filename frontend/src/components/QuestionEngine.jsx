import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  Send,
  ChevronRight,
  Loader2,
  BookmarkCheck,
  SkipForward,
  Sparkles,
  CheckCircle,
} from 'lucide-react'
import { clsx } from 'clsx'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'

// Sicherheit: React escaped automatisch — kein dangerouslySetInnerHTML

// ---------------------------------------------------------------------------
// Hilfs-Hook: berechnet Inline-Hints synchron bei Input-Änderung
// (kein Debounce nötig, da getHints rein pattern-basiert / synchron)
// ---------------------------------------------------------------------------
function useInlineHints(getHints, input) {
  return useMemo(() => {
    if (!getHints || !input.trim()) return []
    try {
      return getHints(input) || []
    } catch {
      return []
    }
  }, [getHints, input])
}

// ---------------------------------------------------------------------------
// Phase-Synthese-Modal
// ---------------------------------------------------------------------------
function PhaseSynthesisModal({ open, onClose, proposals, onAccept, onReject, phaseName }) {
  return (
    <Dialog open={open} onClose={onClose} title={`KI-Vorschläge für ${phaseName || 'diese Phase'}`}>
      <div className="space-y-3">
        {proposals && proposals.length > 0 ? (
          proposals.map((proposal, idx) => (
            <div key={idx} className="border border-surface-border rounded-xl p-4 bg-primary-50">
              <p className="text-sm text-ink mb-3 leading-relaxed">{proposal.suggestion}</p>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => onAccept(idx)}
                  className="flex items-center gap-1"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  Übernehmen
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onReject(idx)}
                  className="text-ink-light"
                >
                  ✗ Ablehnen
                </Button>
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-ink-muted">Keine Vorschläge vorhanden.</p>
        )}
        <div className="pt-2 border-t border-surface-border">
          <Button variant="primary" size="md" onClick={onClose} className="w-full">
            Weiter zur nächsten Phase
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Chat-Bubble (für appearance="chat")
// ---------------------------------------------------------------------------
function ChatBubble({ text, role }) {
  const isUser = role === 'user'
  return (
    <div className={clsx('flex mb-3', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
          isUser
            ? 'bg-primary-600 text-white rounded-br-sm'
            : 'bg-surface-bg text-ink rounded-bl-sm'
        )}
      >
        {text}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline-Hint-Chips
// ---------------------------------------------------------------------------
function HintChips({ hints, onSelect }) {
  if (!hints || hints.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {hints.map((hint) => (
        <button
          key={hint.id}
          type="button"
          onClick={() => onSelect(hint.text)}
          className={clsx(
            'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium',
            'border border-primary-200 bg-primary-50 text-primary-700',
            'hover:bg-primary-100 hover:border-primary-300 transition-colors'
          )}
        >
          <Sparkles className="w-3 h-3" />
          {hint.text}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fortschritts-Balken
// ---------------------------------------------------------------------------
function ProgressBar({ current, total }) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0
  return (
    <div className="w-full h-1 bg-surface-bg rounded-full overflow-hidden">
      <div
        className="h-full bg-primary-600 rounded-full transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Abschluss-Anzeige
// ---------------------------------------------------------------------------
function SessionCompleteView({ source }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-14 h-14 rounded-2xl bg-status-fertig-bg flex items-center justify-center mb-4">
        <CheckCircle className="w-7 h-7 text-status-fertig-text" />
      </div>
      <h3 className="text-base font-semibold text-ink mb-1">Alle Fragen beantwortet!</h3>
      <p className="text-sm text-ink-muted">
        {source === 'wizard'
          ? 'Deine Antworten wurden gespeichert. Du kannst die Session schließen.'
          : 'Danke für deine Antworten.'}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Haupt-Komponente: QuestionEngine
// ---------------------------------------------------------------------------
export function QuestionEngine({
  source,
  questions,
  onAnswer,
  onSkip,
  inlineHints,
  phaseSynthesis,
  onSaveAndContinue,
  appearance = 'form',
}) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([]) // Array<{ questionId, questionText, answer }>
  const [showSynthesisModal, setShowSynthesisModal] = useState(false)
  const [sessionComplete, setSessionComplete] = useState(false)

  const textareaRef = useRef(null)

  const currentQuestion = questions[currentIndex] || null
  const hints = useInlineHints(inlineHints, input)

  // Fokus auf Textarea setzen wenn neue Frage aktiv wird
  useEffect(() => {
    if (!sessionComplete && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [currentIndex, sessionComplete])

  const handleHintSelect = useCallback((hintText) => {
    setInput(hintText)
    if (textareaRef.current) textareaRef.current.focus()
  }, [])

  async function handleSubmit() {
    if (!input.trim() || loading || !currentQuestion) return
    if (!onAnswer) return // Sicherheits-Guard: onAnswer ist Pflicht-Prop
    setLoading(true)
    setError(null)
    try {
      const result = (await onAnswer(currentQuestion.id, input.trim())) ?? {}
      setHistory((prev) => [
        ...prev,
        {
          questionId: currentQuestion.id,
          questionText: currentQuestion.text,
          answer: input.trim(),
        },
      ])
      setInput('')

      if (result.type === 'session_complete') {
        setSessionComplete(true)
      } else if (result.type === 'phase_complete') {
        if (phaseSynthesis) {
          setShowSynthesisModal(true)
        } else {
          setCurrentIndex((idx) => idx + 1)
        }
      } else {
        // next_question
        setCurrentIndex((idx) => idx + 1)
      }
    } catch (e) {
      setError(e.message || 'Fehler beim Senden der Antwort')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (appearance === 'form' && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleSkip() {
    if (!onSkip || !currentQuestion) return
    onSkip(currentQuestion.id)
    setInput('')
    setCurrentIndex((idx) => idx + 1)
  }

  function handleSynthesisClose() {
    setShowSynthesisModal(false)
    setCurrentIndex((idx) => idx + 1)
  }

  async function handleSaveAndContinue() {
    if (!onSaveAndContinue || saving) return
    setSaving(true)
    try {
      await onSaveAndContinue()
    } catch (e) {
      setError(e.message || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  // Phasen-Name der aktuellen Frage (für Badge)
  const currentPhaseName = currentQuestion?.phase_name || null

  // Synthese-Modal Phasen-Name ermitteln (letzte beantwortete Frage)
  const lastAnswered = history[history.length - 1]
  const synthesisPhaseLabel = lastAnswered
    ? questions.find((q) => q.id === lastAnswered.questionId)?.phase_name ||
      `Phase ${lastAnswered.questionId}`
    : 'diese Phase'

  if (sessionComplete) {
    return (
      <div className="relative">
        <SessionCompleteView source={source} />
        {onSaveAndContinue && (
          <div className="flex justify-end mt-4">
            <Button variant="secondary" size="sm" onClick={handleSaveAndContinue} disabled={saving}>
              {saving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <BookmarkCheck className="w-3.5 h-3.5" />
              )}
              {saving ? 'Speichern…' : 'Speichern & Weiter'}
            </Button>
          </div>
        )}
      </div>
    )
  }

  if (!currentQuestion) {
    return <div className="py-8 text-center text-sm text-ink-muted">Keine Fragen vorhanden.</div>
  }

  // -------------------------------------------------------------------------
  // Form-Appearance
  // -------------------------------------------------------------------------
  if (appearance === 'form') {
    return (
      <div className="relative">
        <PhaseSynthesisModal
          open={showSynthesisModal}
          onClose={handleSynthesisClose}
          proposals={phaseSynthesis?.proposals || []}
          onAccept={phaseSynthesis?.onAccept}
          onReject={phaseSynthesis?.onReject}
          phaseName={synthesisPhaseLabel}
        />

        <div className="bg-white rounded-xl border border-surface-border overflow-hidden">
          {/* Fortschritts-Balken oben */}
          <ProgressBar current={history.length} total={questions.length} />

          <div className="p-5 space-y-4">
            {/* Header: Phase-Badge + Fortschritts-Label */}
            <div className="flex items-center justify-between">
              {currentPhaseName && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary-50 text-primary-700 border border-primary-200">
                  {currentPhaseName}
                </span>
              )}
              <span className="text-xs text-ink-muted ml-auto">
                Frage {currentIndex + 1} von {questions.length}
              </span>
            </div>

            {/* Fragen-Text als Label */}
            <div>
              <label
                htmlFor="qe-textarea"
                className="block text-sm font-medium text-ink mb-3 leading-relaxed"
              >
                {currentQuestion.text}
              </label>
              <textarea
                id="qe-textarea"
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={4}
                placeholder="Deine Antwort… (Enter zum Absenden, Shift+Enter für Zeilenumbruch)"
                className={clsx(
                  'w-full text-sm border rounded-lg p-3 resize-y transition-colors',
                  'focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                  'bg-surface-bg placeholder-gray-400 text-ink',
                  error ? 'border-status-fehler-border' : 'border-surface-border'
                )}
              />
              {/* Nachhaken — statische Hilfe-Fragen aus MD */}
              {currentQuestion.nachhaken && currentQuestion.nachhaken.length > 0 && (
                <details className="mt-2 group">
                  <summary className="text-xs text-ink-muted cursor-pointer hover:text-ink select-none list-none flex items-center gap-1">
                    <span className="text-base leading-none">💡</span>
                    <span className="underline decoration-dotted">
                      Hilfe wenn du nicht weiterweißt
                    </span>
                  </summary>
                  <ul className="mt-2 space-y-1 pl-1 border-l-2 border-primary-100 ml-1">
                    {currentQuestion.nachhaken.map((hint, i) => (
                      <li key={i} className="text-xs text-ink-muted pl-2 leading-relaxed">
                        → {hint}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {/* Inline-Hints */}
              <HintChips hints={hints} onSelect={handleHintSelect} />
            </div>

            {error && (
              <p className="text-xs text-status-fehler-text bg-status-fehler-bg rounded-lg p-3">
                {error}
              </p>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {onSkip && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSkip}
                    type="button"
                    className="text-ink-muted text-xs"
                  >
                    <SkipForward className="w-3.5 h-3.5" />
                    Überspringen
                  </Button>
                )}
              </div>
              <div className="flex items-center gap-2">
                {onSaveAndContinue && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSaveAndContinue}
                    disabled={saving}
                    type="button"
                    className="text-ink-muted text-xs"
                  >
                    {saving ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <BookmarkCheck className="w-3.5 h-3.5" />
                    )}
                    {saving ? 'Speichern…' : 'Speichern & Weiter'}
                  </Button>
                )}
                <Button
                  variant="primary"
                  size="md"
                  onClick={handleSubmit}
                  disabled={loading || !input.trim()}
                  type="button"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  {loading ? 'Wird gesendet…' : 'Weiter →'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Chat-Appearance — eigener Sub-Render, damit useEffect/useRef erlaubt
  // -------------------------------------------------------------------------
  return (
    <ChatAppearance
      currentQuestion={currentQuestion}
      currentIndex={currentIndex}
      questionsTotal={questions.length}
      history={history}
      input={input}
      setInput={setInput}
      loading={loading}
      saving={saving}
      error={error}
      hints={hints}
      onHintSelect={handleHintSelect}
      onSubmit={handleSubmit}
      onSkip={onSkip ? handleSkip : null}
      onSaveAndContinue={onSaveAndContinue ? handleSaveAndContinue : null}
      showSynthesisModal={showSynthesisModal}
      onSynthesisClose={handleSynthesisClose}
      phaseSynthesis={phaseSynthesis}
      synthesisPhaseLabel={synthesisPhaseLabel}
    />
  )
}

// ---------------------------------------------------------------------------
// Chat-Appearance als separater Funktions-Render (damit useEffect erlaubt)
// ---------------------------------------------------------------------------
function ChatAppearance({
  currentQuestion,
  currentIndex,
  questionsTotal,
  history,
  input,
  setInput,
  loading,
  saving,
  error,
  hints,
  onHintSelect,
  onSubmit,
  onSkip,
  onSaveAndContinue,
  showSynthesisModal,
  onSynthesisClose,
  phaseSynthesis,
  synthesisPhaseLabel,
}) {
  const textareaRef = useRef(null)
  const chatEndRef = useRef(null)

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [history.length, currentIndex])

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.focus()
  }, [currentIndex])

  function handleKeyDown(e) {
    // Chat-Modus: kein Enter-Submit (Chat-Konvention: Send-Button)
    // Shift+Enter = Zeilenumbruch (normal)
  }

  return (
    <div className="flex flex-col h-full min-h-[400px] max-h-[600px] bg-white rounded-xl border border-surface-border overflow-hidden">
      <PhaseSynthesisModal
        open={showSynthesisModal}
        onClose={onSynthesisClose}
        proposals={phaseSynthesis?.proposals || []}
        onAccept={phaseSynthesis?.onAccept}
        onReject={phaseSynthesis?.onReject}
        phaseName={synthesisPhaseLabel}
      />

      {/* Chat-Header */}
      <div className="px-4 py-3 border-b border-surface-border flex items-center justify-between">
        <span className="text-xs font-medium text-ink-muted">
          Frage {currentIndex + 1} von {questionsTotal}
        </span>
        <ProgressBar current={history.length} total={questionsTotal} />
      </div>

      {/* Chat-History */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {history.map((entry, idx) => (
          <div key={entry.questionId}>
            <ChatBubble text={entry.questionText} role="bot" />
            <ChatBubble text={entry.answer} role="user" />
          </div>
        ))}
        {/* Aktuelle Frage als Bot-Bubble */}
        <ChatBubble text={currentQuestion.text} role="bot" />
        <div ref={chatEndRef} />
      </div>

      {/* Input-Bereich */}
      <div className="border-t border-surface-border px-4 py-3 bg-surface-bg">
        {/* Inline-Hints über dem Input */}
        <HintChips
          hints={hints}
          onSelect={(val) => {
            onHintSelect(val)
            if (textareaRef.current) textareaRef.current.focus()
          }}
        />

        <div className="flex gap-2 mt-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="Deine Antwort…"
            className={clsx(
              'flex-1 text-sm border rounded-xl p-3 resize-none transition-colors',
              'focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
              'bg-white placeholder-gray-400 text-ink',
              error ? 'border-status-fehler-border' : 'border-surface-border'
            )}
          />
          <button
            onClick={onSubmit}
            disabled={loading || !input.trim()}
            type="button"
            className={clsx(
              'shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors mt-auto',
              'bg-primary-600 text-white hover:bg-primary-700',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            aria-label="Antwort absenden"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>

        {error && <p className="text-xs text-status-fehler-text mt-2">{error}</p>}

        {/* Skip + Save-Buttons */}
        <div className="flex items-center justify-between mt-2">
          <div>
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                className="text-xs text-ink-muted hover:text-ink flex items-center gap-1 transition-colors"
              >
                <SkipForward className="w-3 h-3" />
                Überspringen
              </button>
            )}
          </div>
          <div>
            {onSaveAndContinue && (
              <button
                type="button"
                onClick={onSaveAndContinue}
                disabled={saving}
                className="text-xs text-ink-muted hover:text-primary-600 flex items-center gap-1 transition-colors disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <BookmarkCheck className="w-3 h-3" />
                )}
                {saving ? 'Speichern…' : 'Speichern & Weiter'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
