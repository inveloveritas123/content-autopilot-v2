import { useEffect } from 'react'
import { clsx } from 'clsx'
import { CloseButton } from './CloseButton'

const maxWidths = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
}

export function Dialog({
  open,
  onClose,
  title,
  titleIcon: TitleIcon,
  children,
  className,
  contentClassName,
  maxWidth = 'lg',
  closeOnBackdrop = true,
  closeOnEscape = true,
}) {
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

  useEffect(() => {
    if (!open || !closeOnEscape) return
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, closeOnEscape, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* bg-black/50: reiner Overlay-Scrim ohne semantische Bedeutung, kein Token nötig */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={closeOnBackdrop ? onClose : undefined}
      />
      <div
        className={clsx(
          // rounded-card: Dialog ist ein Card-artiger Container (großflächige
          // Modal-Fläche), kein interaktives Steuerelement.
          'relative bg-surface-card rounded-card shadow-xl border border-surface-border w-full mx-4 max-h-[90vh] overflow-y-auto',
          maxWidths[maxWidth] || maxWidths.lg,
          className
        )}
      >
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
              {TitleIcon && <TitleIcon className="w-5 h-5 text-primary-600 shrink-0" />}
              {title}
            </h2>
            <CloseButton onClick={onClose} />
          </div>
        )}
        <div className={contentClassName ?? 'px-6 py-4'}>{children}</div>
      </div>
    </div>
  )
}
