import { useState, useEffect } from 'react'
import { Cpu, Plus, Trash2, Zap, CheckCircle2, XCircle, Loader2, Star, Eye, EyeOff } from 'lucide-react'
import { getLLMProviders, createLLMProvider, updateLLMProvider, deleteLLMProvider, testLLMProvider } from '../api'

const PROVIDER_TYPES = [
  { value: 'litellm', label: 'LiteLLM Proxy', defaultUrl: 'http://host.docker.internal:4000/v1' },
  { value: 'openai', label: 'OpenAI', defaultUrl: 'https://api.openai.com/v1' },
  { value: 'anthropic', label: 'Anthropic (Claude)', defaultUrl: 'https://api.anthropic.com/v1' },
  { value: 'google', label: 'Google (Gemini)', defaultUrl: '' },
  { value: 'requesty', label: 'Requesty.ai', defaultUrl: 'https://router.requesty.ai/v1' },
  { value: 'groq', label: 'Groq', defaultUrl: 'https://api.groq.com/openai/v1' },
]

const TASK_OPTIONS = [
  { value: 'all', label: 'Alle Aufgaben' },
  { value: 'analysis', label: 'Analyse' },
  { value: 'creative', label: 'Kreativ (Posts)' },
  { value: 'transcription', label: 'Transkription' },
]

function ProviderCard({ provider, onTest, onDelete, onToggleDefault, testing }) {
  const statusColor = provider.last_test_status === 'ok' ? 'text-emerald-500' : provider.last_test_status === 'error' ? 'text-red-500' : 'text-gray-400'
  const StatusIcon = provider.last_test_status === 'ok' ? CheckCircle2 : provider.last_test_status === 'error' ? XCircle : Cpu

  return (
    <div className={`bg-white rounded-xl border p-4 transition-colors ${provider.is_active ? 'border-surface-border' : 'border-gray-200 opacity-60'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${provider.is_active ? 'bg-primary-50' : 'bg-gray-100'}`}>
            <StatusIcon className={`w-4.5 h-4.5 ${statusColor}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-ink">{provider.name}</h3>
              {provider.is_default && <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />}
            </div>
            <p className="text-xs text-ink-muted">{provider.provider_type} {provider.model_name ? `/ ${provider.model_name}` : ''}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => onTest(provider.id)} disabled={testing} className="p-1.5 rounded-md hover:bg-gray-100 text-ink-muted hover:text-primary-600" title="Testen">
            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          </button>
          <button onClick={() => onToggleDefault(provider)} className="p-1.5 rounded-md hover:bg-gray-100" title="Als Default setzen">
            <Star className={`w-4 h-4 ${provider.is_default ? 'text-amber-500 fill-amber-500' : 'text-gray-300'}`} />
          </button>
          <button onClick={() => onDelete(provider.id)} className="p-1.5 rounded-md hover:bg-red-50 text-ink-muted hover:text-red-500" title="Loeschen">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-100">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
          provider.task_assignment === 'all' ? 'bg-primary-50 text-primary-700' :
          provider.task_assignment === 'analysis' ? 'bg-blue-50 text-blue-700' :
          provider.task_assignment === 'creative' ? 'bg-purple-50 text-purple-700' :
          'bg-amber-50 text-amber-700'
        }`}>
          {TASK_OPTIONS.find(t => t.value === provider.task_assignment)?.label || provider.task_assignment}
        </span>
        {provider.api_key_masked && (
          <span className="text-[11px] text-ink-muted font-mono">{provider.api_key_masked}</span>
        )}
        {provider.base_url && (
          <span className="text-[11px] text-ink-muted truncate max-w-[200px]">{provider.base_url}</span>
        )}
      </div>

      {provider.last_test_error && (
        <p className="text-[11px] text-red-500 mt-2 truncate">{provider.last_test_error}</p>
      )}
    </div>
  )
}

