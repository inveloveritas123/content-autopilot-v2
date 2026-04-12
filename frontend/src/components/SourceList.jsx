import { useState } from 'react'
import { Radio, Rss, Mic, Globe, Plus, RefreshCw, Trash2, Power, Clock, Loader2, Search } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { getSources, createSource, updateSource, deleteSource, checkSource, searchChannels } from '../api'

const SOURCE_TYPES = [
  { key: '', label: 'Alle', icon: Radio },
  { key: 'youtube', label: 'YouTube', icon: Radio },
  { key: 'rss', label: 'RSS-Feeds', icon: Rss },
  { key: 'podcast', label: 'Podcasts', icon: Mic },
  { key: 'web', label: 'Webseiten', icon: Globe },
]

const INTERVAL_OPTIONS = [
  { value: 15, label: '15 Min' },
  { value: 30, label: '30 Min' },
  { value: 60, label: '1 Std' },
  { value: 120, label: '2 Std' },
  { value: 240, label: '4 Std' },
  { value: 720, label: '12 Std' },
  { value: 1440, label: '24 Std' },
]

const DEFAULT_INTERVALS = { youtube: 120, rss: 60, podcast: 360, web: 240 }

function relativeTime(dateStr) {
  if (!dateStr) return 'Nie'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Gerade eben'
  if (mins < 60) return `vor ${mins} Min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `vor ${hours} Std`
  return `vor ${Math.floor(hours / 24)} Tagen`
}

function SourceCard({ source, onCheck, onToggle, onDelete, onUpdateInterval, checking }) {
  const typeInfo = SOURCE_TYPES.find(t => t.key === source.type) || SOURCE_TYPES[0]
  const Icon = typeInfo.icon

  return (
    <div className={`bg-white rounded-xl border transition-colors ${source.is_active ? 'border-surface-border hover:border-primary-300' : 'border-gray-200 opacity-60'}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${source.is_active ? 'bg-primary-50' : 'bg-gray-100'}`}>
              <Icon className={`w-4.5 h-4.5 ${source.is_active ? 'text-primary-600' : 'text-gray-400'}`} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-ink truncate">{source.name}</h3>
              <p className="text-xs text-ink-muted truncate mt-0.5">{source.url || source.channel_id || '—'}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button onClick={() => onCheck(source.id)} disabled={checking} className="p-1.5 rounded-md hover:bg-gray-100 text-ink-muted hover:text-primary-600 transition-colors" title="Jetzt pruefen">
              {checking ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            </button>
            <button onClick={() => onToggle(source)} className="p-1.5 rounded-md hover:bg-gray-100 transition-colors" title={source.is_active ? 'Deaktivieren' : 'Aktivieren'}>
              <Power className={`w-4 h-4 ${source.is_active ? 'text-emerald-500' : 'text-gray-400'}`} />
            </button>
            <button onClick={() => onDelete(source.id)} className="p-1.5 rounded-md hover:bg-red-50 text-ink-muted hover:text-red-500 transition-colors" title="Loeschen">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-100">
          <div className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Clock className="w-3 h-3" />
            {relativeTime(source.last_checked_at)}
          </div>
          <select
            value={source.polling_interval_minutes || DEFAULT_INTERVALS[source.type] || 60}
            onChange={e => onUpdateInterval(source.id, parseInt(e.target.value))}
            className="text-xs border border-gray-200 rounded-md px-2 py-1 text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            {INTERVAL_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <span className={`ml-auto inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${source.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
            {source.is_active ? 'Aktiv' : 'Pausiert'}
          </span>
        </div>
      </div>
    </div>
  )
}

