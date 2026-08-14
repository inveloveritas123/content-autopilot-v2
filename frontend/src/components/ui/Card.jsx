import { clsx } from 'clsx'

export function Card({ className, children, ...props }) {
  return (
    <div
      className={clsx(
        'bg-surface-card rounded-card border border-surface-border shadow-sm',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ className, children }) {
  return (
    <div className={clsx('px-6 py-4 border-b border-surface-border', className)}>
      {children}
    </div>
  )
}

export function CardTitle({ className, children }) {
  return (
    <h3 className={clsx('text-lg font-semibold text-ink', className)}>
      {children}
    </h3>
  )
}

export function CardContent({ className, children }) {
  return <div className={clsx('px-6 py-4', className)}>{children}</div>
}
