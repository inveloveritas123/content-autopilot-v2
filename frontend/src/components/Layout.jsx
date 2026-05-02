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
  Fingerprint,
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
} from 'lucide-react'
import { getProjects, createProject, deleteProject } from '../api'

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
  { to: '/voice', label: 'Voice-Profil', icon: Fingerprint },
  { to: '/brand-voice', label: 'Brand Voice', icon: Mic2 },
  { to: '/settings', label: 'Einstellungen', icon: Settings },
]

function ProjectSwitcher() {
  const [projects, setProjects] = useState([])
  const [open, setOpen] = useState(false)
  const [activeId, setActiveId] = useState(() => localStorage.getItem('activeProjectId') || null)
  const [activeName, setActiveName] = useState(() => localStorage.getItem('activeProjectName') || 'Standard')
  const [showNewForm, setShowNewForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
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
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors group"
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
              className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer group"
              onClick={() => selectProject(p)}
            >
              {activeId === p.id
                ? <Check className="w-3.5 h-3.5 text-primary-600 shrink-0" />
                : <div className="w-3.5 h-3.5 shrink-0" />
              }
              <span className={`flex-1 text-xs truncate ${activeId === p.id ? 'font-semibold text-primary-700' : 'text-ink'}`}>
                {p.name}
              </span>
              {p.source_count !== undefined && (
                <span className="text-[10px] text-ink-muted">{p.source_count} Quellen</span>
              )}
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
