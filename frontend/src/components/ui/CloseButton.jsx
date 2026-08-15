import { X } from 'lucide-react'
import { clsx } from 'clsx'

export function CloseButton({ onClick, className, size = 'md', label = 'Schließen' }) {
  const sizes = {
    sm: 'w-3.5 h-3.5',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  }
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={clsx(
        'shrink-0 p-1 rounded text-ink-muted hover:text-ink-light hover:bg-surface-bg transition-colors',
        className
      )}
    >
      <X className={sizes[size]} />
    </button>
  )
}
