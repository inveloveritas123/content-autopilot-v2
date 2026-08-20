// AUDITED-2026-08-14 (D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState, useEffect, useRef, useMemo } from 'react'
import { useToast } from './ui/Toast'
import TimeFilter from './TimeFilter'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Dialog } from './ui/Dialog'
import { Tabs } from './ui/Tabs'
import { Input, Select } from './ui/Input'
import { useApi } from '../hooks/useApi'
import {
  getItems,
  getItem,
  transcribeItem,
  analyzeItem,
  generateContent,
  syncTranscripts,
  updateAllViews,
  getPipelineProgress,
  getPipelineLog,
  getCookieStatus,
  batchTranscribe,
  retryTranscribe,
  bulkRetryFailed,
  bulkArchiveFailed,
  getSources,
  getActivityLog,
  getPipelineStatus,
  resetBudgetFlag,
  triggerAutoPipeline,
  queueAllAnalysis,
  resetStuckItems,
  getTranscribedBreakdown,
  analyzeAllSourceItems,
  archiveSourceItems,
} from '../api'
import CookieSetup from './CookieSetup'

const statusLabels = {
  new: 'Neu',
  transcribing: 'Transkribiert...',
  transcribed: 'Transkribiert',
  needs_voicescriptor: 'Fehler (alt)',
  transcription_failed: 'Transkription fehlgeschlagen',
  analyzing: 'Analysiert...',
  analyzed: 'Analysiert',
  generating: 'Generiert...',
  content_ready: 'Content fertig',
  processed: 'Verarbeitet (alt)',
  approved: 'Freigegeben',
  published: 'Veroeffentlicht',
}

