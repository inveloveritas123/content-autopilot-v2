import { clsx } from 'clsx'

const colors = {
  gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  blue: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  green: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  yellow: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  red: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
  orange: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
}

const statusColors = {
  new: 'blue',
  transcribing: 'yellow',
  transcribed: 'blue',
  analyzing: 'yellow',
  analyzed: 'purple',
  generating: 'yellow',
  content_ready: 'green',
  approved: 'green',
  published: 'gray',
  needs_voicescriptor: 'red',
  transcription_failed: 'red',
  draft: 'gray',
  reviewed: 'blue',
  scheduled: 'purple',
}

export function Badge({ color, status, className, children }) {
  const resolvedColor = color || statusColors[status] || 'orange'
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        colors[resolvedColor],
        className
      )}
    >
      {children || status}
    </span>
  )
}
