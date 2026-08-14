import { useEffect } from 'react'
import { clsx } from 'clsx'

export function Dialog({ open, onClose, title, children, className }) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* bg-black/50: reiner Overlay-Scrim ohne semantische Bedeutung, kein Token nötig */}
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div
        className={clsx(
          // rounded-card: Dialog ist ein Card-artiger Container (großflächige
          // Modal-Fläche), kein interaktives Steuerelement.
          'relative bg-surface-card rounded-card shadow-xl border border-surface-border w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto',
          className
        )}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border">
          <h2 className="text-lg font-semibold text-ink">{title}</h2>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink-light text-xl"
          >
            &times;
          </button>
        </div>
        <div className="px-6 py-4">{children}</div>
      </div>
    </div>
  )
}
