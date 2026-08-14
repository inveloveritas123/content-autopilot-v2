import { clsx } from 'clsx'

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="border-b border-surface-border">
      <nav className="flex gap-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={clsx(
              // rounded* bewusst nicht gesetzt: Tab-Unterstrich ist kein Card-
              // oder Control-Container, sondern eine Linie ohne Ecken.
              'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
              active === tab.id
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-ink-light hover:text-ink'
            )}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
