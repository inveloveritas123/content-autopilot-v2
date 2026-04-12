import { NavLink } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  LayoutDashboard,
  GitBranchPlus,
  Radio,
  Lightbulb,
  FileText,
  BarChart3,
  Fingerprint,
  Settings,
} from 'lucide-react'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/pipeline', label: 'Pipeline', icon: GitBranchPlus },
  { to: '/sources', label: 'Quellen', icon: Radio },
  { to: '/ideas', label: 'Ideen', icon: Lightbulb },
  { to: '/posts', label: 'Posts', icon: FileText },
  { to: '/feedback', label: 'Feedback', icon: BarChart3 },
  { to: '/voice', label: 'Voice-Profil', icon: Fingerprint },
  { to: '/settings', label: 'Einstellungen', icon: Settings },
]

export default function Layout({ children }) {
  return (
    <div className="flex h-screen bg-surface-bg">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-surface-border flex flex-col shrink-0">
        {/* Brand Header */}
        <div className="px-6 py-5 border-b border-surface-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary-700 flex items-center justify-center">
              <span className="text-white font-bold text-sm">ZB</span>
            </div>
            <div>
              <h1 className="text-base font-bold text-ink">Content Autopilot</h1>
              <p className="text-[11px] text-ink-muted leading-tight">Mach's doch gleich richtig.</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {navItems.map(item => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700 border-l-2 border-primary-700'
                    : 'text-ink-light hover:bg-gray-50 hover:text-ink'
                )}
              >
                <Icon className="w-[18px] h-[18px] flex-shrink-0" strokeWidth={1.75} />
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-surface-border">
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
            System aktiv
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  )
}
