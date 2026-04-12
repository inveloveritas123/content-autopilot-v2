import { useState, useEffect } from 'react'
import { FileText, Check, Copy, Edit3, Eye, ThumbsUp, BarChart3, Send, X } from 'lucide-react'
import { getContentList, getContentPiece, approveContent, submitEditDiff, submitPerformance } from '../api'

const STATUS_COLORS = {
  draft: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  published: 'bg-primary-100 text-primary-700',
  rejected: 'bg-red-100 text-red-700',
}

function PostCard({ post, onSelect }) {
  const variant = post.content_metadata?.variant
  const angle = post.content_metadata?.angle
  return (
    <div
      onClick={() => onSelect(post.id)}
      className="bg-white rounded-xl border border-surface-border hover:border-primary-300 hover:shadow-sm transition-all cursor-pointer p-5"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[post.status] || 'bg-gray-100 text-gray-600'}`}>
            {post.status === 'draft' ? 'Entwurf' : post.status === 'approved' ? 'Freigegeben' : post.status === 'published' ? 'Gepostet' : post.status}
          </span>
          {variant && <span className="text-xs text-ink-muted">Variante {variant}</span>}
          {angle && <span className="px-2 py-0.5 rounded bg-gray-100 text-xs text-ink-light">{angle}</span>}
        </div>
        <span className="text-xs text-ink-muted">{post.channel || 'linkedin'}</span>
      </div>
      <p className="text-sm text-ink leading-relaxed line-clamp-4 whitespace-pre-line">
        {post.content_text}
      </p>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
        <span className="text-[11px] text-ink-muted">
          {post.created_at ? new Date(post.created_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '-'}
        </span>
        <span className="text-xs text-primary-600 font-medium">Details &rarr;</span>
      </div>
    </div>
  )
}

function PostDetail({ postId, onClose, onRefresh }) {
  const [post, setPost] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState('')
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState(null)
  const [showPerf, setShowPerf] = useState(false)
  const [perfData, setPerfData] = useState({ impressions: '', reactions: '', comments: '', shares: '' })

  useEffect(() => { loadPost() }, [postId])

  async function loadPost() {
    setLoading(true)
    try {
      const data = await getContentPiece(postId)
      setPost(data)
      setEditText(data.content_text)
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setLoading(false)
  }

  async function handleApprove() {
    try {
      await approveContent(postId)
      setMessage({ type: 'success', text: 'Post freigegeben!' })
      await loadPost()
      onRefresh()
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  async function handleSaveEdit() {
    try {
      await submitEditDiff({
        content_piece_id: postId,
        final_text: editText,
      })
      setMessage({ type: 'success', text: 'Bearbeitung gespeichert und als Lernsignal erfasst!' })
      setEditMode(false)
      await loadPost()
      onRefresh()
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  async function handlePerformance() {
    try {
      await submitPerformance({
        content_piece_id: postId,
        impressions: parseInt(perfData.impressions) || null,
        reactions: parseInt(perfData.reactions) || null,
        comments: parseInt(perfData.comments) || null,
        shares: parseInt(perfData.shares) || null,
      })
      setMessage({ type: 'success', text: 'Performance-Daten gespeichert!' })
      setShowPerf(false)
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(post.content_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) return <div className="p-6 text-center text-ink-muted">Lade...</div>
  if (!post) return null

  const charCount = (editMode ? editText : post.content_text).length

  return (
    <div className="bg-white rounded-xl border border-surface-border shadow-sm">
      <div className="p-5 border-b border-surface-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[post.status] || 'bg-gray-100'}`}>
            {post.status === 'draft' ? 'Entwurf' : post.status === 'approved' ? 'Freigegeben' : post.status}
          </span>
          <span className="text-xs text-ink-muted">{charCount} Zeichen</span>
        </div>
        <div className="flex items-center gap-2">
          {!editMode && post.status === 'draft' && (
            <>
              <button onClick={() => setEditMode(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light hover:text-ink border border-gray-200 rounded-lg hover:bg-gray-50">
                <Edit3 className="w-3.5 h-3.5" /> Bearbeiten
              </button>
              <button onClick={handleApprove} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700">
                <Check className="w-3.5 h-3.5" /> Freigeben
              </button>
            </>
          )}
          {post.status === 'approved' && (
            <button onClick={() => setShowPerf(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50">
              <BarChart3 className="w-3.5 h-3.5" /> Performance
            </button>
          )}
          <button onClick={handleCopy} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light hover:text-ink border border-gray-200 rounded-lg hover:bg-gray-50">
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Kopiert!' : 'Kopieren'}
          </button>
          <button onClick={onClose} className="p-1.5 text-ink-muted hover:text-ink rounded-lg hover:bg-gray-100">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {message && (
        <div className={`mx-5 mt-4 p-3 rounded-lg text-sm ${message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
          {message.text}
        </div>
      )}

      <div className="p-5">
        {editMode ? (
          <div>
            <textarea
              className="w-full text-sm border border-gray-300 rounded-lg p-4 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none leading-relaxed"
              rows={12}
              value={editText}
              onChange={e => setEditText(e.target.value)}
            />
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-ink-muted">{editText.length} Zeichen</span>
              <div className="flex gap-2">
                <button onClick={() => { setEditMode(false); setEditText(post.content_text) }} className="px-4 py-2 text-sm text-ink-light hover:text-ink border border-gray-200 rounded-lg">
                  Abbrechen
                </button>
                <button onClick={handleSaveEdit} className="px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800">
                  Speichern (Lernsignal)
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="whitespace-pre-line text-sm text-ink leading-relaxed bg-gray-50 rounded-lg p-5 border border-gray-100">
            {post.content_text}
          </div>
        )}
      </div>

      {/* Performance Modal */}
      {showPerf && (
        <div className="px-5 pb-5">
          <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
            <h4 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-primary-600" /> LinkedIn-Performance eintragen
            </h4>
            <div className="grid grid-cols-2 gap-3">
              {['impressions', 'reactions', 'comments', 'shares'].map(field => (
                <div key={field}>
                  <label className="text-xs text-ink-light capitalize">{field === 'impressions' ? 'Aufrufe' : field === 'reactions' ? 'Reaktionen' : field === 'comments' ? 'Kommentare' : 'Shares'}</label>
                  <input
                    type="number"
                    className="w-full mt-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                    value={perfData[field]}
                    onChange={e => setPerfData(prev => ({ ...prev, [field]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setShowPerf(false)} className="px-3 py-1.5 text-xs text-ink-light border border-gray-200 rounded-lg">Abbrechen</button>
              <button onClick={handlePerformance} className="px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800">Speichern</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Posts() {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [filter, setFilter] = useState('')

  useEffect(() => { loadPosts() }, [filter])

  async function loadPosts() {
    setLoading(true)
    try {
      const params = {}
      if (filter) params.status = filter
      const data = await getContentList(params)
      setPosts(Array.isArray(data) ? data : data.items || [])
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const filters = [
    { value: '', label: 'Alle' },
    { value: 'draft', label: 'Entwuerfe' },
    { value: 'approved', label: 'Freigegeben' },
    { value: 'published', label: 'Gepostet' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">LinkedIn-Posts</h1>
          <p className="text-sm text-ink-light mt-0.5">Bearbeite, gib frei oder tracke deine Posts.</p>
        </div>
        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
          {filters.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filter === f.value ? 'bg-white text-ink shadow-sm' : 'text-ink-light hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>}

      {selectedId ? (
        <PostDetail postId={selectedId} onClose={() => setSelectedId(null)} onRefresh={loadPosts} />
      ) : loading ? (
        <div className="text-center py-12 text-ink-muted">Lade Posts...</div>
      ) : posts.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-ink-light">Noch keine Posts vorhanden.</p>
          <p className="text-xs text-ink-muted mt-1">Beantworte Fragen zu einer Idee, um Posts zu generieren.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {posts.map(post => (
            <PostCard key={post.id} post={post} onSelect={setSelectedId} />
          ))}
        </div>
      )}
    </div>
  )
}
