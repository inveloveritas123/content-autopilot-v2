import { useState, useEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useToast } from './ui/Toast'
import { useUiMode } from '../hooks/useUiMode'
import { clsx } from 'clsx'
import {
  LayoutDashboard,
  GitBranchPlus,
  Radio,
  Lightbulb,
  FileText,
  BarChart3,
  PieChart,
  Settings,
  CalendarDays,
  Send,
  MessagesSquare,
  Mic2,
  Brain,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import TenantSwitcher from './TenantSwitcher'

// #90 finale Zuordnung (Robert-Freigabe 2026-06-13); Admin/Tooling-Screens ins Admin-Tool #98 ausgelagert
// mvp:true  = Kern-Flow (Setup/Speicher/Input/Output), immer sichtbar
// mvp:false = Feature-Creep / Fortgeschrittene, nur im Modus "features"
const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, mvp: true },
  { to: '/pipeline', label: 'Pipeline', icon: GitBranchPlus, mvp: true },
  { to: '/sources', label: 'Quellen', icon: Radio, mvp: true },
  { to: '/ideas', label: 'Ideen', icon: Lightbulb, mvp: true },
  { to: '/posts', label: 'Posts', icon: FileText, mvp: true },
  { to: '/dialogue', label: 'Dialogue', icon: MessagesSquare, mvp: false },
  { to: '/publish', label: 'Posten', icon: Send, mvp: false },
  { to: '/calendar', label: 'Kalender', icon: CalendarDays, mvp: false },
  { to: '/analytics', label: 'Analytics', icon: PieChart, mvp: false },
  { to: '/feedback', label: 'Feedback', icon: BarChart3, mvp: false },
  { to: '/settings', label: 'Einstellungen', icon: Settings, mvp: true },
  // LLM Analytics entfernt (jetzt im Admin-Tool #98)
]

const brandVoiceNavItems = [
  { to: '/brand-voice', label: 'Brand Voice', icon: Mic2, mvp: true },
  { to: '/brand-voice/insights', label: 'So liest KI mich', icon: Brain, mvp: true },
  // Review-Queue entfernt (jetzt im Admin-Tool #98 unter /admin/drift-quality/review-queue)
  { to: '/memory', label: 'Gedächtnis', icon: Sparkles, mvp: true },
  { to: '/memory/viz', label: 'Gedächtnis-Karte', icon: Sparkles, mvp: false },
  { to: '/settings/company-profile', label: 'Firmen-Profil', icon: Settings, mvp: false },
  { to: '/settings/data-deletion', label: 'Recht auf Vergessen', icon: ShieldAlert, mvp: false },
]

// adminNavItems vollständig entfernt (#90/#98): Modelle + Prompt-Studio → Admin-Tool

// Rendert eine einzelne Nav-Gruppe gefiltert nach Modus.
// isMvp=true → nur Einträge mit mvp===true; isMvp=false → alle Einträge.
function NavGroup({ items, isMvp }) {
  const visible = isMvp ? items.filter((i) => i.mvp === true) : items
  return visible.map((item) => {
    const Icon = item.icon
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === '/'}
        className={({ isActive }) =>
          clsx(
            'flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm font-medium transition-colors',
            isActive
              ? 'bg-primary-50 text-primary-700 border-l-2 border-primary-700'
              : 'text-ink-light hover:bg-gray-50 hover:text-ink'
          )
        }
      >
        <Icon className="w-[18px] h-[18px] flex-shrink-0" strokeWidth={1.75} />
        {item.label}
      </NavLink>
    )
  })
}

