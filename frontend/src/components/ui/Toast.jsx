/**
 * Toast-System — useToast() Hook + ToastProvider
 *
 * Variants: success | error | info | warning
 * Position: bottom-right (Desktop), bottom-center (< sm = Mobile)
 * Max 3 Toasts gestapelt. Auto-dismiss: 4s (success/info), 8s (error/warning).
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react'

// ─── Kontext ─────────────────────────────────────────────────────────────────

const ToastContext = createContext(null)

// ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

// Toast hatte 4 Bedeutungen (success/error/warning/info) — passt direkt in
// 4 der 5 Status-Tokens (SSOT-Zuordnung: info≈neu, success≈fertig,
// warning≈aktiv, error≈fehler; "archiviert" bleibt ungenutzt, da Toast keinen
// neutralen/inaktiven Zustand kennt).
const VARIANT_STYLES = {
  success: {
    container: 'bg-status-fertig-bg border-status-fertig-border text-status-fertig-text',
    icon: CheckCircle2,
    iconClass: 'text-status-fertig-text',
  },
  error: {
    container: 'bg-status-fehler-bg border-status-fehler-border text-status-fehler-text',
    icon: AlertCircle,
    iconClass: 'text-status-fehler-text',
  },
  warning: {
    container: 'bg-status-aktiv-bg border-status-aktiv-border text-status-aktiv-text',
    icon: AlertTriangle,
    iconClass: 'text-status-aktiv-text',
  },
  info: {
    container: 'bg-status-neu-bg border-status-neu-border text-status-neu-text',
    icon: Info,
    iconClass: 'text-status-neu-text',
  },
}

const DISMISS_DELAY = {
  success: 4000,
  info: 4000,
  warning: 8000,
  error: 8000,
}

let _nextId = 0
function nextId() {
  return ++_nextId
}

// ─── Toast-Item-Komponente ────────────────────────────────────────────────────

function ToastItem({ id, message, variant = 'info', onDismiss }) {
  const cfg = VARIANT_STYLES[variant] || VARIANT_STYLES.info
  const Icon = cfg.icon

  return (
    <div
      role="alert"
      aria-live="assertive"
      // rounded-card: Toast ist eine eigenständige Card-Fläche (kein
      // interaktives Steuerelement wie Button/Input), analog zu Dialog.
      className={`flex items-start gap-3 w-full max-w-sm px-4 py-3 rounded-card border shadow-lg text-sm transition-all animate-toast-in ${cfg.container}`}
    >
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cfg.iconClass}`} aria-hidden="true" />
      <span className="flex-1 leading-snug">{message}</span>
      <button
        onClick={() => onDismiss(id)}
        className="shrink-0 p-0.5 rounded hover:bg-black/10 transition-colors"
        aria-label="Schließen"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

// ─── ToastProvider ────────────────────────────────────────────────────────────

const MAX_TOASTS = 3

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef({})

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id])
    delete timers.current[id]
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (message, variant = 'info') => {
      const id = nextId()
      const delay = DISMISS_DELAY[variant] ?? 4000

      setToasts((prev) => {
        const next = [...prev, { id, message, variant }]
        // Max 3: älteste entfernen
        return next.slice(-MAX_TOASTS)
      })

      timers.current[id] = setTimeout(() => dismiss(id), delay)
      return id
    },
    [dismiss]
  )

  // Timer-Cleanup bei Unmount
  useEffect(() => {
    return () => Object.values(timers.current).forEach(clearTimeout)
  }, [])

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      {/* Positionierung: bottom-right auf Desktop, bottom-center auf Mobile */}
      <div
        aria-label="Benachrichtigungen"
        className="fixed z-50 flex flex-col-reverse gap-2 p-4
          bottom-0 left-1/2 -translate-x-1/2
          sm:left-auto sm:translate-x-0 sm:right-4 sm:bottom-4
          w-full sm:w-auto pointer-events-none"
      >
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto w-full sm:w-80">
            <ToastItem id={t.id} message={t.message} variant={t.variant} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// ─── useToast Hook ────────────────────────────────────────────────────────────

/**
 * useToast() — gibt Objekt mit Shorthand-Methoden zurück:
 *   toast.success(msg)
 *   toast.error(msg)
 *   toast.warning(msg)
 *   toast.info(msg)
 *   toast.show(msg, variant)
 */
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast muss innerhalb von <ToastProvider> verwendet werden.')
  }
  const { toast, dismiss } = ctx
  return {
    show: toast,
    success: (msg) => toast(msg, 'success'),
    error: (msg) => toast(msg, 'error'),
    warning: (msg) => toast(msg, 'warning'),
    info: (msg) => toast(msg, 'info'),
    dismiss,
  }
}
