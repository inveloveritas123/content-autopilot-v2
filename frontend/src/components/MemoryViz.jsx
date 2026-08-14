/**
 * Vector-DB-Visualisierung (Issue #148, Welle F).
 * Force-Directed-Graph (react-force-graph-2d) — Cosine-Similarity-Edges aus pgvector.
 *
 * Critical #3: Default-View nutzt `text_preview`, kein `full_text` im DOM.
 * Should-Fix: ResizeObserver statt hartkodiertem width={1024}.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Network, RefreshCw, Loader2, AlertCircle, Eye } from 'lucide-react'
import { Button } from './ui/Button'
import ForceGraph2D from 'react-force-graph-2d'
import { getMemoryVizData, getMemoryChunkFullText } from '../api'

// S3: HTML-Escape-Helper — verhindert XSS in nodeLabel-Template (Trust-Boundary: eigene DB,
// aber Defense-in-Depth gegen Daten mit < > & Zeichen aus Nutzereingaben).
function escapeHtml(s) {
  if (!s) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

// bewusst behalten: Force-Graph-Knoten-/Legenden-Farben (Canvas-Rendering via
// ForceGraph2D, kein DOM/Tailwind-Kontext) — 4 unterscheidbare Daten-Kategorien,
// keine Status-Bedeutung.
const CLASS_COLORS = {
  werte: '#2563eb',
  stories: '#16a34a',
  konflikte: '#dc2626',
  unklassifiziert: '#6b7280',
}

export default function MemoryViz() {
  const [data, setData] = useState({ nodes: [], edges: [], stats: {} })
  const [days, setDays] = useState(180)
  const [classification, setClassification] = useState('')
  const [sourceType, setSourceType] = useState('')
  const [edgeThreshold, setEdgeThreshold] = useState(0.75)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)

  // Should-Fix: ResizeObserver statt hartkodiertem width={1024}
  const containerRef = useRef()
  const [graphWidth, setGraphWidth] = useState(800)
  const fgRef = useRef()

  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setGraphWidth(Math.floor(entry.contentRect.width))
      }
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  // Critical #3: Confirm-Dialog-State für Full-Text-Anfrage
  const [fullTextLoading, setFullTextLoading] = useState(false)
  const [fullTextError, setFullTextError] = useState(null)
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)
  const [confirmReason, setConfirmReason] = useState('')
  const [fullTextData, setFullTextData] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = { days, edge_threshold: edgeThreshold, max_nodes: 200, max_edges: 200 }
      if (classification) params.classification = classification
      if (sourceType) params.source_type = sourceType
      const r = await getMemoryVizData(params)
      setData(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    load()
  }, [])

  const graphData = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target, value: e.weight })),
    }),
    [data]
  )

  const handleNodeClick = useCallback((n) => {
    setSelectedNode(n)
    setFullTextData(null)
    setFullTextError(null)
    setShowConfirmDialog(false)
    setConfirmReason('')
  }, [])

  async function handleRequestFullText() {
    if (!selectedNode) return
    if (!confirmReason.trim()) return
    setFullTextLoading(true)
    setFullTextError(null)
    try {
      const result = await getMemoryChunkFullText(selectedNode.id, confirmReason.trim())
      setFullTextData(result)
      setShowConfirmDialog(false)
    } catch (e) {
      setFullTextError(e.message)
    } finally {
      setFullTextLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1400 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        <Network size={22} style={{ display: 'inline', marginRight: 8 }} />
        Gedächtnis-Vektor-Karte
      </h1>
      <p className="text-ink-light" style={{ marginBottom: 16, fontSize: 14 }}>
        Jeder Punkt = ein Memory-Chunk. Verbindungen = Cosine-Similarity ≥ {edgeThreshold}. Klick
        auf Punkt = Details.
      </p>

      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 16,
          flexWrap: 'wrap',
          alignItems: 'flex-end',
        }}
      >
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Zeitraum (Tage)</label>
          <input
            type="number"
            min="1"
            max="3650"
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value, 10) || 180)}
            data-testid="viz-days"
            className="border-surface-border"
            style={{ width: 100, padding: 6, border: '1px solid', borderRadius: 4 }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Klassifikation</label>
          <select
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
            data-testid="viz-class"
            className="border-surface-border"
            style={{ padding: 6, border: '1px solid', borderRadius: 4 }}
          >
            <option value="">— alle —</option>
            <option value="werte">werte</option>
            <option value="stories">stories</option>
            <option value="konflikte">konflikte</option>
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Quelle</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            data-testid="viz-source"
            className="border-surface-border"
            style={{ padding: 6, border: '1px solid', borderRadius: 4 }}
          >
            <option value="">— alle —</option>
            <option value="voice_telegram">voice_telegram</option>
            <option value="voice_whatsapp">voice_whatsapp</option>
            <option value="photo_telegram">photo_telegram</option>
            <option value="photo_whatsapp">photo_whatsapp</option>
            <option value="manual_note">manual_note</option>
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Edge-Schwelle</label>
          <input
            type="number"
            min="0.5"
            max="1"
            step="0.05"
            value={edgeThreshold}
            onChange={(e) => setEdgeThreshold(parseFloat(e.target.value) || 0.75)}
            data-testid="viz-threshold"
            className="border-surface-border"
            style={{ width: 80, padding: 6, border: '1px solid', borderRadius: 4 }}
          />
        </div>
        <Button data-testid="btn-viz-reload" onClick={load} disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {loading ? ' Lädt…' : ' Neu laden'}
        </Button>
      </div>

      {error && (
        <div
          className="bg-status-fehler-bg text-status-fehler-text"
          style={{
            padding: 12,
            borderRadius: 6,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        {/* Should-Fix: ref auf Container, graphWidth aus ResizeObserver */}
        <div
          ref={containerRef}
          // bewusst behalten: dunkler Canvas-Hintergrund für ForceGraph2D (Kontrast
          // zu hellen Knoten/Kanten), keine Status-Bedeutung.
          style={{
            height: 600,
            background: '#0f172a',
            borderRadius: 8,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {graphData.nodes.length === 0 ? (
            <div
              className="text-ink-muted"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
              }}
            >
              <AlertCircle size={20} style={{ marginRight: 8 }} />
              {loading ? 'Lade Daten…' : 'Keine Memory-Chunks im gewählten Zeitraum / Filter.'}
            </div>
          ) : (
            // bewusst behalten: ForceGraph2D-Canvas-Props (backgroundColor, nodeColor-
            // Fallback, nodeLabel-HTML-Tooltip, linkColor) rendern außerhalb des
            // Tailwind/DOM-Klassenkontexts — Canvas- bzw. Tooltip-Inline-Styles,
            // keine Status-Bedeutung.
            <ForceGraph2D
              ref={fgRef}
              graphData={graphData}
              backgroundColor="#0f172a"
              nodeRelSize={5}
              nodeColor={(n) => n.color || '#6b7280'}
              nodeLabel={(n) =>
                `<div style="max-width:300px;background:#fff;padding:6px;border-radius:4px;font-size:12px">${escapeHtml(n.label)}<br/><i style="color:#64748b">${escapeHtml(n.classification || '')} · ${escapeHtml(n.source_type)}</i></div>`
              }
              linkColor={() => 'rgba(255,255,255,0.2)'}
              linkWidth={(l) => Math.max(0.3, (l.value - 0.5) * 3)}
              onNodeClick={handleNodeClick}
              cooldownTicks={100}
              width={graphWidth}
              height={600}
            />
          )}
        </div>

        <div
          data-testid="viz-sidebar"
          className="bg-surface-bg"
          style={{ padding: 16, borderRadius: 8, fontSize: 13 }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Statistik</h3>
          <div>
            Gesamt: <strong>{data.stats?.total || 0}</strong>
          </div>
          <div>
            Mit Embedding: <strong>{data.stats?.with_embedding || 0}</strong>
          </div>
          <div>Soft-Deleted: {data.stats?.soft_deleted || 0}</div>
          <div>
            Angezeigt: {data.stats?.shown_nodes || 0} Knoten · {data.stats?.shown_edges || 0} Kanten
          </div>

          <h4 style={{ marginTop: 16, fontSize: 14, fontWeight: 600 }}>Klassifikation</h4>
          {(data.stats?.by_classification || []).map((c) => (
            <div
              key={c.name}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 5,
                  background: CLASS_COLORS[c.name] || CLASS_COLORS.unklassifiziert,
                  display: 'inline-block',
                }}
              />
              <span style={{ flex: 1 }}>{c.name}</span>
              <span className="text-ink-light">{c.count}</span>
            </div>
          ))}

          <h4 style={{ marginTop: 16, fontSize: 14, fontWeight: 600 }}>Quellen</h4>
          {(data.stats?.by_source_type || []).map((s) => (
            <div key={s.name} style={{ display: 'flex', padding: '2px 0' }}>
              <span style={{ flex: 1 }}>{s.name}</span>
              <span className="text-ink-light">{s.count}</span>
            </div>
          ))}

          {selectedNode && (
            <div
              data-testid="viz-detail"
              className="bg-surface-card border-surface-border"
              style={{
                marginTop: 20,
                padding: 12,
                border: '1px solid',
                borderRadius: 6,
              }}
            >
              <h4 style={{ fontWeight: 600, marginBottom: 6 }}>Ausgewählt</h4>
              <div className="text-ink-light" style={{ fontSize: 12, marginBottom: 4 }}>
                {selectedNode.classification || 'unklassifiziert'} · {selectedNode.source_type}
              </div>

              {/* Critical #3: Standard-View zeigt nur text_preview */}
              {!fullTextData && (
                <>
                  <div data-testid="viz-text-preview" style={{ fontSize: 13 }}>
                    {selectedNode.text_preview}
                  </div>
                  {!showConfirmDialog && (
                    <Button
                      data-testid="btn-viz-show-full"
                      onClick={() => setShowConfirmDialog(true)}
                      style={{ marginTop: 8, fontSize: 11, padding: '4px 8px' }}
                    >
                      <Eye size={12} style={{ marginRight: 4 }} />
                      Vollständigen Inhalt anzeigen…
                    </Button>
                  )}
                  {showConfirmDialog && (
                    <div
                      className="bg-status-aktiv-bg"
                      style={{
                        marginTop: 8,
                        padding: 8,
                        borderRadius: 4,
                        fontSize: 12,
                      }}
                    >
                      <p style={{ fontWeight: 600, marginBottom: 4 }}>
                        Vollständigen Inhalt anzeigen?
                      </p>
                      <p className="text-status-aktiv-text" style={{ marginBottom: 6 }}>
                        Dieser Zugriff wird im Audit-Log vermerkt.
                      </p>
                      <input
                        type="text"
                        placeholder="Begründung (Pflicht)"
                        value={confirmReason}
                        onChange={(e) => setConfirmReason(e.target.value)}
                        data-testid="viz-confirm-reason"
                        className="border-surface-border"
                        style={{
                          width: '100%',
                          padding: '4px 6px',
                          border: '1px solid',
                          borderRadius: 4,
                          marginBottom: 6,
                          fontSize: 12,
                        }}
                      />
                      {fullTextError && (
                        <div
                          className="text-status-fehler-text"
                          style={{ fontSize: 11, marginBottom: 4 }}
                        >
                          {fullTextError}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 6 }}>
                        <Button
                          data-testid="btn-viz-confirm-ok"
                          onClick={handleRequestFullText}
                          disabled={fullTextLoading || !confirmReason.trim()}
                          style={{ fontSize: 11, padding: '4px 8px' }}
                        >
                          {fullTextLoading ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            'OK, anzeigen'
                          )}
                        </Button>
                        <Button
                          data-testid="btn-viz-confirm-cancel"
                          onClick={() => {
                            setShowConfirmDialog(false)
                            setConfirmReason('')
                          }}
                          className="border-surface-border"
                          style={{
                            fontSize: 11,
                            padding: '4px 8px',
                            background: 'transparent',
                            border: '1px solid',
                          }}
                        >
                          Abbrechen
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Critical #3: Full-Text-View nach Confirm */}
              {fullTextData && (
                <>
                  <div data-testid="viz-full-text" style={{ fontSize: 13 }}>
                    {fullTextData.full_text}
                  </div>
                  <div className="text-ink-muted" style={{ fontSize: 11, marginTop: 4 }}>
                    (Volltext — Zugriff wurde im Audit-Log vermerkt)
                  </div>
                  <Button
                    onClick={() => setFullTextData(null)}
                    className="border-surface-border"
                    style={{
                      marginTop: 6,
                      fontSize: 11,
                      padding: '2px 6px',
                      background: 'transparent',
                      border: '1px solid',
                    }}
                  >
                    Vorschau
                  </Button>
                </>
              )}

              <div className="text-ink-muted" style={{ fontSize: 11, marginTop: 6 }}>
                {new Date(selectedNode.created_at).toLocaleString('de-DE')}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
