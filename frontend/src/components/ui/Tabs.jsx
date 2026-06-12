import { clsx } from 'clsx'

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="border-b border-gray-200 dark:border-gray-700">
      <nav className="flex gap-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={clsx(
              'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
              active === tab.id
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            )}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
