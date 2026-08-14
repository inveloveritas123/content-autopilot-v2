import { useState, useEffect, useMemo } from 'react'
import { Search, Sparkles, MessageSquare, Mic, Image, FileText, Clock, Send } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import {
  searchMemory,
  getMemoryRecent,
  getMemoryPicker,
  getMemoryStats,
  addMemoryNote,
} from '../api'

const SOURCE_ICONS = {
  voice_telegram: Mic,
  voice_whatsapp: Mic,
  photo_telegram: Image,
  photo_whatsapp: Image,
  manual_note: FileText,
  transcript_extra: FileText,
}

const CLASS_COLORS = {
  werte: 'bg-status-fertig-bg text-status-fertig-text',
  stories: 'bg-status-aktiv-bg text-status-aktiv-text',
  konflikte: 'bg-status-fehler-bg text-status-fehler-text',
}

function timeAgo(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (sec < 60) return 'gerade eben'
  if (sec < 3600) return `${Math.floor(sec / 60)} Min.`
  if (sec < 86400) return `${Math.floor(sec / 3600)} Std.`
  if (sec < 604800) return `vor ${Math.floor(sec / 86400)} Tagen`
  return d.toLocaleDateString('de-DE')
}

function ChunkCard({ chunk, onSelect }) {
  const Icon = SOURCE_ICONS[chunk.source_type] || FileText
  const cls = chunk.classification
  const colorClass = (cls && CLASS_COLORS[cls]) || 'bg-surface-bg text-ink-light'
  return (
    <div
      className="bg-white rounded-xl border border-surface-border p-3 hover:border-primary-300 transition-colors cursor-pointer"
      onClick={() => onSelect && onSelect(chunk)}
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-primary-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 text-[11px] text-ink-muted">
            <span>{chunk.source_type}</span>
            {cls && <span className={`px-1.5 py-0.5 rounded-full ${colorClass}`}>{cls}</span>}
            <span className="ml-auto">{timeAgo(chunk.created_at)}</span>
            {chunk.similarity != null && (
              <span className="px-1.5 py-0.5 rounded-full bg-primary-50 text-primary-700">
                {(chunk.similarity * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <p className="text-sm text-ink whitespace-pre-wrap break-words line-clamp-4">
            {chunk.content_text || chunk.preview || ''}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function Memory() {
  const [activeTab, setActiveTab] = useState('picker')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [recent, setRecent] = useState([])
  const [picker, setPicker] = useState([])
  const [stats, setStats] = useState(null)
  const [noteText, setNoteText] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)
  const [error, setError] = useState(null)

  async function loadAll() {
    setError(null)
    try {
      const [r, p, s] = await Promise.all([
        getMemoryRecent({ limit: 20 }).catch(() => []),
        getMemoryPicker({ days_min: 7, days_max: 60, limit: 5 }).catch(() => ({ items: [] })),
        getMemoryStats().catch(() => null),
      ])
      setRecent(Array.isArray(r) ? r : [])
      setPicker(p && Array.isArray(p.items) ? p.items : [])
      setStats(s)
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  async function handleSearch(e) {
    if (e) e.preventDefault()
    if (!query.trim() || query.trim().length < 2) return
    setSearching(true)
    setError(null)
    try {
      const r = await searchMemory({ q: query.trim(), limit: 15 })
      setSearchResults(r)
      setActiveTab('search')
    } catch (e) {
      setError(e.message)
    } finally {
      setSearching(false)
    }
  }

  async function handleAddNote(e) {
    if (e) e.preventDefault()
    if (!noteText.trim()) return
    setNoteSaving(true)
    setError(null)
    try {
      await addMemoryNote({ text: noteText.trim(), classify: true })
      setNoteText('')
      await loadAll()
    } catch (e) {
      setError(e.message)
    } finally {
      setNoteSaving(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-ink flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-primary-600" />
          Unternehmensgedächtnis
        </h1>
        <p className="text-sm text-ink-muted mt-1">
          Sprachnotizen aus Telegram/WhatsApp, Fotos mit OCR, manuelle Notizen — semantisch
          durchsuchbar.
        </p>
      </div>

      {/* Stats-Strip */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white rounded-xl border border-surface-border p-3">
            <p className="text-xs text-ink-muted">Gesamt</p>
            <p className="text-2xl font-bold text-ink">{stats.total}</p>
            {stats.soft_deleted > 0 && (
              <p className="text-[10px] text-ink-muted">davon {stats.soft_deleted} gelöscht</p>
            )}
          </div>
          <div className="bg-white rounded-xl border border-surface-border p-3">
            <p className="text-xs text-ink-muted">Embedded</p>
            <p className="text-2xl font-bold text-ink">{stats.embedded}</p>
            <p className="text-[10px] text-ink-muted">
              {Math.round((stats.embedding_coverage || 0) * 100)}% Coverage
            </p>
          </div>
          <div className="bg-white rounded-xl border border-surface-border p-3 col-span-2">
            <p className="text-xs text-ink-muted mb-1">Klassifikation</p>
            <div className="flex flex-wrap gap-1.5">
              {(stats.by_classification || []).map((c) => (
                <span
                  key={c.classification}
                  className={`text-[11px] px-2 py-0.5 rounded-full ${CLASS_COLORS[c.classification] || 'bg-surface-bg text-ink-light'}`}
                >
                  {c.classification}: {c.count}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Search-Bar */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-3 text-ink-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Was hast du letztens über deine Werte erzählt?"
            className="w-full pl-10 pr-3 py-2.5 min-h-[44px] text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <Button type="submit" disabled={searching || query.trim().length < 2}>
          {searching ? 'Suche…' : 'Suchen'}
        </Button>
      </form>

      {error && (
        <div className="bg-status-fehler-bg border border-status-fehler-border rounded-lg p-3 text-sm text-status-fehler-text">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-surface-border flex gap-1">
        {[
          { id: 'picker', label: 'Picker' },
          { id: 'search', label: 'Suche', disabled: !searchResults },
          { id: 'recent', label: 'Neueste' },
          { id: 'note', label: '+ Notiz' },
        ].map((t) => (
          <button
            key={t.id}
            disabled={t.disabled}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === t.id
                ? 'border-primary-600 text-primary-700 font-medium'
                : 'border-transparent text-ink-muted hover:text-ink disabled:opacity-40'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Picker */}
      {activeTab === 'picker' && (
        <div className="space-y-3">
          <p className="text-xs text-ink-muted flex items-center gap-1">
            <Clock className="w-3 h-3" /> Vorschläge aus deinem Gedächtnis (vor 7-60 Tagen)
          </p>
          {picker.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Noch keine alten Erinnerungen — kommt mit der Zeit.
            </p>
          ) : (
            <div className="grid gap-3">
              {picker.map((item) => (
                <div
                  key={item.id}
                  className="bg-status-aktiv-bg/50 border border-status-aktiv-border rounded-xl p-3"
                >
                  <p className="text-sm font-medium text-status-aktiv-text mb-1">{item.suggestion}</p>
                  <p className="text-xs text-ink whitespace-pre-wrap break-words line-clamp-3">
                    {item.preview}
                  </p>
                  <p className="text-[11px] text-ink-muted mt-1.5">
                    {item.source_type} · vor {item.days_ago} Tagen
                    {item.classification ? ` · ${item.classification}` : ''}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Search Results */}
      {activeTab === 'search' && searchResults && (
        <div className="space-y-3">
          <p className="text-xs text-ink-muted">
            {searchResults.count} Treffer für „{searchResults.query}"
          </p>
          {searchResults.results.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Keine Treffer — vielleicht eine andere Formulierung versuchen.
            </p>
          ) : (
            <div className="grid gap-3">
              {searchResults.results.map((c) => (
                <ChunkCard key={c.id} chunk={c} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Recent */}
      {activeTab === 'recent' && (
        <div className="space-y-3">
          {recent.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Noch keine Inhalte. Sprachnachrichten oder Fotos via Telegram/WhatsApp einsenden, oder
              hier eine Notiz hinzufügen.
            </p>
          ) : (
            <div className="grid gap-3">
              {recent.map((c) => (
                <ChunkCard key={c.id} chunk={c} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add Note */}
      {activeTab === 'note' && (
        <form onSubmit={handleAddNote} className="space-y-3">
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Eine spontane Notiz, ein Gedanke, eine Begebenheit — alles was du sonst vergessen würdest."
            rows={6}
            className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={noteSaving || !noteText.trim()}>
              <Send className="w-3.5 h-3.5 mr-1.5 inline" />
              {noteSaving ? 'Speichere…' : 'Notiz speichern'}
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
