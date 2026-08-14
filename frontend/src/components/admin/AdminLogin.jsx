import { useState } from 'react'
import { Shield, Loader2, AlertCircle } from 'lucide-react'
import { adminLogin } from '../../api'

export default function AdminLogin({ onAuthenticated }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await adminLogin(username, password)
      onAuthenticated()
    } catch (err) {
      if (err.status === 401) {
        setError('Ungültige Zugangsdaten')
      } else if (err.status === 503) {
        setError('Admin-Login nicht konfiguriert (ADMIN_USERNAME / ADMIN_PASSWORD fehlen in .env)')
      } else {
        setError(err.message || 'Anmeldung fehlgeschlagen')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    // bewusst behalten: bg-slate-900/800/700 + border-slate-700/600 = dunkle
    // Admin-Shell-Oberfläche (Login/Sidebar) — kein Dark-Surface-Token vorhanden,
    // Tier-2-Palette ist bewusst Light-only (Dark-Mode am 2026-08-14 entfernt,
    // siehe tailwind.config.js). amber-* ist primitive-identisch zu accent-*
    // (Brand-Akzent) und deshalb migriert.
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-500 mb-4">
            <Shield className="w-7 h-7 text-white" strokeWidth={1.75} />
          </div>
          <h1 className="text-2xl font-bold text-white">Admin-Tool</h1>
          <p className="text-ink-muted text-sm mt-1">Content Autopilot — Operator-Zugang</p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="bg-slate-800 border border-slate-700 rounded-2xl p-6 space-y-4"
        >
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Benutzername</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="w-full bg-slate-700 border border-slate-600 text-white rounded-lg px-3 py-2.5 text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
              placeholder="admin"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Passwort</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-slate-700 border border-slate-600 text-white rounded-lg px-3 py-2.5 text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 bg-status-fehler-bg/40 border border-status-fehler-border/60 rounded-lg text-xs text-status-fehler-text">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-accent-500 hover:bg-accent-400 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-lg transition-colors"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Shield className="w-4 h-4" />
            )}
            Anmelden
          </button>
        </form>

        <p className="text-center text-xs text-slate-500 mt-4">
          Zugangsdaten: ADMIN_USERNAME / ADMIN_PASSWORD in .env
        </p>
      </div>
    </div>
  )
}
