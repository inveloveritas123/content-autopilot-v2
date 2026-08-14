// AUDITED-2026-08-14 (Welle D6): Tiefen-Audit, Datei vollstaendig gelesen.
import { useState } from 'react'
import { ThumbsUp, MessageSquare, Share2, MoreHorizontal } from 'lucide-react'

// Device configs: label, preview width, "Mehr anzeigen" char cutoff
const DEVICES = {
  desktop: { label: 'Desktop', width: 552, cutoff: 210 },
  tablet: { label: 'Tablet', width: 480, cutoff: 175 },
  mobile: { label: 'Mobile', width: 375, cutoff: 150 },
}

/**
 * Formats post text into React elements.
 * Highlights #hashtags and @mentions as primary-colored spans.
 * URLs are shown truncated.
 * No dangerouslySetInnerHTML — all values are plain React text nodes.
 */
function formatPostText(text, cutoff, expanded) {
  const full = String(text ?? '')
  const displayText = !expanded && full.length > cutoff ? full.slice(0, cutoff) : full

  const lines = displayText.split('\n')
  const result = []

  lines.forEach((line, lineIdx) => {
    const parts = []
    const tokenRe = /(#[\w\u00C0-\u024F]+|@[\w\u00C0-\u024F.]+|https?:\/\/[^\s]+)/g
    let lastIdx = 0
    let m
    while ((m = tokenRe.exec(line)) !== null) {
      if (m.index > lastIdx) {
        parts.push({ type: 'text', value: line.slice(lastIdx, m.index) })
      }
      if (m[0].startsWith('#')) {
        parts.push({ type: 'hashtag', value: m[0] })
      } else if (m[0].startsWith('@')) {
        parts.push({ type: 'mention', value: m[0] })
      } else {
        parts.push({ type: 'url', value: m[0] })
      }
      lastIdx = m.index + m[0].length
    }
    if (lastIdx < line.length) {
      parts.push({ type: 'text', value: line.slice(lastIdx) })
    }

    result.push(
      <span key={lineIdx}>
        {parts.map((p, i) => {
          if (p.type === 'text') return <span key={i}>{p.value}</span>
          if (p.type === 'hashtag')
            return (
              <span key={i} className="text-primary-600 hover:underline cursor-pointer">
                {p.value}
              </span>
            )
          if (p.type === 'mention')
            return (
              <span
                key={i}
                className="text-primary-600 hover:underline cursor-pointer font-semibold"
              >
                {p.value}
              </span>
            )
          if (p.type === 'url') {
            const display = p.value.length > 40 ? p.value.slice(0, 40) + '\u2026' : p.value
            return (
              <span key={i} className="text-primary-600 hover:underline cursor-pointer">
                {display}
              </span>
            )
          }
          return null
        })}
        {lineIdx < lines.length - 1 && <br />}
      </span>
    )
  })

  return result
}

function CarouselPreview({ slides }) {
  if (!slides || slides.length === 0) return null
  const first = slides[0]
  return (
    <div className="mt-2 rounded-lg overflow-hidden border border-surface-border bg-surface-bg">
      <div className="flex items-center justify-between px-3 py-2 bg-primary-50 border-b border-surface-border">
        <span className="text-xs font-semibold text-primary-700">
          Carousel ({slides.length} Slides)
        </span>
        <span className="text-[10px] text-primary-600">&larr; swipe &rarr;</span>
      </div>
      <div className="p-3">
        <p className="text-xs font-bold text-ink truncate">
          {first.title || first.heading || 'Slide 1'}
        </p>
        <p className="text-xs text-ink-light line-clamp-2 mt-0.5">{first.body || ''}</p>
      </div>
      <div className="flex gap-1 px-3 pb-2">
        {slides.slice(0, 8).map((_, i) => (
          <div
            key={i}
            className={`h-1 rounded-full flex-grow ${i === 0 ? 'bg-primary-500' : 'bg-surface-border'}`}
          />
        ))}
      </div>
    </div>
  )
}

function LinkedInPost({ text, device, carouselSlides, authorName, authorTitle }) {
  const [expanded, setExpanded] = useState(false)
  const config = DEVICES[device]
  const isTruncated = !expanded && (text || '').length > config.cutoff

  return (
    <div
      className="bg-white rounded-lg border border-surface-border overflow-hidden font-sans"
      style={{ width: config.width, maxWidth: '100%', fontSize: '14px' }}
    >
      {/* Header: avatar, name, title, timestamp, options */}
      <div className="flex items-start gap-3 p-4 pb-2">
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-lg">
            {(authorName || 'U')[0].toUpperCase()}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-semibold text-ink text-sm leading-tight">
                {authorName || 'Dein Name'}
              </p>
              <p className="text-xs text-ink-light leading-tight truncate max-w-[200px]">
                {authorTitle || 'Unternehmer \u00b7 1. Grad'}
              </p>
              <p className="text-xs text-ink-muted leading-tight">Gerade &bull; 🌐</p>
            </div>
            <button
              className="p-2 rounded-full hover:bg-surface-bg text-ink-muted transition-colors"
              style={{ minWidth: 44, minHeight: 44 }}
              aria-label="Optionen"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Post text */}
      <div className="px-4 py-2 text-ink leading-snug" style={{ fontSize: '14px' }}>
        <p className="whitespace-pre-line break-words">
          {formatPostText(text, config.cutoff, expanded)}
          {isTruncated && '\u2026 '}
          {!expanded && isTruncated && (
            <button
              onClick={() => setExpanded(true)}
              className="text-ink-light hover:text-ink font-semibold text-sm"
            >
              Mehr anzeigen
            </button>
          )}
          {expanded && (text || '').length > config.cutoff && (
            <button
              onClick={() => setExpanded(false)}
              className="text-ink-light hover:text-ink font-semibold text-sm ml-1"
            >
              Weniger anzeigen
            </button>
          )}
        </p>
      </div>

      {/* Carousel preview (optional) */}
      {carouselSlides && carouselSlides.length > 0 && (
        <div className="px-4 pb-2">
          <CarouselPreview slides={carouselSlides} />
        </div>
      )}

      {/* Reactions summary */}
      <div className="px-4 py-1 flex items-center gap-1 text-xs text-ink-light">
        <span>👍</span>
        <span>💡</span>
        <span>❤️</span>
        <span className="ml-1">124</span>
        <span className="ml-auto">12 Kommentare &middot; 8 Reposts</span>
      </div>

      {/* Action bar */}
      <div className="border-t border-surface-border px-2 py-1 flex">
        {[
          { icon: ThumbsUp, label: 'Gef\u00e4llt mir' },
          { icon: MessageSquare, label: 'Kommentieren' },
          { icon: Share2, label: 'Teilen' },
        ].map(({ icon: Icon, label }) => (
          <button
            key={label}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg hover:bg-surface-bg text-ink-light text-xs font-semibold transition-colors"
            style={{ minHeight: 44 }}
            aria-label={label}
          >
            <Icon className="w-4 h-4" />
            {device !== 'mobile' && <span>{label}</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * PostPreview — shows how a LinkedIn post looks on Desktop / Tablet / Mobile.
 *
 * Props:
 *   text            string   — post text (plain text, no HTML)
 *   carouselSlides  array?   — optional slides array from CarouselEditor
 *   authorName      string?  — display name
 *   authorTitle     string?  — subtitle / position
 *   defaultDevice   'desktop'|'tablet'|'mobile'  — initially active tab
 */
export default function PostPreview({
  text = '',
  carouselSlides = null,
  authorName = '',
  authorTitle = '',
  defaultDevice = 'mobile',
}) {
  const [activeDevice, setActiveDevice] = useState(defaultDevice)

  return (
    <div>
      {/* Device tabs */}
      <div className="flex gap-1 mb-4 bg-surface-bg rounded-xl p-1 w-fit">
        {Object.entries(DEVICES).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setActiveDevice(key)}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors ${
              activeDevice === key
                ? 'bg-white text-ink shadow-sm'
                : 'text-ink-light hover:text-ink'
            }`}
            style={{ minHeight: 44, minWidth: 44 }}
          >
            {cfg.label}
            <span className="ml-1 text-[10px] text-ink-muted font-normal">{cfg.width}px</span>
          </button>
        ))}
      </div>

      {/* Scrollable preview frame */}
      <div className="overflow-x-auto">
        <div className="flex justify-start">
          <LinkedInPost
            key={activeDevice}
            text={text}
            device={activeDevice}
            carouselSlides={carouselSlides}
            authorName={authorName}
            authorTitle={authorTitle}
          />
        </div>
      </div>

      {/* Info hint */}
      <p className="text-[10px] text-ink-muted mt-2">
        &quot;Mehr anzeigen&quot; bei {DEVICES[activeDevice].cutoff}+ Zeichen auf{' '}
        {DEVICES[activeDevice].label} ({DEVICES[activeDevice].width}px). LinkedIn-Look approximiert,
        kein Live-Embed.
      </p>
    </div>
  )
}
