import { useState, useEffect } from 'react'
import { useToast } from './ui/Toast'
import {
  Radio,
  Rss,
  Mic,
  Globe,
  Plus,
  RefreshCw,
  Trash2,
  Power,
  Clock,
  Loader2,
  Search,
  Compass,
  ExternalLink,
  Play,
  Tag,
  Archive,
  BarChart3,
  AlertTriangle,
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import {
  getSources,
  createSource,
  updateSource,
  updateSourceKeywords,
  deleteSource,
  checkSource,
  searchChannels,
  searchVideos,
  discoverSources,
  getSourceStats,
  analyzeAllSourceItems,
  archiveSourceItems,
  getSourceFunnel,
  bulkArchiveIdeas,
  getSourceItems,
} from '../api'

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

function SourceCard({
  source,
  onCheck,
  onToggle,
  onDelete,
  onUpdateInterval,
  onUpdateKeywords,
  checking,
  stats,
}) {
  const { toast } = useToast()
  const typeInfo = SOURCE_TYPES.find((t) => t.key === source.type) || SOURCE_TYPES[0]
  const Icon = typeInfo.icon
  const s = stats || {}
  const [kwEdit, setKwEdit] = useState(false)
  const [kwInput, setKwInput] = useState(source.keywords || '')
  const [kwSaving, setKwSaving] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)

  const handleAnalyzeAll = async () => {
    if (!window.confirm(`Alle transkribierten Artikel von "${source.name}" zur Analyse einreihen?`))
      return
    setAnalyzing(true)
    try {
      const r = await analyzeAllSourceItems(source.id)
      setAnalyzeResult(`${r.queued} Items eingereiht`)
      setTimeout(() => setAnalyzeResult(null), 4000)
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  const handleArchiveAll = async () => {
    if (
      !window.confirm(
        `Alle ${s.total_items} Items von "${source.name}" archivieren und Quelle deaktivieren?\n\nDie Items bleiben in der Datenbank, werden aber aus der Pipeline-Ansicht entfernt.`
      )
    )
      return
    try {
      const r = await archiveSourceItems(source.id)
      setAnalyzeResult(`${r.archived} Items archiviert`)
      setTimeout(() => {
        setAnalyzeResult(null)
        window.location.reload()
      }, 2000)
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    }
  }

  const transcribedCount = s.by_status?.transcribed || 0

  const handleSaveKeywords = async () => {
    setKwSaving(true)
    await onUpdateKeywords(source.id, kwInput.trim())
    setKwEdit(false)
    setKwSaving(false)
  }

  const kwChips = (source.keywords || '')
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean)
  const convColor =
    s.conversion_pct >= 60
      ? 'text-status-fertig-text'
      : s.conversion_pct >= 30
        ? 'text-status-aktiv-text'
        : 'text-status-fehler-text'

  // Health badge logic
  const isTop = s.total_items > 0 && s.conversion_pct === 100
  const needsKey = s.total_items > 0 && s.conversion_pct < 20 && s.transcription_failed > 5
  const isStale = s.is_stale && source.is_active
  const healthBadge = isTop ? (
    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-status-fertig-bg text-status-fertig-text">
      ★ Top
    </span>
  ) : isStale ? (
    <span
      className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-border text-ink-muted"
      title={`Letztes Item vor ${s.last_item_days_ago} Tagen`}
    >
      ● Veraltet
    </span>
  ) : needsKey ? (
    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-status-aktiv-bg text-status-aktiv-text">
      ⚠ API-Key
    </span>
  ) : null

  return (
    <div
      className={`bg-white rounded-xl border transition-colors ${source.is_active ? 'border-surface-border hover:border-primary-300' : 'border-surface-border opacity-60'}`}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${source.is_active ? 'bg-primary-50' : 'bg-surface-bg'}`}
            >
              <Icon
                className={`w-4.5 h-4.5 ${source.is_active ? 'text-primary-600' : 'text-ink-muted'}`}
              />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-semibold text-ink truncate">{source.name}</h3>
                {healthBadge}
              </div>
              <p className="text-xs text-ink-muted truncate mt-0.5">
                {source.url || source.channel_id || '—'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => onCheck(source.id)}
              disabled={checking}
              className="p-1.5 rounded-md hover:bg-surface-bg text-ink-muted hover:text-primary-600 transition-colors"
              title="Jetzt pruefen"
            >
              {checking ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
            </button>
            <button
              onClick={() => onToggle(source)}
              className="p-1.5 rounded-md hover:bg-surface-bg transition-colors"
              title={source.is_active ? 'Deaktivieren' : 'Aktivieren'}
            >
              <Power
                className={`w-4 h-4 ${source.is_active ? 'text-status-fertig-text' : 'text-ink-muted'}`}
              />
            </button>
            {s.total_items > 100 && s.content_ready === 0 && (
              <button
                onClick={handleArchiveAll}
                className="p-1.5 rounded-md hover:bg-status-aktiv-bg text-ink-muted hover:text-status-aktiv-text transition-colors"
                title={`Alle ${s.total_items} Items archivieren + Quelle deaktivieren`}
              >
                <Archive className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => onDelete(source.id)}
              className="p-1.5 rounded-md hover:bg-status-fehler-bg text-ink-muted hover:text-status-fehler-text transition-colors"
              title="Loeschen"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Quality Stats */}
        {s.total_items > 0 && (
          <div className="flex items-center gap-3 mt-3 px-1">
            <div className="text-center">
              <p className="text-sm font-bold text-ink">{s.total_items}</p>
              <p className="text-[10px] text-ink-muted">Items</p>
            </div>
            <div className="flex-1 h-1.5 bg-surface-bg rounded-full overflow-hidden mx-1">
              <div
                className="h-full bg-status-fertig-border rounded-full transition-all"
                style={{ width: `${Math.max(s.conversion_pct, 2)}%` }}
              />
            </div>
            <div className="text-center">
              <p className={`text-sm font-bold ${convColor}`}>{s.conversion_pct}%</p>
              <p className="text-[10px] text-ink-muted">→ Content</p>
            </div>
            <div className="text-center">
              <p className="text-sm font-bold text-status-fertig-text">{s.content_ready}</p>
              <p className="text-[10px] text-ink-muted">Bereit</p>
            </div>
            {s.transcription_failed > 0 && (
              <div className="text-center">
                <p className="text-sm font-bold text-status-fehler-text">
                  {s.transcription_failed}
                </p>
                <p className="text-[10px] text-ink-muted">Fehler</p>
              </div>
            )}
            {s.transcription_success_rate != null && (
              <div className="text-center ml-auto" title="Transkriptions-Erfolgsrate">
                <p
                  className={`text-sm font-bold ${s.transcription_success_rate >= 70 ? 'text-status-fertig-text' : s.transcription_success_rate >= 40 ? 'text-status-aktiv-text' : 'text-status-fehler-text'}`}
                >
                  {s.transcription_success_rate}%
                </p>
                <p className="text-[10px] text-ink-muted">Transkrip.</p>
              </div>
            )}
            {s.last_item_days_ago != null && (
              <div className="text-center" title={`Letztes Item vor ${s.last_item_days_ago} Tagen`}>
                <p
                  className={`text-sm font-bold ${s.last_item_days_ago <= 7 ? 'text-status-fertig-text' : s.last_item_days_ago <= 30 ? 'text-status-aktiv-text' : 'text-ink-muted'}`}
                >
                  {s.last_item_days_ago}d
                </p>
                <p className="text-[10px] text-ink-muted">Aktualität</p>
              </div>
            )}
          </div>
        )}

        {/* Keyword Filter */}
        <div className="mt-3 pt-2 border-t border-surface-border">
          {kwEdit ? (
            <div className="flex items-center gap-1.5">
              <Tag className="w-3 h-3 text-accent-600 shrink-0" />
              <input
                value={kwInput}
                onChange={(e) => setKwInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveKeywords()
                  if (e.key === 'Escape') setKwEdit(false)
                }}
                placeholder="KI, Startup, LinkedIn (kommagetrennt)"
                className="flex-1 text-xs border border-accent-200 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-accent-400"
                autoFocus
              />
              <button
                onClick={handleSaveKeywords}
                disabled={kwSaving}
                className="text-xs px-2 py-1 bg-accent-700 text-white rounded-md hover:bg-accent-800 disabled:opacity-50 shrink-0"
              >
                {kwSaving ? '...' : 'OK'}
              </button>
              <button
                onClick={() => setKwEdit(false)}
                className="text-xs text-ink-muted hover:text-ink-light shrink-0"
              >
                ✕
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Tag className="w-3 h-3 text-ink-muted shrink-0" />
              {kwChips.length > 0 ? (
                kwChips.map((kw) => (
                  <span
                    key={kw}
                    className="px-1.5 py-0.5 rounded bg-accent-50 text-accent-700 text-[10px] font-medium"
                  >
                    {kw}
                  </span>
                ))
              ) : (
                <span className="text-[10px] text-ink-muted">Kein Keyword-Filter</span>
              )}
              <button
                onClick={() => {
                  setKwInput(source.keywords || '')
                  setKwEdit(true)
                }}
                className="ml-auto text-[10px] text-ink-muted hover:text-accent-600 shrink-0"
              >
                {kwChips.length > 0 ? 'Bearbeiten' : '+ Filter setzen'}
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-surface-border">
          <div className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Clock className="w-3 h-3" />
            {relativeTime(source.last_checked_at)}
          </div>
          <select
            value={source.polling_interval_minutes || DEFAULT_INTERVALS[source.type] || 60}
            onChange={(e) => onUpdateInterval(source.id, parseInt(e.target.value))}
            className="text-xs border border-surface-border rounded-md px-2 py-1 text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            {INTERVAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {transcribedCount > 0 && (
            <button
              onClick={handleAnalyzeAll}
              disabled={analyzing}
              title={`${transcribedCount} transkribierte Artikel analysieren`}
              className="text-[10px] px-2 py-0.5 bg-status-aktiv-bg hover:bg-status-aktiv-border text-status-aktiv-text border border-status-aktiv-border rounded-md font-medium transition-colors disabled:opacity-50"
            >
              {analyzing ? '...' : analyzeResult || `Analyse (${transcribedCount})`}
            </button>
          )}
          <span
            className={`ml-auto inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${source.is_active ? 'bg-status-fertig-bg text-status-fertig-text' : 'bg-surface-border text-ink-muted'}`}
          >
            {source.is_active ? 'Aktiv' : 'Pausiert'}
          </span>
        </div>
      </div>
    </div>
  )
}

function AddSourceForm({ type, onAdd, onCancel }) {
  const { toast } = useToast()
  const [form, setForm] = useState({
    name: '',
    type: type || 'youtube',
    url: '',
    channel_id: '',
    language: 'de',
    auto_process: false,
    polling_interval_minutes: DEFAULT_INTERVALS[type] || 60,
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
      toast.error('Suche fehlgeschlagen: ' + e.message)
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
        {type === 'youtube'
          ? 'YouTube-Kanal'
          : type === 'rss'
            ? 'RSS-Feed'
            : type === 'podcast'
              ? 'Podcast'
              : 'Webseite'}{' '}
        hinzufuegen
      </h3>

      {type === 'youtube' && (
        <div className="mb-4">
          <div className="flex gap-2 mb-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="YouTube-Kanal suchen..."
              className="flex-1 text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button
              onClick={handleSearch}
              disabled={searching}
              className="px-3 py-2 bg-surface-bg rounded-lg hover:bg-surface-border transition-colors"
            >
              {searching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto mb-3">
              {searchResults.map((ch) => (
                <button
                  key={ch.channel_id}
                  onClick={() => selectChannel(ch)}
                  className="w-full text-left flex items-center gap-2 p-2 rounded-lg hover:bg-surface-bg text-sm"
                >
                  {ch.thumbnail && (
                    <img src={ch.thumbnail} alt="" className="w-8 h-8 rounded-full" />
                  )}
                  <span className="font-medium truncate">{ch.name}</span>
                  <span className="text-xs text-ink-muted ml-auto">{ch.subscribers}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Name"
          className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />

        {type === 'youtube' ? (
          <input
            value={form.channel_id}
            onChange={(e) => setForm({ ...form, channel_id: e.target.value })}
            placeholder="Channel-ID oder Kanal-URL"
            className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        ) : (
          <input
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            placeholder={
              type === 'rss'
                ? 'RSS-Feed URL'
                : type === 'podcast'
                  ? 'Podcast-RSS URL'
                  : 'Webseiten-URL'
            }
            className="w-full text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        )}

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-xs text-ink-muted">Intervall:</label>
            <select
              value={form.polling_interval_minutes}
              onChange={(e) =>
                setForm({ ...form, polling_interval_minutes: parseInt(e.target.value) })
              }
              className="text-sm border border-surface-border rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {INTERVAL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-ink-light">
            <input
              type="checkbox"
              checked={form.auto_process}
              onChange={(e) => setForm({ ...form, auto_process: e.target.checked })}
              className="rounded"
            />
            Auto-Verarbeitung
          </label>
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-sm text-ink-light hover:text-ink">
            Abbrechen
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !form.name || (!form.url && !form.channel_id)}
            className="px-4 py-1.5 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Speichern...' : 'Hinzufuegen'}
          </button>
        </div>
      </div>
    </div>
  )
}

function YouTubeVideoSearch() {
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const data = await searchVideos(query)
      setResults(data)
      setSearched(true)
    } catch (e) {
      toast.error('Suche fehlgeschlagen: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mb-5 bg-white rounded-xl border border-surface-border p-4">
      <h3 className="text-xs font-semibold text-ink mb-3 flex items-center gap-1.5">
        <Play className="w-3.5 h-3.5 text-primary-600" />
        YouTube-Video suchen
      </h3>
      <div className="flex gap-2 mb-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="z.B. KI Handwerk Digitalisierung..."
          className="flex-1 text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium bg-surface-bg rounded-lg hover:bg-surface-border disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        </button>
      </div>

      {results.length > 0 && (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {results.map((v, i) => (
            <a
              key={v.video_id || i}
              href={v.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-surface-bg transition-colors group"
            >
              {v.thumbnail ? (
                <img
                  src={v.thumbnail}
                  alt=""
                  className="w-20 h-12 rounded object-cover shrink-0 bg-surface-bg"
                />
              ) : (
                <div className="w-20 h-12 rounded bg-surface-bg flex items-center justify-center shrink-0">
                  <Play className="w-5 h-5 text-ink-muted" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-ink line-clamp-2 group-hover:text-primary-700">
                  {v.title}
                </p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  {v.channel_name && (
                    <span className="text-[10px] text-ink-muted">{v.channel_name}</span>
                  )}
                  {v.duration && <span className="text-[10px] text-ink-muted">{v.duration}</span>}
                  {v.view_count && (
                    <span className="text-[10px] text-ink-muted">{v.view_count}</span>
                  )}
                  {v.published && <span className="text-[10px] text-ink-muted">{v.published}</span>}
                </div>
              </div>
              <ExternalLink className="w-3.5 h-3.5 text-ink-muted group-hover:text-primary-500 shrink-0 mt-0.5" />
            </a>
          ))}
        </div>
      )}

      {searched && results.length === 0 && !loading && (
        <p className="text-xs text-ink-muted text-center py-4">Keine Videos gefunden.</p>
      )}
    </div>
  )
}

function DiscoverCard({ item, onAdd, adding }) {
  return (
    <div className="bg-white rounded-xl border border-surface-border hover:border-primary-300 transition-colors p-4 flex items-start gap-3">
      {item.thumbnail ? (
        <img
          src={item.thumbnail}
          alt=""
          className="w-11 h-11 rounded-lg object-cover shrink-0"
          onError={(e) => {
            e.target.style.display = 'none'
          }}
        />
      ) : (
        <div className="w-11 h-11 rounded-lg bg-surface-bg flex items-center justify-center shrink-0">
          {item.source_type === 'podcast' ? (
            <Mic className="w-5 h-5 text-ink-muted" />
          ) : item.source_type === 'website' ? (
            <Globe className="w-5 h-5 text-ink-muted" />
          ) : (
            <Radio className="w-5 h-5 text-ink-muted" />
          )}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-ink truncate">{item.name}</p>
        {item.description && (
          <p className="text-xs text-ink-muted mt-0.5 line-clamp-2">{item.description}</p>
        )}
        <div className="flex items-center gap-2 mt-1">
          {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary-600 hover:underline flex items-center gap-0.5 truncate max-w-[180px]"
            >
              <ExternalLink className="w-3 h-3 shrink-0" />
              <span className="truncate">{item.url.replace(/^https?:\/\//, '')}</span>
            </a>
          )}
          {item.episode_count > 0 && (
            <span className="text-xs text-ink-muted">{item.episode_count} Eps.</span>
          )}
          {item.feed_url && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-status-fertig-bg text-status-fertig-text">
              RSS
            </span>
          )}
          {item.genre && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-surface-bg text-ink-light">
              {item.genre}
            </span>
          )}
        </div>
      </div>
      <div className="shrink-0 mt-0.5">
        {item.already_added ? (
          <span className="inline-flex items-center px-2 py-1 rounded-lg text-xs font-medium bg-status-fertig-bg text-status-fertig-text">
            Hinzugefuegt
          </span>
        ) : (
          <button
            onClick={() => onAdd(item)}
            disabled={adding}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors"
          >
            {adding ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
            Add
          </button>
        )}
      </div>
    </div>
  )
}

function DiscoverTab({ sources }) {
  const { toast } = useToast()
  const [topics, setTopics] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeType, setActiveType] = useState('youtube')
  const [addingKey, setAddingKey] = useState(null)

  const existingChannelIds = new Set((sources || []).map((s) => s.channel_id).filter(Boolean))
  const existingUrls = new Set((sources || []).map((s) => s.url).filter(Boolean))

  const handleDiscover = async () => {
    if (!topics.trim()) return
    setLoading(true)
    setResults(null)
    try {
      const data = await discoverSources(topics)
      setResults(data)
      setActiveType('youtube')
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async (item) => {
    const key = item.url || item.channel_id
    setAddingKey(key)
    try {
      const data = { name: item.name, language: 'de', auto_process: false }
      if (item.source_type === 'podcast') {
        data.type = 'podcast'
        data.url = item.feed_url || item.url
      } else if (item.source_type === 'website') {
        data.type = 'web'
        data.url = item.url
      } else {
        data.type = 'youtube'
        data.channel_id = item.channel_id
        data.url = item.url
      }
      await createSource(data)
      setResults((prev) => {
        if (!prev) return prev
        const listKey =
          item.source_type === 'podcast'
            ? 'podcasts'
            : item.source_type === 'website'
              ? 'websites'
              : 'youtube'
        return {
          ...prev,
          [listKey]: prev[listKey].map((i) =>
            i.channel_id === item.channel_id && i.url === item.url
              ? { ...i, already_added: true }
              : i
          ),
        }
      })
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    } finally {
      setAddingKey(null)
    }
  }

  const tabs = results
    ? [
        { key: 'youtube', label: 'YouTube', count: results.youtube.length },
        { key: 'podcasts', label: 'Podcasts', count: results.podcasts.length },
        { key: 'websites', label: 'Webseiten', count: results.websites.length },
      ]
    : []

  const currentItems = results
    ? activeType === 'youtube'
      ? results.youtube
      : activeType === 'podcasts'
        ? results.podcasts
        : results.websites
    : []

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-surface-border p-5">
        <p className="text-sm text-ink-light mb-3">
          Gib Themen ein — das System sucht passende YouTube-Kanaele, Podcasts und schlaegt
          Webseiten vor.
        </p>
        <div className="flex gap-2">
          <input
            value={topics}
            onChange={(e) => setTopics(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDiscover()}
            placeholder="z.B. KI, LinkedIn Marketing, Handwerk, Digitalisierung KMU"
            className="flex-1 text-sm border border-surface-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <button
            onClick={handleDiscover}
            disabled={loading || !topics.trim()}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Compass className="w-4 h-4" />
            )}
            {loading ? 'Suche...' : 'Entdecken'}
          </button>
        </div>
        {results && (
          <div className="flex gap-2 mt-3 flex-wrap">
            {results.topics.map((t) => (
              <span
                key={t}
                className="px-2 py-0.5 bg-primary-50 text-primary-700 rounded text-xs font-medium"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      {loading && (
        <div className="text-center py-16">
          <Loader2 className="w-8 h-8 text-primary-600 animate-spin mx-auto mb-3" />
          <p className="text-sm text-ink-muted">
            Suche YouTube, Podcasts, generiere Webseiten-Vorschlaege...
          </p>
        </div>
      )}

      {results && !loading && (
        <>
          <div className="flex gap-1 bg-surface-bg rounded-lg p-1">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveType(t.key)}
                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activeType === t.key
                    ? 'bg-white text-ink shadow-sm'
                    : 'text-ink-light hover:text-ink'
                }`}
              >
                {t.label}
                {t.count > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full bg-surface-border text-[10px]">
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {currentItems.length === 0 ? (
            <div className="text-center py-12 text-ink-muted">
              <p className="text-sm">Keine Ergebnisse fuer diesen Typ.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {currentItems.map((item, i) => (
                <DiscoverCard
                  key={item.channel_id || item.url || i}
                  item={item}
                  onAdd={handleAdd}
                  adding={addingKey === (item.url || item.channel_id)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {!results && !loading && (
        <div className="text-center py-16">
          <Compass className="w-12 h-12 text-ink-muted mx-auto mb-3" />
          <p className="text-sm text-ink-light">Themen eingeben und auf "Entdecken" klicken</p>
        </div>
      )}
    </div>
  )
}

// Pipeline-Status → Tier-2-Status-Token. analyzing/analyzed/generating teilen sich
// status-neu (alle "in Bearbeitung, noch nicht fertig") — das 5-Werte-Vokabular kennt
// keine feinere Zwischenstufe; die Badges bleiben per Label-Text unterscheidbar.
const STATUS_COLORS = {
  new: 'bg-surface-border text-ink-light',
  transcribed: 'bg-status-aktiv-bg text-status-aktiv-text',
  analyzing: 'bg-status-neu-bg text-status-neu-text',
  analyzed: 'bg-status-neu-bg text-status-neu-text',
  generating: 'bg-status-neu-bg text-status-neu-text',
  content_ready: 'bg-status-fertig-bg text-status-fertig-text',
  transcription_failed: 'bg-status-fehler-bg text-status-fehler-text',
}

function SourceItemsModal({ sourceId, sourceName, onClose }) {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const LIMIT = 15

  useEffect(() => {
    if (!sourceId) return
    setLoading(true)
    getSourceItems(sourceId, { limit: LIMIT, offset, status: statusFilter || undefined })
      .then((d) => {
        setItems(d.items || [])
        setTotal(d.total || 0)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sourceId, offset, statusFilter])

  const pages = Math.ceil(total / LIMIT)
  const currentPage = Math.floor(offset / LIMIT) + 1

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border">
          <div>
            <h3 className="font-semibold text-ink text-sm">{sourceName}</h3>
            <p className="text-xs text-ink-muted mt-0.5">{total} Items in der Pipeline</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setOffset(0)
              }}
              className="text-xs border border-surface-border rounded-lg px-2 py-1 text-ink-muted bg-white"
            >
              <option value="">Alle Status</option>
              <option value="transcribed">Warten auf Analyse</option>
              <option value="analyzing">In Analyse</option>
              <option value="analyzed">Analysiert</option>
              <option value="content_ready">Fertig</option>
              <option value="transcription_failed">Fehler</option>
            </select>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-surface-bg text-ink-muted">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-ink-muted text-sm">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Lade Items…
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-ink-muted text-sm">Keine Items gefunden</div>
          ) : (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface-bg border-b border-surface-border">
                <tr>
                  <th className="text-left px-5 py-2.5 font-medium text-ink-muted">Titel</th>
                  <th className="px-3 py-2.5 font-medium text-ink-muted text-right">Status</th>
                  <th className="px-4 py-2.5 font-medium text-ink-muted text-right">Erstellt</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-surface-border hover:bg-surface-bg/60">
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-1.5">
                        {!item.has_transcript && (
                          <span
                            className="text-[9px] bg-status-aktiv-bg text-status-aktiv-text rounded px-1 py-0.5 shrink-0"
                            title="Kein Transkript — Titel wird als Fallback verwendet"
                          >
                            RSS
                          </span>
                        )}
                        <span className="truncate max-w-xs text-ink" title={item.title}>
                          {item.title}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-medium ${STATUS_COLORS[item.status] || 'bg-surface-bg text-ink-light'}`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-ink-muted whitespace-nowrap">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleDateString('de-DE', {
                            day: '2-digit',
                            month: '2-digit',
                          })
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {pages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-surface-border">
            <span className="text-xs text-ink-muted">
              Seite {currentPage} / {pages}
            </span>
            <div className="flex gap-1">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                className="px-2.5 py-1 text-xs border border-surface-border rounded-lg disabled:opacity-40 hover:bg-surface-bg"
              >
                ← Zurück
              </button>
              <button
                disabled={offset + LIMIT >= total}
                onClick={() => setOffset(offset + LIMIT)}
                className="px-2.5 py-1 text-xs border border-surface-border rounded-lg disabled:opacity-40 hover:bg-surface-bg"
              >
                Weiter →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// SHK-related keywords to detect relevant sources
const SHK_KEYWORDS = [
  'shk',
  'handwerk',
  'haustechnik',
  'sanitär',
  'heizung',
  'klimatechnik',
  'gebäudetechnik',
  'profi',
  'fachmagazin',
]
function isSHKSource(name) {
  const lower = (name || '').toLowerCase()
  return SHK_KEYWORDS.some((kw) => lower.includes(kw))
}

function FunnelTab({
  funnelData,
  onArchiveIdeas,
  onCheckSource,
  onAnalyzeSource,
  checkingSourceId,
  analyzingSourceId,
  batchChecking,
  onBatchCheckSHK,
  onPreviewItems,
}) {
  const { toast } = useToast()
  const [archiving, setArchiving] = useState(null)
  const [archiveMsg, setArchiveMsg] = useState(null)

  if (!funnelData || funnelData.length === 0) {
    return (
      <div className="text-center py-8 text-ink-muted text-sm">Keine Funnel-Daten verfügbar</div>
    )
  }

  const relevant = funnelData.filter((s) => isSHKSource(s.source_name))
  const irrelevant = funnelData.filter(
    (s) => !isSHKSource(s.source_name) && (s.items > 0 || s.ideas > 0)
  )
  const empty = funnelData.filter(
    (s) => !isSHKSource(s.source_name) && s.items === 0 && s.ideas === 0
  )

  const maxItems = Math.max(...funnelData.map((s) => s.items), 1)

  async function handleArchiveIdeas(src) {
    if (!window.confirm(`Alle ${src.ideas} Ideen von "${src.source_name}" archivieren?`)) return
    setArchiving(src.source_id)
    try {
      const r = await bulkArchiveIdeas({ source_id: src.source_id })
      setArchiveMsg(`✓ ${r.archived} Ideen von "${src.source_name}" archiviert`)
      setTimeout(() => {
        setArchiveMsg(null)
        if (onArchiveIdeas) onArchiveIdeas()
      }, 4000)
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    }
    setArchiving(null)
  }

  function FunnelRow({ src, highlight }) {
    const barW = src.items > 0 ? Math.max(4, Math.round((src.items / maxItems) * 100)) : 0
    const hasIdeas = src.ideas > 0
    const hasItems = src.items > 0
    const stuck = hasItems && !hasIdeas
    const isChecking = checkingSourceId === src.source_id
    const isAnalyzing = analyzingSourceId === src.source_id
    return (
      <tr
        className={`border-b border-surface-border last:border-0 ${highlight ? 'bg-status-fertig-bg/40' : 'hover:bg-surface-bg/60'}`}
      >
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-1.5">
            {stuck && !highlight && (
              <AlertTriangle className="w-3 h-3 text-status-aktiv-text shrink-0" />
            )}
            {highlight && (
              <span className="text-status-fertig-text text-[10px] font-bold uppercase tracking-wide">
                SHK
              </span>
            )}
            <span
              className="text-xs font-medium text-ink truncate max-w-[180px]"
              title={src.source_name}
            >
              {src.source_name}
            </span>
          </div>
        </td>
        <td className="px-3 py-2.5">
          <div className="flex items-center gap-2">
            <div className="w-20 h-1.5 bg-surface-border rounded-full overflow-hidden">
              <div className="h-full bg-primary-400 rounded-full" style={{ width: `${barW}%` }} />
            </div>
            <span className="text-xs font-mono text-ink-muted">
              {src.items.toLocaleString('de')}
            </span>
          </div>
        </td>
        <td className="px-3 py-2.5 text-right">
          <span
            className={`text-xs font-mono ${hasIdeas ? 'text-status-neu-text font-semibold' : stuck ? 'text-status-aktiv-text' : 'text-ink-muted'}`}
          >
            {src.ideas.toLocaleString('de')}
          </span>
        </td>
        <td className="px-3 py-2.5 text-right">
          {/* bewusst behalten: eigene Akzentfarbe fuer die Posts-Spalte, damit sie sich
              in der Funnel-Tabelle optisch von Ideen (status-neu) und Approved (status-fertig)
              unterscheidet, obwohl "Posts" selbst kein Status ist */}
          <span
            className={`text-xs font-mono ${src.posts > 0 ? 'text-accent-700' : 'text-ink-muted'}`}
          >
            {src.posts.toLocaleString('de')}
          </span>
        </td>
        <td className="px-3 py-2.5 text-right">
          <span
            className={`text-xs font-mono ${src.approved > 0 ? 'text-status-fertig-text font-semibold' : 'text-ink-muted'}`}
          >
            {src.approved.toLocaleString('de')}
          </span>
        </td>
        <td className="px-3 py-2.5 text-right">
          <div className="flex items-center justify-end gap-1.5 flex-wrap">
            {onCheckSource && highlight && (
              <button
                onClick={() => onCheckSource(src.source_id)}
                disabled={isChecking || batchChecking}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] font-medium text-status-fertig-text bg-status-fertig-bg border border-status-fertig-border rounded hover:bg-status-fertig-border transition-colors disabled:opacity-50"
                title="Neue Artikel dieser Quelle abrufen"
              >
                {isChecking ? (
                  <Loader2 className="w-2.5 h-2.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-2.5 h-2.5" />
                )}
                Prüfen
              </button>
            )}
            {onAnalyzeSource && stuck && (
              <button
                onClick={() => onAnalyzeSource(src.source_id)}
                disabled={isAnalyzing}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] font-medium text-status-neu-text bg-status-neu-bg border border-status-neu-border rounded hover:bg-status-neu-border transition-colors disabled:opacity-50"
                title="Items dieser Quelle analysieren und Ideen generieren (benötigt LLM-Budget)"
              >
                {isAnalyzing ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : '🧠'}
                Analysieren
              </button>
            )}
            {hasItems && onPreviewItems && (
              <button
                onClick={() => onPreviewItems(src.source_id, src.source_name)}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] font-medium text-ink-light bg-surface-bg border border-surface-border rounded hover:bg-surface-bg transition-colors"
                title="Items dieser Quelle in der Pipeline ansehen"
              >
                📋 Items
              </button>
            )}
            {hasIdeas && (
              <button
                onClick={() => handleArchiveIdeas(src)}
                disabled={archiving === src.source_id}
                className="px-1.5 py-0.5 text-[9px] text-status-fehler-text bg-status-fehler-bg border border-status-fehler-border rounded hover:bg-status-fehler-border transition-colors disabled:opacity-50"
              >
                {archiving === src.source_id ? '...' : 'Ideen löschen'}
              </button>
            )}
            {stuck && !onAnalyzeSource && (
              <span className="text-[10px] text-status-aktiv-text font-medium">Analyse nötig</span>
            )}
          </div>
        </td>
      </tr>
    )
  }

  return (
    <div>
      {archiveMsg && (
        <div className="mb-3 p-2.5 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-xs text-status-fertig-text font-medium">
          {archiveMsg}
        </div>
      )}

      {/* SHK sources — highlight as relevant */}
      {relevant.length > 0 && (
        <div className="mb-4 rounded-xl border border-status-fertig-border bg-status-fertig-bg/30 overflow-hidden">
          <div className="px-4 py-2 bg-status-fertig-bg border-b border-status-fertig-border flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-status-fertig-text">
                Relevante SHK/Handwerk-Quellen
              </span>
              <span className="ml-2 text-[10px] text-status-fertig-text">
                — diese sollten aktiv Ideen produzieren
              </span>
            </div>
            <div className="flex items-center gap-2">
              {onBatchCheckSHK && (
                <button
                  onClick={onBatchCheckSHK}
                  disabled={batchChecking}
                  className="flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold text-status-fertig-text bg-white border border-status-fertig-border rounded-lg hover:bg-status-fertig-bg disabled:opacity-50 transition-colors"
                  title="Aktuelle Artikel von allen SHK-Quellen abrufen"
                >
                  {batchChecking ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  {batchChecking ? 'Prüfe...' : 'Alle SHK abrufen'}
                </button>
              )}
            </div>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-status-fertig-border bg-status-fertig-bg/50">
                <th className="text-left px-4 py-1.5 font-medium text-status-fertig-text">
                  Quelle
                </th>
                <th className="text-left px-3 py-1.5 font-medium text-status-fertig-text">
                  Items
                </th>
                <th className="text-right px-3 py-1.5 font-medium text-status-fertig-text">
                  Ideen
                </th>
                <th className="text-right px-3 py-1.5 font-medium text-status-fertig-text">
                  Posts
                </th>
                <th className="text-right px-3 py-1.5 font-medium text-status-fertig-text">
                  Approved
                </th>
                <th className="py-1.5 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {relevant.map((src) => (
                <FunnelRow key={src.source_id} src={src} highlight={true} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Other active sources */}
      {irrelevant.length > 0 && (
        <div className="rounded-xl border border-surface-border bg-white overflow-hidden">
          <div className="px-4 py-2 bg-surface-bg border-b border-surface-border">
            <span className="text-xs font-semibold text-ink-light">Andere Quellen</span>
            <span className="ml-2 text-[10px] text-ink-light">
              — prüfe ob relevant für deine Nische
            </span>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border bg-surface-bg/50">
                <th className="text-left px-4 py-1.5 font-medium text-ink-muted">Quelle</th>
                <th className="text-left px-3 py-1.5 font-medium text-ink-muted">Items</th>
                <th className="text-right px-3 py-1.5 font-medium text-ink-muted">Ideen</th>
                <th className="text-right px-3 py-1.5 font-medium text-ink-muted">Posts</th>
                <th className="text-right px-3 py-1.5 font-medium text-ink-muted">Approved</th>
                <th className="py-1.5 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {irrelevant.map((src) => (
                <FunnelRow key={src.source_id} src={src} highlight={false} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function SourceList() {
  const { toast } = useToast()
  const { data: sources, loading, refetch } = useApi(getSources)
  const [mainTab, setMainTab] = useState('sources')
  const [activeTypeTab, setActiveTypeTab] = useState('')
  const [addingType, setAddingType] = useState(null)
  const [checkingId, setCheckingId] = useState(null)
  const [sourceStats, setSourceStats] = useState({})
  const [funnelData, setFunnelData] = useState(null)
  const [funnelCheckingId, setFunnelCheckingId] = useState(null)
  const [funnelAnalyzingId, setFunnelAnalyzingId] = useState(null)
  const [batchChecking, setBatchChecking] = useState(false)
  const [funnelMsg, setFunnelMsg] = useState(null)
  const [previewSource, setPreviewSource] = useState(null) // { id, name }

  useEffect(() => {
    getSourceStats()
      .then((s) => setSourceStats(s || {}))
      .catch(() => {})
    getSourceFunnel()
      .then((d) => setFunnelData(Array.isArray(d) ? d : null))
      .catch(() => {})
  }, [])

  const filtered = activeTypeTab
    ? (sources || []).filter((s) => s.type === activeTypeTab)
    : sources || []

  const counts = {}
  for (const s of sources || []) {
    counts[s.type] = (counts[s.type] || 0) + 1
  }

  const handleAdd = async (form) => {
    await createSource(form)
    setAddingType(null)
    refetch()
  }

  const handleCheck = async (id) => {
    setCheckingId(id)
    try {
      await checkSource(id)
    } finally {
      setTimeout(() => setCheckingId(null), 2000)
    }
  }

  const handleFunnelCheck = async (id) => {
    setFunnelCheckingId(id)
    try {
      await checkSource(id)
      setFunnelMsg('✓ Abruf gestartet — neue Artikel werden im Hintergrund geladen')
      setTimeout(() => setFunnelMsg(null), 4000)
    } catch (e) {
      setFunnelMsg('Fehler: ' + e.message)
    }
    setTimeout(() => setFunnelCheckingId(null), 2000)
  }

  const handleBatchCheckSHK = async () => {
    if (!funnelData) return
    const shkSources = funnelData.filter((s) => isSHKSource(s.source_name))
    if (shkSources.length === 0) return
    setBatchChecking(true)
    setFunnelMsg(`Prüfe ${shkSources.length} SHK-Quellen…`)
    try {
      for (const src of shkSources) {
        await checkSource(src.source_id).catch(() => {})
      }
      setFunnelMsg(
        `✓ ${shkSources.length} SHK-Quellen angestoßen — neue Artikel werden im Hintergrund geladen`
      )
      setTimeout(() => setFunnelMsg(null), 6000)
    } catch (e) {
      setFunnelMsg('Fehler: ' + e.message)
    }
    setBatchChecking(false)
  }

  const handleFunnelAnalyze = async (id) => {
    setFunnelAnalyzingId(id)
    try {
      await analyzeAllSourceItems(id)
      setFunnelMsg('✓ Analyse gestartet — Ideen werden im Hintergrund generiert (LLM-Budget nötig)')
      setTimeout(() => {
        setFunnelMsg(null)
        getSourceFunnel()
          .then((d) => setFunnelData(Array.isArray(d) ? d : null))
          .catch(() => {})
      }, 5000)
    } catch (e) {
      setFunnelMsg('Fehler: ' + e.message)
    }
    setTimeout(() => setFunnelAnalyzingId(null), 2000)
  }

  const handlePreviewItems = (id, name) => setPreviewSource({ id, name })

  const handleToggle = async (source) => {
    await updateSource(source.id, { is_active: !source.is_active })
    refetch()
  }

  const handleDelete = async (id) => {
    if (window.confirm('Quelle wirklich loeschen?')) {
      await deleteSource(id)
      refetch()
    }
  }

  const handleUpdateInterval = async (id, minutes) => {
    await updateSource(id, { polling_interval_minutes: minutes })
    refetch()
  }

  const handleUpdateKeywords = async (id, keywords) => {
    await updateSourceKeywords(id, keywords)
    refetch()
  }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Quellen...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Quellen</h1>
          <p className="text-sm text-ink-light mt-0.5">
            {(sources || []).length} Quellen, {(sources || []).filter((s) => s.is_active).length}{' '}
            aktiv
          </p>
        </div>
        {mainTab === 'sources' && (
          <button
            onClick={() => setAddingType(activeTypeTab || 'youtube')}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 transition-colors"
          >
            <Plus className="w-4 h-4" /> Quelle hinzufuegen
          </button>
        )}
      </div>

      {/* Main Tabs */}
      <div className="flex gap-1 mb-5 border-b border-surface-border">
        <button
          onClick={() => setMainTab('sources')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
            mainTab === 'sources'
              ? 'border-primary-600 text-primary-700'
              : 'border-transparent text-ink-muted hover:text-ink'
          }`}
        >
          <Radio className="w-4 h-4" /> Meine Quellen
        </button>
        <button
          onClick={() => setMainTab('funnel')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
            mainTab === 'funnel'
              ? 'border-primary-600 text-primary-700'
              : 'border-transparent text-ink-muted hover:text-ink'
          }`}
        >
          <BarChart3 className="w-4 h-4" /> Pipeline-Übersicht
        </button>
        <button
          onClick={() => setMainTab('discover')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
            mainTab === 'discover'
              ? 'border-primary-600 text-primary-700'
              : 'border-transparent text-ink-muted hover:text-ink'
          }`}
        >
          <Compass className="w-4 h-4" /> Quellen entdecken
        </button>
      </div>

      {mainTab === 'discover' && <DiscoverTab sources={sources} />}

      {mainTab === 'funnel' && (
        <div>
          <div className="mb-4 p-3 bg-status-neu-bg border border-status-neu-border rounded-xl text-xs text-status-neu-text">
            <strong>Pipeline-Übersicht</strong>: Zeigt wie viele Items jede Quelle in jeder Stufe
            hat (Items → Ideen → Posts → Approved). SHK/Handwerk-Quellen sind grün markiert. Quellen
            mit Items aber 0 Ideen haben ein ⚠️ (Analyse nötig).
          </div>
          {funnelMsg && (
            <div className="mb-3 p-2.5 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-xs text-status-fertig-text font-medium">
              {funnelMsg}
            </div>
          )}
          <FunnelTab
            funnelData={funnelData}
            onArchiveIdeas={() =>
              getSourceFunnel()
                .then((d) => setFunnelData(Array.isArray(d) ? d : null))
                .catch(() => {})
            }
            onCheckSource={handleFunnelCheck}
            onAnalyzeSource={handleFunnelAnalyze}
            checkingSourceId={funnelCheckingId}
            analyzingSourceId={funnelAnalyzingId}
            batchChecking={batchChecking}
            onBatchCheckSHK={handleBatchCheckSHK}
            onPreviewItems={handlePreviewItems}
          />
        </div>
      )}

      {mainTab === 'sources' && (
        <>
          {/* Type filter tabs */}
          <div className="flex items-center gap-1 bg-surface-bg rounded-lg p-1 mb-5 overflow-x-auto">
            {SOURCE_TYPES.map((t) => {
              const count = t.key ? counts[t.key] || 0 : (sources || []).length
              return (
                <button
                  key={t.key}
                  onClick={() => setActiveTypeTab(t.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                    activeTypeTab === t.key
                      ? 'bg-white text-ink shadow-sm'
                      : 'text-ink-light hover:text-ink'
                  }`}
                >
                  <t.icon className="w-3.5 h-3.5" />
                  {t.label}
                  {count > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 rounded-full bg-surface-border text-[10px]">
                      {count}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {addingType && (
            <AddSourceForm
              type={addingType}
              onAdd={handleAdd}
              onCancel={() => setAddingType(null)}
            />
          )}

          {/* YouTube Video-Suche im YouTube-Tab */}
          {activeTypeTab === 'youtube' && !addingType && <YouTubeVideoSearch />}

          {/* Source Health Summary */}
          {filtered.length > 0 &&
            (() => {
              const problemSources = filtered.filter((src) => {
                const st = sourceStats[src.id] || {}
                return st.total_items > 50 && (st.content_ready || 0) === 0
              })
              const backlogSources = filtered.filter((src) => {
                const st = sourceStats[src.id] || {}
                return (st.by_status?.transcribed || 0) > 0
              })
              if (problemSources.length === 0 && backlogSources.length === 0) return null
              return (
                <div className="mb-4 rounded-xl border border-surface-border bg-surface-bg p-3">
                  <div className="text-xs font-semibold text-ink-muted uppercase tracking-wide mb-2">
                    Quellen-Status
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {problemSources.map((src) => {
                      const st = sourceStats[src.id] || {}
                      const items = st.total_items || 0
                      const minCost = (items * 0.0005).toFixed(2)
                      const maxCost = (items * 0.003).toFixed(2)
                      return (
                        <div key={src.id} className="flex items-center gap-2 text-xs">
                          <span className="w-2 h-2 rounded-full bg-status-fehler-border shrink-0" />
                          <span className="font-medium text-ink truncate max-w-[180px]">
                            {src.name}
                          </span>
                          <span className="text-status-fehler-text">
                            {items.toLocaleString('de-DE')} Items, 0 Content
                          </span>
                          <span className="text-ink-muted ml-auto shrink-0">
                            ~${minCost}–${maxCost}
                          </span>
                        </div>
                      )
                    })}
                    {backlogSources
                      .filter((src) => !problemSources.find((p) => p.id === src.id))
                      .map((src) => {
                        const st = sourceStats[src.id] || {}
                        const waiting = st.by_status?.transcribed || 0
                        const minCost = (waiting * 0.0005).toFixed(2)
                        const maxCost = (waiting * 0.003).toFixed(2)
                        return (
                          <div key={src.id} className="flex items-center gap-2 text-xs">
                            <span className="w-2 h-2 rounded-full bg-status-aktiv-border shrink-0" />
                            <span className="font-medium text-ink truncate max-w-[180px]">
                              {src.name}
                            </span>
                            <span className="text-status-aktiv-text">
                              {waiting} transkribiert, wartet auf Analyse
                            </span>
                            <span className="text-ink-muted ml-auto shrink-0">
                              ~${minCost}–${maxCost}
                            </span>
                          </div>
                        )
                      })}
                  </div>
                </div>
              )
            })()}

          {filtered.length === 0 ? (
            <div className="text-center py-12">
              <Radio className="w-10 h-10 text-ink-muted mx-auto mb-3" />
              <p className="text-sm text-ink-light">
                Keine Quellen{' '}
                {activeTypeTab
                  ? `vom Typ "${SOURCE_TYPES.find((t) => t.key === activeTypeTab)?.label}"`
                  : ''}{' '}
                vorhanden.
              </p>
              <button
                onClick={() => setAddingType(activeTypeTab || 'youtube')}
                className="mt-2 text-sm text-primary-600 hover:text-primary-700 font-medium"
              >
                Jetzt hinzufuegen
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {filtered.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  onCheck={handleCheck}
                  onToggle={handleToggle}
                  onDelete={handleDelete}
                  onUpdateInterval={handleUpdateInterval}
                  onUpdateKeywords={handleUpdateKeywords}
                  checking={checkingId === source.id}
                  stats={sourceStats[source.id]}
                />
              ))}
            </div>
          )}
        </>
      )}

      {previewSource && (
        <SourceItemsModal
          sourceId={previewSource.id}
          sourceName={previewSource.name}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </div>
  )
}
