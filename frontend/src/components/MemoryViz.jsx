/**
 * Vector-DB-Visualisierung (Issue #148, Welle F).
 * Force-Directed-Graph (react-force-graph-2d) — Cosine-Similarity-Edges aus pgvector.
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { Network, RefreshCw, Loader2, AlertCircle } from 'lucide-react'
import { Button } from './ui/Button'
import ForceGraph2D from 'react-force-graph-2d'
import { getMemoryVizData } from '../api'

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
  const fgRef = useRef()

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
  useEffect(() => { load() /* eslint-disable-line */ }, [])

  const graphData = useMemo(() => ({
    nodes: data.nodes.map(n => ({ ...n })),
    links: data.edges.map(e => ({ source: e.source, target: e.target, value: e.weight })),
  }), [data])

  return (
    <div style={{ padding: 24, maxWidth: 1400 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        <Network size={22} style={{ display: 'inline', marginRight: 8 }} />
        Gedächtnis-Vektor-Karte
      </h1>
      <p style={{ color: '#6b7280', marginBottom: 16, fontSize: 14 }}>
        Jeder Punkt = ein Memory-Chunk. Verbindungen = Cosine-Similarity ≥ {edgeThreshold}.
        Klick auf Punkt = Details.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Zeitraum (Tage)</label>
          <input type="number" min="1" max="3650" value={days}
                 onChange={(e) => setDays(parseInt(e.target.value, 10) || 180)}
                 data-testid="viz-days"
                 style={{ width: 100, padding: 6, border: '1px solid #d1d5db', borderRadius: 4 }} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Klassifikation</label>
          <select value={classification} onChange={(e) => setClassification(e.target.value)}
                  data-testid="viz-class"
                  style={{ padding: 6, border: '1px solid #d1d5db', borderRadius: 4 }}>
            <option value="">— alle —</option>
            <option value="werte">werte</option>
            <option value="stories">stories</option>
            <option value="konflikte">konflikte</option>
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Quelle</label>
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}
                  data-testid="viz-source"
                  style={{ padding: 6, border: '1px solid #d1d5db', borderRadius: 4 }}>
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
          <input type="number" min="0.5" max="1" step="0.05" value={edgeThreshold}
                 onChange={(e) => setEdgeThreshold(parseFloat(e.target.value) || 0.75)}
                 data-testid="viz-threshold"
                 style={{ width: 80, padding: 6, border: '1px solid #d1d5db', borderRadius: 4 }} />
        </div>
        <Button data-testid="btn-viz-reload" onClick={load} disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {loading ? ' Lädt…' : ' Neu laden'}
        </Button>
      </div>

      {error && <div style={{ padding: 12, background: '#fee2e2', color: '#991b1b', borderRadius: 6, marginBottom: 12 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        <div style={{ height: 600, background: '#0f172a', borderRadius: 8, position: 'relative', overflow: 'hidden' }}>
          {graphData.nodes.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af' }}>
              <AlertCircle size={20} style={{ marginRight: 8 }} />
              {loading ? 'Lade Daten…' : 'Keine Memory-Chunks im gewählten Zeitraum / Filter.'}
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef}
              graphData={graphData}
              backgroundColor="#0f172a"
              nodeRelSize={5}
              nodeColor={(n) => n.color || '#6b7280'}
              nodeLabel={(n) => `<div style="max-width:300px;background:#fff;padding:6px;border-radius:4px;font-size:12px">${n.label}<br/><i style="color:#64748b">${n.classification || ''} · ${n.source_type}</i></div>`}
              linkColor={() => 'rgba(255,255,255,0.2)'}
              linkWidth={(l) => Math.max(0.3, (l.value - 0.5) * 3)}
              onNodeClick={(n) => setSelectedNode(n)}
              cooldownTicks={100}
              width={1024}
              height={600}
            />
          )}
        </div>

        <div data-testid="viz-sidebar" style={{ background: '#f9fafb', padding: 16, borderRadius: 8, fontSize: 13 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Statistik</h3>
          <div>Gesamt: <strong>{data.stats?.total || 0}</strong></div>
          <div>Mit Embedding: <strong>{data.stats?.with_embedding || 0}</strong></div>
          <div>Soft-Deleted: {data.stats?.soft_deleted || 0}</div>
          <div>Angezeigt: {data.stats?.shown_nodes || 0} Knoten · {data.stats?.shown_edges || 0} Kanten</div>

          <h4 style={{ marginTop: 16, fontSize: 14, fontWeight: 600 }}>Klassifikation</h4>
          {(data.stats?.by_classification || []).map(c => (
            <div key={c.name} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
              <span style={{ width: 10, height: 10, borderRadius: 5,
                             background: CLASS_COLORS[c.name] || CLASS_COLORS.unklassifiziert,
                             display: 'inline-block' }} />
              <span style={{ flex: 1 }}>{c.name}</span>
              <span style={{ color: '#6b7280' }}>{c.count}</span>
            </div>
          ))}

          <h4 style={{ marginTop: 16, fontSize: 14, fontWeight: 600 }}>Quellen</h4>
          {(data.stats?.by_source_type || []).map(s => (
            <div key={s.name} style={{ display: 'flex', padding: '2px 0' }}>
              <span style={{ flex: 1 }}>{s.name}</span>
              <span style={{ color: '#6b7280' }}>{s.count}</span>
            </div>
          ))}

          {selectedNode && (
            <div data-testid="viz-detail" style={{ marginTop: 20, padding: 12, background: 'white', border: '1px solid #e5e7eb', borderRadius: 6 }}>
              <h4 style={{ fontWeight: 600, marginBottom: 6 }}>Ausgewählt</h4>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                {selectedNode.classification || 'unklassifiziert'} · {selectedNode.source_type}
              </div>
              <div style={{ fontSize: 13 }}>{selectedNode.full_text}</div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
                {new Date(selectedNode.created_at).toLocaleString('de-DE')}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
