import { useState, useEffect, useMemo, useRef, Component } from 'react'
import { flushSync } from 'react-dom'
import { useToast } from './ui/Toast'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { CloseButton } from './ui/CloseButton'
import {
  FileText,
  Check,
  Copy,
  Edit3,
  Eye,
  ThumbsUp,
  ThumbsDown,
  BarChart3,
  Send,
  X,
  Linkedin,
  MessageSquare,
  Repeat2,
  ArrowUpRight,
  CheckSquare,
  Square,
  AlertTriangle,
  Download,
  Zap,
  Search,
  Sparkles,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import {
  getContentList,
  getContentPiece,
  approveContent,
  bulkApproveContent,
  bulkRejectContent,
  bulkPublishContent,
  submitEditDiff,
  submitPerformance,
  suggestHashtags,
  repurposeContent,
  getHookLibrary,
  getBestPostingTimes,
  generateCarousel,
  previewCarousel,
  downloadContentExport,
  autoSchedulePosts,
  updateContentPillar,
  updateContent,
  quickCreatePost,
  createContentSeries,
  postFromUrl,
  rewriteContent,
  generateVariants,
  repurposeFormats,
  predictPerformance,
  rateItemQuality,
  getSources,
  saveDirectPost,
  markPublished,
  updateContentTags,
  getCarouselTemplates,
} from '../api'

// ── Error Boundary for PostDetail (prevents white screen on render crash) ───
class PostDetailErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  componentDidCatch(error, info) {
    console.error('PostDetail crashed:', error, info)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-white rounded-xl border border-status-fehler-border p-8 text-center">
          <p className="text-sm font-semibold text-status-fehler-text mb-2">
            Post konnte nicht angezeigt werden
          </p>
          <p className="text-xs text-ink-muted mb-4">
            {this.state.error?.message || 'Unbekannter Fehler'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              this.props.onClose?.()
            }}
            className="px-4 py-2 text-sm text-ink-muted border border-surface-border rounded-lg hover:bg-surface-bg"
          >
            ← Zurück zur Liste
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ── Content Pillars ─────────────────────────────────────────────────────────
const PILLAR_CONFIG = {
  thought_leadership: {
    label: 'Thought Leadership',
    emoji: '💡',
    // bewusst behalten: 5 Content-Säulen brauchen visuell unterscheidbare Kategorie-Badges
    // (keine Status-Bedeutung) — violet/pink außerhalb des Token-Systems, da accent/primary/
    // status-Paletten bereits an anderer Stelle mit fester Bedeutung belegt sind.
    color: 'bg-violet-100 text-violet-800 border-violet-200',
  },
  how_to: {
    label: 'How-To / Anleitung',
    emoji: '🛠',
    color: 'bg-primary-100 text-primary-800 border-primary-200',
  },
  personal_story: {
    label: 'Persönliche Story',
    emoji: '📖',
    color: 'bg-accent-100 text-accent-800 border-accent-200',
  },
  industry_news: {
    label: 'Branchennews',
    emoji: '📰',
    color: 'bg-status-neu-bg text-status-neu-text border-status-neu-border',
  },
  product_service: {
    label: 'Produkt / Service',
    emoji: '🎯',
    // bewusst behalten: siehe thought_leadership oben — 5. unterscheidbare Kategoriefarbe.
    color: 'bg-pink-100 text-pink-800 border-pink-200',
  },
}

// ── SHK/Handwerk Branchen-Hashtags (statisch, kein LLM nötig) ──────────────
const SHK_HASHTAGS = {
  Fachgebiet: [
    '#Handwerk',
    '#SHK',
    '#Heizung',
    '#Sanitär',
    '#Klimatechnik',
    '#Wärmepumpe',
    '#Gebäudetechnik',
    '#Haustechnik',
    '#Installateur',
    '#Klempner',
    '#Heizungsbau',
    '#Anlagenmechaniker',
  ],
  Energiewende: [
    '#Energiewende',
    '#Wärmewende',
    '#Photovoltaik',
    '#Solarenergie',
    '#Nachhaltigkeit',
    '#Klimaschutz',
    '#Gebäudesanierung',
    '#Effizienzhaus',
    '#NachhaltigBauen',
    '#GreenBuilding',
  ],
  Unternehmer: [
    '#Mittelstand',
    '#Meisterbetrieb',
    '#Handwerksmeister',
    '#Fachbetrieb',
    '#Ausbildung',
    '#HandwerkHatZukunft',
    '#Zukunftsbund',
    '#FamilienUnternehmen',
    '#HandwerkDigital',
  ],
  Reichweite: [
    '#LinkedIn',
    '#Handwerker',
    '#Deutschland',
    '#B2B',
    '#Innovation',
    '#Unternehmertum',
    '#Karriere',
  ],
}

// ── LinkedIn Post Templates ─────────────────────────────────────────────────
const POST_TEMPLATES = [
  {
    id: 'list',
    name: 'Listen-Post',
    emoji: '📋',
    pillar: 'how_to',
    desc: 'X Tipps / Wege / Gründe — sehr hohe Reichweite',
    body: `[ZAHL] Dinge, die ich über [THEMA] gelernt habe:\n\n1️⃣ [PUNKT 1]\n\n2️⃣ [PUNKT 2]\n\n3️⃣ [PUNKT 3]\n\n4️⃣ [PUNKT 4]\n\n5️⃣ [PUNKT 5]\n\nDas Wichtigste: [KERNBOTSCHAFT]\n\nWas würdest du noch ergänzen? 👇`,
  },
  {
    id: 'story',
    name: 'Story-Arc',
    emoji: '📖',
    pillar: 'personal_story',
    desc: 'Hook → Situation → Wendepunkt → Erkenntnis',
    body: `[FESSELNDER HOOK — eine Zeile, die neugierig macht]\n\n[SITUATION beschreiben — wo war ich / was war die Ausgangslage]\n\n[WENDEPUNKT — was hat sich verändert, was habe ich getan]\n\n[ERGEBNIS — was hat sich verbessert, was habe ich gelernt]\n\n[UNIVERSELLE LEKTION — was bedeutet das für andere]\n\nHast du ähnliche Erfahrungen gemacht? Schreib's in die Kommentare. 👇`,
  },
  {
    id: 'hot-take',
    name: 'Hot Take',
    emoji: '🔥',
    pillar: 'thought_leadership',
    desc: 'Kontroverse These + Begründung — maximale Interaktion',
    body: `Unpopuläre Meinung:\n[THESE — möglichst provokant, aber begründbar]\n\nDie meisten denken: [COMMON BELIEF]\n\nIch sehe das anders:\n\n→ [ARGUMENT 1]\n→ [ARGUMENT 2]\n→ [ARGUMENT 3]\n\n[KONTEXT / EINSCHRÄNKUNG — wann gilt das nicht]\n\nFalle ich damit allein? Oder siehst du das ähnlich?`,
  },
  {
    id: 'problem-solution',
    name: 'Problem → Lösung',
    emoji: '🛠',
    pillar: 'how_to',
    desc: 'Klassisches PAS-Format: Problem, Agitation, Solution',
    body: `[PROBLEM — direkt ansprechen, in einer Zeile]\n\nViele [ZIELGRUPPE] kennen das:\n\n[PROBLEM AUSFÜHREN — 2-3 Sätze, Schmerz verstärken]\n\nDas kostet [RESSOURCE: Zeit / Geld / Nerven].\n\nWas wirklich hilft:\n\n✅ [LÖSUNG 1]\n✅ [LÖSUNG 2]\n✅ [LÖSUNG 3]\n\n[ERGEBNIS wenn man die Lösung anwendet]\n\nWas ist deine bewährteste Methode? 👇`,
  },
  {
    id: 'behind-scenes',
    name: 'Behind-the-Scenes',
    emoji: '🎬',
    pillar: 'personal_story',
    desc: 'Persönlicher Einblick — baut Vertrauen und Nähe',
    body: `Heute zeige ich euch, was bei [UNTERNEHMEN/PROJEKT] wirklich passiert:\n\n[EINBLICK 1 — konkret und überraschend]\n\n[EINBLICK 2 — etwas, das man von außen nicht sieht]\n\n[EINBLICK 3 — persönliche Herausforderung oder Lernmoment]\n\nWarum teile ich das?\n\n[BEGRÜNDUNG — Transparenz, Lernen, Community]\n\nWas möchtest du noch über [THEMA] wissen? Frag mich! 👇`,
  },
  {
    id: 'stat-insight',
    name: 'Statistik + Einordnung',
    emoji: '📊',
    pillar: 'industry_news',
    desc: 'Überraschende Zahl → deine Perspektive dazu',
    body: `[ÜBERRASCHENDE ZAHL / STUDIE]\n\nDas hat mich aufgeweckt.\n\nWas steckt dahinter?\n\n[EINORDNUNG 1 — Kontext und Hintergrund]\n\n[EINORDNUNG 2 — was das für [BRANCHE/ZIELGRUPPE] bedeutet]\n\nMeine Schlussfolgerung:\n\n[KERNAUSSAGE — konkret und handlungsorientiert]\n\nSiehst du das auch so? Oder habe ich etwas übersehen?`,
  },
  {
    id: 'question',
    name: 'Engagement-Frage',
    emoji: '❓',
    pillar: 'thought_leadership',
    desc: 'Eine starke Frage + deine Antwort = Kommentar-Magnet',
    body: `[FRAGE — polarisierend oder überraschend, 1 Zeile]\n\nMeine ehrliche Antwort:\n\n[ANTWORT 1 — persönliche Position]\n\n[ANTWORT 2 — Begründung oder Beispiel]\n\n[ANTWORT 3 — was ich daraus gelernt habe]\n\nAber ich bin neugierig:\nWie siehst du das? ↓`,
  },
  {
    id: 'before-after',
    name: 'Vorher → Nachher',
    emoji: '✨',
    pillar: 'personal_story',
    desc: 'Transformation zeigen — sehr emotional und teilbar',
    body: `[ZEITRAUM] ago vs. heute:\n\nVorher:\n❌ [NEGATIVER ZUSTAND 1]\n❌ [NEGATIVER ZUSTAND 2]\n❌ [NEGATIVER ZUSTAND 3]\n\nHeute:\n✅ [POSITIVER ZUSTAND 1]\n✅ [POSITIVER ZUSTAND 2]\n✅ [POSITIVER ZUSTAND 3]\n\nWas hat sich geändert?\n\n[SCHLÜSSELENTSCHEIDUNG / METHODE]\n\n[ERKENNTNIS — was andere daraus mitnehmen können]\n\nWoran arbeitest du gerade? 👇`,
  },
]

// ── Post Quality Score ──────────────────────────────────────────────────────
// Weights calibrated for LinkedIn B2B DACH posts
function postScore(text) {
  if (!text || text.length < 30)
    return {
      score: 0,
      grade: 'F',
      tips: ['Post ist zu kurz'],
      color: 'text-status-fehler-text',
      bg: 'bg-status-fehler-bg',
    }
  const tips = []
  let pts = 0

  // 1. Length: LinkedIn optimal 800-1500 chars (max 5 pts)
  const len = text.length
  if (len >= 600 && len <= 1500) pts += 5
  else if (len >= 400 && len < 600) {
    pts += 3
    tips.push('Etwas kurz — ideal 800–1.500 Zeichen')
  } else if (len > 1500 && len <= 2500) {
    pts += 3
    tips.push('Etwas lang — ideal unter 1.500 Zeichen')
  } else if (len < 400) {
    pts += 1
    tips.push('Zu kurz für gute Reichweite')
  } else {
    pts += 1
    tips.push('Sehr lang — Leser springen ab')
  }

  // 2. Hook strength: first 210 chars (max 2 pts)
  const hook = text.slice(0, LI_FOLD)
  const hookHasQuestion = /\?/.test(hook)
  const hookHasBold = hook.length > 30
  if (hookHasQuestion) pts += 1
  else tips.push('Hook ohne Frage — Fragen steigern Kommentare')
  if (hookHasBold && !hook.startsWith(' ')) pts += 1

  // 3. Paragraphs / white space (max 1 pt)
  const paragraphs = text.split(/\n\n+/).length
  if (paragraphs >= 3) pts += 1
  else tips.push('Mehr Absätze → bessere Lesbarkeit')

  // 4. Emojis (max 1 pt)
  const emojiCount = [...text].filter((c) => /\p{Emoji}/u.test(c) && c !== ' ').length
  if (emojiCount >= 1 && emojiCount <= 8) pts += 1
  else if (emojiCount === 0) tips.push('Ein paar Emojis erhöhen Engagement')
  else tips.push('Zu viele Emojis wirken unprofessionell')

  // 5. Call-to-action / question at end (max 1 pt)
  const ending = text.slice(-200)
  if (/\?/.test(ending)) pts += 1
  else tips.push('Frage am Ende animiert zu Kommentaren')

  const score = Math.min(10, Math.round(pts))
  const grade = score >= 8 ? 'A' : score >= 6 ? 'B' : score >= 4 ? 'C' : 'D'
  const color =
    score >= 8
      ? 'text-status-fertig-text'
      : score >= 6
        ? 'text-primary-600'
        : score >= 4
          ? 'text-status-aktiv-text'
          : 'text-status-fehler-text'
  const bg =
    score >= 8
      ? 'bg-status-fertig-bg'
      : score >= 6
        ? 'bg-primary-50'
        : score >= 4
          ? 'bg-status-aktiv-bg'
          : 'bg-status-fehler-bg'
  return { score, grade, tips: tips.slice(0, 3), color, bg }
}

// ── LinkedIn Unicode Formatting ─────────────────────────────────────────────
const BOLD_MAP = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
const BOLD_UNI = '𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵'
const ITALIC_MAP = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
const ITALIC_UNI = '𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻'

function buildLookup(src, dst) {
  const chars = [...dst] // iterate by codepoint (emoji-safe)
  const map = {}
  for (let i = 0; i < src.length; i++) map[src[i]] = chars[i]
  return map
}
const BOLD_LOOKUP = buildLookup(BOLD_MAP, BOLD_UNI)
const ITALIC_LOOKUP = buildLookup(ITALIC_MAP, ITALIC_UNI)

function applyBold(text) {
  return [...text].map((c) => BOLD_LOOKUP[c] || c).join('')
}
function applyItalic(text) {
  return [...text].map((c) => ITALIC_LOOKUP[c] || c).join('')
}
function applyStrike(text) {
  return [...text].map((c) => (c === '\n' ? c : c + '\u0336')).join('')
}

function FormatToolbar({ textareaRef, value, onChange }) {
  function applyFormat(fn) {
    const el = textareaRef.current
    if (!el) return
    const start = el.selectionStart
    const end = el.selectionEnd
    if (start === end) return // no selection
    const before = value.slice(0, start)
    const selected = value.slice(start, end)
    const after = value.slice(end)
    const formatted = fn(selected)
    onChange(before + formatted + after)
    // Restore selection after React re-render
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(start, start + formatted.length)
    })
  }
  const btn =
    'px-2.5 py-1 text-xs font-medium border border-surface-border rounded hover:bg-surface-bg text-ink-muted hover:text-ink transition-colors'
  return (
    <div className="flex items-center gap-1.5 mb-2 p-2 bg-surface-bg border border-surface-border rounded-lg">
      <span className="text-[10px] text-ink-muted mr-1">LinkedIn Formatierung:</span>
      <button
        type="button"
        className={btn}
        onClick={() => applyFormat(applyBold)}
        title="Fett (Text auswählen)"
      >
        <span className="font-bold">B</span>
      </button>
      <button
        type="button"
        className={btn}
        onClick={() => applyFormat(applyItalic)}
        title="Kursiv (Text auswählen)"
      >
        <span className="italic">I</span>
      </button>
      <button
        type="button"
        className={btn}
        onClick={() => applyFormat(applyStrike)}
        title="Durchgestrichen (Text auswählen)"
      >
        <span className="line-through">S</span>
      </button>
      <span className="text-[10px] text-ink-muted ml-1">← Text markieren, dann klicken</span>
    </div>
  )
}

// ── Duplicate Detection ─────────────────────────────────────────────────────
function jaccardSim(a, b) {
  const words = (t) =>
    new Set(
      t
        .toLowerCase()
        .replace(/[^\wäöüß]/g, ' ')
        .split(/\s+/)
        .filter((w) => w.length > 3)
    )
  const A = words(a),
    B = words(b)
  if (!A.size || !B.size) return 0
  let inter = 0
  A.forEach((w) => {
    if (B.has(w)) inter++
  })
  return inter / (A.size + B.size - inter)
}

function computeDuplicates(posts, threshold = 0.55) {
  const map = new Map() // postId -> max sim score (0–1)
  for (let i = 0; i < posts.length; i++) {
    for (let j = i + 1; j < posts.length; j++) {
      const sim = jaccardSim(posts[i].content_text || '', posts[j].content_text || '')
      if (sim >= threshold) {
        map.set(posts[i].id, Math.max(map.get(posts[i].id) || 0, sim))
        map.set(posts[j].id, Math.max(map.get(posts[j].id) || 0, sim))
      }
    }
  }
  return map
}

// LinkedIn fold: ~210 visible chars before "…mehr" on desktop
const LI_FOLD = 210
const LI_MAX = 3000

