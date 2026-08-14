// AUDITED-2026-08-14 (Welle D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useToast } from './ui/Toast'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import LLMSettings from './LLMSettings'
import TelegramBotSettings from './TelegramBotSettings'
import IndustryAndHooks from './IndustryAndHooks'
import { Badge } from './ui/Badge'
import { Input, Textarea } from './ui/Input'
import { Dialog } from './ui/Dialog'
import { useApi } from '../hooks/useApi'
import { useUiMode } from '../hooks/useUiMode'
import {
  getSettings,
  updateSettings,
  setApiKey,
  ncBrowse,
  ncSuggest,
  refreshIdeasWithProfile,
  getLlmRouting,
  getLLMCostHistory,
  getModelMode,
  setModelMode,
} from '../api'

export default function Settings() {
  const toast = useToast()
  const { data, loading, refetch } = useApi(getSettings)

  // #90 UI-Modus: MVP vs Features
  const { mode: uiMode, setMode: setUiMode } = useUiMode()
  const [uiModeSaving, setUiModeSaving] = useState(false)
  const [localApiKey, setLocalApiKey] = useState(localStorage.getItem('apiKey') || '')
  const [tone, setTone] = useState('')
  const [language, setLanguage] = useState('')
  const [targetAudience, setTargetAudience] = useState('')
  const [ytApiKey, setYtApiKey] = useState('')
  const [ytKeySet, setYtKeySet] = useState(false)
  const [showYtKey, setShowYtKey] = useState(false)
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

  // Modell-Modus-Switch (Issue #72)
  const [modelMode, setModelModeState] = useState('testmodus')
  const [modelModeSaving, setModelModeSaving] = useState(false)

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
      setNcTranscriptPath(
        data.settings.nc_transcript_path ||
          '/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte'
      )
      setNcAnalysisPath(
        data.settings.nc_analysis_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen'
      )
      setNcContentPath(
        data.settings.nc_content_path || '/zukunftsbund/Projekte/Content-Autopilot/Daten/Content'
      )
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

  // Modell-Modus beim Start laden
  useEffect(() => {
    getModelMode()
      .then((r) => setModelModeState(r.model_mode || 'testmodus'))
      .catch(() => setModelModeState('testmodus'))
  }, [])

  const handleSaveModelMode = async (mode) => {
    setModelModeSaving(true)
    try {
      await setModelMode(mode)
      setModelModeState(mode)
      toast.success('Modell-Modus gespeichert!')
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    } finally {
      setModelModeSaving(false)
    }
  }

  const handleSaveApiKey = () => {
    setApiKey(localApiKey)
    window.location.reload()
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateSettings({
        tone,
        language,
        target_audience: targetAudience,
        youtube_api_key: ytApiKey && ytApiKey !== '••••••••' ? ytApiKey : undefined,
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
      toast.success('Einstellungen gespeichert!')
      refetchRouting()
    } catch (e) {
      toast.error('Fehler: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRefreshIdeas = async () => {
    if (
      !window.confirm(
        'Bestehende "neue" Ideen werden gelöscht und mit deinem aktuellen Unternehmer-Profil neu generiert. Fortfahren?'
      )
    )
      return
    setRefreshing(true)
    try {
      const r = await refreshIdeasWithProfile(20)
      toast.success(r.message || 'Ideen werden im Hintergrund neu generiert.')
    } catch (e) {
      toast.error('Fehler: ' + (e.message || 'Unbekannter Fehler'))
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
      setBrowserEntries(entries.filter((e) => e.is_directory))
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
      toast.success('Vorschläge übernommen!')
    } catch (e) {
      toast.error('Fehler: ' + e.message)
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
      toast.error('Fehler beim Speichern: ' + e.message)
    } finally {
      setProfileSaving(false)
    }
  }

  const SHK_PRESETS = [
    {
      label: 'SHK-Handwerker',
      name: '',
      industry: 'SHK-Handwerk (Sanitär, Heizung, Klima)',
      specialization: 'Sanitär-, Heizungs- und Klimatechnik',
      audience: 'Hausbesitzer, Bauherren, Gewerbetreibende',
    },
    {
      label: 'Elektro-Handwerk',
      name: '',
      industry: 'Elektrohandwerk',
      specialization: 'Elektroinstallation, Smart Home, PV-Anlagen',
      audience: 'Hausbesitzer, Gewerbetreibende, Bauträger',
    },
    {
      label: 'Bau & Ausbau',
      name: '',
      industry: 'Bauhandwerk',
      specialization: 'Hoch- und Tiefbau, Innenausbau',
      audience: 'Bauherren, Architekten, Wohnungseigentümer',
    },
    {
      label: 'IT & Beratung',
      name: '',
      industry: 'IT-Dienstleistungen & Beratung',
      specialization: 'Digitalisierung, Cloud, KI',
      audience: 'KMU-Inhaber, Führungskräfte, IT-Entscheider',
    },
  ]

  // #90 Handler für Modus-Wechsel — aktualisiert Context sofort, kein Reload nötig
  const handleUiModeChange = async (newMode) => {
    if (newMode === uiMode) return
    setUiModeSaving(true)
    try {
      await setUiMode(newMode)
      toast.success(
        newMode === 'mvp'
          ? 'Ansicht auf MVP umgestellt — Navigation aktualisiert.'
          : 'Ansicht auf Voll-Stand umgestellt — alle Features sichtbar.'
      )
    } catch (e) {
      toast.error('Fehler beim Speichern des Modus: ' + e.message)
    } finally {
      setUiModeSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-ink">Einstellungen</h2>

      {/* Oberflächen-Modus (Issue #90) */}
      <Card>
        <CardHeader>
          <CardTitle>Oberflächen-Modus</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-ink-light">
            <strong>MVP</strong> zeigt nur die Kern-Flows (Dashboard, Pipeline, Quellen, Ideen,
            Posts, Posten, Brand Voice, Gedächtnis, Einstellungen). <strong>Features</strong>{' '}
            schaltet den vollen Funktionsumfang frei (Dialogue, Kalender, Analytics, Admin-Tools
            usw.).
          </p>
          {/* Segmented Control: MVP | Features */}
          <div className="inline-flex rounded-lg border border-surface-border overflow-hidden">
            {[
              { value: 'mvp', label: 'MVP', desc: 'Schlank' },
              { value: 'features', label: 'Features', desc: 'Voll-Stand' },
            ].map(({ value, label, desc }) => (
              <button
                key={value}
                disabled={uiModeSaving}
                onClick={() => handleUiModeChange(value)}
                className={[
                  'px-5 py-2.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50',
                  uiMode === value
                    ? 'bg-primary-700 text-white'
                    : 'bg-white text-ink-light hover:bg-surface-bg',
                ].join(' ')}
              >
                {label}
                <span className="ml-1.5 text-xs opacity-70">{desc}</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-ink-muted">
            Modus wird pro Tenant gespeichert. Die Navigation passt sich sofort an — kein Reload
            nötig.
          </p>
        </CardContent>
      </Card>

      {/* Brand Voice Wizard CTA — replaces old v1 profile form */}
      <div className="rounded-xl border-2 border-primary-200 bg-primary-50 overflow-hidden shadow-sm">
        <div className="px-5 py-3 bg-primary-100 border-b border-primary-200 flex items-center gap-2">
          <span className="text-primary-600 text-lg">🎤</span>
          <div className="flex-1">
            <p className="font-bold text-primary-900 text-sm">
              Unternehmer-Profil — jetzt im Brand-Voice-Wizard
            </p>
            <p className="text-xs text-primary-700">
              Branche, Zielkunde und Angebot werden geführt im Wizard erfasst — präziser und direkt
              für die KI nutzbar.
            </p>
          </div>
          {profileComplete && (
            <span className="text-xs font-semibold text-status-fertig-text bg-status-fertig-bg px-2 py-1 rounded">
              ✓ Wizard abgeschlossen
            </span>
          )}
        </div>
        <div className="p-5 flex items-center gap-4">
          <Link
            to="/brand-voice/wizard"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Brand-Voice-Wizard starten
          </Link>
          <Link to="/brand-voice" className="text-sm text-primary-700 hover:underline">
            Brand Voice übersicht
          </Link>
        </div>
      </div>

      {/* API Key */}
      <Card>
        <CardHeader>
          <CardTitle>API-Zugang</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            label="Tenant API-Key"
            type="password"
            value={localApiKey}
            onChange={(e) => setLocalApiKey(e.target.value)}
            placeholder="Dein API-Key"
          />
          <Button size="sm" onClick={handleSaveApiKey}>
            API-Key speichern
          </Button>
          {data && (
            <p className="text-sm text-status-fertig-text">
              Verbunden als: <strong>{data.name}</strong>
            </p>
          )}
        </CardContent>
      </Card>

      {/* LLM Provider Management — prominent position */}
      <Card>
        <CardContent>
          <LLMSettings />
        </CardContent>
      </Card>

      {/* Phase 4.4 + 7.4 — Industry-Profil + Hook-Bibliothek */}
      <IndustryAndHooks />

      {/* YouTube API Key */}
      <Card>
        <CardHeader>
          <CardTitle>YouTube API</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {ytKeySet && ytApiKey === '••••••••' ? (
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-ink-light mb-1">
                  YouTube Data API Key (optional)
                </label>
                <div className="flex items-center gap-2 border border-surface-border rounded-lg px-3 py-2 bg-surface-bg">
                  <span className="text-sm font-mono text-ink-light flex-1">••••••••</span>
                  <span className="text-xs text-status-fertig-text font-medium">Gespeichert</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setYtApiKey('')
                  setYtKeySet(false)
                }}
                className="mt-6 px-3 py-2 text-xs font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg transition-colors"
              >
                Aendern
              </button>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-ink-light mb-1">
                YouTube Data API Key (optional)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type={showYtKey ? 'text' : 'password'}
                  value={ytApiKey}
                  onChange={(e) => setYtApiKey(e.target.value)}
                  placeholder="AIza..."
                  className="flex-1 border border-surface-border rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
                <button
                  type="button"
                  onClick={() => setShowYtKey((s) => !s)}
                  className="p-2 rounded-md text-ink-muted hover:bg-surface-bg"
                  title={showYtKey ? 'Verbergen' : 'Anzeigen'}
                >
                  {showYtKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
          <div className="bg-status-aktiv-bg border border-status-aktiv-border rounded-lg p-3">
            <p className="text-sm text-status-aktiv-text font-medium">
              Hinweis: Volle Funktionalitaet
            </p>
            <p className="text-xs text-status-aktiv-text mt-1">
              Ohne YT API Key werden Views per Scraping ermittelt (langsamer, max 100
              Videos/Durchlauf). Mit API Key: Praezise Views, Beschreibungen,
              Veroeffentlichungsdaten und schnellerer Import. Key erstellen unter: Google Cloud
              Console &rarr; APIs &amp; Services &rarr; YouTube Data API v3
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Nextcloud Ordner */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Nextcloud-Ordner</CardTitle>
            <Button size="sm" variant="secondary" onClick={handleSuggest}>
              Vorschlaege laden
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-ink-light">
            Lege fest wo Transkripte, Analysen und Content in Nextcloud gespeichert werden. Mehrere
            Lese-Ordner moeglich.
          </p>

          {/* Write paths */}
          <div className="space-y-3">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  label="Transkripte speichern in"
                  value={ncTranscriptPath}
                  onChange={(e) => setNcTranscriptPath(e.target.value)}
                />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('transcript')}>
                Durchsuchen
              </Button>
            </div>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  label="Analysen speichern in"
                  value={ncAnalysisPath}
                  onChange={(e) => setNcAnalysisPath(e.target.value)}
                />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('analysis')}>
                Durchsuchen
              </Button>
            </div>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  label="Content speichern in"
                  value={ncContentPath}
                  onChange={(e) => setNcContentPath(e.target.value)}
                />
              </div>
              <Button size="sm" variant="secondary" onClick={() => openBrowser('content')}>
                Durchsuchen
              </Button>
            </div>
          </div>

          {/* Read paths */}
          <div>
            <label className="block text-sm font-medium text-ink-light mb-2">
              Lese-Ordner (Transkripte/Analysen suchen in)
            </label>
            <div className="space-y-2">
              {ncReadPaths.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-sm text-ink-light flex-1 bg-surface-bg px-3 py-1.5 rounded">
                    {p}
                  </span>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => setNcReadPaths(ncReadPaths.filter((_, j) => j !== i))}
                  >
                    X
                  </Button>
                </div>
              ))}
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => openBrowser('read')}>
                  + Ordner hinzufuegen
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* v1 Unternehmer-Profil form removed — data captured via Brand-Voice-Wizard (Issue 122) */}

      {/* Content Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Content-Einstellungen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            label="Tonalitaet"
            value={tone}
            onChange={(e) => setTone(e.target.value)}
            placeholder="professionell, informativ, mit persoenlicher Note"
            rows={2}
          />
          <Input label="Sprache" value={language} onChange={(e) => setLanguage(e.target.value)} />
          <Input
            label="Zielgruppe (allgemein)"
            value={targetAudience}
            onChange={(e) => setTargetAudience(e.target.value)}
            placeholder="Fuehrungskraefte, KMU-Inhaber"
          />
        </CardContent>
      </Card>

      {/* Budget & Kosten */}
      <Card>
        <CardHeader>
          <CardTitle>Budget & Kosten</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-ink-light">
            Tages-Limit fuer KI-Ausgaben. Bei Ueberschreitung pausiert die Pipeline automatisch
            (Circuit Breaker). Aktuell: Gemini Flash ~0,075$/1M Token, Mistral Medium ~0,40$/1M
            Token.
          </p>
          <div className="flex items-end gap-3">
            <div className="w-40">
              <label className="block text-sm font-medium text-ink-light mb-1">
                Tageslimit (EUR)
              </label>
              <input
                type="number"
                min="0.50"
                max="50.00"
                step="0.50"
                value={dailyBudgetEur}
                onChange={(e) => setDailyBudgetEur(e.target.value)}
                placeholder="z.B. 5.00"
                className="w-full border border-surface-border rounded-lg px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            {dailyBudgetEur && (
              <span className="text-xs text-ink-light pb-1.5">
                ≈ {Math.round((parseFloat(dailyBudgetEur) / 0.075) * 1000)}k Analyse-Tokens/Tag
              </span>
            )}
          </div>
          {(() => {
            const today = new Date().toISOString().slice(0, 10)
            const todayEntry = Array.isArray(costHistory)
              ? costHistory.find((e) => e.date === today)
              : null
            const spentEur = todayEntry ? todayEntry.total_cents / 100 : 0
            const limitEur = dailyBudgetEur ? parseFloat(dailyBudgetEur) : 0
            const pct = limitEur > 0 ? Math.min(100, (spentEur / limitEur) * 100) : 0
            const barColor =
              pct >= 90
                ? 'bg-status-fehler-border'
                : pct >= 70
                  ? 'bg-status-aktiv-border'
                  : 'bg-status-fertig-border'
            if (!todayEntry && !limitEur) return null
            return (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-light">Verbrauch heute</span>
                  <span
                    className={`font-semibold ${pct >= 90 ? 'text-status-fehler-text' : pct >= 70 ? 'text-status-aktiv-text' : 'text-status-fertig-text'}`}
                  >
                    ${spentEur.toFixed(3)}{' '}
                    {limitEur > 0 ? `/ $${limitEur.toFixed(2)}` : '(kein Limit gesetzt)'}
                  </span>
                </div>
                {limitEur > 0 && (
                  <div className="h-2 bg-surface-bg rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${barColor}`}
                      style={{ width: `${Math.max(pct, pct > 0 ? 3 : 0)}%` }}
                    />
                  </div>
                )}
                {todayEntry && (
                  <p className="text-[11px] text-ink-muted">
                    {todayEntry.calls} LLM-Aufrufe ·{' '}
                    {((todayEntry.input_tokens + todayEntry.output_tokens) / 1000).toFixed(0)}k
                    Token
                  </p>
                )}
              </div>
            )
          })()}
          <div className="bg-status-fertig-bg border border-status-fertig-border rounded-lg p-3">
            <p className="text-xs text-status-fertig-text font-medium">
              Aktuelles Routing (seit Cycle 86)
            </p>
            <p className="text-xs text-status-fertig-text mt-1">
              Analyse/Tagging/Summary → <code>google/gemini-2.0-flash</code> (0,075$/1M, ~40x
              guenstiger als Sonnet)
              <br />
              Ideation/Posts/Fragen → <code>mistral/mistral-medium-latest</code> (0,40$/1M, 7x
              guenstiger)
              <br />
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
              <span className="text-xs bg-status-fertig-bg text-status-fertig-text px-2 py-1 rounded font-medium">
                Ziel: ~25-35$/Monat
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-ink-light mb-3">{routingData.note}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-surface-border">
                    <th className="text-left py-2 pr-4 font-medium text-ink-light">Aufgabe</th>
                    <th className="text-left py-2 pr-4 font-medium text-ink-light">Modell</th>
                    <th className="text-right py-2 pr-4 font-medium text-ink-light">
                      $/1M Token
                    </th>
                    <th className="text-right py-2 font-medium text-ink-light">max_tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {routingData.routing.map((r) => {
                    const currentKey = routingOverrides[r.purpose] || r.model_key
                    const modelOptions = [
                      {
                        key: 'gemini-flash',
                        id: 'google/gemini-2.0-flash',
                        cost: 0.075,
                        label: 'Gemini Flash (günstig)',
                      },
                      {
                        key: 'claude-sonnet',
                        id: 'mistral/mistral-medium-latest',
                        cost: 0.4,
                        label: 'Mistral Medium (kreativ)',
                      },
                    ]
                    const selected =
                      modelOptions.find((o) => o.key === currentKey) || modelOptions[0]
                    return (
                      <tr
                        key={r.purpose}
                        className="border-b border-surface-border hover:bg-surface-bg"
                      >
                        <td className="py-1.5 pr-4 text-ink-light">{r.label}</td>
                        <td className="py-1.5 pr-4">
                          <select
                            value={currentKey}
                            onChange={(e) =>
                              setRoutingOverrides((prev) => ({
                                ...prev,
                                [r.purpose]: e.target.value,
                              }))
                            }
                            className="text-[10px] font-mono border border-surface-border rounded px-1.5 py-0.5 bg-white text-ink-light cursor-pointer"
                          >
                            {modelOptions.map((o) => (
                              <option key={o.key} value={o.key}>
                                {o.id}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-1.5 pr-4 text-right">
                          <span
                            className={`font-medium ${selected.cost <= 0.1 ? 'text-status-fertig-text' : selected.cost <= 0.5 ? 'text-status-aktiv-text' : 'text-status-fehler-text'}`}
                          >
                            ${selected.cost.toFixed(3)}
                          </span>
                        </td>
                        <td className="py-1.5 text-right text-ink-light">{r.max_tokens}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Telegram-Bot (pro Projekt) */}
      <TelegramBotSettings />

      {/* Daten & Export */}
      <Card>
        <CardHeader>
          <CardTitle>Daten & Export</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-ink-light">
            Exportiere alle Tenant-Daten als ZIP-Archiv oder importiere ein vorhandenes Backup.
          </p>
          <Link to="/settings/export-import">
            <Button variant="secondary">Zu Export / Import</Button>
          </Link>
        </CardContent>
      </Card>

      {/* Modell-Hoheit */}
      <Card>
        <CardHeader>
          <CardTitle>Modell-Hoheit · Pipeline-Phasen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-ink-light">
            Offizielles Default-Modell pro Phase (P01–P12c) ansehen und bei Bedarf einen globalen
            Test-Override (beliebige Requesty-Modell-ID, z.B. Gemini Flash) setzen.
          </p>
          <Link to="/settings/pipeline-models">
            <Button variant="secondary">Zu Modell-Hoheit</Button>
          </Link>
        </CardContent>
      </Card>

      {/* Modell-Modus-Switch (Issue #72) */}
      <Card>
        <CardHeader>
          <CardTitle>KI-Qualitaetsmodus</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-ink-light">
            Steuert welches Modell fuer kreative Aufgaben (Ideation, Fragen, Posts) verwendet wird.
            Analysepfade (Transkription, Tagging, Scoring) sind in jedem Modus unveraendert.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              {
                key: 'testmodus',
                label: 'Testmodus',
                desc: 'Standard: Gemini Flash Lite (guenstig, ~$0.075/1M)',
                badge: 'Standard',
                // new→status-neu (info-artig, "aktueller Default")
                badgeClass: 'bg-status-neu-bg text-status-neu-text',
                border: 'border-status-neu-border',
              },
              {
                key: 'produktiv',
                label: 'Produktivmodus',
                desc: 'Anthropic Claude Sonnet via Bedrock EU (Qualitaet, hoehere Kosten ~$3/1M)',
                badge: 'Hoehere Kosten',
                badgeClass: 'bg-status-aktiv-bg text-status-aktiv-text',
                border: 'border-status-aktiv-border',
              },
              {
                key: 'benutzerdefiniert',
                label: 'Benutzerdefiniert',
                desc: 'Platzhalter fuer kuenftige per-Aufgabe-Konfiguration (verhalt wie Testmodus)',
                badge: 'Demnachst',
                badgeClass: 'bg-surface-bg text-ink-light',
                border: 'border-surface-border',
              },
            ].map((opt) => (
              <button
                key={opt.key}
                disabled={modelModeSaving}
                onClick={() => handleSaveModelMode(opt.key)}
                className={`text-left p-4 rounded-xl border-2 transition-all focus:outline-none focus:ring-2 focus:ring-primary-400 ${
                  modelMode === opt.key
                    ? `${opt.border} bg-white shadow-md`
                    : 'border-surface-border bg-surface-bg hover:border-surface-border'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-sm text-ink">{opt.label}</span>
                  {modelMode === opt.key && (
                    <span className="text-[10px] font-bold text-primary-600 uppercase tracking-wide">
                      Aktiv
                    </span>
                  )}
                </div>
                <p className="text-xs text-ink-light mb-2">{opt.desc}</p>
                <span
                  className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${opt.badgeClass}`}
                >
                  {opt.badge}
                </span>
              </button>
            ))}
          </div>
          {modelMode === 'produktiv' && (
            <div className="rounded-lg border border-status-aktiv-border bg-status-aktiv-bg p-3">
              <p className="text-xs font-semibold text-status-aktiv-text mb-1">
                Kostenhinweis Produktivmodus
              </p>
              <p className="text-xs text-status-aktiv-text">
                Kreative Pfade (Ideation, Smart-Fragen, Post-Generierung) laufen auf{' '}
                <code className="font-mono">bedrock/claude-sonnet-4-6@eu-central-1</code> (Bedrock
                Frankfurt, EU-souveraen). Kosten ca. $3/1M Input-Token statt $0.075 im Testmodus —
                ca. 40x teurer fuer kreative Aufgaben. Analysepfade bleiben unveraendert.
              </p>
            </div>
          )}
          {modelModeSaving && (
            <p className="text-xs text-ink-muted animate-pulse">Wird gespeichert...</p>
          )}
        </CardContent>
      </Card>

      <div className="sticky bottom-4 z-10">
        <Button onClick={handleSave} disabled={saving} className="w-full shadow-lg">
          {saving ? 'Speichern...' : '💾 Alle Einstellungen speichern'}
        </Button>
      </div>

      {/* NC Folder Browser Dialog */}
      <Dialog
        open={showBrowser}
        onClose={() => setShowBrowser(false)}
        title={`Nextcloud-Ordner waehlen`}
        className="max-w-lg"
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-ink-light">
            <span>Pfad:</span>
            <span className="font-mono bg-surface-bg px-2 py-1 rounded">{browserPath}</span>
          </div>

          {/* Navigation */}
          {browserPath !== '/' && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const parent = browserPath.split('/').slice(0, -1).join('/') || '/'
                browseTo(parent)
              }}
            >
              &larr; Zurueck
            </Button>
          )}

          {browserLoading ? (
            <p className="text-sm text-ink-light py-4 text-center">Lade...</p>
          ) : (
            <div className="max-h-64 overflow-y-auto space-y-1">
              {browserEntries.length === 0 && (
                <p className="text-sm text-ink-muted py-4 text-center">Keine Unterordner</p>
              )}
              {browserEntries.map((entry) => (
                <div
                  key={entry.path}
                  className="flex items-center justify-between p-2 hover:bg-surface-bg rounded-lg"
                >
                  <button
                    onClick={() => browseTo(entry.path + '/')}
                    className="flex items-center gap-2 text-sm text-ink-light hover:text-primary-600"
                  >
                    <span>📁</span> {entry.name}
                  </button>
                  <Button size="sm" variant="secondary" onClick={() => selectFolder(entry.path)}>
                    Waehlen
                  </Button>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2 pt-2 border-t border-surface-border">
            <Button size="sm" onClick={() => selectFolder(browserPath.replace(/\/$/, ''))}>
              Diesen Ordner waehlen
            </Button>
            <Input
              placeholder="Neuer Pfad..."
              value={browserPath}
              onChange={(e) => setBrowserPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && selectFolder(browserPath.replace(/\/$/, ''))}
            />
          </div>
        </div>
      </Dialog>
    </div>
  )
}
