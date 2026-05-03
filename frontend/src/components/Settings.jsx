import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import LLMSettings from './LLMSettings'
import { Badge } from './ui/Badge'
import { Input, Textarea } from './ui/Input'
import { Dialog } from './ui/Dialog'
import { useApi } from '../hooks/useApi'
import { getSettings, updateSettings, setApiKey, ncBrowse, ncSuggest, refreshIdeasWithProfile, getLlmRouting, getLLMCostHistory } from '../api'

export default function Settings() {
  const { data, loading, refetch } = useApi(getSettings)
  const [localApiKey, setLocalApiKey] = useState(localStorage.getItem('apiKey') || '')
  const [tone, setTone] = useState('')
  const [language, setLanguage] = useState('')
  const [targetAudience, setTargetAudience] = useState('')
  const [ytApiKey, setYtApiKey] = useState('')
  const [ytKeySet, setYtKeySet] = useState(false)
  const [ncTranscriptPath, setNcTranscriptPath] = useState('')
  const [ncAnalysisPath, setNcAnalysisPath] = useState('')
  const [ncContentPath, setNcContentPath] = useState('')
  const [ncReadPaths, setNcReadPaths] = useState([])
  const [newReadPath, setNewReadPath] = useState('')
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [dailyBudgetEur, setDailyBudgetEur] = useState('')
  const [routingOverrides, setRoutingOverrides] = useState({})
  const { data: routingData, refetch: refetchRouting } = useApi(getLlmRouting)
  const { data: costHistory } = useApi(() => getLLMCostHistory(2))

  // Entrepreneur Profile
  const [entName, setEntName] = useState('')
  const [entIndustry, setEntIndustry] = useState('')
  const [entSpecialization, setEntSpecialization] = useState('')
  const [entAudience, setEntAudience] = useState('')

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
      if (data.settings.youtube_api_key) {
        setYtApiKey('••••••••')
        setYtKeySet(true)
      } else {
        setYtApiKey('')
        setYtKeySet(false)
      }
      setNcTranscriptPath(data.settings.nc_transcript_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte')
      setNcAnalysisPath(data.settings.nc_analysis_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen')
      setNcContentPath(data.settings.nc_content_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Content')
      setNcReadPaths(data.settings.nc_read_paths || [])
      if (data.settings.daily_budget_eur) setDailyBudgetEur(String(data.settings.daily_budget_eur))
      if (data.settings.llm_routing) setRoutingOverrides(data.settings.llm_routing)
      const ent = data.settings.entrepreneur || {}
      setEntName(ent.name || '')
      setEntIndustry(ent.industry || '')
      setEntSpecialization(ent.specialization || '')
      setEntAudience(ent.target_audience || '')
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
        youtube_api_key: (ytApiKey && ytApiKey !== '••••••••') ? ytApiKey : undefined,
        nc_transcript_path: ncTranscriptPath,
        nc_analysis_path: ncAnalysisPath,
        nc_content_path: ncContentPath,
        nc_read_paths: ncReadPaths,
        daily_budget_eur: dailyBudgetEur ? parseFloat(dailyBudgetEur) : undefined,
        llm_routing: Object.keys(routingOverrides).length > 0 ? routingOverrides : undefined,
        entrepreneur: {
          name: entName,
          industry: entIndustry,
          specialization: entSpecialization,
          target_audience: entAudience,
        },
      })
      alert('Einstellungen gespeichert!')
      refetchRouting()
    } catch (e) {
      alert('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRefreshIdeas = async () => {
    if (!window.confirm('Bestehende "neue" Ideen werden gelöscht und mit deinem aktuellen Unternehmer-Profil neu generiert. Fortfahren?')) return
    setRefreshing(true)
    try {
      const r = await refreshIdeasWithProfile(20)
      alert(r.message || 'Ideen werden im Hintergrund neu generiert.')
    } catch (e) {
      alert('Fehler: ' + (e.message || 'Unbekannter Fehler'))
    } finally {
      setRefreshing(false)
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

  const profileComplete = !!(entName || entIndustry)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)

  const handleSaveProfile = async () => {
    setProfileSaving(true)
    try {
      await updateSettings({
        entrepreneur: {
          name: entName,
          industry: entIndustry,
          specialization: entSpecialization,
          target_audience: entAudience,
        },
      })
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 3000)
    } catch (e) {
      alert('Fehler beim Speichern: ' + e.message)
    } finally {
      setProfileSaving(false)
    }
  }

  const SHK_PRESETS = [
    { label: 'SHK-Handwerker', name: '', industry: 'SHK-Handwerk (Sanitär, Heizung, Klima)', specialization: 'Sanitär-, Heizungs- und Klimatechnik', audience: 'Hausbesitzer, Bauherren, Gewerbetreibende' },
    { label: 'Elektro-Handwerk', name: '', industry: 'Elektrohandwerk', specialization: 'Elektroinstallation, Smart Home, PV-Anlagen', audience: 'Hausbesitzer, Gewerbetreibende, Bauträger' },
    { label: 'Bau & Ausbau', name: '', industry: 'Bauhandwerk', specialization: 'Hoch- und Tiefbau, Innenausbau', audience: 'Bauherren, Architekten, Wohnungseigentümer' },
    { label: 'IT & Beratung', name: '', industry: 'IT-Dienstleistungen & Beratung', specialization: 'Digitalisierung, Cloud, KI', audience: 'KMU-Inhaber, Führungskräfte, IT-Entscheider' },
  ]

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Einstellungen</h2>

      {/* Brand Voice Wizard CTA — replaces old v1 profile form */}
      <div className="rounded-xl border-2 border-primary-200 bg-primary-50 overflow-hidden shadow-sm">
        <div className="px-5 py-3 bg-primary-100 border-b border-primary-200 flex items-center gap-2">
          <span className="text-primary-600 text-lg">🎤</span>
          <div className="flex-1">
            <p className="font-bold text-primary-900 text-sm">Unternehmer-Profil — jetzt im Brand-Voice-Wizard</p>
            <p className="text-xs text-primary-700">Branche, Zielkunde und Angebot werden geführt im Wizard erfasst — präziser und direkt für die KI nutzbar.</p>
          </div>
          {profileComplete && <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-1 rounded">✓ Wizard abgeschlossen</span>}
        </div>
        <div className="p-5 flex items-center gap-4">
          <Link to="/brand-voice/wizard" className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors">
            Brand-Voice-Wizard starten
          </Link>
          <Link to="/brand-voice" className="text-sm text-primary-700 hover:underline">
            Brand Voice übersicht
          </Link>
        </div>
      </div>

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

      {/* LLM Provider Management — prominent position */}
      <Card>
        <CardContent>
          <LLMSettings />
        </CardContent>
      </Card>

      {/* YouTube API Key */}
      <Card>
        <CardHeader><CardTitle>YouTube API</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {ytKeySet && ytApiKey === '••••••••' ? (
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">YouTube Data API Key (optional)</label>
                <div className="flex items-center gap-2 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-800">
                  <span className="text-sm font-mono text-gray-500 flex-1">••••••••</span>
                  <span className="text-xs text-emerald-600 font-medium">Gespeichert</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => { setYtApiKey(''); setYtKeySet(false) }}
                className="mt-6 px-3 py-2 text-xs font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg transition-colors"
              >
                Aendern
              </button>
            </div>
          ) : (
            <Input label="YouTube Data API Key (optional)" type="password" value={ytApiKey}
              onChange={e => setYtApiKey(e.target.value)}
              placeholder="AIza..." />
          )}
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

      {/* v1 Unternehmer-Profil form removed — data captured via Brand-Voice-Wizard (#122) */}

      {/* Content Settings */}
      <Card>
        <CardHeader><CardTitle>Content-Einstellungen</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Textarea label="Tonalitaet" value={tone} onChange={e => setTone(e.target.value)}
            placeholder="professionell, informativ, mit persoenlicher Note" rows={2} />
          <Input label="Sprache" value={language} onChange={e => setLanguage(e.target.value)} />
          <Input label="Zielgruppe (allgemein)" value={targetAudience} onChange={e => setTargetAudience(e.target.value)}
            placeholder="Fuehrungskraefte, KMU-Inhaber" />
        </CardContent>
      </Card>

      {/* Budget & Kosten */}
      <Card>
        <CardHeader><CardTitle>Budget & Kosten</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Tages-Limit fuer KI-Ausgaben. Bei Ueberschreitung pausiert die Pipeline automatisch (Circuit Breaker).
            Aktuell: Gemini Flash ~0,075$/1M Token, Mistral Medium ~0,40$/1M Token.
          </p>
          <div className="flex items-end gap-3">
            <div className="w-40">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Tageslimit (EUR)
              </label>
              <input
                type="number" min="0.50" max="50.00" step="0.50"
                value={dailyBudgetEur}
                onChange={e => setDailyBudgetEur(e.target.value)}
                placeholder="z.B. 5.00"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            {dailyBudgetEur && (
              <span className="text-xs text-gray-500 pb-1.5">
                ≈ {Math.round(parseFloat(dailyBudgetEur) / 0.075 * 1000)}k Analyse-Tokens/Tag
              </span>
            )}
          </div>
          {(() => {
            const today = new Date().toISOString().slice(0, 10)
            const todayEntry = Array.isArray(costHistory) ? costHistory.find(e => e.date === today) : null
            const spentEur = todayEntry ? todayEntry.total_cents / 100 : 0
            const limitEur = dailyBudgetEur ? parseFloat(dailyBudgetEur) : 0
            const pct = limitEur > 0 ? Math.min(100, (spentEur / limitEur) * 100) : 0
            const barColor = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'
            if (!todayEntry && !limitEur) return null
            return (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">Verbrauch heute</span>
                  <span className={`font-semibold ${pct >= 90 ? 'text-red-600' : pct >= 70 ? 'text-amber-600' : 'text-emerald-600'}`}>
                    ${spentEur.toFixed(3)} {limitEur > 0 ? `/ $${limitEur.toFixed(2)}` : '(kein Limit gesetzt)'}
                  </span>
                </div>
                {limitEur > 0 && (
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${Math.max(pct, pct > 0 ? 3 : 0)}%` }} />
                  </div>
                )}
                {todayEntry && (
                  <p className="text-[11px] text-gray-400">{todayEntry.calls} LLM-Aufrufe · {((todayEntry.input_tokens + todayEntry.output_tokens) / 1000).toFixed(0)}k Token</p>
                )}
              </div>
            )
          })()}
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
            <p className="text-xs text-green-800 dark:text-green-200 font-medium">Aktuelles Routing (seit Cycle 86)</p>
            <p className="text-xs text-green-700 dark:text-green-300 mt-1">
              Analyse/Tagging/Summary → <code>google/gemini-2.0-flash</code> (0,075$/1M, ~40x guenstiger als Sonnet)<br/>
              Ideation/Posts/Fragen → <code>mistral/mistral-medium-latest</code> (0,40$/1M, 7x guenstiger)<br/>
              Kein <code>anthropic/claude-*</code> mehr im Backend.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* KI-Modelle Routing */}
      {routingData?.routing && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>KI-Modelle pro Aufgabe</CardTitle>
              <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-2 py-1 rounded font-medium">
                Ziel: ~25-35$/Monat
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {routingData.note}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 pr-4 font-medium text-gray-600 dark:text-gray-400">Aufgabe</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600 dark:text-gray-400">Modell</th>
                    <th className="text-right py-2 pr-4 font-medium text-gray-600 dark:text-gray-400">$/1M Token</th>
                    <th className="text-right py-2 font-medium text-gray-600 dark:text-gray-400">max_tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {routingData.routing.map(r => {
                    const currentKey = routingOverrides[r.purpose] || r.model_key
                    const modelOptions = [
                      { key: 'gemini-flash', id: 'google/gemini-2.0-flash', cost: 0.075, label: 'Gemini Flash (günstig)' },
                      { key: 'claude-sonnet', id: 'mistral/mistral-medium-latest', cost: 0.40, label: 'Mistral Medium (kreativ)' },
                    ]
                    const selected = modelOptions.find(o => o.key === currentKey) || modelOptions[0]
                    return (
                      <tr key={r.purpose} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        <td className="py-1.5 pr-4 text-gray-700 dark:text-gray-300">{r.label}</td>
                        <td className="py-1.5 pr-4">
                          <select
                            value={currentKey}
                            onChange={e => setRoutingOverrides(prev => ({ ...prev, [r.purpose]: e.target.value }))}
                            className="text-[10px] font-mono border border-gray-200 dark:border-gray-600 rounded px-1.5 py-0.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 cursor-pointer"
                          >
                            {modelOptions.map(o => (
                              <option key={o.key} value={o.key}>{o.id}</option>
                            ))}
                          </select>
                        </td>
                        <td className="py-1.5 pr-4 text-right">
                          <span className={`font-medium ${selected.cost <= 0.1 ? 'text-green-600' : selected.cost <= 0.5 ? 'text-yellow-600' : 'text-red-600'}`}>
                            ${selected.cost.toFixed(3)}
                          </span>
                        </td>
                        <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">{r.max_tokens}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Daten & Export */}
      <Card>
        <CardHeader><CardTitle>Daten & Export</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Exportiere alle Tenant-Daten als ZIP-Archiv oder importiere ein vorhandenes Backup.
          </p>
          <Link to="/settings/export-import">
            <Button variant="secondary">Zu Export / Import</Button>
          </Link>
        </CardContent>
      </Card>

      <div className="sticky bottom-4 z-10">
        <Button onClick={handleSave} disabled={saving} className="w-full shadow-lg">
          {saving ? 'Speichern...' : '💾 Alle Einstellungen speichern'}
        </Button>
      </div>

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
