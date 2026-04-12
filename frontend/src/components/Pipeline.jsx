import { useState, useEffect, useRef } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Dialog } from './ui/Dialog'
import { Tabs } from './ui/Tabs'
import { Input, Select } from './ui/Input'
import { useApi } from '../hooks/useApi'
import { getItems, getItem, transcribeItem, analyzeItem, generateContent, syncTranscripts, updateAllViews, getPipelineProgress, getPipelineLog, getCookieStatus, batchTranscribe } from '../api'
import CookieSetup from './CookieSetup'

const statusLabels = {
  new: 'Neu',
  transcribing: 'Transkribiert...',
  transcribed: 'Transkribiert',
  needs_voicescriptor: 'Braucht VoiceScriptor',
  analyzing: 'Analysiert...',
  analyzed: 'Analysiert',
  generating: 'Generiert...',
  content_ready: 'Content fertig',
  approved: 'Freigegeben',
  published: 'Veroeffentlicht',
}

export default function Pipeline() {
  const [statusFilter, setStatusFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [sortField, setSortField] = useState('published_at')
  const [sortDir, setSortDir] = useState('desc')
  const [searchText, setSearchText] = useState('')
  const [showLog, setShowLog] = useState(false)
  const [showCookieSetup, setShowCookieSetup] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const autoRefreshRef = useRef(null)
  const { data: cookieStatus, refetch: refetchCookies } = useApi(getCookieStatus, [])
  const { data: progress, refetch: refetchProgress } = useApi(getPipelineProgress, [])
  const { data: activityLog, refetch: refetchLog } = useApi(() => getPipelineLog(30), [])
  const { data: items, loading, refetch } = useApi(
    () => getItems({ limit: 200, status: statusFilter || undefined, source_id: sourceFilter || undefined }),
    [statusFilter, sourceFilter]
  )
  const [selectedItem, setSelectedItem] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailTab, setDetailTab] = useState('info')
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkRunning, setBulkRunning] = useState(false)

  // Auto-refresh every 10s when batch is running or items are processing
  useEffect(() => {
    const hasProcessing = progress && progress.processing > 0
    if (batchRunning || hasProcessing) {
      autoRefreshRef.current = setInterval(() => {
        refetch()
        refetchProgress()
        refetchLog()
      }, 10000)
    }
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current) }
  }, [batchRunning, progress?.processing])

  const openDetail = async (item) => {
    setSelectedItem(item)
    setDetailTab('info')
    const full = await getItem(item.id)
    setDetail(full)
  }

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAllWithStatus = (status) => {
    const ids = (items || []).filter(i => i.status === status).map(i => i.id)
    setSelectedIds(new Set(ids))
  }

  const handleBulkTranscribe = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter(i => selectedIds.has(i.id) && (i.status === 'new' || i.status === 'needs_voicescriptor'))
    for (const item of targets) {
      try { await transcribeItem(item.id) } catch (e) { /* continue */ }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleBulkAnalyze = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter(i => selectedIds.has(i.id) && i.status === 'transcribed')
    for (const item of targets) {
      try { await analyzeItem(item.id) } catch (e) { /* continue */ }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleBulkGenerate = async () => {
    setBulkRunning(true)
    const targets = (items || []).filter(i => selectedIds.has(i.id) && i.status === 'analyzed')
    for (const item of targets) {
      try { await generateContent(item.id) } catch (e) { /* continue */ }
    }
    setSelectedIds(new Set())
    setBulkRunning(false)
    setTimeout(refetch, 2000)
  }

  const handleSyncTranscripts = async () => {
    const result = await syncTranscripts()
    alert(`Sync: ${result.synced} Transkripte zugeordnet (${result.checked} geprueft, ${result.available_transcripts} VoiceScriptor-Transkripte vorhanden)`)
    refetch()
  }

  const handleUpdateViews = async () => {
    await updateAllViews()
    alert('View-Update gestartet (laeuft im Hintergrund)')
  }

  if (loading) return <div className="text-gray-500">Lade Pipeline...</div>

  // Filter
  let filtered = [...(items || [])]
  if (searchText) {
    const q = searchText.toLowerCase()
    filtered = filtered.filter(i =>
      (i.title || '').toLowerCase().includes(q) ||
      (i.channel_name || '').toLowerCase().includes(q) ||
      (i.keywords || []).some(k => k.toLowerCase().includes(q))
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

  const newCount = (items || []).filter(i => i.status === 'new').length
  const transcribedCount = (items || []).filter(i => i.status === 'transcribed').length
  const analyzedCount = (items || []).filter(i => i.status === 'analyzed').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Pipeline</h2>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="secondary" onClick={handleSyncTranscripts}>Transkripte sync</Button>
          <Button size="sm" variant="secondary" onClick={handleUpdateViews}>Views aktualisieren</Button>
          <Button size="sm" onClick={async () => {
            setBatchRunning(true)
            try {
              await batchTranscribe()
              setShowLog(true)
            } catch (e) { alert('Fehler: ' + e.message) }
          }} disabled={batchRunning || newCount === 0}>
            {batchRunning ? 'Batch laeuft...' : `Alle transkribieren (${newCount})`}
          </Button>
          <Button size="sm" variant="secondary" onClick={handleBulkAnalyze} disabled={bulkRunning || selectedIds.size === 0}>Analysieren ({selectedIds.size})</Button>
          <Button size="sm" variant="secondary" onClick={handleBulkGenerate} disabled={bulkRunning || selectedIds.size === 0}>Content ({selectedIds.size})</Button>
          <Button size="sm" variant="ghost" onClick={() => { setSelectedIds(new Set()); refetch() }}>Aktualisieren</Button>
        </div>
      </div>

      {/* Progress Bar */}
      {progress && (
        <Card>
          <CardContent className="py-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex gap-4 text-xs">
                <span className="text-gray-500">Gesamt: <strong>{progress.total}</strong></span>
                <span className="text-blue-600">Neu: <strong>{progress.new}</strong></span>
                <span className="text-yellow-600">In Arbeit: <strong>{progress.processing}</strong></span>
                <span className="text-green-600">Fertig: <strong>{progress.done}</strong></span>
                {progress.failed > 0 && <span className="text-red-600">Fehler: <strong>{progress.failed}</strong></span>}
              </div>
              <Button size="sm" variant="ghost" onClick={() => { setShowLog(!showLog); if (!showLog) refetchLog() }}>
                {showLog ? 'Log ausblenden' : 'Activity Log'}
              </Button>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 flex overflow-hidden">
              {progress.percent_content > 0 && (
                <div className="bg-green-500 h-full transition-all" style={{width: `${progress.percent_content}%`}} title={`Content: ${progress.percent_content}%`} />
              )}
              {(progress.percent_analyzed - progress.percent_content) > 0 && (
                <div className="bg-purple-500 h-full transition-all" style={{width: `${progress.percent_analyzed - progress.percent_content}%`}} title={`Analysiert: ${progress.percent_analyzed}%`} />
              )}
              {(progress.percent_transcribed - progress.percent_analyzed) > 0 && (
                <div className="bg-blue-500 h-full transition-all" style={{width: `${progress.percent_transcribed - progress.percent_analyzed}%`}} title={`Transkribiert: ${progress.percent_transcribed}%`} />
              )}
            </div>
            <div className="flex gap-4 mt-1.5 text-[10px] text-gray-400">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block"></span> Transkribiert {progress.percent_transcribed}%</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500 inline-block"></span> Analysiert {progress.percent_analyzed}%</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block"></span> Content {progress.percent_content}%</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Cookie Status - always visible */}
      {cookieStatus && (() => {
        const isError = !cookieStatus.has_cookies
        const isWarning = cookieStatus.needs_refresh || cookieStatus.needs_voicescriptor_count > 10
        const isOk = cookieStatus.has_cookies && !cookieStatus.needs_refresh && cookieStatus.needs_voicescriptor_count <= 10
        const bg = isError ? 'bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700'
          : isWarning ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700'
          : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
        return (
          <div className={`border rounded-lg p-3 flex items-center justify-between ${bg}`}>
            <div>
              <p className={`text-sm font-medium ${isError ? 'text-red-800 dark:text-red-200' : isWarning ? 'text-amber-800 dark:text-amber-200' : 'text-gray-600 dark:text-gray-400'}`}>
                {cookieStatus.message}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {cookieStatus.needs_voicescriptor_count > 0 && `${cookieStatus.needs_voicescriptor_count} Videos warten auf Transkription. `}
                {cookieStatus.autopilot?.age_hours > 0 && `Alter: ${Math.round(cookieStatus.autopilot.age_hours)}h. `}
                {cookieStatus.voicescriptor?.exists && 'VoiceScriptor: sync. '}
                {!cookieStatus.voicescriptor?.exists && cookieStatus.has_cookies && 'VoiceScriptor: nicht sync! '}
              </p>
            </div>
            <Button size="sm" variant={isOk ? 'secondary' : 'primary'} onClick={() => setShowCookieSetup(true)}>
              {isError ? 'Cookies einrichten' : 'Cookies erneuern'}
            </Button>
          </div>
        )
      })()}

      {/* Cookie Setup Dialog */}
      <CookieSetup
        open={showCookieSetup}
        onClose={() => setShowCookieSetup(false)}
        onSaved={() => { refetchCookies(); refetchProgress() }}
      />

      {/* Activity Log */}
      {showLog && activityLog && (
        <Card>
          <CardHeader><CardTitle>Activity Log</CardTitle></CardHeader>
          <CardContent className="p-0 max-h-64 overflow-y-auto">
            {activityLog.length === 0 ? (
              <p className="p-4 text-sm text-gray-500">Noch keine Aktivitaeten.</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {activityLog.map(entry => (
                    <tr key={entry.id} className={`border-b border-gray-100 dark:border-gray-800 ${entry.is_error ? 'bg-red-50 dark:bg-red-900/10' : ''}`}>
                      <td className="px-4 py-2 text-xs text-gray-400 whitespace-nowrap">
                        {entry.updated_at ? new Date(entry.updated_at).toLocaleString('de-DE') : '-'}
                      </td>
                      <td className="px-4 py-2">
                        <span className="text-gray-700 dark:text-gray-300 line-clamp-1">{entry.title}</span>
                      </td>
                      <td className="px-4 py-2">
                        {entry.channel_name && <span className="text-xs text-gray-400">{entry.channel_name}</span>}
                      </td>
                      <td className="px-4 py-2">
                        <span className={`text-xs font-medium ${entry.is_error ? 'text-red-600' : entry.is_processing ? 'text-yellow-600' : 'text-green-600'}`}>
                          {entry.message}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-400">
                        {entry.transcript_source || ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Filters + Sort */}
      <div className="flex gap-4 flex-wrap items-end">
        <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} label="Status">
          <option value="">Alle</option>
          {Object.entries(statusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={sortField} onChange={e => setSortField(e.target.value)} label="Sortieren nach">
          <option value="published_at">Datum</option>
          <option value="title">Videoname</option>
          <option value="channel_name">Kanal</option>
          <option value="view_count">Views</option>
          <option value="trend_score">Trend</option>
        </Select>
        <Select value={sortDir} onChange={e => setSortDir(e.target.value)} label="Richtung">
          <option value="desc">Absteigend</option>
          <option value="asc">Aufsteigend</option>
        </Select>
        <div className="flex-1 min-w-[200px]">
          <Input label="Suche (Titel, Kanal, Schlagwoerter)" value={searchText}
            onChange={e => setSearchText(e.target.value)}
            placeholder="z.B. KI, Claude, Marketing..." />
        </div>
      </div>

      {/* Video List */}
      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-sm text-gray-500 dark:text-gray-400">
                <th className="px-3 py-3 w-8">
                  <input
                    type="checkbox"
                    onChange={e => {
                      if (e.target.checked) setSelectedIds(new Set(sortedItems.map(i => i.id)))
                      else setSelectedIds(new Set())
                    }}
                    checked={selectedIds.size > 0 && selectedIds.size === sortedItems.length}
                  />
                </th>
                <th className="px-3 py-3 font-medium w-16"></th>
                <th className="px-3 py-3 font-medium">Video</th>
                <th className="px-3 py-3 font-medium">Kanal</th>
                <th className="px-3 py-3 font-medium">Datum</th>
                <th className="px-3 py-3 font-medium">Views</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-3 py-3 font-medium">Schlagwoerter</th>
                <th className="px-3 py-3 font-medium">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map(item => (
                <tr key={item.id} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelect(item.id)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    {item.thumbnail_url && (
                      <img src={item.thumbnail_url} alt="" className="w-16 h-10 object-cover rounded" />
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <button onClick={() => openDetail(item)} className="text-left hover:text-primary-600">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1">{item.title || item.external_id}</p>
                      <p className="text-xs text-gray-400">{item.external_id}</p>
                    </button>
                  </td>
                  <td className="px-3 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {item.channel_name || '-'}
                  </td>
                  <td className="px-3 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {item.published_at ? new Date(item.published_at).toLocaleDateString('de-DE') : '-'}
                  </td>
                  <td className="px-3 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {item.view_count ? item.view_count.toLocaleString('de-DE') : '-'}
                  </td>
                  <td className="px-3 py-3">
                    <Badge status={item.status} />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1 max-w-[150px]">
                      {(item.keywords || []).slice(0, 3).map((k, i) => (
                        <span key={i} className="text-[10px] bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-1.5 py-0.5 rounded">{k}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex gap-1">
                      {item.status === 'new' && (
                        <Button size="sm" variant="secondary" onClick={async () => { await transcribeItem(item.id); setTimeout(refetch, 2000) }}>T</Button>
                      )}
                      {item.status === 'transcribed' && (
                        <Button size="sm" variant="secondary" onClick={async () => { await analyzeItem(item.id); setTimeout(refetch, 2000) }}>A</Button>
                      )}
                      {item.status === 'analyzed' && (
                        <Button size="sm" variant="secondary" onClick={async () => { await generateContent(item.id); setTimeout(refetch, 2000) }}>C</Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => openDetail(item)}>Details</Button>
                    </div>
                  </td>
                </tr>
              ))}
              {sortedItems.length === 0 && (
                <tr><td colSpan={9} className="px-6 py-8 text-center text-sm text-gray-500">Keine Videos. Gehe zu Quellen und importiere Kanaele.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <p className="text-xs text-gray-400">{sortedItems.length} Videos insgesamt</p>

      {/* Detail Dialog */}
      <Dialog
        open={!!selectedItem}
        onClose={() => { setSelectedItem(null); setDetail(null) }}
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
                  <div><span className="text-gray-500">Status:</span> <Badge status={detail.status} /></div>
                  <div><span className="text-gray-500">Quelle:</span> {detail.transcript_source || '-'}</div>
                  <div><span className="text-gray-500">Video-ID:</span> {detail.external_id}</div>
                  <div><span className="text-gray-500">Datum:</span> {detail.published_at ? new Date(detail.published_at).toLocaleDateString('de-DE') : '-'}</div>
                  <div><span className="text-gray-500">Dauer:</span> {detail.duration_seconds ? `${Math.floor(detail.duration_seconds / 60)} Min` : '-'}</div>
                </div>
                {detail.url && (
                  <a href={detail.url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary-600 hover:underline">Video ansehen</a>
                )}
                <div className="flex gap-2 pt-2">
                  {detail.status === 'new' && <Button size="sm" onClick={async () => { await transcribeItem(detail.id); alert('Transkription gestartet') }}>Transkribieren</Button>}
                  {detail.status === 'transcribed' && <Button size="sm" onClick={async () => { await analyzeItem(detail.id); alert('Analyse gestartet') }}>Analysieren</Button>}
                  {detail.status === 'analyzed' && <Button size="sm" onClick={async () => { await generateContent(detail.id); alert('Content-Generierung gestartet') }}>Content generieren</Button>}
                </div>
              </div>
            )}

            {detailTab === 'transcript' && (
              <div className="max-h-96 overflow-y-auto">
                {detail.transcript_text ? (
                  <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-800 p-4 rounded-lg">{detail.transcript_text.substring(0, 5000)}{detail.transcript_text.length > 5000 ? '\n\n[... gekuerzt ...]' : ''}</pre>
                ) : (
                  <p className="text-sm text-gray-500">Kein Transkript vorhanden.</p>
                )}
              </div>
            )}

            {detailTab === 'analysis' && (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {detail.analysis ? (
                  <>
                    {detail.analysis.topic_title && (
                      <div className="bg-primary-50 dark:bg-primary-900/20 p-3 rounded-lg">
                        <h4 className="text-sm font-bold text-primary-700 dark:text-primary-300">{detail.analysis.topic_title}</h4>
                        {detail.analysis.topic_pitch && (
                          <p className="text-sm text-primary-600 dark:text-primary-400 mt-1">{detail.analysis.topic_pitch}</p>
                        )}
                      </div>
                    )}
                    {detail.analysis.hashtags && detail.analysis.hashtags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {detail.analysis.hashtags.map((h, i) => (
                          <span key={i} className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-1 rounded-full font-medium">{h.startsWith('#') ? h : `#${h}`}</span>
                        ))}
                      </div>
                    )}
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Summary</h4>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{detail.analysis.summary}</p>
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Kernaussagen</h4>
                      <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 space-y-1">
                        {(detail.analysis.key_points || []).map((kp, i) => <li key={i}>{kp}</li>)}
                      </ul>
                    </div>
                    <div className="flex items-center gap-4">
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Trend-Score</h4>
                        <p className="text-2xl font-bold text-primary-600">{detail.analysis.trend_score}/10</p>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Tags</h4>
                        <div className="flex flex-wrap gap-1">
                          {(detail.analysis.tags || []).map((tag, i) => <Badge key={i} color="gray">{tag}</Badge>)}
                        </div>
                      </div>
                    </div>
                    {detail.analysis.content_angles && (
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Content-Winkel</h4>
                        <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 space-y-1">
                          {detail.analysis.content_angles.map((a, i) => <li key={i}>{a}</li>)}
                        </ul>
                      </div>
                    )}
                    {detail.analysis.fact_check && (
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Faktencheck</h4>
                        <div className="space-y-2">
                          {detail.analysis.fact_check.map((fc, i) => (
                            <div key={i} className="bg-gray-50 dark:bg-gray-800 p-2 rounded text-sm">
                              <p className="font-medium">{fc.claim}</p>
                              <Badge color={fc.status === 'confirmed' ? 'green' : fc.status === 'partially' ? 'yellow' : 'red'}>{fc.status}</Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-gray-500">Keine Analyse vorhanden.</p>
                )}
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  )
}