// #90 Segmented Switch: MVP ⇄ Features — prominent im Sidebar-Header auf jeder Seite.
// Fail-open: während `loading` ist der Switch neutral (disabled), zeigt aber immer.
// Tooltip erklärt den Unterschied. Keine neue Lib nötig.
function UiModeSwitch() {
  const { mode, loading, setMode } = useUiMode()
  const [saving, setSaving] = useState(false)

  const handleSwitch = async (newMode) => {
    if (newMode === mode || saving || loading) return
    setSaving(true)
    try {
      await setMode(newMode)
    } catch {
      // setMode schlägt fehl → ignorieren, mode bleibt unverändert (fail-open)
    } finally {
      setSaving(false)
    }
  }

  const disabled = loading || saving

  return (
    <div
      className="flex rounded-lg border border-surface-border overflow-hidden"
      title="MVP = schlanke Kern-Ansicht · Features = Voll-Stand"
    >
      {[
        { value: 'mvp', label: 'MVP' },
        { value: 'features', label: 'Features' },
      ].map(({ value, label }) => {
        const isActive = !loading && mode === value
        return (
          <button
            key={value}
            onClick={() => handleSwitch(value)}
            disabled={disabled}
            className={clsx(
              'flex-1 px-2.5 py-1.5 text-[11px] font-semibold transition-colors focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:cursor-not-allowed',
              isActive
                ? 'bg-primary-700 text-white'
                : loading
                  ? 'bg-gray-50 text-gray-300'
                  : 'bg-white text-ink-muted hover:bg-gray-50 hover:text-ink'
            )}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

export default function Layout({ children }) {
  // #90 Route-Guard-Entscheidung: NUR Nav-Gating, kein harter Route-Block.
  // Begründung: MVP soll aufräumen, nicht sperren. Wer eine MVP-false-Route per
  // Direktlink aufruft, landet trotzdem auf der Seite — kein Bruch-Risiko.
  const { mode, loading: modeLoading } = useUiMode()
  // Während Laden: fail-open = alle Einträge zeigen (kein Flackern/Verstecken)
  const isMvp = !modeLoading && mode === 'mvp'

  return (
    <div className="flex h-screen bg-surface-bg">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-surface-border flex flex-col shrink-0">
        {/* Brand Header */}
        <div className="px-4 py-4 border-b border-surface-border">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-lg bg-primary-700 flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-sm">ZB</span>
            </div>
            <div>
              <h1 className="text-base font-bold text-ink">Content Autopilot</h1>
              <p className="text-[11px] text-ink-muted leading-tight">
                Mach's doch gleich richtig.
              </p>
            </div>
          </div>
          {/* MVP ⇄ Features Switch (#90) — prominent, 1-Klick, jede Seite */}
          <div className="mb-2">
            <UiModeSwitch />
          </div>
          <TenantSwitcher />
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto flex flex-col">
          <div className="space-y-0.5">
            <NavGroup items={navItems} isMvp={isMvp} />
          </div>

          {/* Brand Voice section — nur anzeigen wenn mindestens ein Eintrag sichtbar */}
          {(!isMvp || brandVoiceNavItems.some((i) => i.mvp)) && (
            <div className="mt-4 pt-3 border-t border-surface-border space-y-0.5">
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                Brand Voice
              </p>
              <NavGroup items={brandVoiceNavItems} isMvp={isMvp} />
            </div>
          )}

          <div className="flex-1" />
          {/* Admin/Tooling-Screens sind unter /admin verfügbar (Admin-Tool #98) */}
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
      <main className="flex-1 overflow-auto flex flex-col">
        <div className="flex-1 p-6 max-w-7xl mx-auto w-full">{children}</div>
        <footer className="px-6 py-3 border-t border-surface-border">
          <div className="max-w-7xl mx-auto flex items-center justify-center gap-2 text-[11px] text-ink-muted">
            <span className="font-medium text-ink-light">Zukunftsbund GmbH</span>
            <span>·</span>
            <span>© {new Date().getFullYear()}</span>
            <span>·</span>
            <a
              href="https://zukunftsbund.de"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary-700 transition-colors"
            >
              zukunftsbund.de
            </a>
            <span>·</span>
            <a
              href="mailto:kontakt@zukunftsbund.de"
              className="hover:text-primary-700 transition-colors"
            >
              kontakt@zukunftsbund.de
            </a>
          </div>
        </footer>
      </main>
    </div>
  )
}
