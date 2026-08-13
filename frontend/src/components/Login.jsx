import { useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import { userLogin } from '../api'

export default function Login({ onAuthenticated }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await userLogin(email, password)
      onAuthenticated()
    } catch (err) {
      if (err.status === 401) {
        setError('E-Mail oder Passwort falsch.')
      } else {
        setError(err.message || 'Anmeldung fehlgeschlagen. Bitte versuche es erneut.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary-700 mb-4">
            <span className="text-white font-bold text-lg">ZB</span>
          </div>
          <h1 className="text-2xl font-bold text-ink">Content Autopilot</h1>
          <p className="text-gray-500 text-sm mt-1">Melde dich an, um fortzufahren.</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4 shadow-sm"
        >
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">E-Mail</label>
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-white border border-gray-300 text-ink rounded-lg px-3 py-2.5 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="du@firma.de"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">Passwort</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-white border border-gray-300 text-ink rounded-lg px-3 py-2.5 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !email || !password}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-primary-700 hover:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-lg transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Anmelden
          </button>
        </form>
      </div>
    </div>
  )
}
