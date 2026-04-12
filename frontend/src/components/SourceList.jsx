import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Input } from './ui/Input'
import { Dialog } from './ui/Dialog'
import { useApi } from '../hooks/useApi'
import { getSources, createSource, updateSource, deleteSource, checkSource, searchChannels, importAllVideos } from '../api'

export default function SourceList() {
  const { data: sources, loading, refetch } = useApi(getSources)
  const [showAdd, setShowAdd] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [form, setForm] = useState({ name: '', type: 'youtube', channel_id: '', url: '', language: 'de', auto_process: false })
  const [saving, setSaving] = useState(false)

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

  const handleSelectChannel = (channel) => {
    setForm({
      name: channel.name,
      type: 'youtube',
      channel_id: channel.channel_id,
      url: channel.url,
      language: 'de',
      auto_process: false,
    })
    setShowSearch(false)
    setShowAdd(true)
  }

  const handleAddFromSearch = async (channel) => {
    setSaving(true)
    try {
      await createSource({
        name: channel.name,
        type: 'youtube',
        channel_id: channel.channel_id,
        url: channel.url,
        language: 'de',
        auto_process: false,
      })
      setSearchResults(prev => prev.filter(c => c.channel_id !== channel.channel_id))
      refetch()
    } catch (e) {
      alert('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleAdd = async () => {
    setSaving(true)
    try {
      await createSource(form)
      setShowAdd(false)
      setForm({ name: '', type: 'youtube', channel_id: '', url: '', language: 'de', auto_process: false })
      refetch()
    } catch (e) {
      alert('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (source) => {
    await updateSource(source.id, { is_active: !source.is_active })
    refetch()
  }

  const handleCheck = async (id) => {
    await checkSource(id)
    alert('Check gestartet!')
  }

  const handleDelete = async (id) => {
    if (confirm('Quelle wirklich loeschen?')) {
      await deleteSource(id)
      refetch()
    }
  }

  // Check if channel is already added
  const isAlreadyAdded = (channelId) => {
    return (sources || []).some(s => s.channel_id === channelId)
  }

  if (loading) return <div className="text-gray-500">Lade Quellen...</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Quellen</h2>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => { setShowSearch(true); setSearchResults([]); setSearchQuery('') }}>
            Kanal suchen
          </Button>
          <Button onClick={() => setShowAdd(true)}>+ Manuell hinzufuegen</Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-sm text-gray-500 dark:text-gray-400">
                <th className="px-6 py-3 font-medium">Name</th>
                <th className="px-6 py-3 font-medium">Typ</th>
                <th className="px-6 py-3 font-medium">Sprache</th>
                <th className="px-6 py-3 font-medium">Letzter Check</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {(sources || []).map(s => (
                <tr key={s.id} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{s.name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{s.channel_id || s.url}</p>
                  </td>
                  <td className="px-6 py-4"><Badge color="blue">{s.type}</Badge></td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">{s.language}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {s.last_checked_at ? new Date(s.last_checked_at).toLocaleString('de-DE') : 'Nie'}
                  </td>
                  <td className="px-6 py-4">
                    <button onClick={() => handleToggle(s)} className="cursor-pointer">
                      <Badge color={s.is_active ? 'green' : 'gray'}>{s.is_active ? 'Aktiv' : 'Inaktiv'}</Badge>
                    </button>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => handleCheck(s.id)}>Pruefen</Button>
                      <Button size="sm" variant="secondary" onClick={async () => {
                        const r = await importAllVideos(s.id)
                        alert(`${r.imported} Videos importiert (${r.with_transcript} mit Transkript, ${r.already_existed} existierten bereits)`)
                        refetch()
                      }}>Alle importieren</Button>
                      <Button size="sm" variant="danger" onClick={() => handleDelete(s.id)}>X</Button>
                    </div>
                  </td>
                </tr>
              ))}
              {(!sources || sources.length === 0) && (
                <tr><td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">Keine Quellen vorhanden. Nutze "Kanal suchen" um YouTube-Kanaele zu finden.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Search Dialog */}
      <Dialog open={showSearch} onClose={() => setShowSearch(false)} title="YouTube-Kanal suchen" className="max-w-2xl">
        <div className="space-y-4">
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                placeholder="z.B. Finanzen, Marketing, KI, Nachrichten..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Button onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
              {searching ? 'Suche...' : 'Suchen'}
            </Button>
          </div>

          {searching && (
            <div className="text-center py-8 text-sm text-gray-500">Suche YouTube-Kanaele...</div>
          )}

          {!searching && searchResults.length > 0 && (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto">
              <p className="text-xs text-gray-500">{searchResults.length} Kanaele gefunden</p>
              {searchResults.map(ch => {
                const added = isAlreadyAdded(ch.channel_id)
                return (
                  <div key={ch.channel_id} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                    {ch.thumbnail && (
                      <img src={ch.thumbnail} alt="" className="w-12 h-12 rounded-full object-cover flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{ch.name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {ch.subscribers && <span className="text-xs text-gray-500">{ch.subscribers}</span>}
                        {ch.video_count && <span className="text-xs text-gray-400">{ch.video_count}</span>}
                      </div>
                      {ch.description && (
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{ch.description}</p>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {added ? (
                        <Badge color="green">Hinzugefuegt</Badge>
                      ) : (
                        <Button size="sm" onClick={() => handleAddFromSearch(ch)} disabled={saving}>
                          + Hinzufuegen
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {!searching && searchResults.length === 0 && searchQuery && (
            <div className="text-center py-8 text-sm text-gray-400">
              Druecke "Suchen" um YouTube-Kanaele zu finden
            </div>
          )}
        </div>
      </Dialog>

      {/* Manual Add Dialog */}
      <Dialog open={showAdd} onClose={() => setShowAdd(false)} title="Quelle manuell hinzufuegen">
        <div className="space-y-4">
          <Input label="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="z.B. Finanzfluss" />
          <Input label="YouTube Channel ID" value={form.channel_id} onChange={e => setForm({ ...form, channel_id: e.target.value })} placeholder="UCxxxxxxxx" />
          <Input label="URL (optional)" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} placeholder="https://youtube.com/@..." />
          <Input label="Sprache" value={form.language} onChange={e => setForm({ ...form, language: e.target.value })} />
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={form.auto_process} onChange={e => setForm({ ...form, auto_process: e.target.checked })} />
            Automatisch verarbeiten
          </label>
          <div className="flex gap-3 justify-end pt-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Abbrechen</Button>
            <Button onClick={handleAdd} disabled={saving || !form.name}>{saving ? 'Speichern...' : 'Hinzufuegen'}</Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
