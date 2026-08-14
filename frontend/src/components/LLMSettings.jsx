import { useState, useEffect, Fragment } from 'react'
import { useToast } from './ui/Toast'
import {
  Cpu,
  Plus,
  Trash2,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  Star,
  Eye,
  EyeOff,
  Pencil,
  Check,
  X,
  FlaskConical,
  RotateCcw,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import {
  getLLMProviders,
  createLLMProvider,
  updateLLMProvider,
  deleteLLMProvider,
  testLLMProvider,
  getLLMCostHistory,
  benchmarkLLM,
  getLlmRouting,
  updateSettings,
  resetLLMProviderCost,
  listProviderModels,
  probeTestProvider,
} from '../api'

const PROVIDER_TYPES = [
  { value: 'litellm', label: 'LiteLLM Proxy', defaultUrl: 'http://host.docker.internal:4000/v1' },
  { value: 'openai', label: 'OpenAI', defaultUrl: 'https://api.openai.com/v1' },
  { value: 'anthropic', label: 'Anthropic (Claude)', defaultUrl: 'https://api.anthropic.com/v1' },
  { value: 'google', label: 'Google (Gemini)', defaultUrl: '' },
  { value: 'requesty', label: 'Requesty.ai', defaultUrl: 'https://router.eu.requesty.ai/v1' },
  { value: 'groq', label: 'Groq', defaultUrl: 'https://api.groq.com/openai/v1' },
]

// Provider selection entries for the "Add Provider" modal grid
const ADD_PROVIDER_OPTIONS = [
  {
    value: 'requesty',
    label: 'Requesty.ai',
    emoji: '🔀',
    defaultUrl: 'https://router.eu.requesty.ai/v1',
    defaultModel: 'vertex/gemini-2.5-flash-lite@europe-central2',
  },
  {
    value: 'openai',
    label: 'OpenAI',
    emoji: '🤖',
    defaultUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o-mini',
  },
  {
    value: 'anthropic',
    label: 'Anthropic',
    emoji: '🧠',
    defaultUrl: 'https://api.anthropic.com/v1',
    defaultModel: 'claude-haiku-3-5',
  },
  {
    value: 'google',
    label: 'Google Vertex',
    emoji: '🔵',
    defaultUrl: '',
    defaultModel: 'gemini-2.0-flash',
  },
  {
    value: 'litellm',
    label: 'Mistral / LiteLLM',
    emoji: '⚡',
    defaultUrl: 'http://host.docker.internal:4000/v1',
    defaultModel: 'mistral/mistral-small-latest',
  },
  {
    value: 'local',
    label: 'Lokales Modell',
    emoji: '💻',
    defaultUrl: 'http://localhost:11434/v1',
    defaultModel: 'llama3',
  },
]

const TASK_OPTIONS = [
  { value: 'all', label: 'Alle Aufgaben' },
  { value: 'analysis', label: 'Analyse' },
  { value: 'creative', label: 'Kreativ (Posts)' },
  { value: 'transcription', label: 'Transkription' },
]

// Requesty.ai Modelle (Auswahlliste für Dropdown)
const REQUESTY_MODELS = [
  {
    value: 'vertex/gemini-2.5-flash-lite@europe-central2',
    label: 'Gemini 2.5 Flash Lite (0.075¢/1M) — günstigst',
  },
  { value: 'mistral/mistral-small-latest', label: 'Mistral Small (0.10¢/1M) — kreativ & günstig' },
  { value: 'mistral/mistral-large-latest', label: 'Mistral Large (2.00¢/1M) — hohe Qualität' },
  { value: 'openai/gpt-4.1-mini', label: 'GPT-4.1 Mini (0.40¢/1M) — ausgewogen' },
  { value: 'openai/gpt-4.1', label: 'GPT-4.1 (2.00¢/1M) — OpenAI Premium' },
  {
    value: 'anthropic/claude-sonnet-4-20250514',
    label: 'Claude Sonnet 4 (3.00¢/1M) — beste Qualität',
  },
]

// Aufgaben → Modell-Zuordnung (Cycle 86: google/gemini-2.0-flash + mistral/mistral-medium-latest)
const TASK_MODEL_MAP = [
  {
    task: 'Analyse / Transkription',
    model: 'Gemini 2.0 Flash',
    modelId: 'google/gemini-2.0-flash',
    tier: 'flash',
    assignment: 'analysis',
    cost: '$0.075/1M',
  },
  {
    task: 'Tagging / Scoring',
    model: 'Gemini 2.0 Flash',
    modelId: 'google/gemini-2.0-flash',
    tier: 'flash',
    assignment: 'analysis',
    cost: '$0.075/1M',
  },
  {
    task: 'Zusammenfassung',
    model: 'Gemini 2.0 Flash',
    modelId: 'google/gemini-2.0-flash',
    tier: 'flash',
    assignment: 'analysis',
    cost: '$0.075/1M',
  },
  {
    task: 'Ideation',
    model: 'Mistral Medium',
    modelId: 'mistral/mistral-medium-latest',
    tier: 'creative',
    assignment: 'creative',
    cost: '$0.40/1M',
  },
  {
    task: 'Posts generieren',
    model: 'Mistral Medium',
    modelId: 'mistral/mistral-medium-latest',
    tier: 'creative',
    assignment: 'creative',
    cost: '$0.40/1M',
  },
  {
    task: 'Smart-Fragen',
    model: 'Mistral Medium',
    modelId: 'mistral/mistral-medium-latest',
    tier: 'creative',
    assignment: 'creative',
    cost: '$0.40/1M',
  },
]

// ——————————————————————————————————————————————————————
// ProviderCard with inline Edit accordion
// ——————————————————————————————————————————————————————
function ProviderCard({
  provider,
  onTest,
  onDelete,
  onToggleDefault,
  onUpdateLimit,
  onUpdateModel,
  onResetCost,
  onUpdate,
  onToggleActive,
  testing,
}) {
  const { toast } = useToast()
  const statusColor =
    provider.last_test_status === 'ok'
      ? 'text-emerald-500'
      : provider.last_test_status === 'error'
        ? 'text-red-500'
        : 'text-gray-400'
  const StatusIcon =
    provider.last_test_status === 'ok'
      ? CheckCircle2
      : provider.last_test_status === 'error'
        ? XCircle
        : Cpu

  const [editingLimit, setEditingLimit] = useState(false)
  const [limitInput, setLimitInput] = useState('')
  const [editingModel, setEditingModel] = useState(false)
  const [modelInput, setModelInput] = useState(provider.model_name || '')
  const [resetting, setResetting] = useState(false)

  // Inline edit form state
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState({
    api_key: '',
    model_name: provider.model_name || '',
    task_assignment: provider.task_assignment || 'all',
    caching: provider.config?.caching ?? false,
    cost_limit_daily_cents: ((provider.cost_limit_daily_cents || 500) / 100).toFixed(2),
  })
  const [showEditKey, setShowEditKey] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [editTesting, setEditTesting] = useState(false)

  // #124: structured Test-Result + Connection-Log statt alert()
  const [editTestResult, setEditTestResult] = useState(null)
  const [editLogEntries, setEditLogEntries] = useState([])
  const editAppendLog = (entry) =>
    setEditLogEntries((prev) => [...prev, { ts: new Date(), ...entry }])
  // #124: Modell-Discovery im Edit-Modus
  const [editModels, setEditModels] = useState([])
  const [editModelsLoading, setEditModelsLoading] = useState(false)
  const [editSupportsListing, setEditSupportsListing] = useState(false)

  const handleEditLoadModels = async () => {
    setEditModelsLoading(true)
    editAppendLog({ level: 'info', msg: 'Modelle abrufen…' })
    const apiKey = editForm.api_key || ''
    const baseUrl = provider.base_url || ''
    if (!apiKey) {
      editAppendLog({
        level: 'warn',
        msg: '⚠ API-Key leer — bitte erst eingeben oder leer lassen für gespeicherten Key',
      })
      setEditModelsLoading(false)
      return
    }
    try {
      const res = await listProviderModels(apiKey, baseUrl)
      if (res.supports_listing) {
        setEditModels(res.models || [])
        setEditSupportsListing(true)
        editAppendLog({ level: 'ok', msg: `✓ ${res.models.length} Modelle gefunden` })
      } else {
        setEditModels([])
        setEditSupportsListing(false)
        editAppendLog({
          level: 'warn',
          msg: `⚠ Provider unterstützt /models nicht (${res.error || 'unbekannt'}) — Free-Text bleibt`,
        })
      }
    } catch (e) {
      setEditModels([])
      setEditSupportsListing(false)
      editAppendLog({ level: 'error', msg: `✗ Modell-Liste fehlgeschlagen: ${e.message}` })
    } finally {
      setEditModelsLoading(false)
    }
  }

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

  const openEditForm = () => {
    setEditForm({
      api_key: '',
      model_name: provider.model_name || '',
      task_assignment: provider.task_assignment || 'all',
      caching: provider.config?.caching ?? false,
      cost_limit_daily_cents: ((provider.cost_limit_daily_cents || 500) / 100).toFixed(2),
    })
    setShowEditKey(false)
    setEditTestResult(null)
    setEditLogEntries([])
    setEditModels([])
    setEditSupportsListing(false)
    setEditOpen(true)
  }

  const handleEditSave = async () => {
    setEditSaving(true)
    try {
      const payload = {
        model_name: editForm.model_name,
        task_assignment: editForm.task_assignment,
        cost_limit_daily_cents: Math.max(
          0,
          Math.round(parseFloat(editForm.cost_limit_daily_cents) * 100)
        ),
        config: { caching: editForm.caching },
      }
      if (editForm.api_key) payload.api_key = editForm.api_key
      await onUpdate(provider.id, payload)
      setEditOpen(false)
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    }
    setEditSaving(false)
  }

  const handleEditTest = async () => {
    setEditTesting(true)
    setEditTestResult(null)
    editAppendLog({ level: 'info', msg: `Test-Call gegen gespeicherten Provider…` })
    try {
      const result = await testLLMProvider(provider.id)
      setEditTestResult(result)
      if (result.status === 'ok') {
        editAppendLog({ level: 'ok', msg: `✓ Verbindung OK — Latenz ${result.latency_ms}ms` })
      } else if (result.http_status === 412) {
        editAppendLog({
          level: 'error',
          msg: `🔴 Budget erschöpft (412) — auf requesty.ai aufladen`,
        })
      } else {
        editAppendLog({ level: 'error', msg: `✗ Test fehlgeschlagen: ${result.error}` })
      }
    } catch (e) {
      setEditTestResult({ status: 'error', error: e.message })
      editAppendLog({ level: 'error', msg: `✗ Test-Aufruf-Fehler: ${e.message}` })
    }
    setEditTesting(false)
  }

  return (
    <div
      className={`bg-white rounded-xl border transition-colors ${editOpen ? 'border-primary-300' : provider.is_active ? 'border-surface-border' : 'border-gray-200 opacity-60'}`}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center ${provider.is_active ? 'bg-primary-50' : 'bg-gray-100'}`}
            >
              <StatusIcon className={`w-4.5 h-4.5 ${statusColor}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-ink">{provider.name}</h3>
                {provider.is_default && (
                  <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                )}
              </div>
              <p className="text-xs text-ink-muted">
                {provider.provider_type} {provider.model_name ? `/ ${provider.model_name}` : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={openEditForm}
              className={`p-1.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 ${editOpen ? 'text-primary-600 bg-primary-50' : 'text-ink-muted hover:text-primary-600'}`}
              title="Bearbeiten"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              onClick={() => onTest(provider.id)}
              disabled={testing}
              className="p-1.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 text-ink-muted hover:text-primary-600"
              title="Testen"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            </button>
            <button
              onClick={() => onToggleDefault(provider)}
              className="p-1.5 rounded-md hover:bg-gray-100"
              title="Als Default setzen"
            >
              <Star
                className={`w-4 h-4 ${provider.is_default ? 'text-amber-500 fill-amber-500' : 'text-gray-300'}`}
              />
            </button>
            <button
              onClick={() => onToggleActive(provider)}
              className={`px-2 py-0.5 rounded-full text-[11px] font-semibold transition-colors ${provider.is_active ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
              title={provider.is_active ? 'Deaktivieren' : 'Aktivieren'}
            >
              {provider.is_active ? 'Aktiv' : 'Inaktiv'}
            </button>
            {!provider.is_active && (
              <button
                onClick={() => onDelete(provider.id)}
                className="p-1.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-red-50 text-ink-muted hover:text-red-500"
                title="Loeschen"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-100">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
              provider.task_assignment === 'all'
                ? 'bg-primary-50 text-primary-700'
                : provider.task_assignment === 'analysis'
                  ? 'bg-blue-50 text-blue-700'
                  : provider.task_assignment === 'creative'
                    ? 'bg-purple-50 text-purple-700'
                    : 'bg-amber-50 text-amber-700'
            }`}
          >
            {TASK_OPTIONS.find((t) => t.value === provider.task_assignment)?.label ||
              provider.task_assignment}
          </span>
          {provider.api_key_masked && (
            <span className="text-[11px] text-ink-muted font-mono">{provider.api_key_masked}</span>
          )}
          {provider.config?.caching && (
            <span className="text-[11px] bg-teal-50 text-teal-700 px-1.5 py-0.5 rounded-full">
              Caching
            </span>
          )}
        </div>

        {/* Cost bar with editable limit */}
        <div
          className={`mt-3 pt-3 border-t border-gray-100 p-2 rounded-lg ${isBlocked ? 'bg-red-50' : isWarning ? 'bg-amber-50' : 'bg-gray-50'}`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] text-ink-muted">Tageskosten</span>
            <div className="flex items-center gap-1">
              <span
                className={`text-[11px] font-semibold ${isBlocked ? 'text-red-600' : isWarning ? 'text-amber-600' : 'text-ink'}`}
              >
                ${(spent / 100).toFixed(2)} /
              </span>
              {editingLimit ? (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={limitInput}
                    onChange={(e) => setLimitInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveLimit()
                      if (e.key === 'Escape') setEditingLimit(false)
                    }}
                    className="w-16 text-[11px] border border-primary-300 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
                    autoFocus
                  />
                  <span className="text-[11px] text-ink-muted">USD</span>
                  <button onClick={saveLimit} className="text-emerald-600 hover:text-emerald-700">
                    <Check className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => setEditingLimit(false)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={startEdit}
                  className="flex items-center gap-0.5 text-[11px] text-ink-muted hover:text-primary-600 group"
                >
                  <span>${(limit / 100).toFixed(2)} USD</span>
                  <Pencil className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              )}
            </div>
          </div>
          <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${isBlocked ? 'bg-red-500' : isWarning ? 'bg-amber-500' : 'bg-primary-500'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          {isBlocked && (
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <p className="text-[10px] text-red-600 font-medium">LIMIT ERREICHT</p>
              <div className="flex gap-1 ml-auto">
                <button
                  onClick={async () => {
                    setResetting(true)
                    try {
                      await onResetCost(provider.id)
                    } finally {
                      setResetting(false)
                    }
                  }}
                  disabled={resetting}
                  className="flex items-center gap-0.5 px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700 rounded-md hover:bg-amber-200 border border-amber-200 transition-colors"
                  title="Tageskosten auf 0 zurücksetzen"
                >
                  {resetting ? (
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />
                  ) : (
                    <RotateCcw className="w-2.5 h-2.5" />
                  )}
                  Reset
                </button>
                {[2, 5].map((usd) => (
                  <button
                    key={usd}
                    onClick={() => onUpdateLimit(provider.id, limit + usd * 100)}
                    className="px-2 py-0.5 text-[10px] font-semibold bg-red-100 text-red-700 rounded-md hover:bg-red-200 border border-red-200 transition-colors"
                    title={`Limit um +$${usd} erhöhen`}
                  >
                    +${usd}
                  </button>
                ))}
              </div>
            </div>
          )}
          {!isBlocked && (
            <div className="mt-1.5 flex justify-end gap-1">
              <button
                onClick={async () => {
                  setResetting(true)
                  try {
                    await onResetCost(provider.id)
                  } finally {
                    setResetting(false)
                  }
                }}
                disabled={resetting || spent === 0}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-ink-muted hover:text-amber-600 hover:bg-amber-50 rounded transition-colors disabled:opacity-30"
                title="Tageskosten auf 0 zurücksetzen"
              >
                {resetting ? (
                  <Loader2 className="w-2.5 h-2.5 animate-spin" />
                ) : (
                  <RotateCcw className="w-2.5 h-2.5" />
                )}
              </button>
              {[2, 5].map((usd) => (
                <button
                  key={usd}
                  onClick={() => onUpdateLimit(provider.id, limit + usd * 100)}
                  className="px-1.5 py-0.5 text-[10px] text-ink-muted hover:text-primary-600 hover:bg-primary-50 rounded transition-colors"
                  title={`Limit um +$${usd} erhöhen`}
                >
                  +${usd}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Model selector */}
        <div className="mt-2 pt-2 border-t border-gray-100">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-ink-muted shrink-0">Modell:</span>
            {editingModel ? (
              <div className="flex items-center gap-1 flex-1">
                <select
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  className="flex-1 text-[11px] border border-primary-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-primary-500 bg-white"
                >
                  <option value="">— Freitext —</option>
                  {REQUESTY_MODELS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={async () => {
                    await onUpdateModel(provider.id, modelInput)
                    setEditingModel(false)
                  }}
                  className="text-emerald-600 hover:text-emerald-700 shrink-0"
                >
                  <Check className="w-3 h-3" />
                </button>
                <button
                  onClick={() => {
                    setModelInput(provider.model_name || '')
                    setEditingModel(false)
                  }}
                  className="text-gray-400 hover:text-gray-600 shrink-0"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  setModelInput(provider.model_name || '')
                  setEditingModel(true)
                }}
                className="flex items-center gap-1 text-[11px] text-ink font-mono hover:text-primary-600 group truncate max-w-[200px]"
                title={provider.model_name || 'Kein Modell'}
              >
                <span className="truncate">{provider.model_name || '—'}</span>
                <Pencil className="w-2.5 h-2.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            )}
          </div>
        </div>

        {provider.last_test_error && (
          <p className="text-[11px] text-red-500 mt-2 truncate">{provider.last_test_error}</p>
        )}
      </div>

      {/* Inline Edit Accordion */}
      {editOpen && (
        <div className="border-t border-primary-100 bg-primary-50/40 rounded-b-xl p-4">
          <h4 className="text-xs font-semibold text-ink mb-3">Provider bearbeiten</h4>
          <div className="space-y-3">
            {/* API Key */}
            <div>
              <label className="block text-xs text-ink-muted mb-1">
                API-Key (leer lassen = unveraendert)
              </label>
              <div className="relative">
                <input
                  type={showEditKey ? 'text' : 'password'}
                  value={editForm.api_key}
                  onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
                  placeholder="sk-... (nur ausfuellen um zu aendern)"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono bg-white"
                />
                <button
                  type="button"
                  onClick={() => setShowEditKey(!showEditKey)}
                  className="absolute right-2 top-2.5 text-ink-muted hover:text-ink"
                >
                  {showEditKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Model Name (#124: mit Live-Discovery, fallback REQUESTY_MODELS) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs text-ink-muted">Modell</label>
                <button
                  type="button"
                  onClick={handleEditLoadModels}
                  disabled={editModelsLoading || !editForm.api_key}
                  title={
                    !editForm.api_key
                      ? 'API-Key oben eingeben — sonst kein Lookup gegen Provider möglich'
                      : ''
                  }
                  className="text-[11px] text-primary-700 hover:text-primary-900 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  {editModelsLoading ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RotateCcw className="w-3 h-3" />
                  )}
                  Modelle laden
                </button>
              </div>
              {editSupportsListing && editModels.length > 0 ? (
                <select
                  value={editForm.model_name}
                  onChange={(e) => setEditForm({ ...editForm, model_name: e.target.value })}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                >
                  <option value="">— bitte wählen —</option>
                  {editModels.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  value={editForm.model_name}
                  onChange={(e) => setEditForm({ ...editForm, model_name: e.target.value })}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                >
                  <option value="">— Freitext / kein Modell —</option>
                  {REQUESTY_MODELS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Task Assignment */}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Aufgabe</label>
                <select
                  value={editForm.task_assignment}
                  onChange={(e) => setEditForm({ ...editForm, task_assignment: e.target.value })}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                >
                  {TASK_OPTIONS.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Cost Cap */}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Kostenlimit / Tag (USD)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={editForm.cost_limit_daily_cents}
                  onChange={(e) =>
                    setEditForm({ ...editForm, cost_limit_daily_cents: e.target.value })
                  }
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                />
              </div>
            </div>

            {/* Caching Checkbox */}
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={editForm.caching}
                onChange={(e) => setEditForm({ ...editForm, caching: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-ink">Prompt-Caching aktivieren</span>
              <span className="text-[11px] text-ink-muted">
                (spart Token bei wiederholten Prompts)
              </span>
            </label>

            {/* #124: Test-Result Pill */}
            {editTestResult && (
              <div className="flex items-center gap-2 text-xs">
                {editTestResult.status === 'ok' ? (
                  <span className="text-emerald-700 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Verbindung OK · {editTestResult.latency_ms}ms
                  </span>
                ) : (
                  <span
                    className="text-red-700 flex items-center gap-1 truncate"
                    title={editTestResult.error}
                  >
                    <XCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{editTestResult.error}</span>
                  </span>
                )}
              </div>
            )}

            {/* #124: Connection-Log */}
            {editLogEntries.length > 0 && (
              <details
                className="text-[11px]"
                open={editLogEntries.some((e) => e.level === 'error')}
              >
                <summary className="cursor-pointer text-ink-muted hover:text-ink select-none">
                  Verbindungs-Log ({editLogEntries.length})
                </summary>
                <div className="mt-1 max-h-40 overflow-y-auto bg-white rounded p-2 space-y-0.5 font-mono border border-gray-100">
                  {editLogEntries.map((e, i) => {
                    const colorMap = {
                      ok: 'text-emerald-700',
                      error: 'text-red-700',
                      warn: 'text-amber-700',
                      info: 'text-ink-muted',
                    }
                    const ts = e.ts.toTimeString().slice(0, 8)
                    return (
                      <div key={i} className={colorMap[e.level] || 'text-ink-muted'}>
                        <span className="text-ink-muted">{ts}</span> {e.msg}
                      </div>
                    )
                  })}
                </div>
              </details>
            )}

            {/* Action Buttons */}
            <div className="flex gap-2 justify-between pt-1">
              <button
                onClick={() => onDelete(provider.id)}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 rounded-lg border border-red-200 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Loeschen
              </button>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditOpen(false)}
                  className="px-3 py-1.5 text-xs text-ink-muted hover:text-ink"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleEditTest}
                  disabled={editTesting}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 rounded-lg border border-primary-200 transition-colors disabled:opacity-50"
                >
                  {editTesting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Zap className="w-3.5 h-3.5" />
                  )}
                  Test-Verbindung
                </button>
                <button
                  onClick={handleEditSave}
                  disabled={editSaving}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-white bg-primary-700 hover:bg-primary-800 rounded-lg transition-colors disabled:opacity-50"
                >
                  {editSaving ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5" />
                  )}
                  Speichern
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function CostHistoryChart() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getLLMCostHistory(7)
      .then((data) => setHistory(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading)
    return (
      <div className="h-28 flex items-center justify-center text-xs text-ink-muted">
        Lade Verlauf...
      </div>
    )
  if (!history.length)
    return (
      <div className="h-28 flex items-center justify-center text-xs text-ink-muted">
        Noch keine Kostendaten
      </div>
    )

  const formatted = history.map((r) => ({
    date: new Date(r.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric' }),
    eur: parseFloat((r.total_cents / 100).toFixed(3)),
    calls: r.calls,
  }))

  return (
    <ResponsiveContainer width="100%" height={100}>
      <BarChart data={formatted} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis
          tick={{ fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v}`}
        />
        <Tooltip
          formatter={(val, name) => [`$${val.toFixed(3)} USD`, 'Kosten']}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11, padding: '4px 8px' }}
        />
        {/* bewusst behalten: Recharts-Bar-fill akzeptiert nur Farb-Literale, kein
            Tailwind-Klassenkontext — Wert entspricht bewusst exakt primary-700
            aus tailwind.config.js, keine neu erfundene Farbe. */}
        <Bar dataKey="eur" fill="#0F766E" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// Map TASK_MODEL_MAP rows to benchmark step keys
const STEP_MAP = {
  'Analyse / Transkription': 'analysis',
  'Tagging / Scoring': null, // no standalone benchmark
  Zusammenfassung: null,
  Ideation: 'ideation',
  'Posts generieren': 'post_generation',
  'Smart-Fragen': 'smart_questions',
}

function BenchmarkResult({ result, onClose }) {
  const isOk = result.status === 'ok'
  const isBudget = result.status === 'budget_exceeded'
  const bgClass = isOk
    ? 'bg-emerald-50 border-emerald-200'
    : isBudget
      ? 'bg-amber-50 border-amber-200'
      : 'bg-red-50 border-red-200'
  return (
    <div className={`mt-2 p-3 rounded-lg text-xs border ${bgClass}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          {result.item_title && result.item_title !== '—' && (
            <span className="font-medium text-ink">{result.item_title}</span>
          )}
          {result.latency_ms > 0 && <span className="text-ink-muted">{result.latency_ms}ms</span>}
          {result.quality_score != null && (
            <span
              className={`font-semibold px-1.5 py-0.5 rounded ${result.quality_score >= 80 ? 'bg-emerald-100 text-emerald-700' : result.quality_score >= 60 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}
            >
              {result.quality_score.toFixed(0)}/100
            </span>
          )}
          {result.model_used && (
            <span className="text-ink-muted font-mono">{result.model_used}</span>
          )}
        </div>
        <button onClick={onClose} className="text-ink-muted hover:text-ink shrink-0">
          <X className="w-3 h-3" />
        </button>
      </div>
      {result.error ? (
        <p className={isBudget ? 'text-amber-700' : 'text-red-600'}>{result.error}</p>
      ) : (
        <pre className="whitespace-pre-wrap text-ink text-[10px] leading-relaxed max-h-32 overflow-y-auto">
          {result.result_preview}
        </pre>
      )}
    </div>
  )
}

function TaskAssignmentTable({ providers }) {
  const [benchmarking, setBenchmarking] = useState(null) // step key being benchmarked
  const [results, setResults] = useState({}) // step key → result

  const getProvider = (assignment) => {
    const p =
      providers.find((p) => p.task_assignment === assignment && p.is_active) ||
      providers.find((p) => p.task_assignment === 'all' && p.is_default && p.is_active) ||
      providers.find((p) => p.is_active)
    return p?.name || '—'
  }

  const handleBenchmark = async (task) => {
    const step = STEP_MAP[task]
    if (!step) return
    setBenchmarking(step)
    try {
      const result = await benchmarkLLM(step)
      setResults((prev) => ({ ...prev, [step]: result }))
    } catch (e) {
      setResults((prev) => ({
        ...prev,
        [step]: { status: 'error', error: e.message, step, item_title: '—' },
      }))
    }
    setBenchmarking(null)
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
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Kosten</th>
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Provider</th>
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Test</th>
            </tr>
          </thead>
          <tbody>
            {TASK_MODEL_MAP.map((row, i) => {
              const step = STEP_MAP[row.task]
              const isBenchmarking = benchmarking === step
              const hasResult = step && results[step]
              return (
                <Fragment key={row.task}>
                  <tr className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                    <td className="px-3 py-2 text-ink">{row.task}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          row.tier === 'flash'
                            ? 'bg-blue-50 text-blue-700'
                            : 'bg-purple-50 text-purple-700'
                        }`}
                      >
                        {row.model}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-muted text-[10px] font-mono">
                      {row.cost || '—'}
                    </td>
                    <td className="px-3 py-2 text-ink-muted">{getProvider(row.assignment)}</td>
                    <td className="px-3 py-2">
                      {step ? (
                        <button
                          onClick={() => handleBenchmark(row.task)}
                          disabled={!!benchmarking}
                          className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded disabled:opacity-40 transition-colors"
                          title={`${row.task} mit einem echten Item testen`}
                        >
                          {isBenchmarking ? (
                            <Loader2 className="w-2.5 h-2.5 animate-spin" />
                          ) : (
                            <FlaskConical className="w-2.5 h-2.5" />
                          )}
                          Testen
                        </button>
                      ) : (
                        <span className="text-[10px] text-ink-muted">—</span>
                      )}
                    </td>
                  </tr>
                  {hasResult && (
                    <tr className="bg-white">
                      <td colSpan={5} className="px-3 pb-2">
                        <BenchmarkResult
                          result={results[step]}
                          onClose={() =>
                            setResults((prev) => {
                              const n = { ...prev }
                              delete n[step]
                              return n
                            })
                          }
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-ink-muted mt-1.5">
        Routing seit Cycle 86: Gemini 2.0 Flash = günstig ($0.075/1M), Mistral Medium = kreativ
        ($0.40/1M). [Testen] führt einen echten LLM-Aufruf durch — Budget wird verbraucht.
      </p>
    </div>
  )
}

// Model options available via Requesty.ai for per-task override
const ROUTING_MODELS = [
  {
    key: 'gemini-flash',
    label: 'Gemini Flash (0.075$/1M)',
    id: 'vertex/gemini-2.5-flash-lite@europe-central2',
  },
  {
    key: 'mistral-medium',
    label: 'Mistral Medium (0.40$/1M)',
    id: 'mistral/mistral-medium-latest',
  },
  { key: 'mistral-small', label: 'Mistral Small (0.10$/1M)', id: 'mistral/mistral-small-latest' },
  { key: 'gpt4-mini', label: 'GPT-4.1 Mini (0.40$/1M)', id: 'openai/gpt-4.1-mini' },
  {
    key: 'claude-sonnet',
    label: 'Claude Sonnet 4 (3.00$/1M)',
    id: 'anthropic/claude-sonnet-4-20250514',
  },
]

function RoutingOverridePanel() {
  const { toast } = useToast()
  const [routing, setRouting] = useState(null)
  const [overrides, setOverrides] = useState({})
  const [saving, setSaving] = useState(null)
  const [savedMsg, setSavedMsg] = useState(null)

  useEffect(() => {
    getLlmRouting()
      .then((d) => {
        setRouting(d)
        const cur = {}
        ;(d?.routing || []).forEach((r) => {
          cur[r.purpose] = r.model_key
        })
        setOverrides(cur)
      })
      .catch(() => {})
  }, [])

  const handleSave = async (purpose) => {
    setSaving(purpose)
    try {
      const current = {}
      Object.entries(overrides).forEach(([k, v]) => {
        current[k] = v
      })
      await updateSettings({ llm_routing: current })
      setSavedMsg(purpose)
      setTimeout(() => setSavedMsg(null), 2000)
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    }
    setSaving(null)
  }

  if (!routing) return null

  return (
    <div className="mt-5 pt-5 border-t border-gray-100">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-xs font-semibold text-ink">Live Routing Override</h3>
        <span className="text-[10px] text-ink-muted">
          Welches Modell wird für welchen Schritt verwendet
        </span>
        {routing.daily_budget_eur && (
          <span className="ml-auto text-[10px] text-ink-muted">
            Budget: {routing.daily_budget_eur}€/Tag
          </span>
        )}
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Schritt</th>
              <th className="px-3 py-2 text-left font-medium text-ink-muted">Modell</th>
              <th className="px-3 py-2 text-right font-medium text-ink-muted">Kosten/1M</th>
              <th className="px-3 py-2 text-right font-medium text-ink-muted">Max Tokens</th>
              <th className="px-3 py-2 text-right font-medium text-ink-muted"></th>
            </tr>
          </thead>
          <tbody>
            {(routing.routing || []).map((row, i) => {
              const changed = overrides[row.purpose] !== row.model_key
              const isSaved = savedMsg === row.purpose
              const isSaving = saving === row.purpose
              const costInfo = row.cost_per_1m_usd != null ? `$${row.cost_per_1m_usd}/1M` : '—'
              return (
                <tr key={row.purpose} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                  <td className="px-3 py-2 font-medium text-ink">{row.label}</td>
                  <td className="px-3 py-2">
                    <select
                      value={overrides[row.purpose] || row.model_key}
                      onChange={(e) =>
                        setOverrides((prev) => ({ ...prev, [row.purpose]: e.target.value }))
                      }
                      className="text-[11px] border border-gray-200 rounded px-1.5 py-0.5 bg-white focus:outline-none focus:ring-1 focus:ring-primary-400 max-w-[200px]"
                    >
                      {ROUTING_MODELS.map((m) => (
                        <option key={m.key} value={m.key}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11px] text-ink-muted">
                    {costInfo}
                  </td>
                  <td className="px-3 py-2 text-right text-[11px] text-ink-muted">
                    {row.max_tokens}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {isSaved ? (
                      <span className="text-[10px] text-emerald-600 font-medium">Gespeichert</span>
                    ) : (
                      <button
                        onClick={() => handleSave(row.purpose)}
                        disabled={!changed || !!saving}
                        className={`px-2 py-0.5 text-[10px] font-medium rounded border transition-colors ${
                          changed
                            ? 'text-primary-700 bg-primary-50 border-primary-200 hover:bg-primary-100'
                            : 'text-gray-300 border-gray-100 cursor-default'
                        }`}
                      >
                        {isSaving ? '...' : 'Speichern'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-ink-muted mt-1.5">
        Änderungen gelten sofort für neue Pipeline-Aufrufe. Günstigst: Gemini Flash (0.075$/1M).
        Beste Kreativität: Mistral Medium (0.40$/1M).
      </p>
    </div>
  )
}

// ——————————————————————————————————————————————————————
// Add Provider Modal
// ——————————————————————————————————————————————————————
function AddProviderModal({ onClose, onSave }) {
  const { toast } = useToast()
  const [step, setStep] = useState('select') // 'select' | 'form'
  const [selectedType, setSelectedType] = useState(null)
  const [form, setForm] = useState({
    name: '',
    provider_type: '',
    api_key: '',
    base_url: '',
    model_name: '',
    task_assignment: 'all',
    caching: false,
    cost_limit_daily_cents: '5.00',
  })
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)

  // #136: Live-Modell-Discovery + Probe-Test + Connection-Log
  const [models, setModels] = useState([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [supportsListing, setSupportsListing] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null) // { ok, latency_ms, error, ... }
  const [forceSave, setForceSave] = useState(false) // override "speichern nur wenn Test ok"
  const [logEntries, setLogEntries] = useState([])
  const appendLog = (entry) => setLogEntries((prev) => [...prev, { ts: new Date(), ...entry }])

  const handleLoadModels = async () => {
    if (!form.api_key || !form.base_url) return
    setModelsLoading(true)
    appendLog({ level: 'info', msg: 'Modelle abrufen…' })
    try {
      const res = await listProviderModels(form.api_key, form.base_url)
      if (res.supports_listing) {
        setModels(res.models || [])
        setSupportsListing(true)
        appendLog({ level: 'ok', msg: `✓ ${res.models.length} Modelle gefunden` })
      } else {
        setModels([])
        setSupportsListing(false)
        appendLog({
          level: 'warn',
          msg: `⚠ Provider unterstützt /models nicht (${res.error || 'unbekannt'}) — Free-Text`,
        })
      }
    } catch (e) {
      setModels([])
      setSupportsListing(false)
      appendLog({ level: 'error', msg: `✗ Modell-Liste fehlgeschlagen: ${e.message}` })
    } finally {
      setModelsLoading(false)
    }
  }

  const handleTest = async () => {
    if (!form.api_key || !form.base_url) {
      appendLog({ level: 'error', msg: '✗ API-Key + Base-URL erforderlich' })
      return
    }
    setTesting(true)
    setTestResult(null)
    appendLog({ level: 'info', msg: `Test-Call (1 Token, max 5 Output)…` })
    try {
      const res = await probeTestProvider(form.api_key, form.base_url, form.model_name || null)
      setTestResult(res)
      if (res.ok) {
        appendLog({
          level: 'ok',
          msg: `✓ Test ok: ${res.latency_ms}ms, model=${res.model_responded || form.model_name}, tokens=${res.tokens_used || 0}`,
        })
      } else {
        appendLog({
          level: 'error',
          msg: `✗ Test fehlgeschlagen (HTTP ${res.http_status || '?'}): ${res.error}`,
        })
      }
    } catch (e) {
      setTestResult({ ok: false, error: e.message })
      appendLog({ level: 'error', msg: `✗ Test-Call-Fehler: ${e.message}` })
    } finally {
      setTesting(false)
    }
  }

  const handleSelectProvider = (opt) => {
    setSelectedType(opt)
    setForm((f) => ({
      ...f,
      name: opt.label,
      provider_type: opt.value,
      base_url: opt.defaultUrl,
      model_name: opt.defaultModel,
    }))
    setStep('form')
  }

  const handleSave = async () => {
    if (!testResult?.ok && !forceSave) {
      appendLog({
        level: 'warn',
        msg: '⚠ Bitte erst „Verbindung testen" oder „Trotzdem speichern" aktivieren',
      })
      return
    }
    setSaving(true)
    appendLog({ level: 'info', msg: 'Provider speichern…' })
    try {
      const payload = {
        name: form.name,
        provider_type: form.provider_type,
        api_key: form.api_key,
        base_url: form.base_url,
        model_name: form.model_name,
        task_assignment: form.task_assignment,
        auto_cache: !!form.caching,
        cost_limit_daily_cents: Math.round(parseFloat(form.cost_limit_daily_cents || '5') * 100),
        config: { caching: form.caching },
      }
      await onSave(payload)
      appendLog({ level: 'ok', msg: '✓ Provider angelegt' })
      onClose()
    } catch (e) {
      appendLog({ level: 'error', msg: `✗ Speichern fehlgeschlagen: ${e.message}` })
      toast.error('Fehler: ' + e.message)
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            {step === 'form' && (
              <button
                onClick={() => setStep('select')}
                className="mr-1 p-1 rounded-md hover:bg-gray-100 text-ink-muted hover:text-ink"
              >
                <X className="w-4 h-4 rotate-180" style={{ transform: 'rotate(180deg)' }} />
              </button>
            )}
            <h3 className="text-sm font-semibold text-ink">
              {step === 'select' ? 'Provider hinzufuegen' : `${selectedType?.label} einrichten`}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 text-ink-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          {step === 'select' ? (
            <div>
              <p className="text-xs text-ink-muted mb-4">
                Welchen KI-Dienst moechtest du verbinden?
              </p>
              <div className="grid grid-cols-2 gap-2.5">
                {ADD_PROVIDER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => handleSelectProvider(opt)}
                    className="flex items-center gap-3 p-3 rounded-xl border border-gray-200 hover:border-primary-300 hover:bg-primary-50/50 transition-colors text-left group"
                  >
                    <span className="text-2xl">{opt.emoji}</span>
                    <div>
                      <p className="text-sm font-medium text-ink group-hover:text-primary-700">
                        {opt.label}
                      </p>
                      <p className="text-[10px] text-ink-muted truncate max-w-[120px]">
                        {opt.defaultUrl || 'Custom URL'}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Name */}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="z.B. Requesty Production"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {/* API Key */}
              <div>
                <label className="block text-xs text-ink-muted mb-1">API-Key</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={form.api_key}
                    onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                    placeholder="sk-..."
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-2.5 text-ink-muted hover:text-ink"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Base URL</label>
                <input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder="https://api.openai.com/v1"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {/* #136: Modell-Auswahl mit Live-Discovery */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs text-ink-muted">Modell</label>
                  <button
                    type="button"
                    onClick={handleLoadModels}
                    disabled={modelsLoading || !form.api_key || !form.base_url}
                    className="text-[11px] text-primary-700 hover:text-primary-900 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    {modelsLoading ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <RotateCcw className="w-3 h-3" />
                    )}
                    Modelle laden
                  </button>
                </div>
                {supportsListing && models.length > 0 ? (
                  <select
                    value={form.model_name}
                    onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">— bitte wählen —</option>
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={form.model_name}
                    onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                    placeholder="z.B. gpt-4o-mini oder vertex/gemini-2.5-flash-lite@..."
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                )}
                {!supportsListing &&
                  logEntries.some((e) => e.msg?.includes('unterstützt /models nicht')) && (
                    <p className="text-[10px] text-ink-muted mt-1">
                      Provider hat keinen /models-Endpoint — Modellname manuell eintragen.
                    </p>
                  )}
              </div>

              {/* Task Assignment + Cost Cap */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-ink-muted mb-1">Aufgabe</label>
                  <select
                    value={form.task_assignment}
                    onChange={(e) => setForm({ ...form, task_assignment: e.target.value })}
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    {TASK_OPTIONS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-ink-muted mb-1">
                    Kostenlimit / Tag (USD)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.cost_limit_daily_cents}
                    onChange={(e) => setForm({ ...form, cost_limit_daily_cents: e.target.value })}
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              {/* Caching */}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={form.caching}
                  onChange={(e) => setForm({ ...form, caching: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-ink">Prompt-Caching aktivieren</span>
              </label>

              {/* #136: Verbindung-testen-Button */}
              <div className="border-t border-gray-100 pt-3 space-y-2">
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={handleTest}
                    disabled={testing || !form.api_key || !form.base_url}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg disabled:opacity-50"
                  >
                    {testing ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <FlaskConical className="w-3 h-3" />
                    )}
                    Verbindung testen
                  </button>
                  {testResult?.ok && (
                    <span className="text-[11px] text-emerald-700 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      {testResult.latency_ms}ms · {testResult.tokens_used || 0} Tokens
                    </span>
                  )}
                  {testResult && !testResult.ok && (
                    <span
                      className="text-[11px] text-red-700 flex items-center gap-1 truncate max-w-[280px]"
                      title={testResult.error}
                    >
                      <XCircle className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate">{testResult.error}</span>
                    </span>
                  )}
                </div>

                {/* Trotzdem-speichern-Override (sichtbar nur wenn Test fehlgeschlagen) */}
                {testResult && !testResult.ok && (
                  <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-ink-muted">
                    <input
                      type="checkbox"
                      checked={forceSave}
                      onChange={(e) => setForceSave(e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-gray-300 text-primary-600"
                    />
                    Trotz Fehler speichern (z.B. wenn Provider gerade aufgeladen werden muss)
                  </label>
                )}

                {/* Connection-Log */}
                {logEntries.length > 0 && (
                  <details
                    className="text-[11px]"
                    open={logEntries.some((e) => e.level === 'error')}
                  >
                    <summary className="cursor-pointer text-ink-muted hover:text-ink select-none">
                      Verbindungs-Log ({logEntries.length})
                    </summary>
                    <div className="mt-1 max-h-40 overflow-y-auto bg-gray-50 rounded p-2 space-y-0.5 font-mono">
                      {logEntries.map((e, i) => {
                        const colorMap = {
                          ok: 'text-emerald-700',
                          error: 'text-red-700',
                          warn: 'text-amber-700',
                          info: 'text-ink-muted',
                        }
                        const ts = e.ts.toTimeString().slice(0, 8)
                        return (
                          <div key={i} className={colorMap[e.level] || 'text-ink-muted'}>
                            <span className="text-ink-muted">{ts}</span> {e.msg}
                          </div>
                        )
                      })}
                    </div>
                  </details>
                )}
              </div>

              {/* Footer Buttons */}
              <div className="flex gap-2 justify-end pt-1">
                <button
                  onClick={onClose}
                  className="px-3 py-1.5 text-sm text-ink-muted hover:text-ink"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !form.name || (!testResult?.ok && !forceSave)}
                  title={
                    !testResult?.ok && !forceSave
                      ? 'Erst Verbindung testen oder „Trotz Fehler speichern"'
                      : ''
                  }
                  className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Plus className="w-3.5 h-3.5" />
                  )}
                  Hinzufuegen
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ——————————————————————————————————————————————————————
// Main LLMSettings Component
// ——————————————————————————————————————————————————————
export default function LLMSettings() {
  const { toast } = useToast()
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  // #124: Multi-Provider-Test
  const [allTestRunning, setAllTestRunning] = useState(false)
  const [allTestResults, setAllTestResults] = useState(null) // [{providerId, name, status, latency_ms, error}]
  const [testingId, setTestingId] = useState(null)

  useEffect(() => {
    loadProviders()
  }, [])

  async function loadProviders() {
    setLoading(true)
    try {
      const data = await getLLMProviders()
      setProviders(data)
    } catch (e) {
      /* ignore */
    }
    setLoading(false)
  }

  const handleAdd = async (formData) => {
    const payload = {
      name: formData.name,
      provider_type: formData.provider_type,
      api_key: formData.api_key,
      base_url: formData.base_url,
      model_name: formData.model_name,
      task_assignment: formData.task_assignment,
      cost_limit_daily_cents: formData.cost_limit_daily_cents
        ? Math.max(0, Math.round(parseFloat(formData.cost_limit_daily_cents) * 100))
        : undefined,
      config: formData.config || {},
    }
    await createLLMProvider(payload)
    await loadProviders()
  }

  const runTestAll = async () => {
    setAllTestRunning(true)
    const results = []
    for (const p of providers) {
      try {
        const t0 = Date.now()
        const r = await testLLMProvider(p.id)
        results.push({
          providerId: p.id,
          name: p.name,
          status: r.status,
          latency_ms: r.latency_ms ?? Date.now() - t0,
          error: r.error || null,
          http_status: r.http_status || null,
        })
      } catch (e) {
        results.push({ providerId: p.id, name: p.name, status: 'error', error: e.message })
      }
    }
    setAllTestResults(results)
    setAllTestRunning(false)
  }

  const handleTest = async (id) => {
    setTestingId(id)
    try {
      const result = await testLLMProvider(id)
      if (result.status === 'ok') {
        toast.success(`Verbindung OK! Latenz: ${result.latency_ms}ms`)
      } else if (result.http_status === 412) {
        toast.warning(
          `Budget erschoepft! ${result.error} Bitte auf https://requesty.ai einloggen und Guthaben aufladen.`
        )
      } else {
        toast.error(`Test fehlgeschlagen: ${result.error}`)
      }
      await loadProviders()
    } catch (e) {
      toast.error('Test-Fehler: ' + e.message)
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

  const handleUpdateModel = async (id, modelName) => {
    await updateLLMProvider(id, { model_name: modelName })
    await loadProviders()
  }

  const handleResetCost = async (id) => {
    await resetLLMProviderCost(id)
    await loadProviders()
  }

  const handleUpdate = async (id, payload) => {
    await updateLLMProvider(id, payload)
    await loadProviders()
  }

  const handleToggleActive = async (provider) => {
    await updateLLMProvider(provider.id, { is_active: !provider.is_active })
    await loadProviders()
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
        <div className="flex items-center gap-2">
          {providers.length > 0 && (
            <button
              onClick={runTestAll}
              disabled={allTestRunning}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg disabled:opacity-50"
              title="Test aller konfigurierten Provider mit minimalem Probe-Call"
            >
              {allTestRunning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FlaskConical className="w-3.5 h-3.5" />
              )}
              Alle testen
            </button>
          )}
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800"
          >
            <Plus className="w-3.5 h-3.5" /> Provider
          </button>
        </div>
      </div>

      {/* #124: Multi-Provider-Test Result Tabelle */}
      {allTestResults && (
        <div className="mb-4 bg-white rounded-xl border border-surface-border p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-ink">Test-Ergebnisse aller Provider</h3>
            <button
              onClick={() => setAllTestResults(null)}
              className="text-[11px] text-ink-muted hover:text-ink"
            >
              Schließen
            </button>
          </div>
          <table className="w-full text-xs">
            <thead className="text-[10px] text-ink-muted uppercase tracking-wide">
              <tr>
                <th className="text-left py-1">Provider</th>
                <th className="text-right py-1">Status</th>
                <th className="text-right py-1">Latenz</th>
                <th className="text-left py-1 pl-3">Detail</th>
              </tr>
            </thead>
            <tbody>
              {allTestResults.map((r) => (
                <tr key={r.providerId} className="border-t border-gray-100">
                  <td className="py-1.5 font-medium text-ink">{r.name}</td>
                  <td className="py-1.5 text-right">
                    {r.status === 'ok' ? (
                      <span className="text-emerald-700 inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> ok
                      </span>
                    ) : (
                      <span className="text-red-700 inline-flex items-center gap-1">
                        <XCircle className="w-3 h-3" /> {r.http_status || 'fail'}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 text-right text-ink-muted">
                    {r.latency_ms ? `${r.latency_ms}ms` : '—'}
                  </td>
                  <td
                    className="py-1.5 pl-3 text-ink-muted truncate max-w-[300px]"
                    title={r.error || ''}
                  >
                    {r.status === 'ok' ? '—' : r.error || 'unbekannt'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {providers.length === 0 ? (
        <div className="text-center py-8 bg-gray-50 rounded-xl">
          <Cpu className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-ink-light">Kein KI-Provider konfiguriert.</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="mt-2 text-xs text-primary-600 font-medium"
          >
            Jetzt hinzufuegen
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {providers.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              onTest={handleTest}
              onDelete={handleDelete}
              onToggleDefault={handleToggleDefault}
              onUpdateLimit={handleUpdateLimit}
              onUpdateModel={handleUpdateModel}
              onResetCost={handleResetCost}
              onUpdate={handleUpdate}
              onToggleActive={handleToggleActive}
              testing={testingId === p.id}
            />
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

      {/* Live Routing Override */}
      {providers.length > 0 && <RoutingOverridePanel />}

      {/* Add Provider Modal */}
      {showAddModal && (
        <AddProviderModal onClose={() => setShowAddModal(false)} onSave={handleAdd} />
      )}
    </div>
  )
}
