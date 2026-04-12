import { useState, useEffect } from 'react'
import { Cpu, Plus, Trash2, Zap, CheckCircle2, XCircle, Loader2, Star, Eye, EyeOff, Pencil, Check, X } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getLLMProviders, createLLMProvider, updateLLMProvider, deleteLLMProvider, testLLMProvider, getLLMCostHistory } from '../api'

const PROVIDER_TYPES = [
  { value: 'litellm', label: 'LiteLLM Proxy', defaultUrl: 'http://host.docker.internal:4000/v1' },
  { value: 'openai', label: 'OpenAI', defaultUrl: 'https://api.openai.com/v1' },
  { value: 'anthropic', label: 'Anthropic (Claude)', defaultUrl: 'https://api.anthropic.com/v1' },
  { value: 'google', label: 'Google (Gemini)', defaultUrl: '' },
  { value: 'requesty', label: 'Requesty.ai', defaultUrl: 'https://router.eu.requesty.ai/v1' },
  { value: 'groq', label: 'Groq', defaultUrl: 'https://api.groq.com/openai/v1' },
]

const TASK_OPTIONS = [
  { value: 'all', label: 'Alle Aufgaben' },
  { value: 'analysis', label: 'Analyse' },
  { value: 'creative', label: 'Kreativ (Posts)' },
  { value: 'transcription', label: 'Transkription' },
]

// Aufgaben → Modell-Zuordnung (spiegelt provider_resolver.py TASK_MODEL_MAP)
const TASK_MODEL_MAP = [
  { task: 'Recherche / Analyse', model: 'Gemini 2.5 Flash Lite', tier: 'flash', assignment: 'analysis' },
  { task: 'Transkription', model: 'Gemini 2.5 Flash Lite', tier: 'flash', assignment: 'analysis' },
  { task: 'Ideen (Draft)', model: 'Gemini 2.5 Flash Lite', tier: 'flash', assignment: 'analysis' },
  { task: 'Voice-Profil', model: 'Claude Haiku 4.5', tier: 'creative', assignment: 'creative' },
  { task: 'Posts finalisieren', model: 'Claude Haiku 4.5', tier: 'creative', assignment: 'creative' },
  { task: 'Content DNA', model: 'Claude Haiku 4.5', tier: 'creative', assignment: 'creative' },
]

