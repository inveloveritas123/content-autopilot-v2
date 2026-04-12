import { clsx } from 'clsx'

export function Card({ className, children, ...props }) {
  return (
    <div className={clsx('bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm', className)} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ className, children }) {
  return <div className={clsx('px-6 py-4 border-b border-gray-100 dark:border-gray-800', className)}>{children}</div>
}

export function CardTitle({ className, children }) {
  return <h3 className={clsx('text-lg font-semibold text-gray-900 dark:text-gray-100', className)}>{children}</h3>
}

export function CardContent({ className, children }) {
  return <div className={clsx('px-6 py-4', className)}>{children}</div>
}
