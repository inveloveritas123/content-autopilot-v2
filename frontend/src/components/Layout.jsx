import { useState, useEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
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
  ChevronDown,
  Plus,
  Trash2,
  FolderOpen,
  Check,
  CalendarDays,
  Send,
  MessagesSquare,
  Mic2,
  Brain,
  ShieldAlert,
  Pencil,
  Sparkles,
} from 'lucide-react'
import { getProjects, createProject, deleteProject, updateProject } from '../api'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/pipeline', label: 'Pipeline', icon: GitBranchPlus },
  { to: '/sources', label: 'Quellen', icon: Radio },
  { to: '/ideas', label: 'Ideen', icon: Lightbulb },
  { to: '/posts', label: 'Posts', icon: FileText },
  { to: '/dialogue', label: 'Dialogue', icon: MessagesSquare },
  { to: '/publish', label: 'Posten', icon: Send },
  { to: '/calendar', label: 'Kalender', icon: CalendarDays },
  { to: '/analytics', label: 'Analytics', icon: PieChart },
  { to: '/feedback', label: 'Feedback', icon: BarChart3 },
  { to: '/settings', label: 'Einstellungen', icon: Settings },
  { to: '/settings/analytics', label: 'LLM Analytics', icon: BarChart3 },
]

const brandVoiceNavItems = [
  { to: '/brand-voice', label: 'Brand Voice', icon: Mic2 },
  { to: '/brand-voice/insights', label: 'So liest KI mich', icon: Brain },
  { to: '/brand-voice/review-queue', label: 'Review-Queue', icon: ShieldAlert },
  { to: '/memory', label: 'Gedächtnis', icon: Sparkles },
  { to: '/memory/viz', label: 'Gedächtnis-Karte', icon: Sparkles },
  { to: '/settings/company-profile', label: 'Firmen-Profil', icon: Settings },
  { to: '/settings/data-deletion', label: 'Recht auf Vergessen', icon: ShieldAlert },
]

const adminNavItems = [
  { to: '/admin/models/backtest', label: 'Modelle', icon: Settings },
]