function CharCounter({ text }) {
  const len = text.length
  const pct = Math.min((len / LI_MAX) * 100, 100)
  const color =
    len > 2500
      ? 'text-status-fehler-text'
      : len > 1300
        ? 'text-status-aktiv-text'
        : 'text-status-fertig-text'
  const barColor =
    len > 2500 ? 'bg-status-fehler-border' : len > 1300 ? 'bg-status-aktiv-border' : 'bg-status-fertig-border'
  const foldPct = Math.min((LI_FOLD / LI_MAX) * 100, 100)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <span className={`font-semibold tabular-nums ${color}`}>{len.toLocaleString('de')}</span>
          <span className="text-ink-muted">/ 3.000 Zeichen</span>
          {len <= LI_FOLD ? (
            <span className="px-1.5 py-0.5 bg-status-fertig-bg text-status-fertig-text rounded text-[10px] font-medium">
              ✓ Vor der Falte
            </span>
          ) : (
            <span className="px-1.5 py-0.5 bg-status-aktiv-bg text-status-aktiv-text rounded text-[10px] font-medium">
              ↓ Nach „…mehr" ({len - LI_FOLD} Zeichen)
            </span>
          )}
        </div>
        <span className="text-ink-muted tabular-nums">{LI_MAX - len} übrig</span>
      </div>
      {/* Progress bar with fold marker */}
      <div className="relative h-1.5 bg-surface-border rounded-full overflow-visible">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
        {/* Fold marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 bg-primary-400 rounded"
          style={{ left: `${foldPct}%` }}
          title={`LinkedIn-Falte bei ${LI_FOLD} Zeichen`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-ink-muted">
        <span>0</span>
        <span className="text-primary-500" style={{ marginLeft: `${foldPct - 5}%` }}>
          Falte
        </span>
        <span>3.000</span>
      </div>
    </div>
  )
}

function LinkedInPreview({
  text: rawText,
  authorName = 'Eric M.',
  authorTitle = 'Unternehmer | SHK & Handwerk',
}) {
  const text = rawText || ''
  const [expanded, setExpanded] = useState(false)
  const isLong = text.length > LI_FOLD

  // Split at fold point for authentic preview
  const visibleText = isLong && !expanded ? text.slice(0, LI_FOLD) : text
  const foldChar = isLong && !expanded ? text[LI_FOLD - 1] : null

  return (
    // bewusst behalten: gray-*/blue-* hier = originalgetreue Nachbildung der echten
    // LinkedIn-UI-Farben (Fremdmarke), keine App-eigene Bedeutung — Token-Ersatz würde
    // die Vorschau-Illusion brechen.
    <div className="bg-white rounded-xl border border-gray-200 shadow-md max-w-lg mx-auto font-sans">
      {/* Header */}
      <div className="p-4 flex items-start gap-3">
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-teal-400 to-teal-700 flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
          {authorName.charAt(0)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-sm text-gray-900">{authorName}</span>
            <span className="text-gray-400 text-xs">• 1.</span>
          </div>
          <p className="text-xs text-gray-500 truncate">{authorTitle}</p>
          <div className="flex items-center gap-1 mt-0.5">
            <span className="text-xs text-gray-400">gerade eben</span>
            <span className="text-gray-300">·</span>
            <span className="text-xs text-gray-400">🌐</span>
          </div>
        </div>
        <button className="text-xs font-semibold text-blue-600 hover:text-blue-700 px-2">
          + Folgen
        </button>
      </div>
      {/* Content */}
      <div className="px-4 pb-3">
        <div className="text-sm text-gray-900 leading-relaxed whitespace-pre-line">
          {visibleText}
          {isLong && !expanded ? '…' : ''}
        </div>
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-blue-600 hover:text-blue-700 font-medium mt-1"
          >
            {expanded ? 'Weniger anzeigen' : 'mehr anzeigen'}
          </button>
        )}
        {isLong && !expanded && (
          <p className="text-[10px] text-gray-400 mt-1">
            ↑ LinkedIn zeigt {LI_FOLD} Zeichen — {text.length - LI_FOLD} weitere hinter „mehr
            anzeigen"
          </p>
        )}
      </div>
      {/* Reactions bar */}
      <div className="px-4 py-1.5 flex items-center justify-between border-t border-gray-100">
        <div className="flex items-center gap-1">
          <span className="text-base">👍</span>
          <span className="text-base">❤️</span>
          <span className="text-xs text-gray-500 ml-1">47</span>
        </div>
        <div className="text-xs text-gray-500">12 Kommentare · 3 Weiterleitungen</div>
      </div>
      {/* Action buttons */}
      <div className="px-2 pb-3 flex items-center justify-around border-t border-gray-100 pt-1">
        {[
          { icon: ThumbsUp, label: 'Gefällt mir' },
          { icon: MessageSquare, label: 'Kommentieren' },
          { icon: Repeat2, label: 'Weiterleiten' },
          { icon: Send, label: 'Senden' },
        ].map(({ icon: Icon, label }) => (
          <button
            key={label}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-gray-500 hover:bg-gray-100 text-xs font-medium"
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

const STATUS_COLORS = {
  draft: 'bg-status-neu-bg text-status-neu-text',
  approved: 'bg-status-fertig-bg text-status-fertig-text',
  published: 'bg-primary-100 text-primary-700',
  rejected: 'bg-status-fehler-bg text-status-fehler-text',
}

function HighlightText({ text: rawText, query }) {
  const text = rawText || ''
  if (!query || !query.trim()) return <>{text}</>
  const q = query.trim()
  const parts = text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === q.toLowerCase() ? (
          <mark key={i} className="bg-accent-200 text-accent-900 rounded-sm px-0.5 not-italic">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  )
}

function PostCard({ post, onSelect, isSelected, onToggleSelect, dupeSim, searchTerm, isFocused }) {
  const variant = post.content_metadata?.variant
  const angle = post.content_metadata?.angle
  const dupeWarn = dupeSim != null && dupeSim >= 0.55
  const qs = useMemo(() => postScore(post.content_text || ''), [post.content_text])
  const [userRating, setUserRating] = useState(null) // null | 'up' | 'down'
  async function handleRate(e, dir) {
    e.stopPropagation()
    if (!post.source_item_id) return
    const newRating = userRating === dir ? null : dir
    setUserRating(newRating)
    if (newRating) {
      try {
        await rateItemQuality(post.source_item_id, 'post_generation', newRating === 'up' ? 5 : 1)
      } catch {}
    }
  }
  return (
    <div
      id={`post-card-${post.id}`}
      onClick={() => onSelect(post.id)}
      className={`bg-white rounded-xl border hover:shadow-sm transition-all cursor-pointer p-5 ${isFocused ? 'border-primary-400 ring-2 ring-primary-200' : isSelected ? 'border-status-fertig-border bg-status-fertig-bg' : dupeWarn ? 'border-status-aktiv-border hover:border-accent-400' : 'border-surface-border hover:border-primary-300'}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          {post.status === 'draft' && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onToggleSelect(post.id)
              }}
              className="text-status-fertig-text hover:opacity-80 flex-shrink-0"
            >
              {isSelected ? (
                <CheckSquare className="w-4 h-4" />
              ) : (
                <Square className="w-4 h-4 text-ink-muted hover:text-status-fertig-border" />
              )}
            </button>
          )}
          <span
            className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[post.status] || 'bg-surface-bg text-ink-light'}`}
          >
            {post.status === 'draft'
              ? 'Entwurf'
              : post.status === 'approved'
                ? 'Freigegeben'
                : post.status === 'published'
                  ? 'Gepostet'
                  : post.status}
          </span>
          {variant && <span className="text-xs text-ink-muted">Variante {variant}</span>}
          {angle && (
            <span className="px-2 py-0.5 rounded bg-surface-bg text-xs text-ink-light">{angle}</span>
          )}
          {(() => {
            const p = post.content_metadata?.pillar
            const cfg = p && PILLAR_CONFIG[p]
            return cfg ? (
              <span className={`px-2 py-0.5 rounded border text-[11px] font-medium ${cfg.color}`}>
                {cfg.emoji} {cfg.label}
              </span>
            ) : null
          })()}
          {dupeWarn && (
            <span
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-status-aktiv-bg text-status-aktiv-text text-[11px] font-medium"
              title={`Ähnlichkeit: ${Math.round(dupeSim * 100)}%`}
            >
              <AlertTriangle className="w-3 h-3" /> {Math.round(dupeSim * 100)}% ähnlich
            </span>
          )}
        </div>
        {/* Quality Score Badge */}
        <span
          className={`shrink-0 px-2 py-0.5 rounded-lg text-[11px] font-bold ${qs.color} ${qs.bg}`}
          title={qs.tips.length ? qs.tips.join(' · ') : 'Guter Post!'}
        >
          {qs.score}/10
        </span>
      </div>
      <p className="text-sm text-ink leading-relaxed line-clamp-4 whitespace-pre-line">
        <HighlightText text={post.content_text || ''} query={searchTerm} />
      </p>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-surface-border">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] text-ink-muted shrink-0">
            {post.created_at
              ? new Date(post.created_at).toLocaleDateString('de-DE', {
                  day: '2-digit',
                  month: '2-digit',
                  year: 'numeric',
                })
              : '-'}
          </span>
          {post.source_name && (
            <span
              className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-bg text-ink-light max-w-[100px] truncate"
              title={post.source_name}
            >
              {post.source_name}
            </span>
          )}
          {(post.source_item_title || post.content_metadata?.source_title) && (
            <span
              className="text-[10px] text-ink-light truncate max-w-[160px]"
              title={post.source_item_title || post.content_metadata?.source_title}
            >
              🎬 {post.source_item_title || post.content_metadata?.source_title}
            </span>
          )}
          {post.status === 'draft' &&
            post.created_at &&
            (() => {
              const ageDays = Math.floor((Date.now() - new Date(post.created_at)) / 86400000)
              if (ageDays >= 30)
                return (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-status-fehler-bg text-status-fehler-text"
                    title={`${ageDays} Tage alt`}
                  >
                    🔴 {ageDays >= 90 ? '90d+' : `${ageDays}d`}
                  </span>
                )
              if (ageDays >= 14)
                return (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-accent-100 text-accent-700"
                    title={`${ageDays} Tage alt`}
                  >
                    🟠 {ageDays}d
                  </span>
                )
              if (ageDays >= 7)
                return (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-status-aktiv-bg text-status-aktiv-text"
                    title={`${ageDays} Tage alt`}
                  >
                    🟡 {ageDays}d
                  </span>
                )
              return null
            })()}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Tags */}
          {(post.content_metadata?.tags || []).map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded-full text-[9px] font-medium bg-accent-100 text-accent-700 border border-accent-200"
            >
              #{tag}
            </span>
          ))}
          {post.source_item_id && (
            <div className="flex items-center gap-1" title="Qualität bewerten">
              <button
                onClick={(e) => handleRate(e, 'up')}
                className={`p-1 rounded transition-colors ${userRating === 'up' ? 'text-status-fertig-text bg-status-fertig-bg' : 'text-ink-muted hover:text-status-fertig-border'}`}
              >
                <ThumbsUp className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={(e) => handleRate(e, 'down')}
                className={`p-1 rounded transition-colors ${userRating === 'down' ? 'text-status-fehler-text bg-status-fehler-bg' : 'text-ink-muted hover:text-status-fehler-border'}`}
              >
                <ThumbsDown className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          <span className="text-xs text-primary-600 font-medium">Details &rarr;</span>
        </div>
      </div>
    </div>
  )
}

function TriageCard({ post, approveSet, rejectSet, onApprove, onReject }) {
  const angle = post.content_metadata?.angle
  const channel = post.channel || 'linkedin'
  const preview = (post.content_text || '').slice(0, 80)
  const hasMore = (post.content_text || '').length > 80
  const isApproved = approveSet.has(post.id)
  const isRejected = rejectSet.has(post.id)
  return (
    <div
      className={`rounded-xl border p-3 transition-all ${
        isApproved
          ? 'border-status-fertig-border bg-status-fertig-bg'
          : isRejected
            ? 'border-status-fehler-border bg-status-fehler-bg'
            : 'border-surface-border bg-white hover:border-primary-300'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1 mr-2">
          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-status-neu-bg text-status-neu-text shrink-0">
            {channel}
          </span>
          {angle && <span className="text-[10px] text-ink-muted truncate">{angle}</span>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onApprove(post.id)}
            className={`w-7 h-7 rounded-lg flex items-center justify-center text-sm font-bold transition-colors ${
              isApproved
                ? 'bg-status-fertig-border text-white'
                : 'bg-status-fertig-bg text-status-fertig-text hover:bg-status-fertig-border'
            }`}
            title="Freigeben"
          >
            ✓
          </button>
          <button
            onClick={() => onReject(post.id)}
            className={`w-7 h-7 rounded-lg flex items-center justify-center text-sm font-bold transition-colors ${
              isRejected
                ? 'bg-status-fehler-border text-white'
                : 'bg-status-fehler-bg text-status-fehler-text hover:bg-status-fehler-border'
            }`}
            title="Verwerfen"
          >
            ✗
          </button>
        </div>
      </div>
      <p className="text-xs text-ink leading-relaxed">
        {preview}
        {hasMore ? '…' : ''}
      </p>
    </div>
  )
}

// ── AI Rewrite Panel ─────────────────────────────────────────────────────────
const REWRITE_MODES = [
  { id: 'shorter', emoji: '✂️', label: 'Kürzer', desc: '600–900 Zeichen, Kern bleibt' },
  { id: 'hook', emoji: '🎣', label: 'Hook verbessern', desc: 'Erste 3 Zeilen neu — mehr Klicks' },
  { id: 'cta', emoji: '🎯', label: 'CTA hinzufügen', desc: 'Stärkerer Abschluss + Frage' },
  {
    id: 'professional',
    emoji: '👔',
    label: 'Professioneller',
    desc: 'B2B DACH Ton, mehr Autorität',
  },
  { id: 'casual', emoji: '😊', label: 'Lockerer', desc: 'Persönlicher, zugänglicher' },
]

function RewritePanel({ postId, postText, loading, result, onRewrite, onApply }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-4 h-4 text-accent-500" />
        <span className="text-sm font-semibold text-ink">KI-Post-Rewriter</span>
        <span className="text-[11px] text-ink-muted ml-1">Wähle einen Verbesserungs-Modus:</span>
      </div>

      {/* Mode buttons */}
      <div className="grid grid-cols-5 gap-2">
        {REWRITE_MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => onRewrite(m.id)}
            disabled={loading}
            className="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-surface-border bg-white hover:border-accent-300 hover:bg-accent-50 transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed group"
          >
            <span className="text-2xl">{m.emoji}</span>
            <span className="text-[11px] font-semibold text-ink group-hover:text-accent-800 leading-tight">
              {m.label}
            </span>
            <span className="text-[10px] text-ink-muted leading-tight">{m.desc}</span>
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 p-4 bg-accent-50 rounded-xl border border-accent-200">
          <RefreshCw className="w-4 h-4 text-accent-500 animate-spin" />
          <span className="text-sm text-accent-700">KI überarbeitet den Post...</span>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          {/* Stats comparison */}
          <div className="flex items-center gap-4 p-3 bg-accent-50 rounded-lg border border-accent-100 text-xs">
            <span className="text-ink-muted">
              Original: <strong className="text-ink">{result.original_chars} Z</strong>
            </span>
            <span className="text-accent-400">→</span>
            <span className="text-ink-muted">
              Rewrite:{' '}
              <strong
                className={
                  result.rewritten_chars <= 900
                    ? 'text-status-fertig-text'
                    : result.rewritten_chars <= 1500
                      ? 'text-primary-700'
                      : 'text-status-aktiv-text'
                }
              >
                {result.rewritten_chars} Z
              </strong>
            </span>
            <span
              className={`ml-auto font-medium ${result.rewritten_chars < result.original_chars ? 'text-status-fertig-text' : 'text-status-aktiv-text'}`}
            >
              {result.rewritten_chars < result.original_chars
                ? `−${result.original_chars - result.rewritten_chars}`
                : `+${result.rewritten_chars - result.original_chars}`}{' '}
              Zeichen
            </span>
          </div>

          {/* Rewritten text */}
          <div className="relative">
            <div
              className={`bg-white border border-accent-200 rounded-xl p-4 text-sm text-ink leading-relaxed whitespace-pre-line ${expanded ? '' : 'max-h-48 overflow-hidden'}`}
            >
              {result.rewritten_text}
            </div>
            {!expanded && result.rewritten_chars > 400 && (
              <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white to-transparent rounded-b-xl" />
            )}
            <button
              onClick={() => setExpanded(!expanded)}
              className="absolute bottom-2 right-3 flex items-center gap-1 text-[11px] text-accent-600 hover:text-accent-800 font-medium"
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-3 h-3" /> Einklappen
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3" /> Mehr anzeigen
                </>
              )}
            </button>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onApply(result.rewritten_text)}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-accent-600 rounded-lg hover:bg-accent-700 transition-colors"
            >
              <Check className="w-3.5 h-3.5" /> Übernehmen & speichern
            </button>
            <button
              onClick={() => navigator.clipboard.writeText(result.rewritten_text)}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-accent-700 border border-accent-200 rounded-lg hover:bg-accent-50"
            >
              <Copy className="w-3.5 h-3.5" /> Kopieren
            </button>
            <button
              onClick={() => onRewrite(result.mode)}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-50"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Nochmal
            </button>
            <span className="ml-auto text-[10px] text-ink-muted">
              Modus: {REWRITE_MODES.find((m) => m.id === result.mode)?.label}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── A/B Variant Panel ─────────────────────────────────────────────────────────
function ABVariantsPanel({ loading, variants, onGenerate, onApply }) {
  const [picked, setPicked] = useState(null)
  const [expandA, setExpandA] = useState(false)
  const [expandB, setExpandB] = useState(false)

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 bg-accent-50 rounded-xl border border-accent-200">
        <RefreshCw className="w-4 h-4 text-accent-500 animate-spin" />
        <span className="text-sm text-accent-700">
          KI generiert 2 Varianten (Listen- vs. Story-Format)...
        </span>
      </div>
    )
  }

  if (!variants) {
    return (
      <div className="text-center py-8 space-y-3">
        <div className="text-4xl">🅰🅱</div>
        <p className="text-sm font-semibold text-ink">A/B Varianten-Generator</p>
        <p className="text-xs text-ink-muted max-w-xs mx-auto">
          Erhalte 2 strukturell verschiedene Versionen deines Posts — Listen-Format vs.
          Story-Format. Wähle deine Lieblingsversion.
        </p>
        <button
          onClick={onGenerate}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-accent-600 rounded-xl hover:bg-accent-700 transition-colors"
        >
          <Sparkles className="w-4 h-4" /> 2 Varianten generieren
        </button>
      </div>
    )
  }

  const cards = [
    {
      key: 'a',
      v: variants.variant_a,
      label: 'Variante A',
      badge: '📋 Listen-Format',
      badgeColor: 'bg-status-neu-bg text-status-neu-text',
      expanded: expandA,
      setExpanded: setExpandA,
    },
    {
      key: 'b',
      v: variants.variant_b,
      label: 'Variante B',
      badge: '📖 Story-Format',
      badgeColor: 'bg-accent-100 text-accent-800',
      expanded: expandB,
      setExpanded: setExpandB,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">A/B Varianten</span>
          <span className="text-[11px] text-ink-muted">
            Klicke eine Variante zum Auswählen, dann übernehmen
          </span>
        </div>
        <button
          onClick={onGenerate}
          className="flex items-center gap-1.5 text-[11px] text-accent-600 border border-accent-200 rounded-lg px-2.5 py-1 hover:bg-accent-50"
        >
          <RefreshCw className="w-3 h-3" /> Neu generieren
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {cards.map(({ key, v, label, badge, badgeColor, expanded, setExpanded }) => (
          <div
            key={key}
            onClick={() => setPicked(key)}
            className={`relative rounded-xl border-2 cursor-pointer transition-all ${picked === key ? 'border-accent-500 bg-accent-50 shadow-sm' : 'border-surface-border bg-white hover:border-accent-300 hover:bg-accent-50/40'}`}
          >
            {picked === key && (
              <div className="absolute -top-2.5 left-3">
                <span className="px-2 py-0.5 bg-accent-600 text-white text-[10px] font-bold rounded-full">
                  ✓ Gewählt
                </span>
              </div>
            )}
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-ink">{label}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${badgeColor}`}>
                  {badge}
                </span>
              </div>
              <div
                className={`text-xs text-ink leading-relaxed whitespace-pre-line ${expanded ? '' : 'max-h-32 overflow-hidden'}`}
              >
                {v.text}
              </div>
              {!expanded && v.chars > 300 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setExpanded(true)
                  }}
                  className="mt-1 text-[10px] text-accent-600 hover:underline"
                >
                  Mehr anzeigen ({v.chars} Z) ↓
                </button>
              )}
              {expanded && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setExpanded(false)
                  }}
                  className="mt-1 text-[10px] text-accent-600 hover:underline"
                >
                  Einklappen ↑
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {picked && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() =>
              onApply(picked === 'a' ? variants.variant_a.text : variants.variant_b.text)
            }
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-accent-600 rounded-lg hover:bg-accent-700"
          >
            <Check className="w-3.5 h-3.5" /> Variante {picked.toUpperCase()} übernehmen
          </button>
          <button
            onClick={() =>
              navigator.clipboard.writeText(
                picked === 'a' ? variants.variant_a.text : variants.variant_b.text
              )
            }
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-accent-700 border border-accent-200 rounded-lg hover:bg-accent-50"
          >
            <Copy className="w-3.5 h-3.5" /> Kopieren
          </button>
          <span className="ml-auto text-[10px] text-ink-muted">
            {picked === 'a' ? variants.variant_a.chars : variants.variant_b.chars} Zeichen
          </span>
        </div>
      )}
    </div>
  )
}

// ── Multi-Format Repurposer Panel ─────────────────────────────────────────────
const FORMAT_TABS = [
  { id: 'twitter', label: '𝕏 Twitter Thread', icon: '🧵' },
  { id: 'email', label: '📧 Newsletter Intro', icon: '📧' },
  { id: 'blog', label: '📝 Blog Outline', icon: '📝' },
]