function ProviderCard({ provider, onTest, onDelete, onToggleDefault, onUpdateLimit, testing }) {
  const statusColor = provider.last_test_status === 'ok' ? 'text-emerald-500' : provider.last_test_status === 'error' ? 'text-red-500' : 'text-gray-400'
  const StatusIcon = provider.last_test_status === 'ok' ? CheckCircle2 : provider.last_test_status === 'error' ? XCircle : Cpu

  const [editingLimit, setEditingLimit] = useState(false)
  const [limitInput, setLimitInput] = useState('')

  const spent = provider.cost_spent_today_cents || 0
  const limit = provider.cost_limit_daily_cents || 500
  const pct = Math.min((spent / limit) * 100, 100)
  const isWarning = pct >= 80
  const isBlocked = pct >= 100

  const startEdit = () => {
    setLimitInput(((provider.cost_limit_daily_cents || 500) / 100).toFixed(2))
    setEditingLimit(true)
  }

  const saveLimit = async () => {
    const cents = Math.round(parseFloat(limitInput) * 100)
    if (!isNaN(cents) && cents >= 0) {
      await onUpdateLimit(provider.id, cents)
    }
    setEditingLimit(false)
  }

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
      </div>

      {/* Cost bar with editable limit */}
      <div className={`mt-3 pt-3 border-t border-gray-100 p-2 rounded-lg ${isBlocked ? 'bg-red-50' : isWarning ? 'bg-amber-50' : 'bg-gray-50'}`}>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] text-ink-muted">Tageskosten</span>
          <div className="flex items-center gap-1">
            <span className={`text-[11px] font-semibold ${isBlocked ? 'text-red-600' : isWarning ? 'text-amber-600' : 'text-ink'}`}>
              {(spent / 100).toFixed(2)} EUR /
            </span>
            {editingLimit ? (
              <div className="flex items-center gap-1">
                <input
                  type="number" step="0.01" min="0"
                  value={limitInput}
                  onChange={e => setLimitInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveLimit(); if (e.key === 'Escape') setEditingLimit(false) }}
                  className="w-16 text-[11px] border border-primary-300 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  autoFocus
                />
                <span className="text-[11px] text-ink-muted">EUR</span>
                <button onClick={saveLimit} className="text-emerald-600 hover:text-emerald-700"><Check className="w-3 h-3" /></button>
                <button onClick={() => setEditingLimit(false)} className="text-gray-400 hover:text-gray-600"><X className="w-3 h-3" /></button>
              </div>
            ) : (
              <button onClick={startEdit} className="flex items-center gap-0.5 text-[11px] text-ink-muted hover:text-primary-600 group">
                <span>{(limit / 100).toFixed(2)} EUR</span>
                <Pencil className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            )}
          </div>
        </div>
        <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${isBlocked ? 'bg-red-500' : isWarning ? 'bg-amber-500' : 'bg-primary-500'}`}
            style={{ width: `${pct}%` }} />
        </div>
        {isBlocked && <p className="text-[10px] text-red-600 mt-1 font-medium">LIMIT ERREICHT — keine LLM-Calls bis Mitternacht</p>}
      </div>

      {provider.last_test_error && (
        <p className="text-[11px] text-red-500 mt-2 truncate">{provider.last_test_error}</p>
      )}
    </div>
  )
}

function CostHistoryChart() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getLLMCostHistory(7)
      .then(data => setHistory(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="h-28 flex items-center justify-center text-xs text-ink-muted">Lade Verlauf...</div>
  if (!history.length) return (
    <div className="h-28 flex items-center justify-center text-xs text-ink-muted">Noch keine Kostendaten</div>
  )

  const formatted = history.map(r => ({
    date: new Date(r.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric' }),
    eur: parseFloat((r.total_cents / 100).toFixed(3)),
    calls: r.calls,
  }))

  return (
    <ResponsiveContainer width="100%" height={100}>
      <BarChart data={formatted} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `${v}€`} />
        <Tooltip
          formatter={(val, name) => [`${val.toFixed(3)} EUR`, 'Kosten']}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11, padding: '4px 8px' }}
        />
        <Bar dataKey="eur" fill="#0F766E" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function TaskAssignmentTable({ providers }) {
  const getProvider = (assignment) => {
    const p = providers.find(p => p.task_assignment === assignment && p.is_active)
      || providers.find(p => p.task_assignment === 'all' && p.is_default && p.is_active)
      || providers.find(p => p.is_active)
    return p?.name || '—'
  }

  return (
    <div className="mt-5 pt-5 border-t border-gray-100">
      <h3 className="text-xs font-semibold text-ink mb-3">Aufgaben-Zuordnung</h3>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Aufgabe</th>
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Modell</th>
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Provider</th>
            </tr>
          </thead>
          <tbody>
            {TASK_MODEL_MAP.map((row, i) => (
              <tr key={row.task} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                <td className="px-3 py-2 text-ink">{row.task}</td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    row.tier === 'flash' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                  }`}>
                    {row.model}
                  </span>
                </td>
                <td className="px-3 py-2 text-ink-muted">{getProvider(row.assignment)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-ink-muted mt-1.5">Routing basiert auf Provider-Aufgabenzuordnung. Flash = guenstig, Haiku = kreativ.</p>
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

  const handleUpdateLimit = async (id, cents) => {
    await updateLLMProvider(id, { cost_limit_daily_cents: cents })
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
              onToggleDefault={handleToggleDefault} onUpdateLimit={handleUpdateLimit} testing={testingId === p.id} />
          ))}
        </div>
      )}

      {/* Cost History */}
      {providers.length > 0 && (
        <div className="mt-5 pt-5 border-t border-gray-100">
          <h3 className="text-xs font-semibold text-ink mb-3">Kosten der letzten 7 Tage</h3>
          <CostHistoryChart />
        </div>
      )}

      {/* Task Assignment Table */}
      {providers.length > 0 && <TaskAssignmentTable providers={providers} />}

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
