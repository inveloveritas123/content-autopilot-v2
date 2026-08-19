import { clsx } from 'clsx'

export function Input({ className, label, ...props }) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-ink-light mb-1">{label}</label>}
      <input
        className={clsx(
          'w-full px-3 py-2 rounded-control border border-surface-border bg-surface-card text-ink placeholder-ink-muted focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm',
          className
        )}
        {...props}
      />
    </div>
  )
}

export function Select({ className, label, children, ...props }) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-ink-light mb-1">{label}</label>}
      <select
        className={clsx(
          'w-full px-3 py-2 rounded-control border border-surface-border bg-surface-card text-ink focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
          className
        )}
        {...props}
      >
        {children}
      </select>
    </div>
  )
}

export function Textarea({ className, label, ...props }) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-ink-light mb-1">{label}</label>}
      <textarea
        className={clsx(
          'w-full px-3 py-2 rounded-control border border-surface-border bg-surface-card text-ink placeholder-ink-muted focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
          className
        )}
        {...props}
      />
    </div>
  )
}
