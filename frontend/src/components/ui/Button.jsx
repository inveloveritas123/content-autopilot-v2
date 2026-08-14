import { clsx } from 'clsx'

// danger/success nutzen die status-fehler/status-fertig-Tokens (SSOT-Status-
// Vokabular) statt eigener Rot/Grün-Werte — ein Button ist hier semantisch
// eine "fehler"- bzw. "fertig"-Aktion, kein sechster Farbwert.
const variants = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700 border-transparent',
  secondary:
    'bg-surface-card text-ink hover:bg-surface-bg border-surface-border',
  danger: 'bg-status-fehler-text text-white hover:opacity-90 border-transparent',
  ghost: 'bg-transparent text-ink-light hover:bg-surface-bg border-transparent',
  success: 'bg-status-fertig-text text-white hover:opacity-90 border-transparent',
}

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
}

export function Button({ variant = 'primary', size = 'md', className, children, ...props }) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-control border font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}
