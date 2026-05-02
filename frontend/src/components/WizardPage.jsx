import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { X, CheckCircle2, Circle, Loader2, BookmarkCheck, Mic2, ArrowRight } from 'lucide-react'
import { clsx } from 'clsx'
import { QuestionEngine } from './QuestionEngine'
import { Button } from './ui/Button'
import {
  startWizardSession,
  getWizardSession,
  answerWizardQuestion,
  synthesizeWizardPhase,
  finalizeWizardSession,
  getBrandVoicePipelineStatus,
} from '../api'

// ---------------------------------------------------------------------------
// Phasen-Definition (statisch, kein DB-Fetch nötig)
// ---------------------------------------------------------------------------
const WIZARD_PHASES = [
  {
    id: 1,
    name: 'Ankommen & Geschichte',
    questions: [
      'Wer bist du und was machst du?',
      'Was war dein Wendepunkt?',
      'Was hat dich bewegt, den Weg zu gehen den du gehst?',
    ],
  },
  {
    id: 2,
    name: 'Alltag & Antrieb',
    questions: [
      'Beschreib einen typischen Arbeitstag.',
      'Was treibt dich täglich an?',
      'Welche Momente in der Arbeit geben dir Energie?',
      'Ich arbeite, weil…',
    ],
  },
  {
    id: 3,
    name: 'Zielkunde',
    questions: [
      'Wer ist dein Lieblingskunde?',
      'Was ist das größte Problem deines Kunden?',
      'Was verändert sich für deinen Kunden nach der Zusammenarbeit?',
      'Wer ist NICHT dein Kunde?',
    ],
  },
  {
    id: 4,
    name: 'Angebot & Markt',
    questions: [
      'Was bietest du an?',
      'Was unterscheidet dich vom Wettbewerb?',
      'Was ist dein Preispunkt und warum?',
      'Ich helfe meinen Kunden dabei…',
    ],
  },
  {
    id: 5,
    name: 'Sprache & Stil',
    questions: [
      'Welche Wörter nutzt du nie?',
      'Wie klingst du in einem Gespräch mit einem Kunden?',
      'Drei Adjektive die deinen Stil beschreiben:',
      'Was nervt dich an anderen LinkedIn-Posts?',
    ],
  },
  {
    id: 6,
    name: 'Vertrauenssignale',
    questions: [
      'Deine größte Erfolgsgeschichte in einem Satz:',
      'Was sagen Kunden nach der Zusammenarbeit?',
      'Was kannst du belegen?',
    ],
  },
]

// ---------------------------------------------------------------------------
// Inline-Hints (pattern-basiert, kein LLM)
// ---------------------------------------------------------------------------
function getInlineHints(currentInput) {
  const hints = []
  const lower = currentInput.toLowerCase()
  if (lower.includes('werkstatt') || lower.includes('werkzeug'))
    hints.push({ id: 'h1', text: 'Meinst du Werkleiter oder Produktionsleiter als Zielgruppe?' })
  if (lower.includes('coach') || lower.includes('coaching'))
    hints.push({ id: 'h2', text: 'Führungskräfte-Coaching oder Persönlichkeitsentwicklung?' })
  if (lower.includes('berater') || lower.includes('beratung'))
    hints.push({ id: 'h3', text: 'Strategie-, Prozess- oder IT-Beratung?' })
  if (lower.includes('agentur'))
    hints.push({ id: 'h4', text: 'Digital-, Marketing- oder Kreativagentur?' })
  if (lower.length > 50 && !lower.includes('weil') && !lower.includes('wegen'))
    hints.push({ id: 'h5', text: 'Tipp: Nenne das "Warum" — es macht Antworten überzeugender.' })
  return hints
}

// ---------------------------------------------------------------------------
// Stepper (Desktop-Sidebar)
// ---------------------------------------------------------------------------
function PhaseIcon({ status }) {
  if (status === 'done') return <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
  if (status === 'active') return <Circle className="w-5 h-5 text-primary-600 fill-primary-100 shrink-0" />
  return <Circle className="w-5 h-5 text-gray-300 shrink-0" />
}

