import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Shield,
  LayoutDashboard,
  BarChart3,
  GitBranchPlus,
  Users,
  UserCog,
  Cpu,
  FileCode,
  LogOut,
} from 'lucide-react'
import { adminLogout } from '../../api'

const adminNavItems = [
  { to: '/admin/uebersicht', label: 'Übersicht', icon: LayoutDashboard },
  { to: '/admin/llm-analytics', label: 'LLM Analytics', icon: BarChart3 },
  { to: '/admin/drift-quality', label: 'Drift / Quality-Review', icon: GitBranchPlus },
  { to: '/admin/users', label: 'Nutzer & API-Keys', icon: Users },
  { to: '/admin/accounts', label: 'Login-Accounts', icon: UserCog },
  { to: '/admin/modelle', label: 'Modelle', icon: Cpu },
  { to: '/admin/prompt-studio', label: 'Prompt-Studio', icon: FileCode },
]

export default function AdminLayout({ onLogout }) {
  const navigate = useNavigate()

  async function handleLogout() {
    try {
      await adminLogout()
    } catch {
      // Fehler ignorieren — Session-Cookie wird serverseitig invalidiert
    }
    onLogout()
    navigate('/admin', { replace: true })
  }

  return (
    // bewusst behalten: bg-slate-950/900/800 + border-slate-700 = dunkle
    // Admin-Sidebar-Oberfläche — kein Dark-Surface-Token vorhanden, Tier-2-Palette
    // ist bewusst Light-only (Dark-Mode am 2026-08-14 entfernt, siehe
    // tailwind.config.js). amber-* ist primitive-identisch zu accent-* (Brand-Akzent)
    // und deshalb migriert; text-red-400 (Logout-Hover) -> status-fehler-text
    // (Destruktiv-Bedeutung passt zur Fehler-Semantik).
    <div className="flex h-screen bg-slate-950">
      {/* Admin Sidebar */}
      <aside className="w-64 bg-slate-900 border-r border-slate-700/60 flex flex-col shrink-0">
        {/* Brand Header */}
        <div className="px-4 py-4 border-b border-slate-700/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent-500 flex items-center justify-center shrink-0">
              <Shield className="w-4 h-4 text-white" strokeWidth={2} />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white">Admin-Tool</h1>
              <p className="text-[11px] text-slate-400 leading-tight">Content Autopilot</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto space-y-0.5">
          {adminNavItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-accent-500/15 text-accent-400 border-l-2 border-accent-400'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                  }`
                }
              >
                <Icon className="w-[18px] h-[18px] flex-shrink-0" strokeWidth={1.75} />
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 py-3 border-t border-slate-700/60">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-status-fehler-text transition-colors"
          >
            <LogOut className="w-[18px] h-[18px]" strokeWidth={1.75} />
            Abmelden
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-6xl mx-auto w-full">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