export default function Pipeline() {
  const { toast } = useToast()
  const [statusFilter, setStatusFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [sourceTypeFilter, setSourceTypeFilter] = useState('')
  const [archivedFilter, setArchivedFilter] = useState('false')
  const [timeFilter, setTimeFilter] = useState({ period: 'last_30d' })
  const [sortField, setSortField] = useState('published_at')
  const [sortDir, setSortDir] = useState('desc')
  const [searchText, setSearchText] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showLog, setShowLog] = useState(false)
  const [logStatusGroup, setLogStatusGroup] = useState('')
  const [logSourceId, setLogSourceId] = useState('')
  const [logTimeFilter, setLogTimeFilter] = useState({ period: 'last_7d' })
  const [logEntries, setLogEntries] = useState([])
  const [logPage, setLogPage] = useState(0)
  const [logHasMore, setLogHasMore] = useState(true)
  const [logLoading, setLogLoading] = useState(false)
  const [sources, setSources] = useState([])
  const [showCookieSetup, setShowCookieSetup] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const autoRefreshRef = useRef(null)
  const { data: cookieStatus, refetch: refetchCookies } = useApi(getCookieStatus, [])
  const { data: pipelineStatus, refetch: refetchPipelineStatus } = useApi(getPipelineStatus, [])
  const {
    data: progress,
    refetch: refetchProgress,
    silentRefetch: silentRefetchProgress,
  } = useApi(getPipelineProgress, [])
  const {
    data: activityLog,
    refetch: refetchLog,
    silentRefetch: silentRefetchLog,
  } = useApi(() => getPipelineLog(30), [])
  const {
    data: items,
    loading,
    refetch,
    silentRefetch: silentRefetchItems,
  } = useApi(
    () =>
      getItems({
        limit: 200,
        status: statusFilter || undefined,
        source_id: sourceFilter || undefined,
        source_type: sourceTypeFilter || undefined,
        archived: archivedFilter || undefined,
        period: timeFilter.period || undefined,
        date_from: timeFilter.date_from,
        date_to: timeFilter.date_to,
        search: debouncedSearch || undefined,
      }),
    [statusFilter, sourceFilter, sourceTypeFilter, archivedFilter, timeFilter, debouncedSearch]
  )
  const [selectedItem, setSelectedItem] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailTab, setDetailTab] = useState('info')
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkRunning, setBulkRunning] = useState(false)
  const [transcribedBreakdown, setTranscribedBreakdown] = useState(null)
  const [breakdownLoading, setBreakdownLoading] = useState(false)

  // Debounce search text → trigger backend search after 400ms idle
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchText), 400)
    return () => clearTimeout(t)
  }, [searchText])

  // Auto-refresh every 15s when batch is running, items are processing, or transcribed items waiting
  useEffect(() => {
    const hasProcessing = progress && progress.processing > 0
    const hasWaiting = progress && (progress.by_status?.transcribed || 0) > 0
    if (batchRunning || hasProcessing || hasWaiting) {
      autoRefreshRef.current = setInterval(() => {
        silentRefetchItems()
        silentRefetchProgress()
        silentRefetchLog()
        refetchPipelineStatus()
      }, 15000)
    }
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [batchRunning, progress?.processing, progress?.by_status?.transcribed])

  // Load sources for filter dropdown
  useEffect(() => {
    getSources()
      .then((d) => setSources(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  // Load transcribed breakdown whenever pipeline status refreshes
  const loadBreakdown = () => {
    setBreakdownLoading(true)
    getTranscribedBreakdown()
      .then((d) => setTranscribedBreakdown(d))
      .catch(() => {})
      .finally(() => setBreakdownLoading(false))
  }
  useEffect(() => {
    loadBreakdown()
  }, [])

  // Reset and reload log when filters or visibility changes
  useEffect(() => {
    if (showLog) loadLog(true)
  }, [showLog, logStatusGroup, logSourceId, logTimeFilter])

  const openDetail = async (item) => {
    setSelectedItem(item)
    setDetailTab('info')
    const full = await getItem(item.id)
    setDetail(full)
  }

  async function loadLog(reset = false) {
    setLogLoading(true)
    const page = reset ? 0 : logPage
    const params = { limit: 30, offset: page * 30 }
    if (logStatusGroup) params.status_group = logStatusGroup
    if (logSourceId) params.source_id = logSourceId
    if (logTimeFilter.period && logTimeFilter.period !== 'all') params.period = logTimeFilter.period
    if (logTimeFilter.date_from) params.date_from = logTimeFilter.date_from
    if (logTimeFilter.date_to) params.date_to = logTimeFilter.date_to
    try {
      const data = await getActivityLog(params)
      if (reset) {
        setLogEntries(data)
        setLogPage(1)
      } else {
        setLogEntries((prev) => [...prev, ...data])
        setLogPage((p) => p + 1)
      }
      setLogHasMore(data.length === 30)
    } catch {}
    setLogLoading(false)
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAllWithStatus = (status) => {
    const ids = (items || []).filter((i) => i.status === status).map((i) => i.id)
    setSelectedIds(new Set(ids))
  }

  const handleBulkTranscribe = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter(
      (i) => selectedIds.has(i.id) && (i.status === 'new' || i.status === 'needs_voicescriptor')
    )
    for (const item of targets) {
      try {
        await transcribeItem(item.id)
      } catch (e) {
        /* continue */
      }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleBulkAnalyze = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter((i) => selectedIds.has(i.id) && i.status === 'transcribed')
    for (const item of targets) {
      try {
        await analyzeItem(item.id)
      } catch (e) {
        /* continue */
      }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleBulkGenerate = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter((i) => selectedIds.has(i.id) && i.status === 'analyzed')
    for (const item of targets) {
      try {
        await generateContent(item.id)
      } catch (e) {
        /* continue */
      }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleSyncTranscripts = async () => {
    const result = await syncTranscripts()
    toast.success(
      `Sync: ${result.synced} Transkripte zugeordnet (${result.checked} geprueft, ${result.available_transcripts} VoiceScriptor-Transkripte vorhanden)`
    )
    refetch()
  }

  const handleUpdateViews = async () => {
    await updateAllViews()
    toast.info('View-Update gestartet (laeuft im Hintergrund)')
  }

  if (loading) return <div className="text-ink-light">Lade Pipeline...</div>

  // Filter
  let filtered = [...(items || [])]
  if (searchText) {
    const q = searchText.toLowerCase()
    filtered = filtered.filter(
      (i) =>
        (i.title || '').toLowerCase().includes(q) ||
        (i.channel_name || '').toLowerCase().includes(q) ||
        (i.keywords || []).some((k) => k.toLowerCase().includes(q))
    )
  }
  // Sort
  const sortedItems = filtered.sort((a, b) => {
    let va, vb
    if (sortField === 'published_at') {
      va = a.published_at ? new Date(a.published_at).getTime() : 0
      vb = b.published_at ? new Date(b.published_at).getTime() : 0
    } else if (sortField === 'title') {
      va = (a.title || '').toLowerCase()
      vb = (b.title || '').toLowerCase()
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    } else if (sortField === 'channel_name') {
      va = (a.channel_name || '').toLowerCase()
      vb = (b.channel_name || '').toLowerCase()
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    } else if (sortField === 'view_count') {
      va = a.view_count || 0
      vb = b.view_count || 0
    } else if (sortField === 'trend_score') {
      va = a.trend_score || 0
      vb = b.trend_score || 0
    } else {
      va = a.created_at ? new Date(a.created_at).getTime() : 0
      vb = b.created_at ? new Date(b.created_at).getTime() : 0
    }
    return sortDir === 'asc' ? va - vb : vb - va
  })

  const newCount = (items || []).filter((i) => i.status === 'new').length
  const transcribedCount = (items || []).filter((i) => i.status === 'transcribed').length
  const analyzedCount = (items || []).filter((i) => i.status === 'analyzed').length
  const failedCount = (items || []).filter(
    (i) => i.status === 'transcription_failed' || i.status === 'needs_voicescriptor'
  ).length

  return (
    <div className="space-y-6">
      {pipelineStatus?.llm_budget_exceeded && (
        <div className="p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-sm flex items-start gap-3">
          <span className="text-status-fehler-text shrink-0 mt-0.5">🔴</span>
          <div className="flex-1">
            <span className="font-semibold text-status-fehler-text">
              KI-Pipeline pausiert: Guthaben beim KI-Anbieter erschöpft.
            </span>
            <span className="text-status-fehler-text ml-1">
              Analyse und Content-Generierung sind gestoppt. Bitte bei{' '}
              <a
                href="https://requesty.ai"
                target="_blank"
                rel="noopener noreferrer"
                className="underline font-medium"
              >
                requesty.ai
              </a>{' '}
              Guthaben aufladen.
              {pipelineStatus.llm_budget_pause_seconds > 0 &&
                ` Automatische Wiederaufnahme in ~${Math.ceil(pipelineStatus.llm_budget_pause_seconds / 60)} Min.`}
            </span>
            {(() => {
              const waiting =
                (pipelineStatus.counts?.transcribed || 0) + (pipelineStatus.counts?.analyzed || 0)
              if (waiting === 0) return null
              const minCost = (waiting * 0.0005).toFixed(2)
              const maxCost = (waiting * 0.003).toFixed(2)
              return (
                <div className="mt-1.5 text-status-fehler-text">
                  <span className="font-medium">{waiting.toLocaleString('de-DE')} Artikel</span>{' '}
                  warten auf Verarbeitung — geschaetzte Kosten:{' '}
                  <span className="font-medium">
                    ${minCost}–${maxCost}
                  </span>{' '}
                  (je nach Modell).
                </div>
              )
            })()}
          </div>
          <div className="flex flex-col gap-1.5 shrink-0">
            <button
              className="px-3 py-1 bg-status-fehler-bg hover:bg-status-fehler-bg text-white text-xs font-semibold rounded-lg transition-colors"
              onClick={async () => {
                try {
                  await resetBudgetFlag()
                  await triggerAutoPipeline()
                  refetchPipelineStatus()
                  refetchProgress()
                } catch (e) {
                  toast.error('Fehler: ' + e.message)
                }
              }}
              title="Flag löschen + 100 Items starten"
            >
              ▶ Fortsetzen (100)
            </button>
            <button
              className="px-3 py-1 bg-status-fehler-bg hover:bg-status-fehler-bg text-white text-xs font-semibold rounded-lg transition-colors"
              onClick={async () => {
                try {
                  const breakdown = await getTranscribedBreakdown()
                  const lines = breakdown.sources
                    .map((s) => `  ${s.name}: ${s.count.toLocaleString('de-DE')} Items`)
                    .join('\n')
                  const minCost = (breakdown.total * 0.0005).toFixed(2)
                  const maxCost = (breakdown.total * 0.003).toFixed(2)
                  if (
                    !window.confirm(
                      `Alle ${breakdown.total.toLocaleString('de-DE')} Items in Analyse-Queue einreihen?\n\nQuellenaufschlüsselung:\n${lines}\n\nGeschätzte Kosten: $${minCost}–$${maxCost}\n\nTipp: In den Quellen einen "Analyse (N)" Button klicken um nur eine Quelle zu verarbeiten.`
                    )
                  )
                    return
                  await resetBudgetFlag()
                  const r = await queueAllAnalysis()
                  toast.success(`${r.queued} Items eingereiht!`)
                  refetchPipelineStatus()
                  refetchProgress()
                } catch (e) {
                  toast.error('Fehler: ' + e.message)
                }
              }}
              title="Alle transkribierten Items auf einmal in die Queue (zeigt Aufschlüsselung)"
            >
              ⚡ Alle einreihen
            </button>
          </div>
        </div>
      )}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold text-ink dark:text-white">Pipeline</h2>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="secondary" onClick={handleSyncTranscripts}>
            Transkripte sync
          </Button>
          <Button size="sm" variant="secondary" onClick={handleUpdateViews}>
            Views aktualisieren
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={async () => {
              try {
                const r = await resetStuckItems()
                if (r.reset > 0) {
                  toast.success(`${r.reset} feststeckende Items zurückgesetzt.`)
                  refetch()
                } else toast.info('Keine feststeckenden Items gefunden.')
              } catch (e) {
                toast.error('Fehler: ' + e.message)
              }
            }}
            title="Items die >15min in 'transcribing/analyzing/generating' stecken zurücksetzen"
          >
            Stuck reset
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              setBatchRunning(true)
              try {
                await batchTranscribe()
                setShowLog(true)
              } catch (e) {
                toast.error('Fehler: ' + e.message)
              }
            }}
            disabled={batchRunning || newCount === 0}
          >
            {batchRunning ? 'Batch laeuft...' : `Alle transkribieren (${newCount})`}
          </Button>
          {failedCount > 0 && (
            <>
              <Button
                size="sm"
                variant="danger"
                onClick={async () => {
                  if (!confirm(`${failedCount} fehlgeschlagene Transkriptionen neu starten?`))
                    return
                  try {
                    const r = await bulkRetryFailed()
                    toast.success(`${r.retried} Items zurückgesetzt und neu gestartet.`)
                    setTimeout(refetch, 1500)
                  } catch (e) {
                    toast.error('Fehler: ' + e.message)
                  }
                }}
              >
                Retry Fehler ({failedCount})
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  if (
                    !confirm(
                      `${failedCount} dauerhaft fehlgeschlagene Items archivieren? (z.B. Spotify-Podcasts ohne Audio-Zugriff)\n\nSie bleiben in der DB, erscheinen aber nicht mehr in der Pipeline.`
                    )
                  )
                    return
                  try {
                    const r = await bulkArchiveFailed()
                    toast.success(r.message)
                    setTimeout(refetch, 1500)
                  } catch (e) {
                    toast.error('Fehler: ' + e.message)
                  }
                }}
              >
                Archivieren ({failedCount})
              </Button>
            </>
          )}
          <Button
            size="sm"
            variant="secondary"
            onClick={handleBulkAnalyze}
            disabled={bulkRunning || selectedIds.size === 0}
          >
            Analysieren ({selectedIds.size})
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleBulkGenerate}
            disabled={bulkRunning || selectedIds.size === 0}
          >
            Content ({selectedIds.size})
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setSelectedIds(new Set())
              refetch()
            }}
          >
            Aktualisieren
          </Button>
        </div>
      </div>

      {/* Progress Bar */}
      {progress && (
        <Card>
          <CardContent className="py-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex gap-4 text-xs">
                <span className="text-ink-light">
                  Gesamt: <strong>{progress.total}</strong>
                </span>
                <span className="text-primary-600">
                  Neu: <strong>{progress.new}</strong>
                </span>
                <span className="text-accent-600">
                  In Arbeit: <strong>{progress.processing}</strong>
                </span>
                <span className="text-status-fertig-text">
                  Fertig: <strong>{progress.done}</strong>
                </span>
                {progress.failed > 0 && (
                  <span className="text-status-fehler-text">
                    Fehler: <strong>{progress.failed}</strong>
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowLog(!showLog)
                  if (!showLog) refetchLog()
                }}
              >
                {showLog ? 'Log ausblenden' : 'Activity Log'}
              </Button>
            </div>
            <div className="w-full bg-surface-bg dark:bg-surface-card rounded-full h-3 flex overflow-hidden">
              {progress.percent_content > 0 && (
                <div
                  className="bg-status-fertig-bg h-full transition-all"
                  style={{ width: `${progress.percent_content}%` }}
                  title={`Content: ${progress.percent_content}%`}
                />
              )}
              {progress.percent_analyzed - progress.percent_content > 0 && (
                <div
                  className="bg-accent-500 h-full transition-all"
                  style={{ width: `${progress.percent_analyzed - progress.percent_content}%` }}
                  title={`Analysiert: ${progress.percent_analyzed}%`}
                />
              )}
              {progress.percent_transcribed - progress.percent_analyzed > 0 && (
                <div
                  className="bg-primary-500 h-full transition-all"
                  style={{ width: `${progress.percent_transcribed - progress.percent_analyzed}%` }}
                  title={`Transkribiert: ${progress.percent_transcribed}%`}
                />
              )}
            </div>
            <div className="flex gap-4 mt-1.5 text-[10px] text-ink-light">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-primary-500 inline-block"></span>{' '}
                Transkribiert {progress.percent_transcribed}%
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-accent-500 inline-block"></span> Analysiert{' '}
                {progress.percent_analyzed}%
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-status-fertig-bg inline-block"></span>{' '}
                Content {progress.percent_content}%
              </span>
              {pipelineStatus?.eta_hours > 0 && (
                <span className="flex items-center gap-1 ml-auto text-ink-light">
                  {pipelineStatus.throughput_per_hour >= 5
                    ? `⏱ ~${pipelineStatus.eta_hours}h bis fertig · ${pipelineStatus.throughput_per_hour}/h`
                    : `⏱ ~${pipelineStatus.eta_hours}h bis fertig (geschätzt)`}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Warteschlangen-Analyse: per-source transcribed breakdown */}
      {transcribedBreakdown && transcribedBreakdown.total > 0 && (
        <div className="rounded-xl border border-accent-200 bg-accent-50 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-accent-600 text-base">⏳</span>
              <span className="font-semibold text-sm text-accent-900">
                Warteschlange: {transcribedBreakdown.total.toLocaleString('de-DE')} Items warten auf
                Analyse
              </span>
              <span className="text-xs text-accent-700">
                (~${(transcribedBreakdown.total * 0.0005).toFixed(2)}–$
                {(transcribedBreakdown.total * 0.003).toFixed(2)} geschätzte Kosten)
              </span>
            </div>
            <button
              onClick={loadBreakdown}
              className="text-xs text-accent-600 hover:text-accent-800 underline"
              disabled={breakdownLoading}
            >
              {breakdownLoading ? '...' : 'Aktualisieren'}
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-accent-700 border-b border-accent-200">
                  <th className="text-left pb-1.5 font-medium">Quelle</th>
                  <th className="text-right pb-1.5 font-medium pr-3">Wartend</th>
                  <th className="text-right pb-1.5 font-medium pr-3">Min. Kosten</th>
                  <th className="pb-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {transcribedBreakdown.sources.map((src) => (
                  <tr key={src.id} className="border-b border-accent-100 last:border-0">
                    <td className="py-1.5 text-accent-900 font-medium truncate max-w-[200px]">
                      {src.name}
                    </td>
                    <td className="py-1.5 text-right pr-3 text-accent-800 font-mono">
                      {src.count.toLocaleString('de-DE')}
                    </td>
                    <td className="py-1.5 text-right pr-3 text-accent-700">
                      ${(src.count * 0.0005).toFixed(2)}
                    </td>
                    <td className="py-1.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={async () => {
                            if (
                              !window.confirm(
                                `${src.count} Items von "${src.name}" in Analyse-Queue einreihen?\n\nGeschätzte Kosten: $${(src.count * 0.0005).toFixed(2)}–$${(src.count * 0.003).toFixed(2)}`
                              )
                            )
                              return
                            try {
                              const r = await queueAllAnalysis(src.id)
                              toast.success(`${r.queued} Items eingereiht!`)
                              loadBreakdown()
                              refetchPipelineStatus()
                            } catch (e) {
                              toast.error('Fehler: ' + e.message)
                            }
                          }}
                          className="px-2 py-0.5 text-xs bg-status-fertig-bg hover:bg-status-fertig-bg text-white rounded font-medium transition-colors"
                          title="Items dieser Quelle analysieren"
                        >
                          Analyse starten
                        </button>
                        {src.count > 50 && (
                          <button
                            onClick={async () => {
                              if (
                                !window.confirm(
                                  `Alle ${src.count} Items von "${src.name}" archivieren?\n\nDie Items bleiben in der DB, werden aber nicht mehr verarbeitet.`
                                )
                              )
                                return
                              try {
                                const r = await archiveSourceItems(src.id)
                                toast.success(
                                  r.archived > 0
                                    ? `${r.archived} Items archiviert.`
                                    : 'Keine Items archiviert.'
                                )
                                loadBreakdown()
                                refetchPipelineStatus()
                                refetchProgress()
                              } catch (e) {
                                toast.error('Fehler: ' + e.message)
                              }
                            }}
                            className="px-2 py-0.5 text-xs bg-accent-500 hover:bg-accent-600 text-white rounded font-medium transition-colors"
                            title="Items dieser Quelle archivieren (aus Pipeline entfernen)"
                          >
                            Archivieren
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cookie Status - always visible */}
      {cookieStatus &&
        (() => {
          const isError = !cookieStatus.has_cookies
          const isWarning =
            cookieStatus.needs_refresh || cookieStatus.needs_voicescriptor_count > 10
          const isOk =
            cookieStatus.has_cookies &&
            !cookieStatus.needs_refresh &&
            cookieStatus.needs_voicescriptor_count <= 10
          const bg = isError
            ? 'bg-status-fehler-bg dark:bg-status-fehler-bg/20 border-status-fehler-border dark:border-status-fehler-border'
            : isWarning
              ? 'bg-accent-50 dark:bg-accent-900/20 border-accent-300 dark:border-accent-700'
              : 'bg-surface-bg dark:bg-surface-card/50 border-surface-border dark:border-surface-border'
          return (
            <div className={`border rounded-lg p-3 flex items-center justify-between ${bg}`}>
              <div>
                <p
                  className={`text-sm font-medium ${isError ? 'text-status-fehler-text dark:text-status-fehler-text' : isWarning ? 'text-accent-800 dark:text-accent-200' : 'text-ink-light dark:text-ink-muted'}`}
                >
                  {cookieStatus.message}
                </p>
                <p className="text-xs text-ink-light mt-0.5">
                  {cookieStatus.needs_voicescriptor_count > 0 &&
                    `${cookieStatus.needs_voicescriptor_count} Videos warten auf Transkription. `}
                  {cookieStatus.autopilot?.age_hours > 0 &&
                    `Alter: ${Math.round(cookieStatus.autopilot.age_hours)}h. `}
                  {cookieStatus.voicescriptor?.exists && 'VoiceScriptor: sync. '}
                  {!cookieStatus.voicescriptor?.exists &&
                    cookieStatus.has_cookies &&
                    'VoiceScriptor: nicht sync! '}
                </p>
              </div>
              <Button
                size="sm"
                variant={isOk ? 'secondary' : 'primary'}
                onClick={() => setShowCookieSetup(true)}
              >
                {isError ? 'Cookies einrichten' : 'Cookies erneuern'}
              </Button>
            </div>
          )
        })()}

      {/* Cookie Setup Dialog */}
      <CookieSetup
        open={showCookieSetup}
        onClose={() => setShowCookieSetup(false)}
        onSaved={() => {
          refetchCookies()
          refetchProgress()
        }}
      />

      {/* Activity Log */}
      {showLog && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle>Activity Log</CardTitle>
              <span className="text-xs text-ink-light">{logEntries.length} Einträge</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Filters */}
            <div className="flex flex-wrap gap-2 items-center">
              {/* Status group chips */}
              {[
                { value: '', label: 'Alle' },
                { value: 'success', label: '✅ Erfolgreich' },
                { value: 'error', label: '❌ Fehler' },
                { value: 'processing', label: '⏳ In Arbeit' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setLogStatusGroup(opt.value)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${logStatusGroup === opt.value ? 'bg-primary-700 text-white border-primary-700' : 'bg-white text-ink-light border-surface-border hover:border-primary-300'}`}
                >
                  {opt.label}
                </button>
              ))}
              {/* Source filter */}
              <select
                value={logSourceId}
                onChange={(e) => setLogSourceId(e.target.value)}
                className="px-2.5 py-1 text-xs border border-surface-border rounded-lg bg-white text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-400"
              >
                <option value="">Alle Quellen</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            {/* Time filter */}
            <TimeFilter
              value={logTimeFilter}
              onChange={(v) => setLogTimeFilter(v)}
              label="Zeitraum"
            />
            {/* Log table */}
            <div className="max-h-[480px] overflow-y-auto rounded border border-surface-border">
              {logLoading && logEntries.length === 0 ? (
                <p className="p-4 text-sm text-ink-light">Lade...</p>
              ) : logEntries.length === 0 ? (
                <p className="p-4 text-sm text-ink-light">
                  Keine Einträge in diesem Zeitraum / Filter.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <tbody>
                    {logEntries.map((entry) => (
                      <tr
                        key={entry.id}
                        className={`border-b border-surface-border hover:bg-surface-bg ${entry.is_error ? 'bg-status-fehler-bg' : ''}`}
                      >
                        <td className="px-3 py-2 text-xs text-ink-light whitespace-nowrap">
                          {entry.updated_at
                            ? new Date(entry.updated_at).toLocaleString('de-DE', {
                                day: '2-digit',
                                month: '2-digit',
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : '-'}
                        </td>
                        <td className="px-3 py-2 max-w-[260px]">
                          <span className="text-ink line-clamp-1 text-xs">{entry.title}</span>
                        </td>
                        <td className="px-3 py-2 text-xs text-ink-light whitespace-nowrap">
                          {entry.source_name || entry.channel_name || ''}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`text-xs font-medium ${entry.is_error ? 'text-status-fehler-text' : entry.is_processing ? 'text-accent-600' : 'text-status-fertig-text'}`}
                          >
                            {entry.is_error ? '❌' : entry.is_processing ? '⏳' : '✅'}{' '}
                            {entry.message}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {/* Load more */}
            {logHasMore && (
              <button
                onClick={() => loadLog(false)}
                disabled={logLoading}
                className="w-full py-2 text-xs font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50 disabled:opacity-50"
              >
                {logLoading ? 'Lade...' : '↓ Mehr laden'}
              </button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Filters + Sort */}
      <div className="flex gap-4 flex-wrap items-end">
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          label="Status"
        >
          <option value="">Alle</option>
          {Object.entries(statusLabels).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select
          value={sourceTypeFilter}
          onChange={(e) => setSourceTypeFilter(e.target.value)}
          label="Quellentyp"
        >
          <option value="">Alle Typen</option>
          <option value="youtube">YouTube</option>
          <option value="rss">RSS</option>
          <option value="podcast">Podcast</option>
          <option value="web">Webseite</option>
        </Select>
        <Select
          value={archivedFilter}
          onChange={(e) => setArchivedFilter(e.target.value)}
          label="Archiv"
        >
          <option value="false">Nur aktive</option>
          <option value="true">Nur archivierte</option>
          <option value="all">Alle</option>
        </Select>
        <Select value={sortField} onChange={(e) => setSortField(e.target.value)} label="Sortieren">
          <option value="published_at">Datum</option>
          <option value="title">Titel</option>
          <option value="channel_name">Quelle</option>
          <option value="view_count">Views</option>
          <option value="trend_score">Trend</option>
        </Select>
        <Select value={sortDir} onChange={(e) => setSortDir(e.target.value)} label="Richtung">
          <option value="desc">Absteigend</option>
          <option value="asc">Aufsteigend</option>
        </Select>
        <div className="flex-1 min-w-[200px]">
          <Input
            label="Suche"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Titel, Kanal, Schlagwoerter..."
          />
        </div>
      </div>
      <div className="mt-2 px-1">
        <TimeFilter
          value={timeFilter}
          onChange={setTimeFilter}
          count={filtered.length}
          label="Zeitraum"
        />
      </div>

      {/* Video List */}
      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b border-surface-border dark:border-surface-border text-left text-sm text-ink-light dark:text-ink-muted">
                <th className="px-3 py-3 w-8">
                  <input
                    type="checkbox"
                    onChange={(e) => {
                      if (e.target.checked) setSelectedIds(new Set(sortedItems.map((i) => i.id)))
                      else setSelectedIds(new Set())
                    }}
                    checked={selectedIds.size > 0 && selectedIds.size === sortedItems.length}
                  />
                </th>
                <th className="px-3 py-3 font-medium w-16"></th>
                <th className="px-3 py-3 font-medium">Video</th>
                <th className="px-3 py-3 font-medium">Kanal</th>
                <th className="px-3 py-3 font-medium">Quelle</th>
                <th className="px-3 py-3 font-medium">Datum</th>
                <th className="px-3 py-3 font-medium">Views</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-3 py-3 font-medium">Schlagwoerter</th>
                <th className="px-3 py-3 font-medium">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-surface-border dark:border-surface-border hover:bg-surface-bg dark:hover:bg-surface-card/50"
                >
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelect(item.id)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    {item.thumbnail_url && (
                      <img
                        src={item.thumbnail_url}
                        alt=""
                        className="w-16 h-10 object-cover rounded"
                      />
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <button
                      onClick={() => openDetail(item)}
                      className="text-left hover:text-primary-600"
                    >
                      <p className="text-sm font-medium text-ink dark:text-ink-muted line-clamp-1">
                        {item.title || item.external_id}
                      </p>
                      <p className="text-xs text-ink-light">{item.external_id}</p>
                    </button>
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-light whitespace-nowrap">
                    {item.channel_name || '-'}
                  </td>
                  <td className="px-3 py-3 text-xs whitespace-nowrap">
                    {(() => {
                      const src = sources.find((s) => s.id === item.source_id)
                      if (!src) return <span className="text-ink-light">—</span>
                      const icons = { youtube: '📺', rss: '📰', podcast: '🎙️', web: '🌐' }
                      return (
                        <span className="flex items-center gap-1 text-ink-light">
                          <span>{icons[src.type] || '📄'}</span>
                          <span className="max-w-[120px] truncate">{src.name}</span>
                        </span>
                      )
                    })()}
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-light whitespace-nowrap">
                    {item.published_at
                      ? new Date(item.published_at).toLocaleDateString('de-DE')
                      : '-'}
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-light whitespace-nowrap">
                    {item.view_count ? item.view_count.toLocaleString('de-DE') : '-'}
                  </td>
                  <td className="px-3 py-3">
                    <Badge status={item.status} />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1 max-w-[150px]">
                      {(item.keywords || []).length > 0 ? (
                        (item.keywords || []).slice(0, 3).map((k, i) => (
                          <span
                            key={i}
                            className="text-[10px] bg-surface-bg dark:bg-surface-card text-ink-light dark:text-ink-muted px-1.5 py-0.5 rounded"
                          >
                            {k}
                          </span>
                        ))
                      ) : ['new', 'transcribed', 'transcription_failed', 'content_ready'].includes(
                          item.status
                        ) ? (
                        <span className="text-[10px] text-ink-light italic">
                          Analyse ausstehend
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex gap-1">
                      {item.status === 'new' && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={async () => {
                            await transcribeItem(item.id)
                            setTimeout(refetch, 2000)
                          }}
                        >
                          T
                        </Button>
                      )}
                      {item.status === 'transcribed' && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={async () => {
                            await analyzeItem(item.id)
                            setTimeout(refetch, 2000)
                          }}
                        >
                          A
                        </Button>
                      )}
                      {item.status === 'analyzed' && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={async () => {
                            await generateContent(item.id)
                            setTimeout(refetch, 2000)
                          }}
                        >
                          C
                        </Button>
                      )}
                      {(item.status === 'transcription_failed' ||
                        item.status === 'needs_voicescriptor') && (
                        <Button
                          size="sm"
                          variant="danger"
                          title="Erneut versuchen (4-Stufen-Fallback)"
                          onClick={async () => {
                            await retryTranscribe(item.id)
                            setTimeout(refetch, 2000)
                          }}
                        >
                          ↺
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => openDetail(item)}>
                        Details
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {sortedItems.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-6 py-8 text-center text-sm text-ink-light">
                    Keine Videos. Gehe zu Quellen und importiere Kanaele.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <p className="text-xs text-ink-light">{sortedItems.length} Videos insgesamt</p>

      {/* Detail Dialog */}
      <Dialog
        open={!!selectedItem}
        onClose={() => {
          setSelectedItem(null)
          setDetail(null)
        }}
        title={detail?.title || 'Details'}
        className="max-w-2xl"
      >
        {detail && (
          <div className="space-y-4">
            <Tabs
              tabs={[
                { id: 'info', label: 'Info' },
                { id: 'transcript', label: 'Transkript' },
                { id: 'analysis', label: 'Analyse' },
              ]}
              active={detailTab}
              onChange={setDetailTab}
            />

            {detailTab === 'info' && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-ink-light">Status:</span> <Badge status={detail.status} />
                  </div>
                  <div>
                    <span className="text-ink-light">Quelle:</span>{' '}
                    {detail.transcript_source || '-'}
                  </div>
                  <div>
                    <span className="text-ink-light">Video-ID:</span> {detail.external_id}
                  </div>
                  <div>
                    <span className="text-ink-light">Datum:</span>{' '}
                    {detail.published_at
                      ? new Date(detail.published_at).toLocaleDateString('de-DE')
                      : '-'}
                  </div>
                  <div>
                    <span className="text-ink-light">Dauer:</span>{' '}
                    {detail.duration_seconds
                      ? `${Math.floor(detail.duration_seconds / 60)} Min`
                      : '-'}
                  </div>
                </div>
                {detail.url && (
                  <a
                    href={detail.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:underline"
                  >
                    Video ansehen
                  </a>
                )}
                <div className="flex gap-2 pt-2">
                  {detail.status === 'new' && (
                    <Button
                      size="sm"
                      onClick={async () => {
                        await transcribeItem(detail.id)
                        toast.info('Transkription gestartet')
                      }}
                    >
                      Transkribieren
                    </Button>
                  )}
                  {detail.status === 'transcribed' && (
                    <Button
                      size="sm"
                      onClick={async () => {
                        await analyzeItem(detail.id)
                        toast.info('Analyse gestartet')
                      }}
                    >
                      Analysieren
                    </Button>
                  )}
                  {detail.status === 'analyzed' && (
                    <Button
                      size="sm"
                      onClick={async () => {
                        await generateContent(detail.id)
                        toast.info('Content-Generierung gestartet')
                      }}
                    >
                      Content generieren
                    </Button>
                  )}
                  {(detail.status === 'transcription_failed' ||
                    detail.status === 'needs_voicescriptor') && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={async () => {
                        await retryTranscribe(detail.id)
                        toast.info('Retry gestartet (4-Stufen-Fallback)')
                      }}
                    >
                      Erneut versuchen
                    </Button>
                  )}
                </div>
              </div>
            )}

            {detailTab === 'transcript' && (
              <div className="max-h-[600px] overflow-y-auto">
                {detail.transcript_text ? (
                  <>
                    <div className="mb-2 text-xs text-ink-light">
                      {detail.transcript_text.length.toLocaleString()} Zeichen
                    </div>
                    <pre className="text-sm text-ink dark:text-ink-muted whitespace-pre-wrap font-mono bg-surface-bg dark:bg-surface-card p-4 rounded-lg">
                      {detail.transcript_text}
                    </pre>
                  </>
                ) : (
                  <p className="text-sm text-ink-light">Kein Transkript vorhanden.</p>
                )}
              </div>
            )}

            {detailTab === 'analysis' && (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {detail.analysis ? (
                  <>
                    {detail.analysis.topic_title && (
                      <div className="bg-primary-50 dark:bg-primary-900/20 p-3 rounded-lg">
                        <h4 className="text-sm font-bold text-primary-700 dark:text-primary-300">
                          {detail.analysis.topic_title}
                        </h4>
                        {detail.analysis.topic_pitch && (
                          <p className="text-sm text-primary-600 dark:text-primary-400 mt-1">
                            {detail.analysis.topic_pitch}
                          </p>
                        )}
                      </div>
                    )}
                    {detail.analysis.hashtags && detail.analysis.hashtags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {detail.analysis.hashtags.map((h, i) => (
                          <span
                            key={i}
                            className="text-xs bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300 px-2 py-1 rounded-full font-medium"
                          >
                            {h.startsWith('#') ? h : `#${h}`}
                          </span>
                        ))}
                      </div>
                    )}
                    <div>
                      <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                        Summary
                      </h4>
                      <p className="text-sm text-ink-light dark:text-ink-muted">
                        {detail.analysis.summary}
                      </p>
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                        Kernaussagen
                      </h4>
                      <ul className="list-disc list-inside text-sm text-ink-light dark:text-ink-muted space-y-1">
                        {(detail.analysis.key_points || []).map((kp, i) => (
                          <li key={i}>{kp}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="flex items-center gap-4">
                      <div>
                        <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                          Trend-Score
                        </h4>
                        <p className="text-2xl font-bold text-primary-600">
                          {detail.analysis.trend_score}/10
                        </p>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                          Tags
                        </h4>
                        <div className="flex flex-wrap gap-1">
                          {(detail.analysis.tags || []).map((tag, i) => (
                            <Badge key={i} color="gray">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                    {detail.analysis.content_angles && (
                      <div>
                        <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                          Content-Winkel
                        </h4>
                        <ul className="list-disc list-inside text-sm text-ink-light dark:text-ink-muted space-y-1">
                          {detail.analysis.content_angles.map((a, i) => (
                            <li key={i}>{a}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {detail.analysis.fact_check && (
                      <div>
                        <h4 className="text-sm font-semibold text-ink dark:text-ink-muted mb-1">
                          Faktencheck
                        </h4>
                        <div className="space-y-2">
                          {detail.analysis.fact_check.map((fc, i) => (
                            <div
                              key={i}
                              className="bg-surface-bg dark:bg-surface-card p-2 rounded text-sm"
                            >
                              <p className="font-medium">{fc.claim}</p>
                              <Badge
                                color={
                                  fc.status === 'confirmed'
                                    ? 'green'
                                    : fc.status === 'partially'
                                      ? 'yellow'
                                      : 'red'
                                }
                              >
                                {fc.status}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-ink-light">Keine Analyse vorhanden.</p>
                )}
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  )
}
