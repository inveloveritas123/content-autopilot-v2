import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Input, Textarea } from './ui/Input'
import { Dialog } from './ui/Dialog'
import { useApi } from '../hooks/useApi'
import { getSettings, updateSettings, setApiKey, ncBrowse, ncSuggest } from '../api'

export default function Settings() {
  const { data, loading, refetch } = useApi(getSettings)
  const [localApiKey, setLocalApiKey] = useState(localStorage.getItem('apiKey') || '')
  const [tone, setTone] = useState('')
  const [language, setLanguage] = useState('')
  const [targetAudience, setTargetAudience] = useState('')
  const [ytApiKey, setYtApiKey] = useState('')
  const [ncTranscriptPath, setNcTranscriptPath] = useState('')
  const [ncAnalysisPath, setNcAnalysisPath] = useState('')
  const [ncContentPath, setNcContentPath] = useState('')
  const [ncReadPaths, setNcReadPaths] = useState([])
  const [newReadPath, setNewReadPath] = useState('')
  const [saving, setSaving] = useState(false)

  // NC Browser
  const [showBrowser, setShowBrowser] = useState(false)
  const [browserPath, setBrowserPath] = useState('/')
  const [browserEntries, setBrowserEntries] = useState([])
  const [browserTarget, setBrowserTarget] = useState(null) // which field to set
  const [browserLoading, setBrowserLoading] = useState(false)

  useEffect(() => {
    if (data?.settings) {
      setTone(data.settings.tone || '')
      setLanguage(data.settings.language || 'de')
      setTargetAudience(data.settings.target_audience || '')
      setYtApiKey(data.settings.youtube_api_key || '')
      setNcTranscriptPath(data.settings.nc_transcript_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte')
      setNcAnalysisPath(data.settings.nc_analysis_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen')
      setNcContentPath(data.settings.nc_content_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Content')
      setNcReadPaths(data.settings.nc_read_paths || [])
    }
  }, [data])

  const handleSaveApiKey = () => {
    setApiKey(localApiKey)
    refetch()
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateSettings({
        tone, language, target_audience: targetAudience,
        youtube_api_key: ytApiKey || undefined,
        nc_transcript_path: ncTranscriptPath,
        nc_analysis_path: ncAnalysisPath,
        nc_content_path: ncContentPath,
        nc_read_paths: ncReadPaths,
      })
      alert('Einstellungen gespeichert!')
    } catch (e) {
      alert('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const openBrowser = async (target) => {
    setBrowserTarget(target)
    setBrowserPath('/')
    setShowBrowser(true)
    await browseTo('/')
  }

  const browseTo = async (path) => {
    setBrowserLoading(true)
    setBrowserPath(path)
    try {
      const entries = await ncBrowse(path)
      setBrowserEntries(entries.filter(e => e.is_directory))
    } catch (e) {
      setBrowserEntries([])
    } finally {
      setBrowserLoading(false)
    }
  }

  const selectFolder = async (path) => {
    let updatedReadPaths = ncReadPaths
    if (browserTarget === 'transcript') setNcTranscriptPath(path)
    else if (browserTarget === 'analysis') setNcAnalysisPath(path)
    else if (browserTarget === 'content') setNcContentPath(path)
    else if (browserTarget === 'read') {
      if (!ncReadPaths.includes(path)) {
        updatedReadPaths = [...ncReadPaths, path]
        setNcReadPaths(updatedReadPaths)
      }
    }
    setShowBrowser(false)

    // Auto-save immediately
    try {
      await updateSettings({
        nc_transcript_path: browserTarget === 'transcript' ? path : ncTranscriptPath,
        nc_analysis_path: browserTarget === 'analysis' ? path : ncAnalysisPath,
        nc_content_path: browserTarget === 'content' ? path : ncContentPath,
        nc_read_paths: updatedReadPaths,
      })
    } catch (e) {
      console.error('Auto-save failed:', e)
    }
  }

  const handleSuggest = async () => {
    try {
      const s = await ncSuggest()
      setNcTranscriptPath(s.transcript)
      setNcAnalysisPath(s.analysis)
      setNcContentPath(s.content)
      if (s.read_paths?.length) setNcReadPaths([...new Set([...ncReadPaths, ...s.read_paths])])
      alert('Vorschlaege uebernommen!')
    } catch (e) {
      alert('Fehler: ' + e.message)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Einstellungen</h2>

      {/* API Key */}
      <Card>
        <CardHeader><CardTitle>API-Zugang</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Input label="Tenant API-Key" type="password" value={localApiKey}
            onChange={e => setLocalApiKey(e.target.value)} placeholder="Dein API-Key" />
          <Button size="sm" onClick={handleSaveApiKey}>API-Key speichern</Button>
          {data && <p className="text-sm text-green-600">Verbunden als: <strong>{data.name}</strong></p>}
        </CardContent>
      </Card>

      {/* YouTube API Key */}
      <Card>
        <CardHeader><CardTitle>YouTube API</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Input label="YouTube Data API Key (optional)" type="password" value={ytApiKey}
            onChange={e => setYtApiKey(e.target.value)}
            placeholder="AIza..." />
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
            <p className="text-sm text-yellow-800 dark:text-yellow-200 font-medium">Hinweis: Volle Funktionalitaet</p>
            <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
              Ohne YT API Key werden Views per Scraping ermittelt (langsamer, max 100 Videos/Durchlauf).
              Mit API Key: Praezise Views, Beschreibungen, Veroeffentlichungsdaten und schnellerer Import.
              Key erstellen unter: Google Cloud Console &rarr; APIs &amp; Services &rarr; YouTube Data API v3
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Nextcloud Ordner */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Nextcloud-Ordner</CardTitle>
            <Button size="sm" variant="secondary" onClick={handleSuggest}>Vorschlaege laden</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-gray-500">Lege fest wo Transkripte, Analysen und Content in Nextcloud gespeichert werden. Mehrere Lese-Ordner moeglich.</p>

          {/* Write paths */}
          <div className="space-y-3">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input label="Transkripte speichern in" value={ncTranscriptPath}
                  onChange={e => setNcTranscriptPath(e.target.value)} />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('transcript')}>Durchsuchen</Button>
            </div>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input label="Analysen speichern in" value={ncAnalysisPath}
                  onChange={e => setNcAnalysisPath(e.target.value)} />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('analysis')}>Durchsuchen</Button>
            </div>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input label="Content speichern in" value={ncContentPath}
                  onChange={e => setNcContentPath(e.target.value)} />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('content')}>Durchsuchen</Button>
            </div>
          </div>

          {/* Read paths */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Lese-Ordner (Transkripte/Analysen suchen in)
            </label>
            <div className="space-y-2">
              {ncReadPaths.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-sm text-gray-600 dark:text-gray-400 flex-1 bg-gray-50 dark:bg-gray-800 px-3 py-1.5 rounded">{p}</span>
                  <Button size="sm" variant="danger" onClick={() => setNcReadPaths(ncReadPaths.filter((_, j) => j !== i))}>X</Button>
                </div>
              ))}
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => openBrowser('read')}>+ Ordner hinzufuegen</Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Content Settings */}
      <Card>
        <CardHeader><CardTitle>Content-Einstellungen</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Textarea label="Tonalitaet" value={tone} onChange={e => setTone(e.target.value)}
            placeholder="professionell, informativ, mit persoenlicher Note" rows={2} />
          <Input label="Sprache" value={language} onChange={e => setLanguage(e.target.value)} />
          <Input label="Zielgruppe" value={targetAudience} onChange={e => setTargetAudience(e.target.value)}
            placeholder="Fuehrungskraefte, KMU-Inhaber" />
        </CardContent>
      </Card>

      <Button onClick={handleSave} disabled={saving} className="w-full">
        {saving ? 'Speichern...' : 'Alle Einstellungen speichern'}
      </Button>

      {/* NC Folder Browser Dialog */}
      <Dialog open={showBrowser} onClose={() => setShowBrowser(false)}
        title={`Nextcloud-Ordner waehlen`} className="max-w-lg">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>Pfad:</span>
            <span className="font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">{browserPath}</span>
          </div>

          {/* Navigation */}
          {browserPath !== '/' && (
            <Button size="sm" variant="ghost" onClick={() => {
              const parent = browserPath.split('/').slice(0, -1).join('/') || '/'
              browseTo(parent)
            }}>&larr; Zurueck</Button>
          )}

          {browserLoading ? (
            <p className="text-sm text-gray-500 py-4 text-center">Lade...</p>
          ) : (
            <div className="max-h-64 overflow-y-auto space-y-1">
              {browserEntries.length === 0 && (
                <p className="text-sm text-gray-400 py-4 text-center">Keine Unterordner</p>
              )}
              {browserEntries.map(entry => (
                <div key={entry.path} className="flex items-center justify-between p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg">
                  <button onClick={() => browseTo(entry.path + '/')}
                    className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 hover:text-primary-600">
                    <span>📁</span> {entry.name}
                  </button>
                  <Button size="sm" variant="secondary" onClick={() => selectFolder(entry.path)}>Waehlen</Button>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
            <Button size="sm" onClick={() => selectFolder(browserPath.replace(/\/$/, ''))}>
              Diesen Ordner waehlen
            </Button>
            <Input placeholder="Neuer Pfad..." value={browserPath}
              onChange={e => setBrowserPath(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && selectFolder(browserPath.replace(/\/$/, ''))} />
          </div>
        </div>
      </Dialog>
    </div>
  )
}