function PhaseStepper({ phases, currentPhase, progress, onPhaseClick }) {
  return (
    <div className="w-56 shrink-0 pr-6 border-r border-gray-200">
      <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-4">Phasen</p>
      <div className="space-y-1">
        {phases.map((phase) => {
          const status = progress[phase.id] || (phase.id === currentPhase ? 'active' : 'pending')
          const isClickable = status === 'done'
          return (
            <button
              key={phase.id}
              type="button"
              onClick={() => isClickable && onPhaseClick(phase.id)}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors text-sm',
                status === 'active' && 'bg-primary-50 text-primary-800 font-medium',
                status === 'done' && 'text-emerald-700 hover:bg-emerald-50 cursor-pointer',
                status === 'pending' && 'text-ink-muted cursor-default'
              )}
            >
              <PhaseIcon status={status} />
              <span className="leading-tight">{phase.name}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Horizontal-Stepper (Tablet / kleine Screens)
// ---------------------------------------------------------------------------
function HorizontalStepper({ phases, currentPhase, progress }) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1 mb-6">
      {phases.map((phase, idx) => {
        const status = progress[phase.id] || (phase.id === currentPhase ? 'active' : 'pending')
        return (
          <div key={phase.id} className="flex items-center gap-1 shrink-0">
            <div
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium',
                status === 'active' && 'bg-primary-100 text-primary-800',
                status === 'done' && 'bg-emerald-100 text-emerald-700',
                status === 'pending' && 'bg-gray-100 text-gray-400'
              )}
            >
              <PhaseIcon status={status} />
              <span className="hidden sm:inline">{phase.name}</span>
              <span className="sm:hidden">{idx + 1}</span>
            </div>
            {idx < phases.length - 1 && (
              <div className="w-4 h-px bg-gray-200 shrink-0" />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pipeline-Status-Banner (nach Finalisierung)
// ---------------------------------------------------------------------------
function PipelineStatusBanner({ pipelineRunId, onDone }) {
  const [status, setStatus] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!pipelineRunId) return
    async function poll() {
      try {
        const data = await getBrandVoicePipelineStatus(pipelineRunId)
        setStatus(data)
        if (data?.status === 'done' || data?.status === 'error') {
          clearInterval(intervalRef.current)
          if (data?.status === 'done') onDone?.()
        }
      } catch {
        // keep polling
      }
    }
    poll()
    intervalRef.current = setInterval(poll, 3000)
    return () => clearInterval(intervalRef.current)
  }, [pipelineRunId, onDone])

  if (!pipelineRunId || !status) return null

  const isDone = status.status === 'done'
  const isError = status.status === 'error'

  return (
    <div
      className={clsx(
        'mb-4 p-4 rounded-xl border flex items-center gap-3 text-sm',
        isDone && 'bg-emerald-50 border-emerald-200 text-emerald-800',
        isError && 'bg-red-50 border-red-200 text-red-700',
        !isDone && !isError && 'bg-blue-50 border-blue-200 text-blue-800'
      )}
    >
      {isDone ? (
        <CheckCircle2 className="w-5 h-5 shrink-0" />
      ) : isError ? (
        <X className="w-5 h-5 shrink-0" />
      ) : (
        <Loader2 className="w-5 h-5 animate-spin shrink-0" />
      )}
      <span>
        {isDone
          ? 'Brand Voice Pipeline abgeschlossen.'
          : isError
          ? 'Pipeline-Fehler: ' + (status.error || 'Unbekannt')
          : `Pipeline läuft — Stage: ${status.stage || '...'} (${status.status || '...'})`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Toast-Banner (Save & Continue Later)
// ---------------------------------------------------------------------------
function SavedToast({ visible }) {
  if (!visible) return null
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-gray-900 text-white text-sm px-5 py-3 rounded-xl shadow-xl flex items-center gap-2">
      <BookmarkCheck className="w-4 h-4 text-emerald-400 shrink-0" />
      Fortschritt gespeichert — du kannst jetzt schließen.
    </div>
  )
}

// ---------------------------------------------------------------------------
// Abschluss-Ansicht
// ---------------------------------------------------------------------------
function DoneView({ onGoToBrandVoice }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-2xl bg-emerald-100 flex items-center justify-center mb-5">
        <CheckCircle2 className="w-8 h-8 text-emerald-600" />
      </div>
      <h2 className="text-lg font-bold text-ink mb-2">Dein Brand Voice ist eingerichtet!</h2>
      <p className="text-sm text-ink-muted mb-6 max-w-sm">
        Alle Phasen wurden abgeschlossen. Dein Brand Voice Profil wird jetzt aufgebaut.
      </p>
      <Button variant="primary" size="lg" onClick={onGoToBrandVoice} className="flex items-center gap-2">
        Zum Brand Voice Dashboard
        <ArrowRight className="w-4 h-4" />
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Haupt-Komponente: WizardPage
// ---------------------------------------------------------------------------
export default function WizardPage() {
  const { sessionId: urlSessionId } = useParams()
  const navigate = useNavigate()

  const [sessionId, setSessionId] = useState(null)
  const [currentPhase, setCurrentPhase] = useState(1)
  const [phaseProgress, setPhaseProgress] = useState({}) // { 1: 'done', 2: 'active', 3: 'pending' }
  const [loading, setLoading] = useState(true)
  const [initError, setInitError] = useState(null)
  const [phaseSynthesisData, setPhaseSynthesisData] = useState(null)
  const [synthesizing, setSynthesizing] = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [pipelineRunId, setPipelineRunId] = useState(null)
  const [done, setDone] = useState(false)
  const [savedToast, setSavedToast] = useState(false)
  const toastTimerRef = useRef(null)

  // Initialisierung: URL-Param prüfen oder neue Session starten
  useEffect(() => {
    async function init() {
      setLoading(true)
      setInitError(null)
      try {
        if (urlSessionId) {
          const session = await getWizardSession(urlSessionId)
          setSessionId(urlSessionId)
          // Zustand aus Session wiederherstellen
          if (session.current_phase) setCurrentPhase(session.current_phase)
          if (session.phase_progress) setPhaseProgress(session.phase_progress)
        } else {
          const result = await startWizardSession()
          const newId = result.session_id || result.id
          setSessionId(newId)
          navigate(`/brand-voice/wizard/${newId}`, { replace: true })
        }
      } catch (e) {
        setInitError(e.message || 'Fehler beim Starten des Wizards')
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [urlSessionId]) // urlSessionId-Änderung (z.B. Resume-Flow) triggert Neu-Initialisierung

  // Cleanup Toast-Timer
  useEffect(() => {
    return () => { if (toastTimerRef.current) clearTimeout(toastTimerRef.current) }
  }, [])

  // Fragen für die aktuelle Phase aufbauen
  const currentPhaseData = WIZARD_PHASES.find((p) => p.id === currentPhase)
  const questions = currentPhaseData
    ? currentPhaseData.questions.map((text, idx) => ({
        id: `p${currentPhase}_q${idx}`,
        text,
        phase: currentPhase,
        phase_name: currentPhaseData.name,
      }))
    : []

  // onAnswer-Handler für QuestionEngine
  const handleAnswer = useCallback(
    async (questionId, answer) => {
      const result = await answerWizardQuestion(sessionId, currentPhase, questionId, answer)
      const responseType = result?.type || result?.response_type || 'next_question'

      if (responseType === 'session_complete') {
        // Alle Phasen durch — finalisieren
        setFinalizing(true)
        try {
          const finalResult = await finalizeWizardSession(sessionId)
          const taskId = finalResult?.task_id || finalResult?.run_id
          if (taskId) setPipelineRunId(taskId)
        } catch {
          // Fehler beim Finalisieren ist nicht kritisch — trotzdem done setzen
        } finally {
          setFinalizing(false)
          setDone(true)
        }
        return { type: 'session_complete' }
      }

      if (responseType === 'phase_complete') {
        // Phase abgeschlossen — Synthese anfordern
        setSynthesizing(true)
        try {
          const synth = await synthesizeWizardPhase(sessionId, currentPhase)
          const proposals = synth?.proposals || synth?.suggestions || []
          setPhaseSynthesisData(proposals)
        } catch {
          setPhaseSynthesisData([])
        } finally {
          setSynthesizing(false)
        }
        return { type: 'phase_complete' }
      }

      // next_question — einfach weiter
      return { type: 'next_question' }
    },
    [sessionId, currentPhase]
  )

  // Nach Synthese-Modal: Phase als done markieren, nächste Phase starten
  const handleAcceptProposal = useCallback(
    async (idx) => {
      if (!phaseSynthesisData || !phaseSynthesisData[idx]) return
      const proposal = phaseSynthesisData[idx]
      const proposalText = proposal?.suggestion || proposal?.text || String(proposal)
      try {
        await answerWizardQuestion(
          sessionId,
          currentPhase,
          `p${currentPhase}_synthesis_${idx}`,
          proposalText
        )
      } catch {
        // nicht kritisch
      }
    },
    [sessionId, currentPhase, phaseSynthesisData]
  )

  const handleRejectProposal = useCallback((idx) => {
    // Ablehnen: kein API-Call nötig, nur UI-Feedback durch Modal-Schließen
    void idx
  }, [])

  // Wenn Synthese-Modal geschlossen wird (über QuestionEngine's onClose-Logik):
  // Phase wechseln
  const advancePhase = useCallback(() => {
    setPhaseProgress((prev) => ({ ...prev, [currentPhase]: 'done' }))
    setPhaseSynthesisData(null)
    const nextPhase = currentPhase + 1
    if (nextPhase > WIZARD_PHASES.length) {
      // Letzte Phase abgeschlossen — Pipeline starten (auch wenn Backend phase_complete statt session_complete schickt)
      setFinalizing(true)
      finalizeWizardSession(sessionId)
        .then((finalResult) => {
          const taskId = finalResult?.task_id || finalResult?.run_id
          if (taskId) setPipelineRunId(taskId)
        })
        .catch(() => {})
        .finally(() => { setFinalizing(false); setDone(true) })
    } else {
      setCurrentPhase(nextPhase)
    }
  }, [currentPhase, sessionId])

  // phaseSynthesis-Prop für QuestionEngine
  // QuestionEngine ruft onAccept/onReject und schließt das Modal intern.
  // Nach Modal-Close wechselt die Phase über advancePhase.
  const phaseSynthesisProp = phaseSynthesisData !== null
    ? {
        proposals: phaseSynthesisData,
        onAccept: (idx) => {
          handleAcceptProposal(idx)
          advancePhase()
        },
        onReject: (idx) => {
          handleRejectProposal(idx)
          advancePhase() // Ablehnen schließt Phase — kein Hängen im Modal
        },
      }
    : undefined

  // Save & Continue Later
  const handleSaveAndContinue = useCallback(() => {
    if (sessionId) {
      localStorage.setItem('wizardSessionId', sessionId)
    }
    setSavedToast(true)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setSavedToast(false), 4000)
  }, [sessionId])

  // Stepper-Navigation (zurück zu abgeschlossenen Phasen)
  const handlePhaseClick = useCallback((phaseId) => {
    setCurrentPhase(phaseId)
    setPhaseSynthesisData(null)
  }, [])

  // Schließen → zurück zu /brand-voice
  function handleClose() {
    navigate('/brand-voice')
  }

  // -------------------------------------------------------------------------
  // Mobile-Sperre
  // -------------------------------------------------------------------------
  const MobileBanner = (
    <div className="md:hidden flex flex-col items-center justify-center min-h-screen px-6 text-center bg-gray-50">
      <Mic2 className="w-10 h-10 text-primary-400 mb-4" />
      <h2 className="text-base font-bold text-ink mb-2">Bitte am Tablet oder Desktop fortfahren</h2>
      <p className="text-sm text-ink-muted">
        Der Brand Voice Wizard ist für größere Bildschirme optimiert. Öffne diese Seite auf einem Tablet oder PC.
      </p>
    </div>
  )

  // -------------------------------------------------------------------------
  // Loading / Error States
  // -------------------------------------------------------------------------
  if (loading) {
    return (
      <>
        <div className="hidden md:flex items-center justify-center min-h-screen">
          <div className="flex flex-col items-center gap-3 text-ink-muted">
            <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
            <p className="text-sm">Wizard wird vorbereitet…</p>
          </div>
        </div>
        {MobileBanner}
      </>
    )
  }

  if (initError) {
    return (
      <>
        <div className="hidden md:flex items-center justify-center min-h-screen">
          <div className="bg-white rounded-xl border border-red-200 p-8 max-w-md text-center">
            <p className="text-sm font-semibold text-red-700 mb-2">Fehler beim Starten</p>
            <p className="text-xs text-ink-muted mb-4">{initError}</p>
            <Button variant="primary" size="sm" onClick={() => navigate('/brand-voice')}>
              Zurück zu Brand Voice
            </Button>
          </div>
        </div>
        {MobileBanner}
      </>
    )
  }

  // -------------------------------------------------------------------------
  // Done-Ansicht
  // -------------------------------------------------------------------------
  if (done) {
    return (
      <>
        <div className="hidden md:block min-h-screen bg-gray-50">
          <div className="max-w-2xl mx-auto py-16 px-6">
            {pipelineRunId && (
              <PipelineStatusBanner
                pipelineRunId={pipelineRunId}
                onDone={() => {}}
              />
            )}
            <DoneView onGoToBrandVoice={() => navigate('/brand-voice')} />
          </div>
        </div>
        {MobileBanner}
      </>
    )
  }

  // -------------------------------------------------------------------------
  // Haupt-Layout
  // -------------------------------------------------------------------------
  return (
    <>
      {/* Mobile-Sperre */}
      {MobileBanner}

      {/* Desktop / Tablet Layout */}
      <div className="hidden md:flex flex-col min-h-screen bg-gray-50">
        {/* Top-Bar */}
        <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
          <div className="flex items-center gap-3">
            <Mic2 className="w-5 h-5 text-primary-600" />
            <h1 className="text-base font-bold text-ink">Brand Voice Onboarding</h1>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-100"
          >
            <X className="w-4 h-4" />
            Schließen
          </button>
        </div>

        {/* Horizontal Stepper (Tablet, < lg) */}
        <div className="lg:hidden px-6 pt-5">
          <HorizontalStepper
            phases={WIZARD_PHASES}
            currentPhase={currentPhase}
            progress={phaseProgress}
          />
        </div>

        {/* Inhalt */}
        <div className="flex flex-1 max-w-5xl w-full mx-auto px-6 py-8 gap-8">
          {/* Desktop-Stepper (Sidebar, >= lg) */}
          <div className="hidden lg:block pt-1">
            <PhaseStepper
              phases={WIZARD_PHASES}
              currentPhase={currentPhase}
              progress={phaseProgress}
              onPhaseClick={handlePhaseClick}
            />
          </div>

          {/* Fragen-Bereich */}
          <div className="flex-1 min-w-0">
            {finalizing ? (
              <div className="flex flex-col items-center justify-center py-16 gap-4 text-ink-muted">
                <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
                <p className="text-sm">Wizard wird abgeschlossen…</p>
              </div>
            ) : synthesizing ? (
              <div className="flex flex-col items-center justify-center py-16 gap-4 text-ink-muted">
                <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
                <p className="text-sm">KI analysiert deine Antworten…</p>
              </div>
            ) : (
              <QuestionEngine
                source="wizard"
                appearance="form"
                questions={questions}
                onAnswer={handleAnswer}
                inlineHints={getInlineHints}
                phaseSynthesis={phaseSynthesisProp}
                onSaveAndContinue={handleSaveAndContinue}
              />
            )}
          </div>
        </div>
      </div>

      {/* Toast */}
      <SavedToast visible={savedToast} />
    </>
  )
}
