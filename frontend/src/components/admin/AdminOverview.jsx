import { Shield, Users, BarChart3, GitBranchPlus, Cpu, FileCode } from 'lucide-react'
import { Link } from 'react-router-dom'

const tiles = [
  {
    to: '/admin/users',
    icon: Users,
    label: 'Nutzer & API-Keys',
    desc: 'Tenant-Nutzer verwalten, Keys rotieren, Kontext setzen.',
    accent: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  },
  {
    to: '/admin/llm-analytics',
    icon: BarChart3,
    label: 'LLM Analytics',
    desc: 'Kosten, Calls, Modell-Nutzung pro Tenant.',
    accent: 'text-teal-400 bg-teal-500/10 border-teal-500/30',
  },
  {
    to: '/admin/drift-quality',
    icon: GitBranchPlus,
    label: 'Drift / Quality-Review',
    desc: 'Brand-Voice-Drift-Beobachtungen und Review-Queue.',
    accent: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  },
  {
    to: '/admin/modelle',
    icon: Cpu,
    label: 'Modelle & Backtest',
    desc: 'Verfügbare LLM-Modelle, Backtest gegen Tenant-Daten.',
    accent: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
  },
  {
    to: '/admin/prompt-studio',
    icon: FileCode,
    label: 'Prompt-Studio',
    desc: 'Prompt-Dateien durchsehen, bearbeiten und validieren.',
    accent: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
  },
]

export default function AdminOverview() {
  return (
    <div>
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
          <Shield className="w-5 h-5 text-amber-400" strokeWidth={1.75} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white">Admin-Tool</h1>
          <p className="text-sm text-slate-400 mt-0.5">Content Autopilot — Operator-Übersicht</p>
        </div>
      </div>

      {/* Tile Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {tiles.map((t) => {
          const Icon = t.icon
          return (
            <Link
              key={t.to}
              to={t.to}
              className={`group flex flex-col gap-3 p-5 rounded-xl border bg-slate-800/50 hover:bg-slate-800 transition-colors border-slate-700 hover:border-slate-600`}
            >
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${t.accent}`}>
                <Icon className={`w-5 h-5 ${t.accent.split(' ')[0]}`} strokeWidth={1.75} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white group-hover:text-amber-300 transition-colors">
                  {t.label}
                </p>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{t.desc}</p>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