function AddSourceForm({ type, onAdd, onCancel }) {
  const [form, setForm] = useState({
    name: '', type: type || 'youtube', url: '', channel_id: '', language: 'de',
    auto_process: false, polling_interval_minutes: DEFAULT_INTERVALS[type] || 60,
  })
  const [saving, setSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)

  const handleSubmit = async () => {
    setSaving(true)
    try {
      await onAdd(form)
    } finally {
      setSaving(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const results = await searchChannels(searchQuery)
      setSearchResults(results)
    } catch (e) {
      alert('Suche fehlgeschlagen: ' + e.message)
    } finally {
      setSearching(false)
    }
  }

  const selectChannel = (ch) => {
    setForm({ ...form, name: ch.name, channel_id: ch.channel_id, url: ch.url })
    setSearchResults([])
  }

  return (
    <div className="bg-white rounded-xl border border-primary-200 p-5 mb-4">
      <h3 className="text-sm font-semibold text-ink mb-4">
        {type === 'youtube' ? 'YouTube-Kanal' : type === 'rss' ? 'RSS-Feed' : type === 'podcast' ? 'Podcast' : 'Webseite'} hinzufuegen
      </h3>

      {type === 'youtube' && (
        <div className="mb-4">
          <div className="flex gap-2 mb-2">
            <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="YouTube-Kanal suchen..." className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
            <button onClick={handleSearch} disabled={searching} className="px-3 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors">
              {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto mb-3">
              {searchResults.map(ch => (
                <button key={ch.channel_id} onClick={() => selectChannel(ch)} className="w-full text-left flex items-center gap-2 p-2 rounded-lg hover:bg-gray-50 text-sm">
                  {ch.thumbnail && <img src={ch.thumbnail} alt="" className="w-8 h-8 rounded-full" />}
                  <span className="font-medium truncate">{ch.name}</span>
                  <span className="text-xs text-ink-muted ml-auto">{ch.subscribers}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
          placeholder="Name" className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />

        {type === 'youtube' ? (
          <input value={form.channel_id} onChange={e => setForm({ ...form, channel_id: e.target.value })}
            placeholder="Channel-ID oder Kanal-URL" className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
        ) : (
          <input value={form.url} onChange={e => setForm({ ...form, url: e.target.value })}
            placeholder={type === 'rss' ? 'RSS-Feed URL' : type === 'podcast' ? 'Podcast-RSS URL' : 'Webseiten-URL'}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500" />
        )}

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-xs text-ink-muted">Intervall:</label>
            <select value={form.polling_interval_minutes} onChange={e => setForm({ ...form, polling_interval_minutes: parseInt(e.target.value) })}
              className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary-500">
              {INTERVAL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-ink-light">
            <input type="checkbox" checked={form.auto_process} onChange={e => setForm({ ...form, auto_process: e.target.checked })} className="rounded" />
            Auto-Verarbeitung
          </label>
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-sm text-ink-light hover:text-ink">Abbrechen</button>
          <button onClick={handleSubmit} disabled={saving || !form.name || (!form.url && !form.channel_id)}
            className="px-4 py-1.5 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors">
            {saving ? 'Speichern...' : 'Hinzufuegen'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function SourceList() {
  const { data: sources, loading, refetch } = useApi(getSources)
  const [activeTab, setActiveTab] = useState('')
  const [addingType, setAddingType] = useState(null)
  const [checkingId, setCheckingId] = useState(null)

  const filtered = activeTab
    ? (sources || []).filter(s => s.type === activeTab)
    : (sources || [])

  const counts = {}
  for (const s of (sources || [])) {
    counts[s.type] = (counts[s.type] || 0) + 1
  }

  const handleAdd = async (form) => {
    await createSource(form)
    setAddingType(null)
    refetch()
  }

  const handleCheck = async (id) => {
    setCheckingId(id)
    try { await checkSource(id) } finally { setTimeout(() => setCheckingId(null), 2000) }
  }

  const handleToggle = async (source) => {
    await updateSource(source.id, { is_active: !source.is_active })
    refetch()
  }

  const handleDelete = async (id) => {
    if (confirm('Quelle wirklich loeschen?')) {
      await deleteSource(id)
      refetch()
    }
  }

  const handleUpdateInterval = async (id, minutes) => {
    await updateSource(id, { polling_interval_minutes: minutes })
    refetch()
  }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Quellen...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Quellen</h1>
          <p className="text-sm text-ink-light mt-0.5">{(sources || []).length} Quellen, {(sources || []).filter(s => s.is_active).length} aktiv</p>
        </div>
        <div className="relative">
          <button onClick={() => setAddingType(activeTab || 'youtube')}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 transition-colors">
            <Plus className="w-4 h-4" /> Quelle hinzufuegen
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 mb-5 overflow-x-auto">
        {SOURCE_TYPES.map(t => {
          const count = t.key ? (counts[t.key] || 0) : (sources || []).length
          return (
            <button key={t.key} onClick={() => setActiveTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                activeTab === t.key ? 'bg-white text-ink shadow-sm' : 'text-ink-light hover:text-ink'
              }`}>
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
              {count > 0 && <span className="ml-1 px-1.5 py-0.5 rounded-full bg-gray-200 text-[10px]">{count}</span>}
            </button>
          )
        })}
      </div>

      {/* Add Form */}
      {addingType && (
        <AddSourceForm type={addingType} onAdd={handleAdd} onCancel={() => setAddingType(null)} />
      )}

      {/* Source Cards */}
      {filtered.length === 0 ? (
        <div className="text-center py-12">
          <Radio className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-ink-light">Keine Quellen {activeTab ? `vom Typ "${SOURCE_TYPES.find(t => t.key === activeTab)?.label}"` : ''} vorhanden.</p>
          <button onClick={() => setAddingType(activeTab || 'youtube')} className="mt-2 text-sm text-primary-600 hover:text-primary-700 font-medium">
            Jetzt hinzufuegen
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map(source => (
            <SourceCard
              key={source.id}
              source={source}
              onCheck={handleCheck}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onUpdateInterval={handleUpdateInterval}
              checking={checkingId === source.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