// ── Pre-Publish Checklist Panel (Cycle 43) ───────────────────────────────────
const AUTO_RULES = [
  {
    id: 'hook',
    label: 'Hook überzeugt (erste Zeile < 210 Zeichen, kein Leerzeichen am Anfang)',
    check: (t) => t && t.length > 10 && !t.startsWith(' ') && t.slice(0, 210).trim().length > 20,
  },
  {
    id: 'length',
    label: 'Optimale Länge (800–1.900 Zeichen)',
    check: (t) => t && t.length >= 800 && t.length <= 1900,
  },
  {
    id: 'paragraphs',
    label: 'Mindestens 3 Absätze (Zeilenumbrüche für Lesbarkeit)',
    check: (t) => t && t.split(/\n\n+/).length >= 3,
  },
  {
    id: 'question',
    label: 'Frage am Ende (animiert Kommentare)',
    check: (t) => t && /\?/.test(t.slice(-250)),
  },
  {
    id: 'emoji',
    label: 'Emojis vorhanden (1–8 Stück)',
    check: (t) => {
      if (!t) return false
      const n = [...t].filter((c) => /\p{Emoji}/u.test(c) && c !== ' ').length
      return n >= 1 && n <= 8
    },
  },
  {
    id: 'no_hashtag_spam',
    label: 'Nicht mehr als 5 Hashtags',
    check: (t) => {
      if (!t) return false
      const n = (t.match(/#\w+/g) || []).length
      return n <= 5
    },
  },
]
const MANUAL_RULES = [
  { id: 'pillar', label: 'Content-Säule zugewiesen' },
  { id: 'cta', label: 'Call-to-Action ist klar' },
  { id: 'typos', label: 'Rechtschreibung geprüft' },
  { id: 'original', label: 'Kein doppelter Inhalt' },
]

function ChecklistPanel({ post, onApprove, approving }) {
  const text = post?.content_text || ''
  const [manual, setManual] = useState({})

  function toggleManual(id) {
    setManual((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const autoResults = AUTO_RULES.map((r) => ({ ...r, passed: r.check(text) }))
  const manualResults = MANUAL_RULES.map((r) => ({ ...r, passed: !!manual[r.id] }))
  const allResults = [...autoResults, ...manualResults]
  const passedCount = allResults.filter((r) => r.passed).length
  const total = allResults.length
  const pct = Math.round((passedCount / total) * 100)
  const criticalPassed = autoResults
    .filter((r) => ['hook', 'length', 'question'].includes(r.id))
    .every((r) => r.passed)
  const readyToApprove = criticalPassed && passedCount >= total - 2

  return (
    <div className="space-y-4">
      {/* Progress header */}
      <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-primary-50 to-status-fertig-bg rounded-xl border border-primary-200">
        <div className="text-center">
          <div
            className={`text-3xl font-black tabular-nums ${pct >= 80 ? 'text-status-fertig-text' : pct >= 60 ? 'text-status-aktiv-text' : 'text-status-fehler-text'}`}
          >
            {pct}
            <span className="text-lg">%</span>
          </div>
          <div className="text-[10px] text-ink-muted">Bereit</div>
        </div>
        <div className="flex-1">
          <div className="h-2.5 bg-white/60 rounded-full overflow-hidden border border-primary-100 mb-1.5">
            <div
              className={`h-full rounded-full transition-all duration-500 ${pct >= 80 ? 'bg-status-fertig-border' : pct >= 60 ? 'bg-status-aktiv-border' : 'bg-status-fehler-border'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-xs text-primary-700">
            <span className="font-semibold">
              {passedCount}/{total}
            </span>{' '}
            Kriterien erfüllt
          </p>
        </div>
        {readyToApprove && post?.status === 'draft' && (
          <button
            onClick={onApprove}
            disabled={approving}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-status-fertig-border hover:opacity-90 rounded-xl disabled:opacity-50 transition-colors"
          >
            <Check className="w-4 h-4" /> {approving ? '...' : 'Jetzt freigeben'}
          </button>
        )}
      </div>

      {/* Auto-checked rules */}
      <div>
        <p className="text-xs font-semibold text-ink-muted mb-2">🤖 Automatisch geprüft</p>
        <div className="space-y-1.5">
          {autoResults.map((r) => (
            <div
              key={r.id}
              className={`flex items-start gap-2.5 p-2.5 rounded-lg border ${r.passed ? 'bg-status-fertig-bg border-status-fertig-border' : 'bg-status-fehler-bg border-status-fehler-border'}`}
            >
              <span
                className={`text-base shrink-0 leading-none mt-0.5 ${r.passed ? 'text-status-fertig-text' : 'text-status-fehler-text'}`}
              >
                {r.passed ? '✓' : '✗'}
              </span>
              <span
                className={`text-xs leading-relaxed ${r.passed ? 'text-status-fertig-text' : 'text-status-fehler-text'}`}
              >
                {r.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Manual checkboxes */}
      <div>
        <p className="text-xs font-semibold text-ink-muted mb-2">☑️ Manuell bestätigen</p>
        <div className="space-y-1.5">
          {manualResults.map((r) => (
            <div
              key={r.id}
              onClick={() => toggleManual(r.id)}
              className={`flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors ${r.passed ? 'bg-status-fertig-bg border-status-fertig-border hover:opacity-90' : 'bg-surface-bg border-surface-border hover:bg-surface-border/40'}`}
            >
              <div
                className={`w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center transition-colors ${r.passed ? 'bg-status-fertig-border border-status-fertig-border' : 'border-ink-muted'}`}
              >
                {r.passed && <Check className="w-2.5 h-2.5 text-white" />}
              </div>
              <span
                className={`text-xs ${r.passed ? 'text-status-fertig-text line-through decoration-status-fertig-border' : 'text-ink'}`}
              >
                {r.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {!readyToApprove && (
        <p className="text-[11px] text-ink-muted text-center pb-1">
          {criticalPassed
            ? 'Fast da — noch manuelle Punkte ausstehend'
            : '⚠️ Kritische Kriterien (Hook, Länge, Frage) noch nicht erfüllt'}
        </p>
      )}
    </div>
  )
}

function MultiFormatPanel({ loading, result, onGenerate }) {
  const [tab, setTab] = useState('twitter')
  const [copied, setCopied] = useState(null)

  function copyText(text, key) {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-3 p-6 bg-accent-50 rounded-xl border border-accent-200">
        <RefreshCw className="w-4 h-4 text-accent-500 animate-spin" />
        <span className="text-sm text-accent-700">
          Konvertiere in 3 Formate (Twitter, Newsletter, Blog)...
        </span>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="text-center py-10 space-y-3">
        <div className="flex justify-center gap-3 text-3xl">🧵 📧 📝</div>
        <p className="text-sm font-semibold text-ink">Multi-Format Repurposer</p>
        <p className="text-xs text-ink-muted max-w-xs mx-auto">
          Wandle diesen LinkedIn-Post in einen Twitter-Thread, ein Newsletter-Intro und ein
          Blog-Outline um — in einem Klick.
        </p>
        <button
          onClick={onGenerate}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-accent-500 rounded-xl hover:bg-accent-600 transition-colors"
        >
          <Sparkles className="w-4 h-4" /> In 3 Formate konvertieren
        </button>
      </div>
    )
  }

  const content = {
    twitter: result.twitter_thread,
    email: result.email_newsletter,
    blog: result.blog_outline,
  }

  const currentData = content[tab]
  const text = currentData?.text || currentData?.tweets?.join('\n\n---\n\n') || ''

  return (
    <div className="space-y-3">
      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 bg-surface-bg rounded-xl">
        {FORMAT_TABS.map((f) => (
          <button
            key={f.id}
            onClick={() => setTab(f.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all ${tab === f.id ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}`}
          >
            <span>{f.icon}</span> {f.label.split(' ').slice(1).join(' ')}
          </button>
        ))}
        <button
          onClick={onGenerate}
          className="px-2.5 py-1.5 text-[10px] text-accent-600 border border-accent-200 rounded-lg hover:bg-accent-50 ml-1 whitespace-nowrap"
        >
          <RefreshCw className="w-3 h-3 inline mr-1" />
          Neu
        </button>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-3 text-[10px] text-ink-muted px-1">
        {tab === 'twitter' && result.twitter_thread && (
          <>
            <span>{result.twitter_thread.tweet_count} Tweets</span>
            <span>·</span>
            <span>
              Ø{' '}
              {result.twitter_thread.tweets?.length
                ? Math.round(
                    result.twitter_thread.tweets.reduce((a, t) => a + t.length, 0) /
                      result.twitter_thread.tweets.length
                  )
                : 0}{' '}
              Z/Tweet
            </span>
          </>
        )}
        {tab === 'email' && <span>{result.email_newsletter?.chars} Zeichen</span>}
        {tab === 'blog' && <span>{result.blog_outline?.chars} Zeichen</span>}
        <span className="ml-auto text-[10px]">Original: {result.original_chars} Z.</span>
      </div>

      {/* Content display */}
      {tab === 'twitter' && result.twitter_thread?.tweets?.length > 0 ? (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {result.twitter_thread.tweets.map((tweet, i) => (
            <div key={i} className="bg-surface-bg rounded-xl border border-surface-border p-3">
              <div className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-primary-100 text-primary-700 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <p className="text-xs text-ink leading-relaxed flex-1">{tweet}</p>
              </div>
              <div className="flex items-center justify-between mt-1.5 pl-7">
                <span
                  className={`text-[9px] ${tweet.length > 280 ? 'text-status-fehler-text font-bold' : 'text-ink-muted'}`}
                >
                  {tweet.length}/280
                </span>
                <button
                  onClick={() => copyText(tweet, `tweet-${i}`)}
                  className="text-[9px] text-primary-600 hover:text-primary-800"
                >
                  {copied === `tweet-${i}` ? '✓ Kopiert' : 'Kopieren'}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-surface-bg rounded-xl border border-surface-border p-4 max-h-80 overflow-y-auto">
          <p className="text-xs text-ink leading-relaxed whitespace-pre-line">{text}</p>
        </div>
      )}

      {/* Copy all button */}
      <button
        onClick={() => copyText(text, 'all')}
        className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-medium border transition-all ${copied === 'all' ? 'bg-status-fertig-bg text-status-fertig-text border-status-fertig-border' : 'bg-white text-ink-muted border-surface-border hover:bg-surface-bg hover:text-ink'}`}
      >
        <Copy className="w-3.5 h-3.5" />
        {copied === 'all'
          ? '✓ Kopiert!'
          : `Ganzen ${FORMAT_TABS.find((f) => f.id === tab)?.label} kopieren`}
      </button>
    </div>
  )
}

// ── Performance Predictor Panel (Cycle 39) ───────────────────────────────────
function PerformancePredictorPanel({ loading, result, onGenerate }) {
  if (loading) {
    return (
      <div className="flex items-center gap-3 p-6 bg-accent-50 rounded-xl border border-accent-200">
        <RefreshCw className="w-4 h-4 text-accent-500 animate-spin" />
        <span className="text-sm text-accent-700">
          Analysiere Post und sage Engagement vorher...
        </span>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="text-center py-10 space-y-3">
        <div className="text-4xl">🔮</div>
        <p className="text-sm font-semibold text-ink">Performance-Vorschau</p>
        <p className="text-xs text-ink-muted max-w-xs mx-auto">
          KI analysiert deinen Post und schätzt Reichweite, Reaktionen und Kommentare — bevor du
          postest.
        </p>
        <button
          onClick={onGenerate}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-accent-600 rounded-xl hover:bg-accent-700 transition-colors"
        >
          <Sparkles className="w-4 h-4" /> Performance vorhersagen
        </button>
      </div>
    )
  }

  const gradeColor =
    {
      A: 'text-status-fertig-text',
      B: 'text-status-neu-text',
      C: 'text-status-aktiv-text',
      D: 'text-status-fehler-text',
    }[result.grade] || 'text-ink-light'
  const gradeBg =
    {
      A: 'bg-status-fertig-bg border-status-fertig-border',
      B: 'bg-status-neu-bg border-status-neu-border',
      C: 'bg-status-aktiv-bg border-status-aktiv-border',
      D: 'bg-status-fehler-bg border-status-fehler-border',
    }[result.grade] || 'bg-surface-bg border-surface-border'

  return (
    <div className="space-y-4">
      {/* Score header */}
      <div className={`rounded-xl border p-4 ${gradeBg}`}>
        <div className="flex items-center gap-4">
          <div className="text-center">
            <div className={`text-4xl font-black tabular-nums ${gradeColor}`}>{result.grade}</div>
            <div className="text-[10px] text-ink-muted mt-0.5">Note</div>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="flex-1 h-2 bg-white/60 rounded-full overflow-hidden border">
                <div
                  className={`h-full rounded-full ${result.engagement_score >= 70 ? 'bg-status-fertig-border' : result.engagement_score >= 50 ? 'bg-status-neu-border' : result.engagement_score >= 30 ? 'bg-status-aktiv-border' : 'bg-status-fehler-border'}`}
                  style={{ width: `${result.engagement_score}%` }}
                />
              </div>
              <span className={`text-sm font-bold tabular-nums ${gradeColor}`}>
                {result.engagement_score}/100
              </span>
            </div>
            <p className="text-[11px] text-ink-muted">{result.hook_feedback}</p>
          </div>
        </div>
      </div>

      {/* Predicted metrics */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { icon: '👁', label: 'Reichweite', value: result.predicted_reach },
          { icon: '❤️', label: 'Reaktionen', value: result.predicted_likes },
          { icon: '💬', label: 'Kommentare', value: result.predicted_comments },
        ].map((m) => (
          <div
            key={m.label}
            className="text-center p-3 bg-surface-bg rounded-xl border border-surface-border"
          >
            <div className="text-xl mb-1">{m.icon}</div>
            <div className="text-xs font-semibold text-ink">{m.value}</div>
            <div className="text-[10px] text-ink-muted">{m.label}</div>
          </div>
        ))}
      </div>

      {/* Strengths & Weaknesses */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 bg-status-fertig-bg rounded-xl border border-status-fertig-border">
          <p className="text-[11px] font-semibold text-status-fertig-text mb-1.5">✅ Stärken</p>
          {(result.strengths || []).map((s, i) => (
            <p key={i} className="text-[11px] text-status-fertig-text mb-0.5">
              · {s}
            </p>
          ))}
        </div>
        <div className="p-3 bg-status-aktiv-bg rounded-xl border border-status-aktiv-border">
          <p className="text-[11px] font-semibold text-status-aktiv-text mb-1.5">⚠️ Schwächen</p>
          {(result.weaknesses || []).map((w, i) => (
            <p key={i} className="text-[11px] text-status-aktiv-text mb-0.5">
              · {w}
            </p>
          ))}
        </div>
      </div>

      {/* Tips */}
      <div className="p-3 bg-accent-50 rounded-xl border border-accent-200">
        <p className="text-[11px] font-semibold text-accent-800 mb-1.5">💡 Verbesserungstipps</p>
        {(result.tips || []).map((t, i) => (
          <div key={i} className="flex gap-2 mb-1">
            <span className="text-[11px] text-accent-600 font-bold shrink-0">{i + 1}.</span>
            <p className="text-[11px] text-accent-700">{t}</p>
          </div>
        ))}
      </div>

      {/* Best time + hook score */}
      <div className="flex items-center gap-3 text-[11px]">
        <span className="text-ink-muted">⏰ Bester Zeitpunkt:</span>
        <span className="font-medium text-ink">{result.best_post_time}</span>
        <span className="ml-auto text-ink-muted">
          Hook: <span className="font-bold text-ink">{result.hook_score}/10</span>
        </span>
        <button
          onClick={onGenerate}
          className="text-[10px] text-accent-600 hover:text-accent-800 border border-accent-200 rounded-lg px-2 py-0.5"
        >
          ↻ Neu
        </button>
      </div>
    </div>
  )
}

function PostDetail({ postId, onClose, onRefresh, prevId, nextId, position, total, onNavigate }) {
  const [post, setPost] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState('')
  const textareaRef = useRef(null)
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState(null)
  const [showPerf, setShowPerf] = useState(false)
  const [perfData, setPerfData] = useState({
    impressions: '',
    reactions: '',
    comments: '',
    shares: '',
  })
  const [showPreview, setShowPreview] = useState(false)
  const [hashtags, setHashtags] = useState(null)
  const [hashtagLoading, setHashtagLoading] = useState(false)
  const [showSHKHashtags, setShowSHKHashtags] = useState(false)
  const [shkCopied, setSHKCopied] = useState(null)
  const [carouselLoading, setCarouselLoading] = useState(false)
  const [carouselPreview, setCarouselPreview] = useState(null)
  const [carouselTemplates, setCarouselTemplates] = useState(null)
  const [selectedCarouselTemplate, setSelectedCarouselTemplate] = useState(null)
  const [repurposeLoading, setRepurposeLoading] = useState(false)
  const [repurposeResult, setRepurposeResult] = useState(null)
  const [pillarSaving, setPillarSaving] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [templateSearch, setTemplateSearch] = useState('')
  const [showRewriter, setShowRewriter] = useState(false)
  const [rewriteLoading, setRewriteLoading] = useState(false)
  const [rewriteResult, setRewriteResult] = useState(null)
  const [showVariants, setShowVariants] = useState(false)
  const [variantsLoading, setVariantsLoading] = useState(false)
  const [variantsResult, setVariantsResult] = useState(null)
  const [showMultiFormat, setShowMultiFormat] = useState(false)
  const [multiFormatLoading, setMultiFormatLoading] = useState(false)
  const [multiFormatResult, setMultiFormatResult] = useState(null)
  const [showPredictor, setShowPredictor] = useState(false)
  const [predictorLoading, setPredictorLoading] = useState(false)
  const [predictorResult, setPredictorResult] = useState(null)
  const [showChecklist, setShowChecklist] = useState(false)
  const [detailRating, setDetailRating] = useState(null) // null | 'up' | 'down'
  const [tags, setTags] = useState([])
  const [tagInput, setTagInput] = useState('')
  const [tagSaving, setTagSaving] = useState(false)

  useEffect(() => {
    loadPost()
  }, [postId])

  // Keyboard navigation: Alt+← / Alt+→ to move between posts
  useEffect(() => {
    if (!onNavigate) return
    function handleKey(e) {
      if (editMode) return // don't navigate while editing
      if (e.altKey && e.key === 'ArrowLeft' && prevId) {
        onNavigate(prevId)
      }
      if (e.altKey && e.key === 'ArrowRight' && nextId) {
        onNavigate(nextId)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [prevId, nextId, onNavigate, editMode])

  async function loadPost() {
    setLoading(true)
    try {
      const data = await getContentPiece(postId)
      setPost(data)
      setEditText(data.content_text)
      setTags(data.content_metadata?.tags || [])
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setLoading(false)
  }

  async function handleAddTag(tagText) {
    const t = tagText.trim().replace(/^#/, '').slice(0, 40)
    if (!t || tags.includes(t)) return
    const newTags = [...tags, t]
    setTags(newTags)
    setTagInput('')
    setTagSaving(true)
    try {
      await updateContentTags(postId, newTags)
    } catch {}
    setTagSaving(false)
    onRefresh()
  }

  async function handleRemoveTag(tag) {
    const newTags = tags.filter((t) => t !== tag)
    setTags(newTags)
    setTagSaving(true)
    try {
      await updateContentTags(postId, newTags)
    } catch {}
    setTagSaving(false)
    onRefresh()
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
    navigator.clipboard.writeText(post.content_text || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleCopyAndPublish() {
    navigator.clipboard.writeText(post.content_text || '')
    setCopied(true)
    try {
      await markPublished(postId)
      setMessage({ type: 'success', text: '✓ Text kopiert + Post als veröffentlicht markiert!' })
      setTimeout(() => {
        setCopied(false)
        loadPost()
        onRefresh()
      }, 2000)
    } catch (e) {
      setMessage({ type: 'error', text: 'Kopiert, aber markieren fehlgeschlagen: ' + e.message })
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (loading) return <div className="p-6 text-center text-ink-muted">Lade...</div>
  if (!post)
    return (
      <div className="bg-white rounded-xl border border-surface-border shadow-sm p-8 text-center">
        <p className="text-sm text-status-fehler-text mb-3">
          {message?.text || 'Post konnte nicht geladen werden.'}
        </p>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-ink-muted border border-surface-border rounded-lg hover:bg-surface-bg"
        >
          ← Zurück zur Liste
        </button>
      </div>
    )

  const charCount = (editMode ? editText : post.content_text || '').length

  return (
    <div className="bg-white rounded-xl border border-surface-border shadow-sm">
      <div className="p-5 border-b border-surface-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Navigation arrows */}
          {onNavigate && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => prevId && onNavigate(prevId)}
                disabled={!prevId}
                className="p-1.5 rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="Vorheriger Post (Alt+←)"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M10 4l-4 4 4 4" />
                </svg>
              </button>
              <span className="text-[11px] text-ink-muted tabular-nums px-1">
                {position}/{total}
              </span>
              <button
                onClick={() => nextId && onNavigate(nextId)}
                disabled={!nextId}
                className="p-1.5 rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="Nächster Post (Alt+→)"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M6 4l4 4-4 4" />
                </svg>
              </button>
            </div>
          )}
          <span
            className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[post.status] || 'bg-surface-bg'}`}
          >
            {post.status === 'draft'
              ? 'Entwurf'
              : post.status === 'approved'
                ? 'Freigegeben'
                : post.status === 'published'
                  ? '✓ Veröffentlicht'
                  : post.status}
          </span>
          <span
            className={`text-xs font-medium tabular-nums ${charCount > 2500 ? 'text-status-fehler-text' : charCount > 1300 ? 'text-status-aktiv-text' : 'text-ink-muted'}`}
          >
            {charCount} Z{charCount <= LI_FOLD ? ' ✓' : ''}
          </span>
          {charCount > 0 &&
            (() => {
              const words = (editMode ? editText : post.content_text || '')
                .trim()
                .split(/\s+/).length
              const secs = Math.round((words / 238) * 60)
              return (
                <span className="text-[11px] text-ink-muted">
                  · {secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}min`} Lesezeit
                </span>
              )
            })()}
        </div>
        <div className="flex items-center gap-2">
          {!editMode && post.status === 'draft' && (
            <>
              <button
                onClick={() => setEditMode(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light hover:text-ink border border-surface-border rounded-lg hover:bg-surface-bg"
              >
                <Edit3 className="w-3.5 h-3.5" /> Bearbeiten
              </button>
              <button
                onClick={handleApprove}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-status-fertig-text rounded-lg hover:opacity-90"
              >
                <Check className="w-3.5 h-3.5" /> Freigeben
              </button>
            </>
          )}
          {post.status === 'approved' && (
            <button
              onClick={() => setShowPerf(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50"
            >
              <BarChart3 className="w-3.5 h-3.5" /> Performance
            </button>
          )}
          {/* Quality Rating */}
          {post.source_item_id && (
            <div
              className="flex items-center gap-1 border border-surface-border rounded-lg px-1.5 py-1"
              title="Qualität bewerten"
            >
              <button
                onClick={async () => {
                  const next = detailRating === 'up' ? null : 'up'
                  setDetailRating(next)
                  if (next)
                    try {
                      await rateItemQuality(post.source_item_id, 'post_generation', 5)
                    } catch {}
                }}
                className={`p-1 rounded transition-colors ${detailRating === 'up' ? 'text-status-fertig-text' : 'text-ink-muted hover:text-status-fertig-text'}`}
              >
                <ThumbsUp className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={async () => {
                  const next = detailRating === 'down' ? null : 'down'
                  setDetailRating(next)
                  if (next)
                    try {
                      await rateItemQuality(post.source_item_id, 'post_generation', 1)
                    } catch {}
                }}
                className={`p-1 rounded transition-colors ${detailRating === 'down' ? 'text-status-fehler-text' : 'text-ink-muted hover:text-status-fehler-text'}`}
              >
                <ThumbsDown className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          {post.status === 'rejected' && (
            <button
              onClick={async () => {
                try {
                  await updateContent(postId, { status: 'draft' })
                  setMessage({ type: 'success', text: '♻️ Post wiederhergestellt!' })
                  await loadPost()
                  onRefresh()
                } catch (e) {
                  setMessage({ type: 'error', text: e.message })
                }
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-status-aktiv-text bg-status-aktiv-bg border border-status-aktiv-border rounded-lg hover:opacity-90"
            >
              ♻️ Wiederherstellen
            </button>
          )}
          <button
            onClick={() => setShowPreview(!showPreview)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showPreview ? 'text-status-neu-text bg-status-neu-bg border-status-neu-border' : 'text-ink-light hover:text-ink border-surface-border hover:bg-surface-bg'}`}
          >
            <Eye className="w-3.5 h-3.5" /> LinkedIn-Vorschau
          </button>
          {/* bewusst behalten: die folgenden 5 Feature-Toggle-Buttons (Templates/Rewrite/
              A-B-Test/Repurpose/Vorhersage) brauchen gleichzeitig sichtbare, voneinander
              unterscheidbare Identitätsfarben (kein Status). primary/accent sind an
              anderer Stelle bereits fest belegt (primary=Freigeben/Performance,
              accent=Wiederherstellen-Bereich); die zugehörigen Panel-Bodies (RewritePanel,
              ABVariantsPanel, MultiFormatPanel, PerformancePredictorPanel, oben in dieser
              Datei) nutzen exakt dieselben rohen Paletten-Farben als ihre Identität und
              blieben dort bewusst unmigriert (Analogie zu PILLAR_CONFIG, Zeile ~108) —
              Buttons und ihre Panels müssen farblich zusammenpassen. */}
          <button
            onClick={() => {
              setShowTemplates(!showTemplates)
              setShowPreview(false)
              setShowRewriter(false)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showTemplates ? 'text-rose-700 bg-rose-50 border-rose-200' : 'text-rose-600 bg-rose-50 border-rose-200 hover:bg-rose-100'}`}
          >
            📐 Templates
          </button>
          <button
            onClick={() => {
              setShowRewriter(!showRewriter)
              setShowTemplates(false)
              setShowPreview(false)
              setShowVariants(false)
              setRewriteResult(null)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showRewriter ? 'text-indigo-700 bg-indigo-50 border-indigo-300' : 'text-indigo-600 bg-indigo-50 border-indigo-200 hover:bg-indigo-100'}`}
          >
            <Sparkles className="w-3.5 h-3.5" /> KI-Rewrite
          </button>
          <button
            onClick={() => {
              setShowVariants(!showVariants)
              setShowRewriter(false)
              setShowTemplates(false)
              setShowPreview(false)
              setShowMultiFormat(false)
              setVariantsResult(null)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showVariants ? 'text-violet-700 bg-violet-50 border-violet-300' : 'text-violet-600 bg-violet-50 border-violet-200 hover:bg-violet-100'}`}
          >
            🅰🅱 A/B Test
          </button>
          <button
            onClick={() => {
              setShowMultiFormat(!showMultiFormat)
              setShowVariants(false)
              setShowRewriter(false)
              setShowTemplates(false)
              setShowPreview(false)
              setShowPredictor(false)
              setMultiFormatResult(null)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showMultiFormat ? 'text-orange-700 bg-orange-50 border-orange-300' : 'text-orange-600 bg-orange-50 border-orange-200 hover:bg-orange-100'}`}
          >
            🔀 Repurpose
          </button>
          <button
            onClick={() => {
              setShowPredictor(!showPredictor)
              setShowMultiFormat(false)
              setShowVariants(false)
              setShowRewriter(false)
              setShowTemplates(false)
              setShowPreview(false)
              setShowChecklist(false)
              setPredictorResult(null)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showPredictor ? 'text-purple-700 bg-purple-50 border-purple-300' : 'text-purple-600 bg-purple-50 border-purple-200 hover:bg-purple-100'}`}
          >
            🔮 Vorhersage
          </button>
          <button
            onClick={() => {
              setShowChecklist(!showChecklist)
              setShowPredictor(false)
              setShowMultiFormat(false)
              setShowVariants(false)
              setShowRewriter(false)
              setShowTemplates(false)
              setShowPreview(false)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showChecklist ? 'text-primary-700 bg-primary-50 border-primary-300' : 'text-primary-600 bg-primary-50 border-primary-200 hover:bg-primary-100'}`}
          >
            ✅ Checklist
          </button>
          <button
            onClick={async () => {
              setCarouselLoading(true)
              try {
                const [p, tmpl] = await Promise.all([
                  previewCarousel(postId, post.content_metadata?.title || 'LinkedIn Carousel'),
                  carouselTemplates ? Promise.resolve(carouselTemplates) : getCarouselTemplates(),
                ])
                setCarouselPreview(p)
                if (!carouselTemplates) setCarouselTemplates(tmpl)
              } catch (e) {
                setMessage({ type: 'error', text: 'Carousel: ' + e.message })
              }
              setCarouselLoading(false)
            }}
            disabled={carouselLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-lg hover:bg-purple-100 disabled:opacity-50"
          >
            {carouselLoading ? '⏳' : '📄'} Karussell
          </button>
          <button
            onClick={async () => {
              setRepurposeLoading(true)
              setRepurposeResult(null)
              try {
                const r = await repurposeContent(postId)
                setRepurposeResult(r)
                onRefresh()
              } catch (e) {
                setMessage({ type: 'error', text: 'Repurpose: ' + e.message })
              }
              setRepurposeLoading(false)
            }}
            disabled={repurposeLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-50"
            title="3 neue Varianten mit anderen Stilen generieren"
          >
            {repurposeLoading ? '⏳' : '♻️'} Varianten
          </button>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light hover:text-ink border border-surface-border rounded-lg hover:bg-surface-bg"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-status-fertig-text" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            {copied ? 'Kopiert!' : 'Kopieren'}
          </button>
          {(post.status === 'approved' || post.status === 'draft') && (
            <button
              onClick={handleCopyAndPublish}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-status-fertig-text bg-status-fertig-bg border border-status-fertig-border rounded-lg hover:opacity-90 transition-colors"
              title="Text kopieren + Post als auf LinkedIn veröffentlicht markieren"
            >
              <Send className="w-3.5 h-3.5" />
              Auf LinkedIn teilen ✓
            </button>
          )}
          {post.status === 'published' && (
            <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-status-fertig-text bg-status-fertig-bg border border-status-fertig-border rounded-lg">
              <Check className="w-3.5 h-3.5" />
              Veröffentlicht
            </span>
          )}
          <button
            onClick={onClose}
            className="p-1.5 text-ink-muted hover:text-ink rounded-lg hover:bg-surface-bg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`mx-5 mt-4 p-3 rounded-lg text-sm ${message.type === 'error' ? 'bg-status-fehler-bg text-status-fehler-text' : 'bg-status-fertig-bg text-status-fertig-text'}`}
        >
          {message.text}
        </div>
      )}

      {repurposeResult && (
        <div className="mx-5 mt-4 p-4 rounded-xl bg-indigo-50 border border-indigo-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-indigo-900">
              ♻️ {repurposeResult.repurposed} Varianten als Entwürfe gespeichert
            </span>
            <button
              onClick={() => setRepurposeResult(null)}
              className="text-indigo-400 hover:text-indigo-700 text-sm"
            >
              ×
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {(repurposeResult.variants || []).map((v, i) => (
              <span
                key={i}
                className="px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800"
              >
                {v.angle} · {v.char_count} Zeichen
              </span>
            ))}
          </div>
          <p className="text-xs text-indigo-600 mt-2">
            Öffne "Entwürfe" um die neuen Varianten zu sehen.
          </p>
        </div>
      )}

      <div className="p-5">
        {editMode ? (
          <div>
            <FormatToolbar textareaRef={textareaRef} value={editText} onChange={setEditText} />
            <textarea
              ref={textareaRef}
              className="w-full text-sm border border-surface-border rounded-lg p-4 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none leading-relaxed"
              rows={12}
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
            />
            <div className="mt-3 space-y-3">
              <CharCounter text={editText} />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setEditMode(false)
                    setEditText(post.content_text)
                  }}
                  className="px-4 py-2 text-sm text-ink-light hover:text-ink border border-surface-border rounded-lg"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleSaveEdit}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800"
                >
                  Speichern (Lernsignal)
                </button>
              </div>
            </div>
          </div>
        ) : showPreview ? (
          <LinkedInPreview text={post.content_text} />
        ) : showRewriter ? (
          <RewritePanel
            postId={postId}
            postText={post.content_text}
            loading={rewriteLoading}
            result={rewriteResult}
            onRewrite={async (mode) => {
              setRewriteLoading(true)
              setRewriteResult(null)
              try {
                const r = await rewriteContent(postId, mode)
                setRewriteResult(r)
              } catch (e) {
                setMessage({ type: 'error', text: 'Rewrite: ' + e.message })
              }
              setRewriteLoading(false)
            }}
            onApply={async (text) => {
              try {
                await submitEditDiff({ content_piece_id: postId, final_text: text })
                setMessage({ type: 'success', text: 'Rewrite übernommen und gespeichert!' })
                setShowRewriter(false)
                setRewriteResult(null)
                await loadPost()
                onRefresh()
              } catch (e) {
                setMessage({ type: 'error', text: e.message })
              }
            }}
          />
        ) : showVariants ? (
          <ABVariantsPanel
            loading={variantsLoading}
            variants={variantsResult}
            onGenerate={async () => {
              setVariantsLoading(true)
              setVariantsResult(null)
              try {
                const r = await generateVariants(postId)
                setVariantsResult(r)
              } catch (e) {
                setMessage({ type: 'error', text: 'Varianten: ' + e.message })
              }
              setVariantsLoading(false)
            }}
            onApply={async (text) => {
              try {
                await submitEditDiff({ content_piece_id: postId, final_text: text })
                setMessage({ type: 'success', text: 'Variante übernommen und gespeichert!' })
                setShowVariants(false)
                setVariantsResult(null)
                await loadPost()
                onRefresh()
              } catch (e) {
                setMessage({ type: 'error', text: e.message })
              }
            }}
          />
        ) : showMultiFormat ? (
          <MultiFormatPanel
            loading={multiFormatLoading}
            result={multiFormatResult}
            onGenerate={async () => {
              setMultiFormatLoading(true)
              setMultiFormatResult(null)
              try {
                const r = await repurposeFormats(postId)
                setMultiFormatResult(r)
              } catch (e) {
                setMessage({ type: 'error', text: 'Repurpose: ' + e.message })
              }
              setMultiFormatLoading(false)
            }}
          />
        ) : showPredictor ? (
          <PerformancePredictorPanel
            loading={predictorLoading}
            result={predictorResult}
            onGenerate={async () => {
              setPredictorLoading(true)
              setPredictorResult(null)
              try {
                const r = await predictPerformance(postId)
                setPredictorResult(r)
              } catch (e) {
                setMessage({ type: 'error', text: 'Vorhersage: ' + e.message })
              }
              setPredictorLoading(false)
            }}
          />
        ) : showChecklist ? (
          <ChecklistPanel
            post={post}
            approving={false}
            onApprove={async () => {
              try {
                await approveContent(postId)
                setMessage({ type: 'success', text: '✅ Post freigegeben!' })
                setShowChecklist(false)
                await loadPost()
                onRefresh()
              } catch (e) {
                setMessage({ type: 'error', text: e.message })
              }
            }}
          />
        ) : showTemplates ? (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <span className="text-xs text-ink-muted font-medium">
                Template wählen → wird in Bearbeitungsmodus übernommen:
              </span>
              <input
                type="text"
                value={templateSearch}
                onChange={(e) => setTemplateSearch(e.target.value)}
                placeholder="Suchen..."
                className="ml-auto px-2.5 py-1 text-xs border border-surface-border rounded-lg focus:outline-none focus:ring-1 focus:ring-rose-400 w-36"
              />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {POST_TEMPLATES.filter(
                (t) =>
                  !templateSearch ||
                  t.name.toLowerCase().includes(templateSearch.toLowerCase()) ||
                  t.desc.toLowerCase().includes(templateSearch.toLowerCase())
              ).map((tpl) => {
                const pillarCfg = PILLAR_CONFIG[tpl.pillar]
                return (
                  <button
                    key={tpl.id}
                    onClick={() => {
                      setEditText(tpl.body)
                      setEditMode(true)
                      setShowTemplates(false)
                    }}
                    className="text-left p-3 rounded-xl border border-surface-border bg-white hover:border-rose-300 hover:bg-rose-50 transition-all group"
                  >
                    <div className="flex items-start gap-2 mb-1.5">
                      <span className="text-xl">{tpl.emoji}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-ink group-hover:text-rose-800">
                          {tpl.name}
                        </p>
                        {pillarCfg && (
                          <span
                            className={`inline-block mt-0.5 px-1.5 py-0 rounded text-[9px] font-medium border ${pillarCfg.color}`}
                          >
                            {pillarCfg.emoji} {pillarCfg.label}
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-[10px] text-ink-muted leading-snug">{tpl.desc}</p>
                  </button>
                )
              })}
            </div>
            <p className="text-[10px] text-ink-muted mt-3 text-center">
              Klicke ein Template → öffnet im Bearbeitungsmodus mit [PLATZHALTER] zum Ausfüllen
            </p>
          </div>
        ) : (
          <div className="whitespace-pre-line text-sm text-ink leading-relaxed bg-surface-bg rounded-lg p-5 border border-surface-border">
            {post.content_text}
          </div>
        )}
      </div>

      {/* Quality Score breakdown */}
      {!editMode &&
        !showPreview &&
        !showTemplates &&
        !showRewriter &&
        !showVariants &&
        !showMultiFormat &&
        !showPredictor &&
        !showChecklist &&
        (() => {
          const qs = postScore(post.content_text || '')
          return (
            <div className="px-5 pb-4">
              <div
                className={`rounded-xl p-3 border ${qs.score >= 8 ? 'border-status-fertig-border bg-status-fertig-bg' : qs.score >= 6 ? 'border-primary-200 bg-primary-50' : qs.score >= 4 ? 'border-status-aktiv-border bg-status-aktiv-bg' : 'border-status-fehler-border bg-status-fehler-bg'}`}
              >
                <div className="flex items-center gap-3">
                  <span className={`text-2xl font-bold tabular-nums ${qs.color}`}>
                    {qs.score}
                    <span className="text-sm font-normal">/10</span>
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs font-semibold ${qs.color}`}>
                        Post-Score {qs.grade}
                      </span>
                      <span className="text-[10px] text-ink-muted">
                        · {(post.content_text || '').length} Zeichen
                      </span>
                    </div>
                    <div className="h-1.5 bg-white/60 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${qs.score >= 8 ? 'bg-status-fertig-text' : qs.score >= 6 ? 'bg-primary-500' : qs.score >= 4 ? 'bg-status-aktiv-text' : 'bg-status-fehler-text'}`}
                        style={{ width: `${qs.score * 10}%` }}
                      />
                    </div>
                  </div>
                </div>
                {qs.tips.length > 0 && (
                  <ul className="mt-2 space-y-0.5">
                    {qs.tips.map((tip, i) => (
                      <li key={i} className="text-[11px] text-ink-muted flex items-start gap-1.5">
                        <span className="shrink-0 mt-0.5">→</span>
                        {tip}
                      </li>
                    ))}
                  </ul>
                )}
                {qs.tips.length === 0 && (
                  <p className="text-[11px] text-status-fertig-text mt-1">
                    ✓ Dieser Post erfüllt alle LinkedIn-Qualitätskriterien
                  </p>
                )}
              </div>
            </div>
          )
        })()}

      {/* Hashtag Suggestions */}
      {!editMode &&
        !showPreview &&
        !showTemplates &&
        !showRewriter &&
        !showVariants &&
        !showMultiFormat &&
        !showPredictor &&
        !showChecklist && (
          <div className="px-5 pb-4">
            {hashtags ? (
              <div className="p-3 bg-status-neu-bg rounded-lg border border-status-neu-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-status-neu-text"># Hashtag-Vorschläge</span>
                  <button
                    onClick={() => setHashtags(null)}
                    className="text-xs text-status-neu-text/70 hover:text-status-neu-text"
                  >
                    ×
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {hashtags.map((tag, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        navigator.clipboard.writeText(tag)
                      }}
                      title="Klicken zum Kopieren"
                      className="px-2.5 py-1 bg-white border border-status-neu-border text-status-neu-text rounded-full text-xs hover:bg-status-neu-text hover:text-white hover:border-status-neu-text transition-colors"
                    >
                      {tag}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-status-neu-text/70 mt-2">Klicken zum Kopieren</p>
              </div>
            ) : (
              <button
                onClick={async () => {
                  setHashtagLoading(true)
                  try {
                    const r = await suggestHashtags(postId)
                    setHashtags(r.hashtags || [])
                  } catch (e) {}
                  setHashtagLoading(false)
                }}
                disabled={hashtagLoading}
                className="flex items-center gap-1.5 text-xs text-status-neu-text hover:opacity-80 font-medium disabled:opacity-50"
              >
                {hashtagLoading ? '⏳ Generiere...' : '# Hashtag-Vorschläge generieren'}
              </button>
            )}
          </div>
        )}

      {/* SHK Branchen-Hashtags Quick-Picker */}
      {!editMode &&
        !showPreview &&
        !showTemplates &&
        !showRewriter &&
        !showVariants &&
        !showMultiFormat &&
        !showPredictor &&
        !showChecklist && (
          <div className="px-5 pb-4">
            {showSHKHashtags ? (
              <div className="p-3 bg-primary-50 rounded-lg border border-primary-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-primary-800">
                    # SHK-Branchenhashtags
                  </span>
                  <button
                    onClick={() => setShowSHKHashtags(false)}
                    className="text-xs text-primary-400 hover:text-primary-600"
                  >
                    ×
                  </button>
                </div>
                {Object.entries(SHK_HASHTAGS).map(([cat, tags]) => (
                  <div key={cat} className="mb-2 last:mb-0">
                    <span className="text-[10px] font-semibold text-primary-600 uppercase tracking-wide">
                      {cat}
                    </span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {tags.map((tag) => (
                        <button
                          key={tag}
                          onClick={() => {
                            navigator.clipboard.writeText(tag)
                            setSHKCopied(tag)
                            setTimeout(() => setSHKCopied(null), 1500)
                          }}
                          title="Kopieren"
                          className={`px-2 py-0.5 rounded-full text-xs border transition-all ${shkCopied === tag ? 'bg-primary-600 text-white border-primary-600' : 'bg-white border-primary-200 text-primary-700 hover:bg-primary-600 hover:text-white hover:border-primary-600'}`}
                        >
                          {shkCopied === tag ? '✓ kopiert' : tag}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                <p className="text-[10px] text-primary-400 mt-2">
                  Klicken → in Zwischenablage · dann in Post einfügen
                </p>
              </div>
            ) : (
              <button
                onClick={() => setShowSHKHashtags(true)}
                className="flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-800 font-medium"
              >
                # SHK-Branchenhashtags (ohne KI)
              </button>
            )}
          </div>
        )}

      {/* Content Pillar Selector */}
      {!editMode &&
        !showPreview &&
        !showTemplates &&
        !showRewriter &&
        !showVariants &&
        !showMultiFormat &&
        !showPredictor &&
        !showChecklist && (
          <div className="px-5 pb-4">
            <div className="p-3 bg-surface-bg rounded-lg border border-surface-border">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-ink-muted">Content-Säule:</span>
                {(() => {
                  const p = post.content_metadata?.pillar
                  const cfg = p && PILLAR_CONFIG[p]
                  return cfg ? (
                    <span
                      className={`px-2 py-0.5 rounded border text-[11px] font-medium ${cfg.color}`}
                    >
                      {cfg.emoji} {cfg.label}
                    </span>
                  ) : (
                    <span className="text-[11px] text-ink-muted italic">Keine Säule zugewiesen</span>
                  )
                })()}
                {pillarSaving && <span className="text-[11px] text-ink-muted ml-1">...</span>}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(PILLAR_CONFIG).map(([key, cfg]) => (
                  <button
                    key={key}
                    onClick={async () => {
                      const newPillar = post.content_metadata?.pillar === key ? null : key
                      setPillarSaving(true)
                      try {
                        await updateContentPillar(post.id, newPillar)
                        setPost((prev) => ({
                          ...prev,
                          content_metadata: { ...(prev.content_metadata || {}), pillar: newPillar },
                        }))
                      } catch (e) {
                        setMessage({ type: 'error', text: 'Säule: ' + e.message })
                      }
                      setPillarSaving(false)
                    }}
                    disabled={pillarSaving}
                    className={`px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all disabled:opacity-50 ${
                      post.content_metadata?.pillar === key
                        ? cfg.color + ' ring-2 ring-offset-1 ring-current'
                        : 'bg-white text-ink-muted border-surface-border hover:border-ink-muted'
                    }`}
                  >
                    {cfg.emoji} {cfg.label}
                  </button>
                ))}
                {post.content_metadata?.pillar && (
                  <button
                    onClick={async () => {
                      setPillarSaving(true)
                      try {
                        await updateContentPillar(post.id, null)
                        setPost((prev) => ({
                          ...prev,
                          content_metadata: { ...(prev.content_metadata || {}), pillar: null },
                        }))
                      } catch {}
                      setPillarSaving(false)
                    }}
                    className="px-2 py-1 rounded-lg border border-dashed border-surface-border text-[11px] text-ink-muted hover:text-status-fehler-text hover:border-status-fehler-border"
                  >
                    × entfernen
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

      {/* Tags */}
      {!editMode &&
        !showPreview &&
        !showTemplates &&
        !showRewriter &&
        !showVariants &&
        !showMultiFormat &&
        !showPredictor &&
        !showChecklist && (
          <div className="px-5 pb-4">
            <div className="p-3 bg-surface-bg rounded-lg border border-surface-border">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-ink-muted">Tags:</span>
                {tagSaving && <span className="text-[11px] text-ink-muted">...</span>}
              </div>
              {/* violet bewusst behalten: Tags sind eine eigene Kategorie neben den 5
                  Status-Tönen und der Content-Säule (PILLAR_CONFIG) — braucht eigene
                  Identitätsfarbe, primary/accent sind bereits anderweitig belegt. */}
              <div className="flex flex-wrap gap-1.5 mb-2">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-violet-100 text-violet-700 border border-violet-200"
                  >
                    #{tag}
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-0.5 text-violet-400 hover:text-violet-700 leading-none"
                      title="Tag entfernen"
                    >
                      ×
                    </button>
                  </span>
                ))}
                {tags.length === 0 && (
                  <span className="text-[11px] text-ink-muted italic">Keine Tags</span>
                )}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  handleAddTag(tagInput)
                }}
                className="flex items-center gap-2"
              >
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  placeholder="Tag hinzufügen (Enter)"
                  maxLength={40}
                  className="flex-1 px-2.5 py-1 text-xs border border-surface-border rounded-lg focus:outline-none focus:ring-1 focus:ring-violet-300 bg-white"
                />
                <button
                  type="submit"
                  disabled={!tagInput.trim() || tagSaving}
                  className="px-2.5 py-1 text-xs font-medium text-violet-700 bg-violet-50 border border-violet-200 rounded-lg hover:bg-violet-100 disabled:opacity-50"
                >
                  + Tag
                </button>
              </form>
              {/* Quick tag suggestions */}
              <div className="flex flex-wrap gap-1 mt-2">
                {[
                  'Wärmepumpe',
                  'Gesetz',
                  'Förderung',
                  'SHK-Trend',
                  'Handwerk',
                  'KI',
                  'Nachhaltigkeit',
                  'Kosten',
                ]
                  .filter((s) => !tags.includes(s))
                  .slice(0, 5)
                  .map((s) => (
                    <button
                      key={s}
                      onClick={() => handleAddTag(s)}
                      className="px-1.5 py-0.5 text-[10px] text-ink-muted bg-white border border-surface-border rounded hover:border-violet-300 hover:text-violet-600 transition-colors"
                    >
                      +{s}
                    </button>
                  ))}
              </div>
            </div>
          </div>
        )}

      {/* Carousel Slide Preview */}
      <Dialog
        open={!!carouselPreview}
        onClose={() => {
          setCarouselPreview(null)
          setSelectedCarouselTemplate(null)
        }}
        maxWidth="xl"
        contentClassName="p-0 flex flex-col max-h-[90vh]"
        className="max-h-[90vh]"
      >
        {carouselPreview && (
          <>
            <div className="p-5 border-b border-surface-border flex items-center justify-between flex-shrink-0">
              <div>
                <h3 className="font-semibold text-ink">📄 Karussell-Vorschau</h3>
                <p className="text-xs text-ink-muted mt-0.5">
                  {carouselPreview.slide_count} Slides · {carouselPreview.title}
                </p>
              </div>
              <CloseButton
                onClick={() => {
                  setCarouselPreview(null)
                  setSelectedCarouselTemplate(null)
                }}
              />
            </div>

            {/* Template Selector */}
            {carouselTemplates && carouselTemplates.length > 0 && (
              <div className="px-5 pt-4 pb-3 border-b border-surface-border flex-shrink-0">
                <p className="text-xs font-semibold text-ink-muted mb-2 uppercase tracking-wide">
                  Vorlage wählen
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => {
                      setSelectedCarouselTemplate(null)
                      setCarouselPreview((prev) => ({
                        ...prev,
                        slides: prev._originalSlides || prev.slides,
                        slide_count: (prev._originalSlides || prev.slides).length,
                      }))
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${!selectedCarouselTemplate ? 'bg-purple-700 text-white border-purple-700' : 'bg-white text-ink-muted border-surface-border hover:border-purple-300'}`}
                  >
                    Aus Post-Text
                  </button>
                  {carouselTemplates.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => {
                        setSelectedCarouselTemplate(t.id)
                        const tSlides = t.slides_config?.slides || []
                        setCarouselPreview((prev) => ({
                          ...prev,
                          _originalSlides: prev._originalSlides || prev.slides,
                          slides: tSlides,
                          slide_count: tSlides.length,
                        }))
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${selectedCarouselTemplate === t.id ? 'bg-purple-700 text-white border-purple-700' : 'bg-white text-ink-muted border-surface-border hover:border-purple-300'}`}
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
                {selectedCarouselTemplate && (
                  <p className="text-[10px] text-ink-muted mt-1.5 italic">
                    Vorlage zeigt Platzhalter — im PDF durch echten Content ersetzen
                  </p>
                )}
              </div>
            )}

            <div className="overflow-x-auto p-5 flex gap-3 flex-shrink-0">
              {carouselPreview.slides.map((slide, i) => (
                <div
                  key={i}
                  className={`flex-shrink-0 w-48 h-48 rounded-xl border-2 flex flex-col items-center justify-center p-3 text-center ${
                    slide.type === 'title'
                      ? 'bg-primary-700 border-primary-600 text-white'
                      : slide.type === 'cta'
                        ? 'bg-accent-500 border-accent-400 text-white'
                        : 'bg-white border-surface-border text-ink'
                  }`}
                >
                  <span className="text-[9px] font-bold uppercase tracking-widest mb-2 opacity-60">
                    {slide.type === 'title' ? 'TITEL' : slide.type === 'cta' ? 'CTA' : `SLIDE ${i}`}
                  </span>
                  {slide.heading && (
                    <p className="text-[11px] font-bold leading-tight mb-1 line-clamp-4">
                      {slide.heading}
                    </p>
                  )}
                  {slide.body && (
                    <p className="text-[10px] leading-tight opacity-80 line-clamp-5">
                      {slide.body}
                    </p>
                  )}
                  {slide.footer && (
                    <p className="text-[10px] font-semibold mt-1 opacity-90">{slide.footer}</p>
                  )}
                </div>
              ))}
            </div>
            <div className="p-5 pt-0 flex justify-end gap-2 flex-shrink-0">
              <button
                onClick={() => {
                  setCarouselPreview(null)
                  setSelectedCarouselTemplate(null)
                }}
                className="px-4 py-2 text-sm text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
              >
                Abbrechen
              </button>
              <button
                onClick={async () => {
                  try {
                    if (selectedCarouselTemplate) {
                      await generateCarousel(null, carouselPreview.title, carouselPreview.slides)
                    } else {
                      await generateCarousel(postId, carouselPreview.title)
                    }
                  } catch (e) {
                    setMessage({ type: 'error', text: e.message })
                  }
                  setCarouselPreview(null)
                  setSelectedCarouselTemplate(null)
                }}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-purple-700 rounded-lg hover:bg-purple-800"
              >
                📥 PDF herunterladen
              </button>
            </div>
          </>
        )}
      </Dialog>

      {/* Performance Modal */}
      {showPerf && (
        <div className="px-5 pb-5">
          <div className="p-4 bg-surface-bg rounded-lg border border-surface-border">
            <h4 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-primary-600" /> LinkedIn-Performance eintragen
            </h4>
            <div className="grid grid-cols-2 gap-3">
              {['impressions', 'reactions', 'comments', 'shares'].map((field) => (
                <div key={field}>
                  <label className="text-xs text-ink-light capitalize">
                    {field === 'impressions'
                      ? 'Aufrufe'
                      : field === 'reactions'
                        ? 'Reaktionen'
                        : field === 'comments'
                          ? 'Kommentare'
                          : 'Shares'}
                  </label>
                  <input
                    type="number"
                    className="w-full mt-1 px-3 py-1.5 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                    value={perfData[field]}
                    onChange={(e) => setPerfData((prev) => ({ ...prev, [field]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={() => setShowPerf(false)}
                className="px-3 py-1.5 text-xs text-ink-light border border-surface-border rounded-lg"
              >
                Abbrechen
              </button>
              <button
                onClick={handlePerformance}
                className="px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Focus Triage Modal ────────────────────────────────────────────────────────
function FocusTriageModal({ posts, onClose, onCommit }) {
  const draftPosts = posts.filter((p) => p.status === 'draft')
  const [idx, setIdx] = useState(0)
  const [decisions, setDecisions] = useState({}) // id → 'approve'|'reject'|'skip'
  const [committing, setCommitting] = useState(false)
  const [done, setDone] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const current = draftPosts[idx]
  const total = draftPosts.length
  const decided = Object.keys(decisions).length
  const toApprove = Object.values(decisions).filter((d) => d === 'approve').length
  const toReject = Object.values(decisions).filter((d) => d === 'reject').length

  function decide(choice) {
    if (!current) return
    setDecisions((prev) => ({ ...prev, [current.id]: choice }))
  }

  function advance() {
    setExpanded(false)
    setIdx((i) => Math.min(i + 1, total))
  }

  function goBack() {
    setExpanded(false)
    setIdx((i) => Math.max(i - 1, 0))
  }

  useEffect(() => {
    function handler(e) {
      const tag = e.target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'ArrowRight' || e.key === 'Enter') {
        decide('approve')
        advance()
      } else if (e.key === 'ArrowLeft' || e.key === 'Backspace') {
        e.preventDefault()
        decide('reject')
        advance()
      } else if (e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault()
        decide('skip')
        advance()
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        goBack()
      } else if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [current, idx])

  async function handleCommit() {
    setCommitting(true)
    const approveIds = Object.entries(decisions)
      .filter(([, v]) => v === 'approve')
      .map(([k]) => k)
    const rejectIds = Object.entries(decisions)
      .filter(([, v]) => v === 'reject')
      .map(([k]) => k)
    let approved = 0,
      rejected = 0
    if (approveIds.length) {
      try {
        const r = await bulkApproveContent(approveIds)
        approved = r.approved || approveIds.length
      } catch {}
    }
    if (rejectIds.length) {
      try {
        const r = await bulkRejectContent(rejectIds)
        rejected = r.rejected || rejectIds.length
      } catch {}
    }
    setCommitting(false)
    setDone(true)
    onCommit({ approved, rejected })
  }

  const isFinished = idx >= total

  const qs = current ? postScore(current.content_text || '') : null

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="xl"
      closeOnEscape={false}
      contentClassName="p-0 flex flex-col max-h-[90vh]"
      className="max-h-[90vh]"
    >
      <>
        {/* Header — eigenes ESC-/Pfeiltasten-Handling oben im Keyboard-Listener,
            Dialog übernimmt daher NICHT selbst ESC (closeOnEscape=false), sonst
            würde onClose doppelt ausgelöst. */}
        <div className="px-6 py-4 border-b border-surface-border flex items-center gap-3 shrink-0">
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <span className="text-sm font-bold text-ink">⚡ Focus-Triage</span>
              <span className="text-xs text-ink-muted">
                {Math.min(idx + 1, total)} / {total} Entwürfe
              </span>
              <span className="text-xs text-status-fertig-text font-medium">✓ {toApprove}</span>
              <span className="text-xs text-status-fehler-text font-medium">✗ {toReject}</span>
            </div>
            <div className="mt-1.5 h-1.5 bg-surface-bg rounded-full overflow-hidden w-full">
              <div
                className="h-full bg-primary-500 rounded-full transition-all"
                style={{ width: `${(idx / total) * 100}%` }}
              />
            </div>
          </div>
          <CloseButton onClick={onClose} />
        </div>

        {/* Keyboard hints */}
        <div className="px-6 py-2 bg-surface-bg border-b border-surface-border flex items-center gap-4 text-[10px] text-ink-muted shrink-0">
          <span>
            <kbd className="px-1.5 py-0.5 bg-white border border-surface-border rounded text-[9px]">
              → Enter
            </kbd>{' '}
            Freigeben
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-white border border-surface-border rounded text-[9px]">
              ← ⌫
            </kbd>{' '}
            Verwerfen
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-white border border-surface-border rounded text-[9px]">
              Space ↓
            </kbd>{' '}
            Überspringen
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-white border border-surface-border rounded text-[9px]">
              ↑
            </kbd>{' '}
            Zurück
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-white border border-surface-border rounded text-[9px]">
              Esc
            </kbd>{' '}
            Schließen
          </span>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {done ? (
            <div className="text-center py-12">
              <div className="text-5xl mb-4">🎉</div>
              <p className="text-lg font-bold text-ink">Triage abgeschlossen!</p>
              <p className="text-sm text-ink-muted mt-1">
                {toApprove} freigegeben · {toReject} verworfen
              </p>
              <button
                onClick={onClose}
                className="mt-6 px-6 py-2.5 bg-primary-700 text-white rounded-xl text-sm font-semibold hover:bg-primary-800"
              >
                Schließen
              </button>
            </div>
          ) : isFinished ? (
            <div className="text-center py-12">
              <div className="text-5xl mb-4">✅</div>
              <p className="text-lg font-bold text-ink">Alle Entwürfe bewertet</p>
              <p className="text-sm text-ink-muted mt-1">
                {toApprove} zum Freigeben · {toReject} zum Verwerfen ·{' '}
                {total - toApprove - toReject} übersprungen
              </p>
              <button
                onClick={handleCommit}
                disabled={committing || toApprove + toReject === 0}
                className="mt-6 px-6 py-2.5 bg-status-fertig-text text-white rounded-xl text-sm font-semibold hover:opacity-90 disabled:opacity-50"
              >
                {committing
                  ? 'Wird gespeichert...'
                  : `${toApprove + toReject} Entscheidungen anwenden`}
              </button>
            </div>
          ) : current ? (
            <div className="space-y-4">
              {/* Meta row */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 bg-status-neu-bg text-status-neu-text rounded-full text-[10px] font-medium">
                  {current.channel || 'linkedin'}
                </span>
                {current.content_metadata?.angle && (
                  <span className="px-2 py-0.5 bg-surface-bg text-ink-light rounded-full text-[10px]">
                    {current.content_metadata.angle}
                  </span>
                )}
                {current.content_metadata?.pillar &&
                  (() => {
                    const p = PILLAR_CONFIG[current.content_metadata.pillar]
                    return p ? (
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${p.color}`}
                      >
                        {p.emoji} {p.label}
                      </span>
                    ) : null
                  })()}
                {qs && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ml-auto ${qs.score >= 8 ? 'bg-status-fertig-bg text-status-fertig-text border-status-fertig-border' : qs.score >= 6 ? 'bg-primary-50 text-primary-700 border-primary-200' : qs.score >= 4 ? 'bg-status-aktiv-bg text-status-aktiv-text border-status-aktiv-border' : 'bg-status-fehler-bg text-status-fehler-text border-status-fehler-border'}`}
                  >
                    Score: {qs.grade} ({qs.score}/10)
                  </span>
                )}
                <span className="text-[10px] text-ink-muted">
                  {(current.content_text || '').length} Z.
                </span>
              </div>

              {/* Post text */}
              <div
                className={`text-sm text-ink leading-relaxed whitespace-pre-line bg-surface-bg rounded-xl p-4 border border-surface-border ${expanded ? '' : 'max-h-48 overflow-hidden'}`}
              >
                {current.content_text}
              </div>
              {!expanded && (current.content_text || '').length > 400 && (
                <button
                  onClick={() => setExpanded(true)}
                  className="text-xs text-primary-600 hover:underline -mt-2"
                >
                  Vollständig anzeigen ↓
                </button>
              )}

              {/* Quality tips */}
              {qs?.tips?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {qs.tips.map((t, i) => (
                    <span
                      key={i}
                      className="text-[10px] px-2 py-0.5 bg-status-aktiv-bg text-status-aktiv-text border border-status-aktiv-border rounded-full"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Decision highlight */}
              {decisions[current.id] && (
                <div
                  className={`text-center py-1.5 rounded-lg text-xs font-bold ${decisions[current.id] === 'approve' ? 'bg-status-fertig-bg text-status-fertig-text' : decisions[current.id] === 'reject' ? 'bg-status-fehler-bg text-status-fehler-text' : 'bg-surface-bg text-ink-light'}`}
                >
                  {decisions[current.id] === 'approve'
                    ? '✓ Wird freigegeben'
                    : decisions[current.id] === 'reject'
                      ? '✗ Wird verworfen'
                      : '→ Übersprungen'}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Action buttons */}
        {!isFinished && !done && current && (
          <div className="px-6 py-4 border-t border-surface-border flex items-center gap-3 shrink-0">
            <button
              onClick={() => {
                decide('reject')
                advance()
              }}
              className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-status-fehler-text bg-status-fehler-bg border-2 border-status-fehler-border hover:opacity-90 transition-colors"
            >
              <span className="text-lg">✗</span> Verwerfen
            </button>
            <button
              onClick={() => {
                decide('skip')
                advance()
              }}
              className="px-5 py-3 rounded-xl text-sm font-medium text-ink-light border border-surface-border hover:bg-surface-bg"
            >
              Überspringen
            </button>
            <button
              onClick={() => {
                decide('approve')
                advance()
              }}
              className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white bg-status-fertig-text border-2 border-status-fertig-text hover:opacity-90 transition-colors"
            >
              <span className="text-lg">✓</span> Freigeben
            </button>
          </div>
        )}

        {/* Mid-session commit */}
        {!isFinished && !done && decided >= 10 && (
          <div className="px-6 pb-3 shrink-0">
            <button
              onClick={handleCommit}
              disabled={committing}
              className="w-full py-2 text-xs font-medium text-status-fertig-text bg-status-fertig-bg border border-status-fertig-border rounded-lg hover:opacity-90 disabled:opacity-50"
            >
              {committing
                ? 'Speichert...'
                : `✓ ${toApprove + toReject} Entscheidungen jetzt anwenden (weiter möglich)`}
            </button>
          </div>
        )}
      </>
    </Dialog>
  )
}

// ── Draft Quality Leaderboard (Cycle 40) ────────────────────────────────────
function LeaderboardModal({ posts, onClose, onCommit }) {
  const drafts = posts.filter((p) => p.status === 'draft')
  const scored = drafts
    .map((p) => ({ ...p, _qs: postScore(p.content_text || '') }))
    .sort((a, b) => b._qs.score - a._qs.score)

  const gradeDist = { A: 0, B: 0, C: 0, D: 0, F: 0 }
  scored.forEach((p) => {
    gradeDist[p._qs.grade] = (gradeDist[p._qs.grade] || 0) + 1
  })
  const total = scored.length

  const [selected, setSelected] = useState(new Set())
  const [approving, setApproving] = useState(false)
  const [msg, setMsg] = useState(null)

  function selectTop(n) {
    setSelected(new Set(scored.slice(0, n).map((p) => p.id)))
  }

  function toggleAll() {
    if (selected.size === scored.length) setSelected(new Set())
    else setSelected(new Set(scored.map((p) => p.id)))
  }

  async function handleApprove() {
    if (!selected.size) return
    setApproving(true)
    try {
      const r = await bulkApproveContent([...selected])
      const count = r.approved || selected.size
      setMsg(`✅ ${count} Posts freigegeben!`)
      setTimeout(() => {
        onCommit(count)
      }, 1800)
    } catch (e) {
      setMsg('Fehler: ' + e.message)
    }
    setApproving(false)
  }

  const GRADE_STYLE = {
    A: 'bg-status-fertig-bg text-status-fertig-text border-status-fertig-border',
    B: 'bg-status-neu-bg text-status-neu-text border-status-neu-border',
    C: 'bg-status-aktiv-bg text-status-aktiv-text border-status-aktiv-border',
    // orange bewusst behalten: eigene Notenstufe "D" zwischen aktiv(C)/fehler(F), kein
    // eigenes Status-Token dafür vorhanden — Zwischenfarbe außerhalb des 5er-Sets.
    D: 'bg-orange-100 text-orange-800 border-orange-300',
    F: 'bg-status-fehler-bg text-status-fehler-text border-status-fehler-border',
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border shrink-0 bg-gradient-to-r from-accent-50 to-accent-50">
        <div>
          <h2 className="text-base font-bold text-ink flex items-center gap-2">
            🏆 Draft-Leaderboard{' '}
            <span className="text-sm font-normal text-ink-muted">— {total} Entwürfe bewertet</span>
          </h2>
          <p className="text-xs text-ink-muted mt-0.5">
            Sortiert nach KI-Qualitätsscore · Beste zuerst
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-2 text-ink-muted hover:text-ink-light rounded-lg hover:bg-surface-bg"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Grade distribution bar */}
      <div className="px-6 py-3 border-b border-surface-border shrink-0 bg-white">
        <div className="flex items-center gap-4">
          <span className="text-xs text-ink-muted font-medium shrink-0">Notenverteilung:</span>
          <div className="flex items-center gap-1.5 flex-1 flex-wrap">
            {Object.entries(gradeDist)
              .filter(([, v]) => v > 0)
              .map(([g, v]) => (
                <span
                  key={g}
                  className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${GRADE_STYLE[g]}`}
                >
                  {g}: {v}
                </span>
              ))}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-ink-muted">Top auswählen:</span>
            {[10, 25, 50, 100].map((n) => (
              <button
                key={n}
                onClick={() => selectTop(Math.min(n, total))}
                className="px-2 py-0.5 text-xs border border-accent-300 text-accent-700 rounded-lg hover:bg-accent-50 font-medium"
              >
                {n}
              </button>
            ))}
            <button
              onClick={toggleAll}
              className="px-2 py-0.5 text-xs border border-surface-border text-ink-light rounded-lg hover:bg-surface-bg"
            >
              {selected.size === total ? 'Alle ab' : 'Alle'}
            </button>
          </div>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y divide-surface-border">
        {scored.length === 0 && (
          <div className="flex items-center justify-center h-40 text-ink-muted text-sm">
            Keine Entwürfe vorhanden
          </div>
        )}
        {scored.map((p, i) => {
          const qs = p._qs
          const isSelected = selected.has(p.id)
          return (
            <div
              key={p.id}
              onClick={() =>
                setSelected((prev) => {
                  const s = new Set(prev)
                  isSelected ? s.delete(p.id) : s.add(p.id)
                  return s
                })
              }
              className={`flex items-start gap-3 px-6 py-3 cursor-pointer transition-colors ${isSelected ? 'bg-accent-50' : 'hover:bg-surface-bg'}`}
            >
              {/* Rank */}
              <span className="text-xs font-bold text-ink-muted w-6 shrink-0 pt-0.5 tabular-nums">
                {i + 1}
              </span>
              {/* Checkbox */}
              <div
                className={`w-4 h-4 rounded border-2 shrink-0 mt-0.5 flex items-center justify-center transition-colors ${isSelected ? 'bg-accent-500 border-accent-500' : 'border-surface-border'}`}
              >
                {isSelected && <Check className="w-2.5 h-2.5 text-white" />}
              </div>
              {/* Grade badge */}
              <span
                className={`px-2 py-0.5 rounded-lg text-xs font-black border shrink-0 ${GRADE_STYLE[qs.grade]}`}
              >
                {qs.grade}
              </span>
              {/* Score bar */}
              <div className="w-16 shrink-0">
                <div className="h-1.5 bg-surface-border rounded-full overflow-hidden mt-1.5">
                  <div
                    className={`h-full rounded-full transition-all ${
                      qs.score >= 8
                        ? 'bg-status-fertig-text'
                        : qs.score >= 6
                          ? 'bg-status-neu-text'
                          : qs.score >= 4
                            ? 'bg-status-aktiv-text'
                            : 'bg-status-fehler-text'
                    }`}
                    style={{ width: `${qs.score * 10}%` }}
                  />
                </div>
                <span className="text-[9px] text-ink-muted tabular-nums">{qs.score}/10</span>
              </div>
              {/* Preview text */}
              <p className="flex-1 text-xs text-ink line-clamp-2 leading-relaxed">
                {(p.content_text || '').slice(0, 180)}
              </p>
              {/* Pillar */}
              {p.content_metadata?.pillar && PILLAR_CONFIG[p.content_metadata.pillar] && (
                <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded border text-ink-muted">
                  {PILLAR_CONFIG[p.content_metadata.pillar].emoji}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer action bar */}
      <div className="px-6 py-4 border-t border-surface-border bg-white shrink-0">
        {msg ? (
          <div className="text-center py-2 text-sm font-semibold text-status-fertig-text">{msg}</div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-ink-muted flex-1">
              {selected.size > 0 ? (
                <>
                  <span className="font-semibold text-accent-700">{selected.size}</span> Posts
                  ausgewählt
                </>
              ) : (
                'Nichts ausgewählt'
              )}
            </span>
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-ink-light border border-surface-border rounded-xl hover:bg-surface-bg"
            >
              Schließen
            </button>
            <button
              onClick={handleApprove}
              disabled={!selected.size || approving}
              className="flex items-center gap-2 px-5 py-2 text-sm font-semibold text-white bg-accent-500 rounded-xl hover:bg-accent-600 disabled:opacity-50 transition-colors"
            >
              {approving ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              {approving ? 'Freigeben...' : `${selected.size} Posts freigeben`}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Posts() {
  const { toast } = useToast()
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [filter, setFilter] = useState('')
  const [showHooks, setShowHooks] = useState(false)
  const [hookAngle, setHookAngle] = useState('')
  const [hookData, setHookData] = useState(null)
  const [showBestTimes, setShowBestTimes] = useState(false)
  const [bestTimesData, setBestTimesData] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [bulkApproving, setBulkApproving] = useState(false)
  const [bulkRejecting, setBulkRejecting] = useState(false)
  const [bulkPublishing, setBulkPublishing] = useState(false)
  const [bulkPillarAssigning, setBulkPillarAssigning] = useState(false)
  const [bulkMsg, setBulkMsg] = useState(null)
  const [showDupeOnly, setShowDupeOnly] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [triageMode, setTriageMode] = useState(false)
  const [showFocusTriage, setShowFocusTriage] = useState(false)
  const [showLeaderboard, setShowLeaderboard] = useState(false)
  const [triageApprove, setTriageApprove] = useState(new Set())
  const [triageReject, setTriageReject] = useState(new Set())
  const [triageExecuting, setTriageExecuting] = useState(false)
  const [triageMsg, setTriageMsg] = useState(null)
  const [search, setSearch] = useState('')
  const [angleFilter, setAngleFilter] = useState('')
  const [pillarFilter, setPillarFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [sourcesList, setSourcesList] = useState([])
  const [sortBy, setSortBy] = useState('newest')
  const [tagFilter, setTagFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('') // #145 Phase 4.1
  const [autoScheduling, setAutoScheduling] = useState(false)
  const [showQuickCreate, setShowQuickCreate] = useState(false)
  const [qcTab, setQcTab] = useState('topic') // 'topic' | 'url'
  const [qcTopic, setQcTopic] = useState('')
  const [qcAngle, setQcAngle] = useState('thought_leadership')
  const [qcPillar, setQcPillar] = useState('')
  const [qcStyleNotes, setQcStyleNotes] = useState('')
  const [qcLoading, setQcLoading] = useState(false)
  const [qcResult, setQcResult] = useState(null)
  const [qcUrl, setQcUrl] = useState('')
  const [showSeriesBuilder, setShowSeriesBuilder] = useState(false)
  const [seriesTopic, setSeriesTopic] = useState('')
  const [seriesPillar, setSeriesPillar] = useState('')
  const [seriesLoading, setSeriesLoading] = useState(false)
  const [seriesResult, setSeriesResult] = useState(null)
  const [autoScheduleResult, setAutoScheduleResult] = useState(null)
  const [directText, setDirectText] = useState('')
  const [directPillar, setDirectPillar] = useState('')
  const [directSaving, setDirectSaving] = useState(false)
  const [directResult, setDirectResult] = useState(null)
  const directRef = useRef(null)
  const [showShortcuts, setShowShortcuts] = useState(false)

  // Compute duplicate map whenever posts change (runs client-side, no extra API call)
  const dupeMap = useMemo(() => computeDuplicates(posts), [posts])
  const dupeCount = dupeMap.size

  // All unique angles for the dropdown
  const angles = useMemo(() => {
    const set = new Set()
    posts.forEach((p) => {
      const a = p.content_metadata?.angle
      if (a) set.add(a)
    })
    return [...set].sort()
  }, [posts])

  // Filtered + sorted posts
  const filteredPosts = useMemo(() => {
    let list = posts
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((p) => (p.content_text || '').toLowerCase().includes(q))
    }
    if (angleFilter) {
      list = list.filter((p) => p.content_metadata?.angle === angleFilter)
    }
    if (pillarFilter) {
      list = list.filter((p) => p.content_metadata?.pillar === pillarFilter)
    }
    if (sourceFilter) {
      list = list.filter((p) => p.source_id === sourceFilter)
    }
    if (tagFilter) {
      list = list.filter((p) => (p.content_metadata?.tags || []).includes(tagFilter))
    }
    if (categoryFilter) {
      list = list.filter((p) => p.category === categoryFilter)
    }
    // Sort
    list = [...list]
    if (sortBy === 'oldest') {
      list.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0))
    } else if (sortBy === 'score_desc') {
      list.sort(
        (a, b) => postScore(b.content_text || '').score - postScore(a.content_text || '').score
      )
    } else if (sortBy === 'score_asc') {
      list.sort(
        (a, b) => postScore(a.content_text || '').score - postScore(b.content_text || '').score
      )
    } else {
      // newest (default — keep backend order or sort by created_at desc)
      list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    }
    return list
  }, [posts, search, angleFilter, pillarFilter, sourceFilter, tagFilter, categoryFilter, sortBy])

  useEffect(() => {
    loadPosts()
    const interval = setInterval(() => loadPosts(true), 30000)
    return () => clearInterval(interval)
  }, [filter])

  useEffect(() => {
    getSources()
      .then((s) => setSourcesList(Array.isArray(s) ? s.filter((x) => x.is_active) : []))
      .catch(() => {})
  }, [])

  // Global keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e) {
      // Ignore when typing in inputs/textareas
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable) return

      if (e.key === '?') {
        e.preventDefault()
        setShowShortcuts((s) => !s)
        return
      }
      if (e.key === 'Escape') {
        setShowShortcuts(false)
        setSelectedId(null)
        return
      }

      // Navigation: j = next, k = prev
      if (e.key === 'j' || e.key === 'k') {
        e.preventDefault()
        const ids = filteredPosts.map((p) => p.id)
        if (ids.length === 0) return
        const currentIdx = selectedId ? ids.indexOf(selectedId) : -1
        let nextIdx = e.key === 'j' ? currentIdx + 1 : currentIdx - 1
        nextIdx = Math.max(0, Math.min(ids.length - 1, nextIdx))
        setSelectedId(ids[nextIdx])
        // Scroll to focused post
        setTimeout(() => {
          document
            .getElementById(`post-card-${ids[nextIdx]}`)
            ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        }, 50)
        return
      }

      // Actions on currently focused post
      if (!selectedId) return
      const post = filteredPosts.find((p) => p.id === selectedId)
      if (!post) return

      if (e.key === 'a' && (post.status === 'draft' || post.status === 'rejected')) {
        e.preventDefault()
        approveContent(selectedId)
          .then(() => loadPosts())
          .catch(() => {})
        return
      }
      if (e.key === 'r' && post.status !== 'rejected') {
        e.preventDefault()
        import('../api')
          .then(({ rejectContent }) => {
            // fallback: use bulk reject with 1 id
            bulkRejectContent([selectedId])
              .then(() => loadPosts())
              .catch(() => {})
          })
          .catch(() => {
            bulkRejectContent([selectedId])
              .then(() => loadPosts())
              .catch(() => {})
          })
        return
      }
      if (e.key === 'c') {
        e.preventDefault()
        navigator.clipboard.writeText(post.content_text || '').catch(() => {})
        return
      }
      if (e.key === 'Enter' || e.key === 'o') {
        e.preventDefault()
        setSelectedId((prev) => (prev === post.id ? null : post.id))
        return
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [filteredPosts, selectedId])

  function triageToggle(id, action) {
    if (action === 'approve') {
      setTriageApprove((prev) => {
        const s = new Set(prev)
        s.has(id) ? s.delete(id) : s.add(id)
        return s
      })
      setTriageReject((prev) => {
        const s = new Set(prev)
        s.delete(id)
        return s
      })
    } else {
      setTriageReject((prev) => {
        const s = new Set(prev)
        s.has(id) ? s.delete(id) : s.add(id)
        return s
      })
      setTriageApprove((prev) => {
        const s = new Set(prev)
        s.delete(id)
        return s
      })
    }
  }

  async function executeTriage() {
    if (!triageApprove.size && !triageReject.size) return
    setTriageExecuting(true)
    let approved = 0,
      rejected = 0
    if (triageApprove.size > 0) {
      try {
        const r = await bulkApproveContent([...triageApprove])
        approved = r.approved || triageApprove.size
      } catch {}
    }
    if (triageReject.size > 0) {
      try {
        const r = await bulkRejectContent([...triageReject])
        rejected = r.rejected || triageReject.size
      } catch {}
    }
    setTriageApprove(new Set())
    setTriageReject(new Set())
    setTriageMsg(`✅ ${approved} freigegeben · 🗑 ${rejected} verworfen`)
    await loadPosts()
    setTimeout(() => setTriageMsg(null), 4000)
    setTriageExecuting(false)
  }

  async function loadPosts(silent = false) {
    const savedScrollY = silent ? window.scrollY : 0
    if (!silent) setLoading(true)
    try {
      const params = {}
      if (filter) params.status = filter
      const data = await getContentList(params)
      // flushSync ensures React commits the DOM update synchronously before scroll restore
      flushSync(() => {
        setPosts(Array.isArray(data) ? data : data.items || [])
      })
      if (silent && savedScrollY > 0) {
        window.scrollTo({ top: savedScrollY, behavior: 'instant' })
      }
    } catch (e) {
      if (!silent) setError(e.message)
      else console.error('[silent-refresh] Posts', e)
    }
    if (!silent) setLoading(false)
  }

  const rejectedCount = posts.filter((p) => p.status === 'rejected').length

  const filters = [
    { value: '', label: 'Alle' },
    { value: 'draft', label: 'Entwürfe' },
    { value: 'approved', label: 'Freigegeben' },
    { value: 'published', label: 'Gepostet' },
    { value: 'rejected', label: `Verworfen${rejectedCount > 0 ? ` (${rejectedCount})` : ''}` },
  ]

  return (
    <div>
      {showFocusTriage && (
        <FocusTriageModal
          posts={filteredPosts.length > 0 ? filteredPosts : posts}
          onClose={() => setShowFocusTriage(false)}
          onCommit={({ approved, rejected }) => {
            setShowFocusTriage(false)
            loadPosts()
            setTriageMsg(`⚡ Focus-Triage: ${approved} freigegeben · ${rejected} verworfen`)
            setTimeout(() => setTriageMsg(null), 5000)
          }}
        />
      )}
      {showLeaderboard && (
        <LeaderboardModal
          posts={posts}
          onClose={() => setShowLeaderboard(false)}
          onCommit={(count) => {
            setShowLeaderboard(false)
            loadPosts()
            setTriageMsg(`🏆 Leaderboard: ${count} Top-Posts freigegeben!`)
            setTimeout(() => setTriageMsg(null), 5000)
          }}
        />
      )}
      {/* Keyboard Shortcuts Modal */}
      <Dialog
        open={showShortcuts}
        onClose={() => setShowShortcuts(false)}
        title="⌨️ Tastenkürzel"
        maxWidth="sm"
      >
        <div className="space-y-1 text-xs">
          {[
            ['j / k', 'Nächster / Vorheriger Post'],
            ['a', 'Post freigeben (approve)'],
            ['r', 'Post verwerfen (reject)'],
            ['c', 'Post-Text in Zwischenablage kopieren'],
            ['Enter / o', 'Post öffnen / schließen'],
            ['Esc', 'Auswahl aufheben / Modal schließen'],
            ['?', 'Diese Hilfe ein-/ausblenden'],
          ].map(([key, desc]) => (
            <div
              key={key}
              className="flex items-center justify-between py-1.5 border-b border-surface-border"
            >
              <span className="text-ink-muted">{desc}</span>
              <kbd className="px-2 py-0.5 bg-surface-bg border border-surface-border rounded text-[10px] font-mono font-semibold text-ink shrink-0 ml-3">
                {key}
              </kbd>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[10px] text-ink-muted">
          Shortcuts funktionieren wenn kein Textfeld fokussiert ist.
        </p>
      </Dialog>

      <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div className="shrink-0">
          <h1 className="text-xl font-bold text-ink whitespace-nowrap">LinkedIn-Posts</h1>
          <p className="text-sm text-ink-light mt-0.5">
            Bearbeite, gib frei oder tracke deine Posts.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {/* Eine Primäraktion (Post erstellen), Rest einheitlich als Secondary mit
              Icon+Text unterschieden statt über Farbe — Owner-Entscheid 2026-08-15
              (9 Identitätsfarben nebeneinander erzeugten "Regenbogen ohne
              Hierarchie"). Aktive Toggle-Zustände heben sich per bg-primary-50 ab. */}
          <button
            onClick={() => {
              setShowSeriesBuilder(!showSeriesBuilder)
              setSeriesResult(null)
              setShowQuickCreate(false)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showSeriesBuilder ? 'bg-primary-50 text-primary-700 border-primary-200' : 'bg-surface-card text-ink-light border-surface-border hover:bg-surface-bg'}`}
            title="3-teilige LinkedIn-Serie generieren"
          >
            🔗 Serie erstellen
          </button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setShowQuickCreate(!showQuickCreate)
              setQcResult(null)
              setShowSeriesBuilder(false)
            }}
            title="AI Post aus Thema generieren"
          >
            ✏️ Post erstellen
          </Button>
          <button
            onClick={() => {
              setTriageMode(!triageMode)
              setTriageApprove(new Set())
              setTriageReject(new Set())
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${triageMode ? 'bg-primary-50 text-primary-700 border-primary-200' : 'bg-surface-card text-ink-light border-surface-border hover:bg-surface-bg'}`}
            title="Schnell-Review für Draft-Posts"
          >
            <Zap className="w-3.5 h-3.5" />
            Triage-Modus
          </button>
          <button
            onClick={() => setShowFocusTriage(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg transition-colors"
            title="Keyboard-gesteuerter Einzel-Post-Review"
          >
            ⚡ Focus-Triage
          </button>
          <button
            onClick={() => setShowLeaderboard(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-surface-card text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg transition-colors"
            title="Alle Entwürfe nach Qualitätsscore sortieren und Top-N freigeben"
          >
            🏆 Leaderboard
          </button>
          <button
            onClick={async () => {
              setExporting(true)
              try {
                await downloadContentExport(filter || undefined)
              } catch (e) {
                setError(e.message)
              }
              setExporting(false)
            }}
            disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light bg-surface-card border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-60 transition-colors"
            title="Posts als CSV exportieren"
          >
            <Download className="w-3.5 h-3.5" />
            {exporting ? 'Exportiert...' : 'CSV Export'}
          </button>
          <button
            onClick={async () => {
              if (
                !window.confirm(
                  'Alle freigegebenen LinkedIn-Posts automatisch einplanen? (2 Posts/Tag, Mo–Fr, 4 Wochen)'
                )
              )
                return
              setAutoScheduling(true)
              setAutoScheduleResult(null)
              try {
                const r = await autoSchedulePosts({
                  max_per_day: 2,
                  channel: 'linkedin',
                  weeks_ahead: 4,
                })
                setAutoScheduleResult({
                  ok: true,
                  msg: r.message,
                  count: r.scheduled,
                  first: r.first_slot,
                  last: r.last_slot,
                })
              } catch (e) {
                setAutoScheduleResult({ ok: false, msg: e.message })
              }
              setAutoScheduling(false)
            }}
            disabled={autoScheduling}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-light bg-surface-card border border-surface-border rounded-lg hover:bg-surface-bg disabled:opacity-60 transition-colors"
            title="Alle freigegebenen Posts automatisch auf beste Posting-Zeiten einplanen"
          >
            📅 {autoScheduling ? 'Plane ein...' : 'Auto-Einplanen'}
          </button>
          <button
            onClick={async () => {
              if (!showBestTimes && !bestTimesData) {
                const d = await getBestPostingTimes()
                setBestTimesData(d)
              }
              setShowBestTimes(!showBestTimes)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showBestTimes ? 'bg-primary-50 text-primary-700 border-primary-200' : 'bg-surface-card text-ink-light border-surface-border hover:bg-surface-bg'}`}
          >
            ⏰ Beste Zeiten
          </button>
          <button
            onClick={async () => {
              if (!showHooks) {
                const d = await getHookLibrary(hookAngle || undefined)
                setHookData(d)
              }
              setShowHooks(!showHooks)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showHooks ? 'bg-primary-50 text-primary-700 border-primary-200' : 'bg-surface-card text-ink-light border-surface-border hover:bg-surface-bg'}`}
          >
            ✍️ Hook-Bibliothek
          </button>
          {dupeCount > 0 && (
            <button
              onClick={() => setShowDupeOnly(!showDupeOnly)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${showDupeOnly ? 'bg-status-aktiv-text text-white border-status-aktiv-text' : 'bg-status-aktiv-bg text-status-aktiv-text border-status-aktiv-border hover:opacity-90'}`}
            >
              <AlertTriangle className="w-3.5 h-3.5" /> {dupeCount} Duplikate
            </button>
          )}
          <button
            onClick={() => setShowShortcuts((s) => !s)}
            className="flex items-center justify-center w-7 h-7 text-xs font-bold text-ink-muted bg-surface-bg border border-surface-border rounded-lg hover:bg-surface-border transition-colors"
            title="Tastenkürzel anzeigen (?)"
          >
            ?
          </button>
        </div>
      </div>
      <div className="flex items-center justify-end mb-5">
        <div className="flex items-center gap-1 bg-surface-bg rounded-lg p-1">
          {filters.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filter === f.value
                  ? 'bg-white text-ink shadow-sm'
                  : 'text-ink-light hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Search + Angle Filter */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink-muted pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Posts durchsuchen..."
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 bg-white"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-light text-sm"
            >
              ×
            </button>
          )}
        </div>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="text-xs border border-surface-border rounded-lg px-2.5 py-1.5 text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-400 bg-white"
        >
          <option value="">Alle Quellen</option>
          {sourcesList.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          value={angleFilter}
          onChange={(e) => setAngleFilter(e.target.value)}
          className="text-xs border border-surface-border rounded-lg px-2.5 py-1.5 text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-400 bg-white"
        >
          <option value="">Alle Angles</option>
          {angles.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <select
          value={pillarFilter}
          onChange={(e) => setPillarFilter(e.target.value)}
          className="text-xs border border-surface-border rounded-lg px-2.5 py-1.5 text-ink-light focus:outline-none focus:ring-1 focus:ring-primary-400 bg-white"
        >
          <option value="">Alle Säulen</option>
          {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
            <option key={k} value={k}>
              {cfg.emoji} {cfg.label}
            </option>
          ))}
        </select>
        {/* Sort dropdown */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="px-2.5 py-1.5 text-xs border border-surface-border rounded-lg focus:outline-none focus:ring-1 focus:ring-primary-400 bg-white text-ink-muted ml-auto"
        >
          <option value="newest">↓ Neueste zuerst</option>
          <option value="oldest">↑ Älteste zuerst</option>
          <option value="score_desc">★ Bester Score</option>
          <option value="score_asc">☆ Schlechtester Score</option>
        </select>
        {/* #145 Phase 4.1: Kategorie-Filter */}
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-[11px] text-ink-muted mr-1">Kategorie:</span>
          {[
            { value: '', label: 'Alle', color: 'bg-surface-bg text-ink-light' },
            { value: 'news', label: 'News', color: 'bg-status-neu-bg text-status-neu-text' },
            {
              value: 'persoenlich',
              label: 'Persönlich',
              color: 'bg-status-aktiv-bg text-status-aktiv-text',
            },
            {
              value: 'trust',
              label: 'Trust',
              color: 'bg-status-fertig-bg text-status-fertig-text',
            },
            // violet bewusst behalten: 4. Kategorie neben den 3 Status-Farben oben,
            // analog zu PILLAR_CONFIG (Zeile ~108) — primary/accent sind bereits
            // anderweitig belegt, braucht eigene Identitätsfarbe.
            { value: 'praxis', label: 'Praxis', color: 'bg-violet-100 text-violet-700' },
          ].map((opt) => (
            <button
              key={opt.value || 'alle'}
              onClick={() => setCategoryFilter(opt.value)}
              className={`px-2.5 py-1 text-[11px] rounded-full transition-colors ${categoryFilter === opt.value ? `${opt.color} ring-1 ring-current` : 'bg-white text-ink-muted hover:bg-surface-bg border border-surface-border'}`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {(search || angleFilter || pillarFilter || sourceFilter || categoryFilter) && (
          <span className="text-xs text-ink-muted">
            {filteredPosts.length} von {posts.length} Posts
          </span>
        )}

        {(search || angleFilter || pillarFilter || sourceFilter || categoryFilter) && (
          <button
            onClick={() => {
              setSearch('')
              setAngleFilter('')
              setPillarFilter('')
              setSourceFilter('')
            }}
            className="text-xs text-ink-muted hover:text-ink-light"
          >
            Filter zurücksetzen
          </button>
        )}
        {sourceFilter && filteredPosts.filter((p) => p.status === 'draft').length > 0 && (
          <button
            onClick={async () => {
              const draftCount = filteredPosts.filter((p) => p.status === 'draft').length
              const srcName =
                sourcesList.find((s) => s.id === sourceFilter)?.name || 'dieser Quelle'
              if (
                !window.confirm(
                  `${draftCount} Entwürfe von "${srcName}" ablehnen?\n\nDie Posts bleiben in der Datenbank (Status: Abgelehnt).`
                )
              )
                return
              try {
                const r = await bulkRejectContent(null, sourceFilter)
                setBulkMsg(`🗑 ${r.rejected} Entwürfe von "${srcName}" abgelehnt`)
                setTimeout(() => {
                  setBulkMsg(null)
                  loadPosts()
                }, 2500)
              } catch (e) {
                toast.error('Fehler: ' + e.message)
              }
            }}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-status-fehler-text bg-status-fehler-bg border border-status-fehler-border rounded-md hover:opacity-90 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            {filteredPosts.filter((p) => p.status === 'draft').length} Entwürfe ablehnen
          </button>
        )}
      </div>

      {/* Series Builder Panel — indigo bewusst behalten: Panel-Identität passend zum
          "Serie erstellen"-Button oben (siehe Kommentar dort) */}
      {showSeriesBuilder && (
        <div className="mb-6 p-5 bg-white border-2 border-indigo-200 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-bold text-ink flex items-center gap-2">
                🔗 LinkedIn-Serie Builder
              </h2>
              <p className="text-[11px] text-ink-muted mt-0.5">
                3 verbundene Posts: Hook → Deep Dive → Fazit/CTA
              </p>
            </div>
            <button
              onClick={() => {
                setShowSeriesBuilder(false)
                setSeriesResult(null)
              }}
              className="text-ink-muted hover:text-ink-light text-lg"
            >
              ×
            </button>
          </div>

          {seriesResult ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-indigo-900">
                  ✅ {seriesResult.posts_created} Posts erstellt
                </span>
                <span className="text-[11px] text-ink-muted">— Thema: {seriesResult.topic}</span>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {(seriesResult.parts || []).map((part) => (
                  <div
                    key={part.part}
                    className="p-3 bg-indigo-50 border border-indigo-200 rounded-xl"
                  >
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                        {part.part}
                      </span>
                      <span className="text-[11px] font-semibold text-indigo-900">
                        {part.label}
                      </span>
                      <span className="text-[10px] text-indigo-500 ml-auto">
                        {part.char_count} Z.
                      </span>
                    </div>
                    <p className="text-[11px] text-ink-muted leading-snug line-clamp-3">
                      {part.preview}…
                    </p>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    loadPosts()
                    setFilter('draft')
                    setShowSeriesBuilder(false)
                  }}
                  className="flex-1 py-2 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
                >
                  Posts ansehen (Entwürfe) →
                </button>
                <button
                  onClick={() => {
                    setSeriesResult(null)
                    setSeriesTopic('')
                  }}
                  className="px-4 py-2 text-xs font-medium text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
                >
                  Neue Serie
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2 text-center text-[10px] text-ink-muted mb-2">
                <div className="p-2 bg-indigo-50 rounded-lg border border-indigo-100">
                  <div className="text-lg mb-0.5">1️⃣</div>
                  <div className="font-semibold text-indigo-800">Intro / Hook</div>
                  <div>Neugier wecken</div>
                </div>
                <div className="p-2 bg-indigo-50 rounded-lg border border-indigo-100">
                  <div className="text-lg mb-0.5">2️⃣</div>
                  <div className="font-semibold text-indigo-800">Deep Dive</div>
                  <div>Hauptinhalt</div>
                </div>
                <div className="p-2 bg-indigo-50 rounded-lg border border-indigo-100">
                  <div className="text-lg mb-0.5">3️⃣</div>
                  <div className="font-semibold text-indigo-800">Fazit / CTA</div>
                  <div>Handlungsaufruf</div>
                </div>
              </div>
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Serien-Thema *
                </label>
                <textarea
                  value={seriesTopic}
                  onChange={(e) => setSeriesTopic(e.target.value)}
                  placeholder="z.B. Wie ich meinen SHK-Betrieb mit KI digitalisiert habe — von 0 auf Autopilot"
                  className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  rows={2}
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Content-Säule (optional)
                </label>
                <select
                  value={seriesPillar}
                  onChange={(e) => setSeriesPillar(e.target.value)}
                  className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white"
                >
                  <option value="">Keine Säule</option>
                  {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                    <option key={k} value={k}>
                      {cfg.emoji} {cfg.label}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={async () => {
                  if (!seriesTopic.trim()) return
                  setSeriesLoading(true)
                  try {
                    const r = await createContentSeries({
                      topic: seriesTopic,
                      pillar: seriesPillar || null,
                    })
                    setSeriesResult(r)
                    loadPosts()
                  } catch (e) {
                    setError('Serie: ' + e.message)
                  }
                  setSeriesLoading(false)
                }}
                disabled={seriesLoading || !seriesTopic.trim()}
                className="w-full py-2.5 text-sm font-semibold text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {seriesLoading ? (
                  <>
                    <span className="animate-spin">⏳</span> Generiere 3 Posts...
                  </>
                ) : (
                  <>🔗 3-teilige Serie generieren</>
                )}
              </button>
              <p className="text-[10px] text-ink-muted text-center">
                ~15-30 Sekunden · 3 Entwürfe werden in Posts gespeichert
              </p>
            </div>
          )}
        </div>
      )}

      {/* Quick-Create AI Panel */}
      {showQuickCreate && (
        <div className="mb-6 p-5 bg-white border-2 border-rose-200 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-ink flex items-center gap-2">
              ✏️ AI Post Generator
            </h2>
            <button
              onClick={() => {
                setShowQuickCreate(false)
                setQcResult(null)
              }}
              className="text-ink-muted hover:text-ink-light text-lg"
            >
              ×
            </button>
          </div>

          {/* Tabs */}
          {!qcResult && (
            <div className="flex gap-1 mb-4 bg-surface-bg rounded-lg p-1">
              <button
                onClick={() => setQcTab('topic')}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${qcTab === 'topic' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}`}
              >
                📝 Thema eingeben
              </button>
              <button
                onClick={() => setQcTab('url')}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${qcTab === 'url' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}`}
              >
                🔗 URL einfügen
              </button>
              <button
                onClick={() => setQcTab('direct')}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${qcTab === 'direct' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}`}
              >
                ✍️ Direkt schreiben
              </button>
            </div>
          )}

          {qcResult ? (
            <div className="space-y-3">
              <div className="p-4 bg-surface-bg rounded-xl border border-surface-border">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-status-neu-bg text-status-neu-text">
                    Entwurf
                  </span>
                  <span className="text-[11px] text-ink-muted">{qcResult.char_count} Zeichen</span>
                  {qcResult.source_title && (
                    <span
                      className="text-[11px] text-ink-muted truncate max-w-[200px]"
                      title={qcResult.source_url}
                    >
                      🔗 {qcResult.source_title}
                    </span>
                  )}
                  {qcResult.pillar && PILLAR_CONFIG[qcResult.pillar] && (
                    <span
                      className={`px-1.5 py-0 rounded border text-[9px] font-medium ${PILLAR_CONFIG[qcResult.pillar].color}`}
                    >
                      {PILLAR_CONFIG[qcResult.pillar].emoji} {PILLAR_CONFIG[qcResult.pillar].label}
                    </span>
                  )}
                </div>
                <p className="text-sm text-ink leading-relaxed whitespace-pre-line line-clamp-6">
                  {qcResult.content_text}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSelectedId(qcResult.id)
                    setShowQuickCreate(false)
                    loadPosts()
                  }}
                  className="flex-1 py-2 text-xs font-semibold text-white bg-primary-700 rounded-lg hover:bg-primary-800"
                >
                  Post öffnen &amp; bearbeiten →
                </button>
                <button
                  onClick={() => {
                    setQcResult(null)
                    setQcTopic('')
                    setQcUrl('')
                  }}
                  className="px-4 py-2 text-xs font-medium text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
                >
                  Neuer Post
                </button>
              </div>
            </div>
          ) : qcTab === 'url' ? (
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Artikel- oder Video-URL *
                </label>
                <input
                  type="url"
                  value={qcUrl}
                  onChange={(e) => setQcUrl(e.target.value)}
                  placeholder="https://www.computerwoche.de/artikel/..."
                  className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-400"
                />
                <p className="text-[10px] text-ink-muted mt-1">
                  Artikel, Blog-Post, YouTube-Video — der Inhalt wird automatisch extrahiert
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                    Post-Stil
                  </label>
                  <select
                    value={qcAngle}
                    onChange={(e) => setQcAngle(e.target.value)}
                    className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-rose-400 bg-white"
                  >
                    {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                      <option key={k} value={k}>
                        {cfg.emoji} {cfg.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                    Content-Säule (optional)
                  </label>
                  <select
                    value={qcPillar}
                    onChange={(e) => setQcPillar(e.target.value)}
                    className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-rose-400 bg-white"
                  >
                    <option value="">Keine Säule</option>
                    {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                      <option key={k} value={k}>
                        {cfg.emoji} {cfg.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!qcUrl.trim()) return
                  setQcLoading(true)
                  try {
                    const r = await postFromUrl({
                      url: qcUrl,
                      angle: qcAngle,
                      pillar: qcPillar || null,
                      style_notes: qcStyleNotes || null,
                    })
                    setQcResult(r)
                    loadPosts()
                  } catch (e) {
                    setError('URL-Post: ' + e.message)
                  }
                  setQcLoading(false)
                }}
                disabled={qcLoading || !qcUrl.trim()}
                className="w-full py-2.5 text-sm font-semibold text-white bg-rose-600 rounded-xl hover:bg-rose-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {qcLoading ? (
                  <>
                    <span className="animate-spin">⏳</span> Analysiere URL...
                  </>
                ) : (
                  <>🔗 Post aus URL generieren</>
                )}
              </button>
            </div>
          ) : qcTab === 'direct' && !directResult ? (
            <div className="space-y-3">
              <div className="p-2.5 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-xs text-status-fertig-text">
                <strong>Kein KI-Budget nötig</strong> — schreibe deinen Post direkt, er wird als
                Entwurf gespeichert und kann im Qualitäts-Check bewertet und freigegeben werden.
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[11px] font-medium text-ink-muted">Post-Text *</label>
                  <span
                    className={`text-[10px] font-mono ${directText.length > 3000 ? 'text-status-fehler-text font-bold' : directText.length > 2500 ? 'text-status-aktiv-text' : 'text-ink-muted'}`}
                  >
                    {directText.length} / 3000 Zeichen
                  </span>
                </div>
                <FormatToolbar
                  textareaRef={directRef}
                  value={directText}
                  onChange={setDirectText}
                />
                <textarea
                  ref={directRef}
                  value={directText}
                  onChange={(e) => setDirectText(e.target.value)}
                  placeholder={
                    'Schreibe deinen LinkedIn-Post hier…\n\nTipp: Beginne mit einem starken Hook (erste Zeile), dann 3-5 Punkte, abschließend eine Frage oder Call-to-Action.'
                  }
                  className="w-full px-3 py-2.5 text-sm border border-surface-border rounded-b-lg resize-none focus:outline-none focus:ring-2 focus:ring-status-fertig-border font-mono leading-relaxed"
                  rows={10}
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Content-Säule (optional)
                </label>
                <select
                  value={directPillar}
                  onChange={(e) => setDirectPillar(e.target.value)}
                  className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-status-fertig-border bg-white"
                >
                  <option value="">Keine Säule</option>
                  {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                    <option key={k} value={k}>
                      {cfg.emoji} {cfg.label}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={async () => {
                  if (!directText.trim() || directText.trim().length < 50) {
                    setError('Post muss mindestens 50 Zeichen lang sein.')
                    return
                  }
                  setDirectSaving(true)
                  try {
                    const r = await saveDirectPost({
                      content_text: directText.trim(),
                      pillar: directPillar || null,
                      angle: 'manual',
                    })
                    setDirectResult(r)
                    loadPosts()
                  } catch (e) {
                    setError('Speichern fehlgeschlagen: ' + e.message)
                  }
                  setDirectSaving(false)
                }}
                disabled={directSaving || directText.trim().length < 50}
                className="w-full py-2.5 text-sm font-semibold text-white bg-status-fertig-text rounded-xl hover:opacity-90 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {directSaving ? (
                  <>
                    <span className="animate-spin">⏳</span> Speichere...
                  </>
                ) : (
                  <>💾 Als Entwurf speichern</>
                )}
              </button>
              {directText.trim().length > 0 && directText.trim().length < 50 && (
                <p className="text-[10px] text-status-fehler-text">
                  Mindestens 50 Zeichen erforderlich ({directText.trim().length}/50)
                </p>
              )}
            </div>
          ) : qcTab === 'direct' && directResult ? (
            <div className="space-y-3">
              <div className="p-4 bg-status-fertig-bg rounded-xl border border-status-fertig-border">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-status-fertig-text font-semibold text-sm">
                    ✓ Post gespeichert!
                  </span>
                  <span className="text-[11px] text-ink-muted">
                    {directResult.char_count} Zeichen
                  </span>
                </div>
                <p className="text-xs text-status-fertig-text leading-relaxed whitespace-pre-line line-clamp-4">
                  {directResult.content_text}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSelectedId(directResult.id)
                    setShowQuickCreate(false)
                  }}
                  className="flex-1 py-2 text-xs font-semibold text-white bg-primary-700 rounded-lg hover:bg-primary-800"
                >
                  Post öffnen &amp; prüfen →
                </button>
                <button
                  onClick={() => {
                    setDirectResult(null)
                    setDirectText('')
                    setDirectPillar('')
                  }}
                  className="px-4 py-2 text-xs font-medium text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
                >
                  Neuer Post
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Thema / Topic *
                </label>
                <textarea
                  value={qcTopic}
                  onChange={(e) => setQcTopic(e.target.value)}
                  placeholder="z.B. KI verändert den Handwerksmarkt — was SHK-Betriebe jetzt wissen müssen"
                  className="w-full px-3 py-2 text-sm border border-surface-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-rose-400"
                  rows={2}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                    Post-Stil
                  </label>
                  <select
                    value={qcAngle}
                    onChange={(e) => setQcAngle(e.target.value)}
                    className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-rose-400 bg-white"
                  >
                    {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                      <option key={k} value={k}>
                        {cfg.emoji} {cfg.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                    Content-Säule (optional)
                  </label>
                  <select
                    value={qcPillar}
                    onChange={(e) => setQcPillar(e.target.value)}
                    className="w-full text-xs border border-surface-border rounded-lg px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-rose-400 bg-white"
                  >
                    <option value="">Keine Säule</option>
                    {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                      <option key={k} value={k}>
                        {cfg.emoji} {cfg.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[11px] font-medium text-ink-muted mb-1 block">
                  Stil-Hinweis (optional)
                </label>
                <input
                  type="text"
                  value={qcStyleNotes}
                  onChange={(e) => setQcStyleNotes(e.target.value)}
                  placeholder="z.B. Aus Unternehmerperspektive, eher persönlich, kein Fachjargon"
                  className="w-full px-3 py-2 text-xs border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-400"
                />
              </div>
              <button
                onClick={async () => {
                  if (!qcTopic.trim()) return
                  setQcLoading(true)
                  try {
                    const r = await quickCreatePost({
                      topic: qcTopic,
                      angle: qcAngle,
                      pillar: qcPillar || null,
                      style_notes: qcStyleNotes || null,
                    })
                    setQcResult(r)
                    loadPosts()
                  } catch (e) {
                    setError('Quick-Create: ' + e.message)
                  }
                  setQcLoading(false)
                }}
                disabled={qcLoading || !qcTopic.trim()}
                className="w-full py-2.5 text-sm font-semibold text-white bg-rose-600 rounded-xl hover:bg-rose-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {qcLoading ? (
                  <>
                    <span className="animate-spin">⏳</span> Generiere Post...
                  </>
                ) : (
                  <>✨ LinkedIn-Post generieren</>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-status-fehler-bg text-status-fehler-text rounded-lg text-sm">
          {error}
        </div>
      )}

      {autoScheduleResult && (
        <div
          className={`mb-4 p-3 rounded-xl text-sm flex items-start gap-3 ${autoScheduleResult.ok ? 'bg-status-fertig-bg border border-status-fertig-border' : 'bg-status-fehler-bg border border-status-fehler-border'}`}
        >
          <span className="text-lg shrink-0">{autoScheduleResult.ok ? '📅' : '⚠️'}</span>
          <div className="flex-1">
            <p
              className={`font-semibold ${autoScheduleResult.ok ? 'text-status-fertig-text' : 'text-status-fehler-text'}`}
            >
              {autoScheduleResult.msg}
            </p>
            {autoScheduleResult.ok && autoScheduleResult.first && (
              <p className="text-xs text-status-fertig-text mt-0.5">
                Erster Post:{' '}
                {new Date(autoScheduleResult.first).toLocaleString('de-DE', {
                  weekday: 'short',
                  day: '2-digit',
                  month: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
                {autoScheduleResult.last &&
                  ` — Letzter: ${new Date(autoScheduleResult.last).toLocaleString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}`}
              </p>
            )}
          </div>
          <button
            onClick={() => setAutoScheduleResult(null)}
            className="text-xs text-ink-muted hover:text-ink-light shrink-0"
          >
            ×
          </button>
        </div>
      )}

      {/* Bulk selection bar */}
      {!selectedId && posts.filter((p) => p.status === 'draft').length > 0 && (
        <div className="mb-4 flex items-center gap-3 p-3 bg-status-aktiv-bg border border-status-aktiv-border rounded-xl">
          <button
            onClick={() => {
              const draftIds = posts.filter((p) => p.status === 'draft').map((p) => p.id)
              setSelected((prev) => (prev.size === draftIds.length ? new Set() : new Set(draftIds)))
            }}
            className="flex items-center gap-2 text-xs font-medium text-status-aktiv-text hover:opacity-80"
          >
            {selected.size === posts.filter((p) => p.status === 'draft').length ? (
              <CheckSquare className="w-4 h-4" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            Alle Entwürfe wählen ({posts.filter((p) => p.status === 'draft').length})
          </button>
          {selected.size > 0 && (
            <>
              <span className="text-xs text-status-aktiv-text">{selected.size} ausgewählt</span>
              <button
                onClick={async () => {
                  setBulkApproving(true)
                  try {
                    const r = await bulkApproveContent([...selected])
                    setBulkMsg(`✅ ${r.approved} Posts freigegeben!`)
                    setSelected(new Set())
                    await loadPosts()
                    setTimeout(() => setBulkMsg(null), 3000)
                  } catch (e) {
                    setBulkMsg('❌ ' + e.message)
                  }
                  setBulkApproving(false)
                }}
                disabled={bulkApproving || bulkRejecting}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-status-fertig-text rounded-lg hover:opacity-90 disabled:opacity-50"
              >
                <Check className="w-3.5 h-3.5" />
                {bulkApproving ? 'Freigeben...' : `${selected.size} freigeben`}
              </button>
              <button
                onClick={async () => {
                  if (
                    !window.confirm(
                      `${selected.size} Post${selected.size !== 1 ? 's' : ''} verwerfen?`
                    )
                  )
                    return
                  setBulkRejecting(true)
                  try {
                    const r = await bulkRejectContent([...selected])
                    setBulkMsg(`🗑 ${r.rejected} Posts verworfen`)
                    setSelected(new Set())
                    await loadPosts()
                    setTimeout(() => setBulkMsg(null), 3000)
                  } catch (e) {
                    setBulkMsg('❌ ' + e.message)
                  }
                  setBulkRejecting(false)
                }}
                disabled={bulkApproving || bulkRejecting}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-status-fehler-text rounded-lg hover:opacity-90 disabled:opacity-50"
              >
                <X className="w-3.5 h-3.5" />
                {bulkRejecting ? 'Verwerfen...' : `${selected.size} verwerfen`}
              </button>
              {/* Bulk Publish — only shown if any selected post is draft/approved */}
              {[...selected].some((id) => {
                const p = posts.find((x) => x.id === id)
                return p && (p.status === 'draft' || p.status === 'approved')
              }) && (
                <button
                  onClick={async () => {
                    const publishIds = [...selected].filter((id) => {
                      const p = posts.find((x) => x.id === id)
                      return p && (p.status === 'draft' || p.status === 'approved')
                    })
                    if (
                      !window.confirm(
                        `${publishIds.length} Post${publishIds.length !== 1 ? 's' : ''} als veröffentlicht markieren?`
                      )
                    )
                      return
                    setBulkPublishing(true)
                    try {
                      const r = await bulkPublishContent(publishIds)
                      setBulkMsg(`✓ ${r.published} Posts als veröffentlicht markiert`)
                      setSelected(new Set())
                      await loadPosts()
                      setTimeout(() => setBulkMsg(null), 3000)
                    } catch (e) {
                      setBulkMsg('❌ ' + e.message)
                    }
                    setBulkPublishing(false)
                  }}
                  disabled={bulkPublishing || bulkApproving || bulkRejecting}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-status-neu-text bg-status-neu-bg border border-status-neu-border rounded-lg hover:opacity-90 disabled:opacity-50"
                >
                  {bulkPublishing
                    ? 'Markiere...'
                    : `✓ ${
                        [...selected].filter((id) => {
                          const p = posts.find((x) => x.id === id)
                          return p && (p.status === 'draft' || p.status === 'approved')
                        }).length
                      } veröffentlicht`}
                </button>
              )}
              {/* Bulk Pillar Assign */}
              <select
                defaultValue=""
                disabled={bulkPillarAssigning}
                onChange={async (e) => {
                  const pillar = e.target.value
                  if (!pillar) return
                  e.target.value = ''
                  setBulkPillarAssigning(true)
                  try {
                    await Promise.all([...selected].map((id) => updateContentPillar(id, pillar)))
                    setBulkMsg(
                      `🏷 ${selected.size} Posts → ${PILLAR_CONFIG[pillar]?.emoji} ${PILLAR_CONFIG[pillar]?.label}`
                    )
                    await loadPosts()
                    setTimeout(() => setBulkMsg(null), 3000)
                  } catch (e) {
                    setBulkMsg('❌ ' + e.message)
                  }
                  setBulkPillarAssigning(false)
                }}
                className="px-2.5 py-1.5 text-xs border border-surface-border rounded-lg bg-white text-ink-muted disabled:opacity-50 cursor-pointer"
              >
                <option value="">{bulkPillarAssigning ? 'Zuweise...' : '🏷 Säule zuweisen'}</option>
                {Object.entries(PILLAR_CONFIG).map(([k, cfg]) => (
                  <option key={k} value={k}>
                    {cfg.emoji} {cfg.label}
                  </option>
                ))}
              </select>
              {/* Bulk Restore (only shown when any rejected post is selected) */}
              {[...selected].some(
                (id) => posts.find((p) => p.id === id)?.status === 'rejected'
              ) && (
                <button
                  onClick={async () => {
                    const rejectedIds = [...selected].filter(
                      (id) => posts.find((p) => p.id === id)?.status === 'rejected'
                    )
                    setBulkPillarAssigning(true)
                    try {
                      await Promise.all(
                        rejectedIds.map((id) => updateContent(id, { status: 'draft' }))
                      )
                      setBulkMsg(`♻️ ${rejectedIds.length} Posts wiederhergestellt`)
                      setSelected(new Set())
                      await loadPosts()
                      setTimeout(() => setBulkMsg(null), 3000)
                    } catch (e) {
                      setBulkMsg('❌ ' + e.message)
                    }
                    setBulkPillarAssigning(false)
                  }}
                  disabled={bulkPillarAssigning}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-status-aktiv-text bg-status-aktiv-bg border border-status-aktiv-border rounded-lg hover:opacity-90 disabled:opacity-50"
                >
                  ♻️{' '}
                  {
                    [...selected].filter(
                      (id) => posts.find((p) => p.id === id)?.status === 'rejected'
                    ).length
                  }{' '}
                  wiederherstellen
                </button>
              )}
              <button
                onClick={() => setSelected(new Set())}
                className="text-xs text-status-aktiv-text hover:opacity-80"
              >
                Abwählen
              </button>
            </>
          )}
          {bulkMsg && (
            <span
              className={`text-xs font-medium ml-auto ${bulkMsg.startsWith('🗑') ? 'text-status-fehler-text' : bulkMsg.startsWith('♻️') ? 'text-status-aktiv-text' : bulkMsg.startsWith('✅') ? 'text-status-fertig-text' : 'text-status-fehler-text'}`}
            >
              {bulkMsg}
            </span>
          )}
        </div>
      )}

      {/* Best-Time-to-Post Panel — teal == primary (1:1 identisch), primary-Palette */}
      {showBestTimes && bestTimesData && (
        <div className="mb-6 bg-primary-50 rounded-xl border border-primary-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-primary-900">
              ⏰ Beste Posting-Zeiten (LinkedIn DACH, B2B)
            </h3>
            <button
              onClick={() => setShowBestTimes(false)}
              className="text-primary-400 hover:text-primary-700 text-lg"
            >
              ×
            </button>
          </div>
          <p className="text-xs text-primary-700 mb-4 italic">{bestTimesData.tip}</p>
          {/* Recommendations */}
          <div className="mb-4">
            <span className="text-xs font-semibold text-primary-700 uppercase tracking-wide">
              Empfehlungen nach Wochentag
            </span>
            <div className="mt-2 space-y-2">
              {bestTimesData.recommendations.map((r) => (
                <div key={r.day} className="flex items-center gap-3 text-sm">
                  <span className="w-24 font-medium text-primary-900">{r.day_name}</span>
                  <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map((s) => (
                      <span
                        key={s}
                        className={`w-3 h-3 rounded-full ${s <= r.score ? 'bg-primary-500' : 'bg-primary-100'}`}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-primary-700">
                    {r.hours.map((h) => `${h}:00`).join(', ')} Uhr
                  </span>
                  <span className="text-xs text-primary-500 italic">{r.note}</span>
                </div>
              ))}
            </div>
          </div>
          {/* Next optimal slots */}
          {bestTimesData.next_slots && bestTimesData.next_slots.length > 0 && (
            <div>
              <span className="text-xs font-semibold text-primary-700 uppercase tracking-wide">
                Nächste optimale Slots
              </span>
              <div className="mt-2 flex flex-wrap gap-2">
                {bestTimesData.next_slots.map((slot, i) => {
                  const d = new Date(slot.datetime)
                  const label =
                    d.toLocaleDateString('de-DE', {
                      weekday: 'short',
                      day: '2-digit',
                      month: '2-digit',
                    }) +
                    ' ' +
                    d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) +
                    ' Uhr'
                  return (
                    <span
                      key={i}
                      className={`px-2.5 py-1 rounded-full text-xs border ${slot.score >= 4 ? 'bg-primary-600 text-white border-primary-600' : 'bg-white text-primary-700 border-primary-300'}`}
                    >
                      {label} {slot.score >= 5 ? '★' : slot.score >= 4 ? '◆' : ''}
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Hook-Bibliothek Panel — amber == accent (1:1 identisch), accent-Palette */}
      {showHooks && hookData && (
        <div className="mb-6 bg-accent-50 rounded-xl border border-accent-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-accent-900 flex items-center gap-2">
              ✍️ Hook-Bibliothek
            </h3>
            <div className="flex items-center gap-2">
              <select
                value={hookAngle}
                onChange={async (e) => {
                  setHookAngle(e.target.value)
                  const d = await getHookLibrary(e.target.value || undefined)
                  setHookData(d)
                }}
                className="text-xs border border-accent-200 rounded-lg px-2 py-1 bg-white"
              >
                <option value="">Alle Typen</option>
                {['meinung', 'howto', 'story', 'kontroverse', 'statistik', 'trend'].map((a) => (
                  <option key={a} value={a}>
                    {a.charAt(0).toUpperCase() + a.slice(1)}
                  </option>
                ))}
              </select>
              <button
                onClick={() => setShowHooks(false)}
                className="text-accent-400 hover:text-accent-700 text-lg"
              >
                ×
              </button>
            </div>
          </div>
          <div className="space-y-3">
            {Object.entries(
              hookAngle && hookData.hooks ? { [hookAngle]: hookData.hooks } : hookData.hooks || {}
            ).map(([angle, hooks]) => (
              <div key={angle}>
                <span className="text-xs font-semibold text-accent-700 uppercase tracking-wide">
                  {angle}
                </span>
                <div className="mt-1.5 space-y-1.5">
                  {hooks.map((hook, i) => (
                    <div key={i} className="flex items-start gap-2 group">
                      <span className="text-sm text-accent-900 flex-1 leading-relaxed italic">
                        "{hook}"
                      </span>
                      <button
                        onClick={() => navigator.clipboard.writeText(hook)}
                        title="Kopieren"
                        className="opacity-0 group-hover:opacity-100 text-xs text-accent-500 hover:text-accent-700 px-2 py-0.5 border border-accent-300 rounded flex-shrink-0"
                      >
                        Kopieren
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedId ? (
        (() => {
          const ids = filteredPosts.map((p) => p.id)
          const idx = ids.indexOf(selectedId)
          return (
            <PostDetailErrorBoundary onClose={() => setSelectedId(null)}>
              <PostDetail
                postId={selectedId}
                onClose={() => setSelectedId(null)}
                onRefresh={loadPosts}
                prevId={idx > 0 ? ids[idx - 1] : null}
                nextId={idx < ids.length - 1 ? ids[idx + 1] : null}
                position={idx >= 0 ? idx + 1 : null}
                total={ids.length}
                onNavigate={setSelectedId}
              />
            </PostDetailErrorBoundary>
          )
        })()
      ) : loading ? (
        <div className="text-center py-12 text-ink-muted">Lade Posts...</div>
      ) : filteredPosts.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 text-surface-border mx-auto mb-3" />
          {posts.length === 0 ? (
            <>
              <p className="text-sm text-ink-light">Noch keine Posts vorhanden.</p>
              <p className="text-xs text-ink-muted mt-1">
                Beantworte Fragen zu einer Idee, um Posts zu generieren.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm text-ink-light">Keine Posts für diese Suche gefunden.</p>
              <button
                onClick={() => {
                  setSearch('')
                  setAngleFilter('')
                }}
                className="mt-2 text-xs text-primary-600 hover:underline"
              >
                Filter zurücksetzen
              </button>
            </>
          )}
        </div>
      ) : (
        <>
          {triageMode ? (
            <>
              {/* violet bewusst behalten: passend zum Triage-Modus-Button oben */}
              <div className="mb-3 flex items-center gap-3 p-3 bg-violet-50 border border-violet-200 rounded-xl">
                <Zap className="w-4 h-4 text-violet-600 shrink-0" />
                <span className="text-xs text-violet-800 font-medium">
                  Triage-Modus — {filteredPosts.filter((p) => p.status === 'draft').length} Entwürfe
                </span>
                <span className="text-xs text-violet-600 ml-2">
                  ✓ {triageApprove.size} freigeben · ✗ {triageReject.size} verwerfen
                </span>
                {triageMsg && (
                  <span className="text-xs font-semibold text-violet-900 ml-auto">{triageMsg}</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 pb-20">
                {filteredPosts
                  .filter((p) => p.status === 'draft')
                  .map((post) => (
                    <TriageCard
                      key={post.id}
                      post={post}
                      approveSet={triageApprove}
                      rejectSet={triageReject}
                      onApprove={(id) => triageToggle(id, 'approve')}
                      onReject={(id) => triageToggle(id, 'reject')}
                    />
                  ))}
              </div>
            </>
          ) : (
            <>
              {showDupeOnly && (
                <div className="mb-4 p-3 bg-status-aktiv-bg border border-status-aktiv-border rounded-xl text-xs text-status-aktiv-text flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>
                    <strong>{dupeCount} Posts</strong> haben ähnlichen Inhalt (≥55%
                    Wort-Überlappung). Prüfe ob Varianten oder echte Duplikate — ggf. einen löschen
                    oder abweisen.
                  </span>
                  <button
                    onClick={() => setShowDupeOnly(false)}
                    className="ml-auto text-status-aktiv-text hover:opacity-80"
                  >
                    ×
                  </button>
                </div>
              )}
              <div className="grid gap-3 md:grid-cols-2">
                {filteredPosts
                  .filter((p) => !showDupeOnly || dupeMap.has(p.id))
                  .map((post) => (
                    <PostCard
                      key={post.id}
                      post={post}
                      onSelect={setSelectedId}
                      isSelected={selected.has(post.id)}
                      isFocused={selectedId === post.id}
                      dupeSim={dupeMap.get(post.id)}
                      searchTerm={search.trim()}
                      onToggleSelect={(id) =>
                        setSelected((prev) => {
                          const next = new Set(prev)
                          next.has(id) ? next.delete(id) : next.add(id)
                          return next
                        })
                      }
                    />
                  ))}
              </div>
            </>
          )}
        </>
      )}

      {/* Triage sticky bottom bar — violet bewusst behalten: passend zum
          Triage-Modus-Button oben (siehe Kommentar dort) */}
      {triageMode && (triageApprove.size > 0 || triageReject.size > 0) && (
        <div className="fixed bottom-0 left-64 right-0 bg-white border-t-2 border-violet-200 shadow-xl px-6 py-3 z-40 flex items-center gap-4">
          <span className="text-sm font-semibold text-violet-800">
            {triageApprove.size + triageReject.size} markiert
          </span>
          {triageApprove.size > 0 && (
            <span className="text-xs text-status-fertig-text">✓ {triageApprove.size} freigeben</span>
          )}
          {triageReject.size > 0 && (
            <span className="text-xs text-status-fehler-text">✗ {triageReject.size} verwerfen</span>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={() => {
                setTriageApprove(new Set())
                setTriageReject(new Set())
              }}
              className="px-3 py-1.5 text-xs text-ink-light border border-surface-border rounded-lg hover:bg-surface-bg"
            >
              Abwählen
            </button>
            <button
              onClick={executeTriage}
              disabled={triageExecuting}
              className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-violet-700 rounded-lg hover:bg-violet-800 disabled:opacity-50"
            >
              <Zap className="w-3.5 h-3.5" />
              {triageExecuting ? 'Wird ausgeführt...' : 'Jetzt ausführen'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