function ProjectSwitcher() {
  const [projects, setProjects] = useState([])
  const [open, setOpen] = useState(false)
  const [activeId, setActiveId] = useState(() => localStorage.getItem('activeProjectId') || null)
  const [activeName, setActiveName] = useState(() => localStorage.getItem('activeProjectName') || 'Standard')
  const [showNewForm, setShowNewForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const dropdownRef = useRef(null)

  useEffect(() => {
    loadProjects()
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false)
        setShowNewForm(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function loadProjects() {
    try {
      const data = await getProjects()
      setProjects(data)
      // Auto-set active to first project if nothing stored
      if (!localStorage.getItem('activeProjectId') && data.length > 0) {
        const first = data[0]
        setActiveId(first.id)
        setActiveName(first.name)
        localStorage.setItem('activeProjectId', first.id)
        localStorage.setItem('activeProjectName', first.name)
      }
    } catch (e) { /* ignore */ }
  }

  const selectProject = (project) => {
    setActiveId(project.id)
    setActiveName(project.name)
    localStorage.setItem('activeProjectId', project.id)
    localStorage.setItem('activeProjectName', project.name)
    setOpen(false)
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const p = await createProject({ name: newName.trim() })
      setNewName('')
      setShowNewForm(false)
      await loadProjects()
      selectProject(p)
    } catch (e) {
      alert('Fehler: ' + e.message)
    } finally {
      setCreating(false)
    }
  }

  const startRename = (e, p) => {
    e.stopPropagation()
    setRenamingId(p.id)
    setRenameValue(p.name)
    setShowNewForm(false)
  }

  const handleRename = async (id) => {
    if (!renameValue.trim()) { setRenamingId(null); return }
    try {
      await updateProject(id, { name: renameValue.trim() })
      if (activeId === id) {
        setActiveName(renameValue.trim())
        localStorage.setItem('activeProjectName', renameValue.trim())
      }
      setRenamingId(null)
      await loadProjects()
    } catch (e) {
      alert('Umbenennen fehlgeschlagen: ' + e.message)
    }
  }

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    if (!confirm('Projekt wirklich loeschen?')) return
    try {
      await deleteProject(id)
      if (activeId === id) {
        localStorage.removeItem('activeProjectId')
        localStorage.removeItem('activeProjectName')
        setActiveId(null)
        setActiveName('Standard')
      }
      await loadProjects()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => { setOpen(!open); setShowNewForm(false) }}
        className="w-full flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-lg hover:bg-gray-50 transition-colors group"
      >
        <div className="w-6 h-6 rounded-md bg-primary-100 flex items-center justify-center shrink-0">
          <FolderOpen className="w-3.5 h-3.5 text-primary-700" />
        </div>
        <span className="flex-1 text-left text-xs font-medium text-ink truncate">{activeName}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-ink-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-surface-border rounded-xl shadow-lg z-50 py-1 overflow-hidden">
          {projects.map(p => (
            <div key={p.id}
              className="flex items-center gap-2 px-3 py-2 min-h-[44px] hover:bg-gray-50 cursor-pointer group"
              onClick={() => renamingId !== p.id && selectProject(p)}
            >
              {activeId === p.id
                ? <Check className="w-3.5 h-3.5 text-primary-600 shrink-0" />
                : <div className="w-3.5 h-3.5 shrink-0" />
              }
              {renamingId === p.id ? (
                <input
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') handleRename(p.id); if (e.key === 'Escape') setRenamingId(null) }}
                  onClick={e => e.stopPropagation()}
                  className="flex-1 text-xs border border-primary-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  autoFocus
                />
              ) : (
                <span className={`flex-1 text-xs truncate ${activeId === p.id ? 'font-semibold text-primary-700' : 'text-ink'}`}>
                  {p.name}
                </span>
              )}
              <button onClick={(e) => startRename(e, p)}
                className="p-0.5 rounded text-gray-300 hover:text-primary-600 opacity-0 group-hover:opacity-100 transition-opacity">
                <Pencil className="w-3 h-3" />
              </button>
              {projects.length > 1 && (
                <button onClick={(e) => handleDelete(e, p.id)}
                  className="p-0.5 rounded text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Trash2 className="w-3 h-3" />
                </button>
              )}
            </div>
          ))}

          <div className="border-t border-gray-100 mt-1 pt-1">
            {showNewForm ? (
              <div className="px-3 py-2 flex items-center gap-2">
                <input
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setShowNewForm(false) }}
                  placeholder="Projektname..."
                  className="flex-1 text-xs border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  autoFocus
                />
                <button onClick={handleCreate} disabled={creating || !newName.trim()}
                  className="text-xs px-2 py-1 bg-primary-700 text-white rounded-md hover:bg-primary-800 disabled:opacity-50">
                  {creating ? '...' : 'OK'}
                </button>
              </div>
            ) : (
              <button onClick={() => setShowNewForm(true)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-ink-muted hover:text-primary-700 hover:bg-gray-50">
                <Plus className="w-3.5 h-3.5" />
                Neues Projekt
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout({ children }) {
  return (
    <div className="flex h-screen bg-surface-bg">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-surface-border flex flex-col shrink-0">
        {/* Brand Header */}
        <div className="px-4 py-4 border-b border-surface-border">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-primary-700 flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-sm">ZB</span>
            </div>
            <div>
              <h1 className="text-base font-bold text-ink">Content Autopilot</h1>
              <p className="text-[11px] text-ink-muted leading-tight">Mach's doch gleich richtig.</p>
            </div>
          </div>
          {/* Project Switcher */}
          <ProjectSwitcher />
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto flex flex-col">
          <div className="space-y-0.5">
            {navItems.map(item => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm font-medium transition-colors',
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
          </div>

          {/* Brand Voice section */}
          <div className="mt-4 pt-3 border-t border-surface-border space-y-0.5">
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Brand Voice
            </p>
            {brandVoiceNavItems.map(item => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm font-medium transition-colors',
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
          </div>

          <div className="flex-1" />

          {/* Admin section */}
          <div className="mt-4 pt-3 border-t border-surface-border space-y-0.5">
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Admin
            </p>
            {adminNavItems.map(item => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 px-3 py-2.5 min-h-[44px] rounded-lg text-sm font-medium transition-colors',
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
          </div>
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
        <div className="flex-1 p-6 max-w-7xl mx-auto w-full">
          {children}
        </div>
        <footer className="px-6 py-3 border-t border-surface-border">
          <div className="max-w-7xl mx-auto flex items-center justify-center gap-2 text-[11px] text-ink-muted">
            <span className="font-medium text-ink-light">Zukunftsbund GmbH</span>
            <span>·</span>
            <span>© {new Date().getFullYear()}</span>
            <span>·</span>
            <a href="https://zukunftsbund.de" target="_blank" rel="noopener noreferrer"
               className="hover:text-primary-700 transition-colors">zukunftsbund.de</a>
            <span>·</span>
            <a href="mailto:kontakt@zukunftsbund.de"
               className="hover:text-primary-700 transition-colors">kontakt@zukunftsbund.de</a>
          </div>
        </footer>
      </main>
    </div>
  )
}