export default function LLMSettings() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [testingId, setTestingId] = useState(null)
  const [form, setForm] = useState({ name: '', provider_type: 'requesty', api_key: '', base_url: 'https://router.eu.requesty.ai/v1', model_name: '', task_assignment: 'all' })
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => { loadProviders() }, [])

  async function loadProviders() {
    setLoading(true)
    try {
      const data = await getLLMProviders()
      setProviders(data)
    } catch (e) { /* ignore */ }
    setLoading(false)
  }

  const handleAdd = async () => {
    setSaving(true)
    try {
      await createLLMProvider(form)
      setShowAdd(false)
      setForm({ name: '', provider_type: 'litellm', api_key: '', base_url: '', model_name: '', task_assignment: 'all' })
      await loadProviders()
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
    setSaving(false)
  }

  const handleTest = async (id) => {
    setTestingId(id)
    try {
      const result = await testLLMProvider(id)
      if (result.status === 'ok') {
        alert(`Test OK (${result.latency_ms}ms)`)
      } else {
        alert(`Test fehlgeschlagen: ${result.error}`)
      }
      await loadProviders()
    } catch (e) {
      alert('Test-Fehler: ' + e.message)
    }
    setTestingId(null)
  }

  const handleDelete = async (id) => {
    if (!confirm('Provider wirklich loeschen?')) return
    await deleteLLMProvider(id)
    await loadProviders()
  }

  const handleToggleDefault = async (provider) => {
    await updateLLMProvider(provider.id, { is_default: !provider.is_default })
    await loadProviders()
  }

  const handleTypeChange = (type) => {
    const pt = PROVIDER_TYPES.find(p => p.value === type)
    setForm({ ...form, provider_type: type, base_url: pt?.defaultUrl || '' })
  }

  if (loading) return <div className="text-center py-8 text-ink-muted">Lade Provider...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary-600" />
            KI-Provider
          </h2>
          <p className="text-xs text-ink-muted mt-0.5">{providers.length} Provider konfiguriert</p>
        </div>
        <button onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800">
          <Plus className="w-3.5 h-3.5" /> Provider
        </button>
      </div>

      {providers.length === 0 ? (
        <div className="text-center py-8 bg-gray-50 rounded-xl">
          <Cpu className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-ink-light">Kein KI-Provider konfiguriert.</p>
          <button onClick={() => setShowAdd(true)} className="mt-2 text-xs text-primary-600 font-medium">Jetzt hinzufuegen</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {providers.map(p => (
            <ProviderCard key={p.id} provider={p} onTest={handleTest} onDelete={handleDelete}
              onToggleDefault={handleToggleDefault} testing={testingId === p.id} />
          ))}
        </div>
      )}

      {/* Cost Dashboard */}
      {providers.some(p => p.cost_limit_daily_cents > 0) && (() => {
        const defaultProvider = providers.find(p => p.is_default) || providers[0]
        if (!defaultProvider) return null
        const spent = defaultProvider.cost_spent_today_cents || 0
        const limit = defaultProvider.cost_limit_daily_cents || 500
        const pct = Math.min((spent / limit) * 100, 100)
        const isWarning = pct >= 80
        const isBlocked = pct >= 100
        return (
          <div className={`mt-4 p-4 rounded-xl border ${isBlocked ? 'bg-red-50 border-red-200' : isWarning ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-200'}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-ink">Tageskosten</span>
              <span className={`text-xs font-bold ${isBlocked ? 'text-red-600' : isWarning ? 'text-amber-600' : 'text-ink'}`}>
                {(spent / 100).toFixed(2)} / {(limit / 100).toFixed(2)} EUR
              </span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all ${isBlocked ? 'bg-red-500' : isWarning ? 'bg-amber-500' : 'bg-primary-500'}`}
                style={{ width: `${pct}%` }} />
            </div>
            {isBlocked && <p className="text-[11px] text-red-600 mt-1 font-medium">TAGESLIMIT ERREICHT — keine LLM-Calls bis Mitternacht</p>}
          </div>
        )
      })()}

      {showAdd && (
        <div className="mt-4 bg-white rounded-xl border border-primary-200 p-5">
          <h3 className="text-sm font-semibold text-ink mb-4">KI-Provider hinzufuegen</h3>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-ink-muted mb-1">Name</label>
                <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="z.B. LiteLLM Proxy" className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
              <div>
                <label className="block text-xs text-ink-muted mb-1">Typ</label>
                <select value={form.provider_type} onChange={e => handleTypeChange(e.target.value)}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500">
                  {PROVIDER_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs text-ink-muted mb-1">API Key</label>
              <div className="relative">
                <input type={showKey ? 'text' : 'password'} value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })}
                  placeholder="sk-..." className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono" />
                <button onClick={() => setShowKey(!showKey)} className="absolute right-2 top-2 text-ink-muted">
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-ink-muted mb-1">Base URL</label>
                <input value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })}
                  placeholder="https://api.openai.com/v1" className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
              <div>
                <label className="block text-xs text-ink-muted mb-1">Model</label>
                <input value={form.model_name} onChange={e => setForm({ ...form, model_name: e.target.value })}
                  placeholder="z.B. gpt-4o, claude-sonnet-4" className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
            </div>
            <div>
              <label className="block text-xs text-ink-muted mb-1">Aufgabe</label>
              <select value={form.task_assignment} onChange={e => setForm({ ...form, task_assignment: e.target.value })}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500">
                {TASK_OPTIONS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 text-sm text-ink-light hover:text-ink">Abbrechen</button>
              <button onClick={handleAdd} disabled={saving || !form.name}
                className="px-4 py-1.5 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50">
                {saving ? 'Speichern...' : 'Hinzufuegen'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
