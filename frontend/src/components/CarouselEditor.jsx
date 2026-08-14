// AUDITED-2026-08-14 (Welle D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState } from 'react'
import { useToast } from './ui/Toast'

function getApiKey() {
  return localStorage.getItem('apiKey') || ''
}

const TYPE_LABELS = {
  cover: 'Cover',
  point: 'Punkt',
  quote: 'Zitat',
  cta: 'CTA',
  transition: 'Uebergang',
}

function SlideCard({ slide, index, total, onMove, onChange, onDelete }) {
  const [editing, setEditing] = useState(false)
  return (
    <div className="bg-white border border-surface-border rounded-xl p-4 flex gap-3">
      <div className="flex flex-col items-center gap-1 shrink-0">
        <span className="text-xs font-bold text-ink-muted w-6 text-center">{index + 1}</span>
        <button
          onClick={() => onMove(index, -1)}
          disabled={index === 0}
          className="text-ink-muted hover:text-ink-light disabled:opacity-20 text-xs"
        >
          ↑
        </button>
        <button
          onClick={() => onMove(index, 1)}
          disabled={index === total - 1}
          className="text-ink-muted hover:text-ink-light disabled:opacity-20 text-xs"
        >
          ↓
        </button>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-semibold text-ink-muted">
            {TYPE_LABELS[slide.type] || slide.type}
          </span>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-primary-600 hover:text-primary-800 ml-auto"
            >
              Bearbeiten
            </button>
          )}
          {editing && (
            <button
              onClick={() => setEditing(false)}
              className="text-xs text-status-fertig-text hover:text-status-fertig-text ml-auto"
            >
              Fertig
            </button>
          )}
          <button
            onClick={() => onDelete(index)}
            className="text-xs text-status-fehler-text/70 hover:text-status-fehler-text"
          >
            x
          </button>
        </div>
        {editing ? (
          <div className="space-y-2">
            <input
              value={slide.title || ''}
              onChange={(e) => onChange(index, 'title', e.target.value)}
              placeholder="Titel / Ueberschrift"
              className="w-full border border-surface-border rounded px-2 py-1 text-sm"
            />
            <textarea
              value={slide.body || ''}
              onChange={(e) => onChange(index, 'body', e.target.value)}
              placeholder="Inhalt"
              rows={3}
              className="w-full border border-surface-border rounded px-2 py-1 text-sm resize-none"
            />
          </div>
        ) : (
          <div>
            {slide.title && (
              <p className="text-sm font-semibold text-ink truncate">{slide.title}</p>
            )}
            <p className="text-xs text-ink-muted line-clamp-2">{slide.body}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function CarouselEditor({
  initialSlides = [],
  contentPieceId,
  tenantId,
  onPdfReady,
}) {
  const { toast } = useToast()
  const [slides, setSlides] = useState(initialSlides)
  const [generating, setGenerating] = useState(false)
  const [pdfUrl, setPdfUrl] = useState(null)

  function handleMove(idx, dir) {
    const newSlides = [...slides]
    const target = idx + dir
    if (target < 0 || target >= newSlides.length) return
    ;[newSlides[idx], newSlides[target]] = [newSlides[target], newSlides[idx]]
    setSlides(newSlides)
    setPdfUrl(null)
  }

  function handleChange(idx, field, value) {
    const newSlides = slides.map((s, i) => (i === idx ? { ...s, [field]: value } : s))
    setSlides(newSlides)
    setPdfUrl(null)
  }

  function handleDelete(idx) {
    setSlides(slides.filter((_, i) => i !== idx))
    setPdfUrl(null)
  }

  async function handleGeneratePdf() {
    setGenerating(true)
    try {
      const resp = await fetch('/api/carousels/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey(),
        },
        body: JSON.stringify({ slides, title: 'LinkedIn Carousel' }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail || 'PDF-Generierung fehlgeschlagen')
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setPdfUrl(url)
      if (onPdfReady) onPdfReady(url)
    } catch (e) {
      console.error(e)
      toast.error('PDF-Generierung fehlgeschlagen: ' + (e.message || 'Unbekannter Fehler'))
    }
    setGenerating(false)
  }

  if (slides.length === 0) {
    return (
      <div className="text-sm text-ink-muted py-4 text-center">
        Keine Slides. Carousel zuerst generieren.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-ink">{slides.length} Slides</h3>
        <button
          onClick={handleGeneratePdf}
          disabled={generating}
          className="px-3 py-1.5 bg-primary-600 text-white text-xs font-semibold rounded-lg hover:bg-primary-700 disabled:opacity-50"
        >
          {generating ? 'Generiere...' : 'PDF erstellen'}
        </button>
      </div>

      <div className="space-y-2">
        {slides.map((slide, idx) => (
          <SlideCard
            key={idx}
            slide={slide}
            index={idx}
            total={slides.length}
            onMove={handleMove}
            onChange={handleChange}
            onDelete={handleDelete}
          />
        ))}
      </div>

      {pdfUrl && (
        <div className="border border-surface-border rounded-xl overflow-hidden">
          <div className="bg-surface-bg px-4 py-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-ink-muted">PDF-Vorschau</span>
            <a
              href={pdfUrl}
              download="carousel.pdf"
              className="text-xs text-primary-600 hover:text-primary-800"
            >
              Download
            </a>
          </div>
          <iframe src={pdfUrl} className="w-full h-96" title="Carousel PDF Vorschau" />
        </div>
      )}
    </div>
  )
}
