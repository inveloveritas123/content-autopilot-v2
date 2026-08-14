import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Tabs } from './ui/Tabs'
import { Textarea } from './ui/Input'
import { useApi } from '../hooks/useApi'
import { getContentList, getItems, updateContent, approveContent } from '../api'

const channelTabs = [
  { id: 'topics', label: 'Themen-Vorschlaege' },
  { id: 'all', label: 'Alle' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'blog', label: 'Blog' },
  { id: 'newsletter', label: 'Newsletter' },
]

export default function ContentPreview() {
  const [activeChannel, setActiveChannel] = useState('topics')
  const {
    data: content,
    loading: contentLoading,
    refetch: refetchContent,
  } = useApi(
    () =>
      activeChannel !== 'topics'
        ? getContentList({ channel: activeChannel === 'all' ? undefined : activeChannel })
        : Promise.resolve([]),
    [activeChannel]
  )
  const { data: analyzedItems, loading: itemsLoading } = useApi(
    () =>
      activeChannel === 'topics'
        ? getItems({ status: 'analyzed', limit: 50 })
        : Promise.resolve([]),
    [activeChannel]
  )
  const { data: contentReadyItems } = useApi(
    () =>
      activeChannel === 'topics'
        ? getItems({ status: 'content_ready', limit: 50 })
        : Promise.resolve([]),
    [activeChannel]
  )
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')

  const handleEdit = (piece) => {
    setEditingId(piece.id)
    setEditText(piece.content_text)
  }

  const handleSave = async (id) => {
    await updateContent(id, { content_text: editText })
    setEditingId(null)
    refetchContent()
  }

  const handleApprove = async (id) => {
    await approveContent(id)
    refetchContent()
  }

  const loading = contentLoading || itemsLoading

  if (loading) return <div className="text-ink-light">Lade Content...</div>

  // Merge analyzed + content_ready items for topic view
  const topicItems = [...(analyzedItems || []), ...(contentReadyItems || [])]
    .filter((i) => i.has_analysis)
    .sort((a, b) => (b.trend_score || 0) - (a.trend_score || 0))

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-ink">Content</h2>

      <Tabs tabs={channelTabs} active={activeChannel} onChange={setActiveChannel} />

      {/* Topic Suggestions View */}
      {activeChannel === 'topics' && (
        <div className="space-y-4 mt-4">
          {topicItems.length === 0 && (
            <p className="text-sm text-ink-light">
              Keine analysierten Videos vorhanden. Analysiere Videos in der Pipeline um
              Themen-Vorschlaege zu erhalten.
            </p>
          )}
          {topicItems.map((item) => (
            <Card key={item.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start gap-4">
                  {item.thumbnail_url && (
                    <img
                      src={item.thumbnail_url}
                      alt=""
                      className="w-24 h-14 object-cover rounded flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge status={item.status} />
                      {item.trend_score && (
                        <span
                          className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                            item.trend_score >= 7
                              ? 'bg-status-fehler-bg text-status-fehler-text'
                              : item.trend_score >= 4
                                ? 'bg-status-aktiv-bg text-status-aktiv-text'
                                : 'bg-surface-border text-ink-light'
                          }`}
                        >
                          Trend {item.trend_score}/10
                        </span>
                      )}
                      {item.published_at && (
                        <span className="text-xs text-ink-muted">
                          {new Date(item.published_at).toLocaleDateString('de-DE')}
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-semibold text-ink line-clamp-1">
                      {item.title}
                    </h3>

                    {/* Topic Pitch from analysis will show via detail view */}
                    <p className="text-xs text-ink-light mt-1 line-clamp-2">
                      Quelle: {item.external_id} | {item.transcript_source || 'Kein Transkript'}
                    </p>
                  </div>
                  <div className="flex-shrink-0 flex flex-col gap-1">
                    {item.url && (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary-500 hover:underline"
                      >
                        Video
                      </a>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Content Pieces View */}
      {activeChannel !== 'topics' && (
        <div className="space-y-4 mt-4">
          {(content || []).length === 0 && (
            <p className="text-sm text-ink-light">Kein Content in dieser Kategorie.</p>
          )}
          {(content || []).map((piece) => (
            <Card key={piece.id}>
              <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex items-center gap-3 flex-wrap">
                  <Badge color="blue">{piece.channel}</Badge>
                  <Badge status={piece.status} />
                  {piece.content_metadata?.source_title && (
                    <span className="text-xs text-ink-light">
                      {piece.content_metadata.source_title}
                    </span>
                  )}
                  {piece.content_metadata?.hashtags && (
                    <div className="flex gap-1">
                      {piece.content_metadata.hashtags.slice(0, 3).map((h, i) => (
                        <span key={i} className="text-xs text-status-neu-text">
                          {h}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  {piece.status === 'draft' && (
                    <>
                      {editingId === piece.id ? (
                        <Button size="sm" variant="success" onClick={() => handleSave(piece.id)}>
                          Speichern
                        </Button>
                      ) : (
                        <Button size="sm" variant="secondary" onClick={() => handleEdit(piece)}>
                          Bearbeiten
                        </Button>
                      )}
                      <Button size="sm" variant="success" onClick={() => handleApprove(piece.id)}>
                        Freigeben
                      </Button>
                    </>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {/* LinkedIn Preview Mock */}
                {piece.channel === 'linkedin' && editingId !== piece.id && (
                  <div className="border border-surface-border rounded-lg p-4 bg-surface-card">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center text-primary-600 font-bold text-sm">
                        ZB
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-ink">
                          Zukunftsbund
                        </p>
                        <p className="text-xs text-ink-light">Gerade eben</p>
                      </div>
                    </div>
                    <div className="text-sm text-ink-light whitespace-pre-wrap">
                      {piece.content_text}
                    </div>
                  </div>
                )}

                {/* Blog Preview */}
                {piece.channel === 'blog' && editingId !== piece.id && (
                  <div className="prose max-w-none text-sm whitespace-pre-wrap">
                    {piece.content_text}
                  </div>
                )}

                {/* Newsletter Preview */}
                {piece.channel === 'newsletter' && editingId !== piece.id && (
                  <div className="bg-surface-bg p-4 rounded-lg border-l-4 border-primary-500">
                    <div className="text-sm text-ink-light whitespace-pre-wrap">
                      {piece.content_text}
                    </div>
                  </div>
                )}

                {/* Edit Mode */}
                {editingId === piece.id && (
                  <Textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={10}
                    className="font-mono"
                  />
                )}

                <div className="mt-3 flex items-center gap-4 text-xs text-ink-muted">
                  <span>
                    Erstellt:{' '}
                    {piece.created_at ? new Date(piece.created_at).toLocaleString('de-DE') : '-'}
                  </span>
                  {piece.content_metadata?.source_url && (
                    <a
                      href={piece.content_metadata.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-500 hover:underline"
                    >
                      Quelle
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
