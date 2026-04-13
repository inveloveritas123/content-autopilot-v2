import { useState, useEffect, useCallback } from 'react'
import { Fingerprint, RefreshCw, TrendingUp, AlertCircle, Mic, BookOpen, RotateCcw, Save, Check, X, Wand2, FlaskConical, Loader2 } from 'lucide-react'
import { getVoiceProfile, getFeedbackStats, updateVoiceProfile, getVoiceProfilesList, runVoiceCompare } from '../api'

const VOICE_DIMENSIONS = [
  { key: 'directness', label: 'Direktheit', desc: 'Klartext statt Drumherumreden', low: 'Diplomatisch', high: 'Klartext' },
  { key: 'competence', label: 'Kompetenz', desc: 'Fachlich fundiert, ohne Belehrung', low: 'Allgemein', high: 'Expertenlevel' },
  { key: 'warmth', label: 'Warmherzigkeit', desc: 'Menschlich, nahbar, auf Augenhoehe', low: 'Sachlich', high: 'Herzlich' },
  { key: 'pragmatism', label: 'Pragmatismus', desc: 'Loesungen statt Theorie', low: 'Theoretisch', high: 'Hands-on' },
  { key: 'confidence', label: 'Selbstbewusstsein', desc: 'Klare Haltung, ohne Arroganz', low: 'Zurueckhaltend', high: 'Selbstsicher' },
  { key: 'humor', label: 'Humor', desc: 'Eine Prise, nie albern', low: 'Ernst', high: 'Humorvoll' },
  { key: 'storytelling', label: 'Storytelling', desc: 'Echte Geschichten, keine Floskeln', low: 'Faktenbasiert', high: 'Geschichtenerzaehler' },
  { key: 'formality', label: 'Formalitaet', desc: 'du-Form, professionell aber locker', low: 'Locker/du', high: 'Formell/Sie' },
  { key: 'emotion', label: 'Emotion', desc: 'Leidenschaft zeigen, nicht aufsetzen', low: 'Nuechtern', high: 'Leidenschaftlich' },
  { key: 'technical_depth', label: 'Fachtiefe', desc: 'Praxis-Wissen, keine Buzzwords', low: 'Einfach', high: 'Technisch tief' },
  { key: 'call_to_action', label: 'CTA-Stil', desc: 'Klar, direkt, ohne Druck', low: 'Subtil', high: 'Direkt' },
  { key: 'authenticity', label: 'Authentizitaet', desc: 'Echt bleiben, nie kuenstlich', low: 'Poliert', high: 'Roh & echt' },
]

function DimensionSlider({ dim, value, defaultValue, onChange, onReset }) {
  const val = value ?? 5
  const isCustom = defaultValue !== undefined && Math.abs(val - defaultValue) > 0.1
  return (
    <div className="group">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink">{dim.label}</span>
          {isCustom && (
            <button onClick={onReset} className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-gray-100" title="Zuruecksetzen">
              <RotateCcw className="w-3 h-3 text-ink-muted" />
            </button>
          )}
        </div>
        <span className={`text-xs font-medium ${isCustom ? 'text-accent-600' : 'text-primary-700'}`}>{val.toFixed(1)}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-[10px] text-ink-muted w-20 text-right shrink-0">{dim.low}</span>
        <div className="flex-1 relative">
          <input
            type="range" min="0" max="10" step="0.5" value={val}
            onChange={e => onChange(parseFloat(e.target.value))}
            className="w-full h-2 rounded-full appearance-none cursor-pointer accent-primary-600
              [&::-webkit-slider-runnable-track]:bg-gradient-to-r [&::-webkit-slider-runnable-track]:from-gray-200 [&::-webkit-slider-runnable-track]:to-primary-200 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:h-2
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary-600 [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:-mt-1
              [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary-600 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white
              [&::-moz-range-track]:bg-gradient-to-r [&::-moz-range-track]:from-gray-200 [&::-moz-range-track]:to-primary-200 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:h-2"
          />
        </div>
        <span className="text-[10px] text-ink-muted w-24 shrink-0">{dim.high}</span>
      </div>
      <p className="text-[10px] text-ink-muted mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">{dim.desc}</p>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color = 'text-primary-600' }) {
  return (
    <div className="bg-white rounded-xl border border-surface-border p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color === 'text-primary-600' ? 'bg-primary-50' : color === 'text-emerald-600' ? 'bg-emerald-50' : 'bg-amber-50'}`}>
          <Icon className={`w-5 h-5 ${color}`} />
        </div>
        <div>
          <p className="text-lg font-bold text-ink">{value}</p>
          <p className="text-xs text-ink-muted">{label}</p>
        </div>
      </div>
      {sub && <p className="text-xs text-ink-light mt-2 pl-[52px]">{sub}</p>}
    </div>
  )
}

// Wizard: Maps step choices to voice dimension presets
const WIZARD_PRESETS = {
  style: {
    direkt:      { directness: 8.5, warmth: 4, humor: 3, formality: 5, confidence: 7.5 },
    herzlich:    { directness: 5, warmth: 9, humor: 5.5, formality: 3, emotion: 7.5, authenticity: 8 },
    humorvoll:   { directness: 6, warmth: 7.5, humor: 9, formality: 2, authenticity: 8.5, emotion: 6 },
    fachlich:    { directness: 7, competence: 9.5, technical_depth: 8.5, humor: 2, confidence: 8 },
  },
  goal: {
    expertise:   { competence: 9, technical_depth: 8, confidence: 7.5, call_to_action: 5, storytelling: 5 },
    kunden:      { call_to_action: 8.5, pragmatism: 8.5, confidence: 7, directness: 7.5 },
    netzwerk:    { warmth: 7.5, storytelling: 8, authenticity: 8.5, emotion: 6 },
    community:   { humor: 6.5, warmth: 8.5, emotion: 7.5, authenticity: 9, storytelling: 7 },
  },
}

function applyWizardChoices(style, goal, formality) {
  const dims = {}
  const stylePre = WIZARD_PRESETS.style[style] || {}
  const goalPre = WIZARD_PRESETS.goal[goal] || {}
  const allKeys = [...new Set([...Object.keys(stylePre), ...Object.keys(goalPre), 'formality', 'pragmatism', 'authenticity'])]
  allKeys.forEach(k => {
    const vals = [stylePre[k], goalPre[k]].filter(v => v !== undefined)
    dims[k] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 5
  })
  dims.formality = formality
  return dims
}

function WizardModal({ onClose, onApply }) {
  const [step, setStep] = useState(1)
  const [style, setStyle] = useState(null)
  const [goal, setGoal] = useState(null)
  const [formality, setFormality] = useState(4)

  const styleOptions = [
    { key: 'direkt', emoji: '🎯', label: 'Direkt & klar', desc: 'Klartext, keine Floskeln, klare Haltung' },
    { key: 'herzlich', emoji: '🤝', label: 'Herzlich & nah', desc: 'Menschlich, empathisch, persönliche Verbindung' },
    { key: 'humorvoll', emoji: '😄', label: 'Locker & humorvoll', desc: 'Leicht, unterhaltsam, authentisch' },
    { key: 'fachlich', emoji: '🔬', label: 'Fachlich & tief', desc: 'Expertise, fundiert, technisch präzise' },
  ]
  const goalOptions = [
    { key: 'expertise', emoji: '🏆', label: 'Expertise zeigen', desc: 'Als Fachexperte wahrgenommen werden' },
    { key: 'kunden', emoji: '💼', label: 'Kunden gewinnen', desc: 'Leads generieren, Dienstleistungen verkaufen' },
    { key: 'netzwerk', emoji: '🌐', label: 'Netzwerk aufbauen', desc: 'Kontakte knüpfen, Community wachsen' },
    { key: 'community', emoji: '💬', label: 'Community aktivieren', desc: 'Engagement, Kommentare, echte Diskussionen' },
  ]

  function handleApply() {
    const dims = applyWizardChoices(style, goal, formality)
    onApply(dims)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-ink">Stimm-Profil Schnell-Setup</h2>
            <p className="text-xs text-ink-muted mt-0.5">Schritt {step} von 3 — 3 Fragen, fertig in 60 Sekunden</p>
          </div>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div className="h-1 bg-primary-600 transition-all" style={{ width: `${(step / 3) * 100}%` }} />
        </div>

        <div className="p-6">
          {step === 1 && (
            <div>
              <h3 className="font-semibold text-ink mb-1">Wie ist Ihr Kommunikationsstil?</h3>
              <p className="text-xs text-ink-muted mb-4">Wählen Sie den Stil der am besten zu Ihnen passt.</p>
              <div className="grid grid-cols-2 gap-3">
                {styleOptions.map(o => (
                  <button key={o.key} onClick={() => setStyle(o.key)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${style === o.key ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'}`}>
                    <span className="text-2xl block mb-2">{o.emoji}</span>
                    <span className="text-sm font-semibold text-ink block">{o.label}</span>
                    <span className="text-xs text-ink-muted">{o.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h3 className="font-semibold text-ink mb-1">Was ist Ihr Hauptziel auf LinkedIn?</h3>
              <p className="text-xs text-ink-muted mb-4">Beeinflusst den Call-to-Action Stil und die Tonalität.</p>
              <div className="grid grid-cols-2 gap-3">
                {goalOptions.map(o => (
                  <button key={o.key} onClick={() => setGoal(o.key)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${goal === o.key ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'}`}>
                    <span className="text-2xl block mb-2">{o.emoji}</span>
                    <span className="text-sm font-semibold text-ink block">{o.label}</span>
                    <span className="text-xs text-ink-muted">{o.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <h3 className="font-semibold text-ink mb-1">Wie formell schreiben Sie?</h3>
              <p className="text-xs text-ink-muted mb-6">Im deutschsprachigen B2B-Raum ist lockeres Du die Norm.</p>
              <div className="px-2">
                <input type="range" min="0" max="10" step="0.5" value={formality}
                  onChange={e => setFormality(parseFloat(e.target.value))}
                  className="w-full accent-primary-600" />
                <div className="flex justify-between mt-2">
                  <span className="text-xs text-ink-muted">Du-Form, locker</span>
                  <span className="text-sm font-bold text-primary-700">{formality.toFixed(1)}</span>
                  <span className="text-xs text-ink-muted">Sie-Form, formell</span>
                </div>
              </div>
              <div className="mt-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-xs font-semibold text-ink mb-2">Vorschau Ihrer Einstellungen:</p>
                <div className="flex flex-wrap gap-2">
                  {style && <span className="px-2 py-1 bg-primary-100 text-primary-700 rounded-full text-xs">{styleOptions.find(o=>o.key===style)?.label}</span>}
                  {goal && <span className="px-2 py-1 bg-primary-100 text-primary-700 rounded-full text-xs">{goalOptions.find(o=>o.key===goal)?.label}</span>}
                  <span className="px-2 py-1 bg-gray-200 text-gray-700 rounded-full text-xs">Formalität: {formality.toFixed(1)}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 pt-0 flex items-center justify-between">
          <button onClick={() => step > 1 ? setStep(step - 1) : onClose()}
            className="px-4 py-2 text-sm text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50">
            {step === 1 ? 'Abbrechen' : 'Zurück'}
          </button>
          {step < 3 ? (
            <button onClick={() => setStep(step + 1)} disabled={step === 1 ? !style : !goal}
              className="px-5 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40 disabled:cursor-not-allowed">
              Weiter →
            </button>
          ) : (
            <button onClick={handleApply}
              className="px-5 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700">
              Profil anwenden ✓
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function VoiceProfile() {
  const [profile, setProfile] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dimensions, setDimensions] = useState({})
  const [defaults, setDefaults] = useState({})
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [showWizard, setShowWizard] = useState(false)

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [p, s] = await Promise.all([getVoiceProfile(), getFeedbackStats()])
      setProfile(p)
      setStats(s)
      if (p?.dimensions) {
        setDimensions({ ...p.dimensions })
        setDefaults(p.defaults || {})
      }
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const handleChange = useCallback((key, value) => {
    setDimensions(prev => ({ ...prev, [key]: value }))
    setDirty(true)
    setSaved(false)
  }, [])

  const handleReset = useCallback((key) => {
    if (defaults[key] !== undefined) {
      setDimensions(prev => ({ ...prev, [key]: defaults[key] }))
      setDirty(true)
      setSaved(false)
    }
  }, [defaults])

  const handleResetAll = () => {
    setDimensions({ ...defaults })
    setDirty(true)
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateVoiceProfile(dimensions)
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError('Speichern fehlgeschlagen: ' + e.message)
    }
    setSaving(false)
  }

  const trendLabels = { improving: 'Wird besser', stable: 'Stabil', declining: 'Wird schlechter', no_data: 'Noch keine Daten' }

  if (loading) return <div className="text-center py-12 text-ink-muted">Lade Voice-Profil...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Voice-Profil</h1>
          <p className="text-sm text-ink-light mt-0.5">Dein Schreibstil in 12 Dimensionen. Schiebe die Regler oder lass die KI lernen.</p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <>
              <button onClick={handleResetAll} className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50">
                <RotateCcw className="w-3.5 h-3.5" /> Alle zuruecksetzen
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50">
                {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? 'Speichern...' : 'Speichern'}
              </button>
            </>
          )}
          {saved && (
            <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <Check className="w-3.5 h-3.5" /> Gespeichert
            </span>
          )}
          <button onClick={() => setShowWizard(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100">
            <Wand2 className="w-3.5 h-3.5" /> Schnell-Setup Wizard
          </button>
          <button onClick={loadData} className="p-2 text-ink-muted hover:text-primary-600 rounded-lg hover:bg-gray-50">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {showWizard && (
        <WizardModal
          onClose={() => setShowWizard(false)}
          onApply={wizardDims => {
            setDimensions(prev => ({ ...prev, ...wizardDims }))
            setDirty(true)
            setSaved(false)
          }}
        />
      )}

      {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>}

      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <StatCard icon={BookOpen} label="Posts insgesamt" value={stats.total_posts} color="text-primary-600" />
          <StatCard icon={TrendingUp} label="Avg. Engagement" value={stats.avg_engagement_rate ? `${stats.avg_engagement_rate}%` : '-'} color="text-emerald-600" />
          <StatCard icon={Mic} label="Lernfortschritt" value={trendLabels[stats.improvement_trend] || 'Unbekannt'}
            sub={stats.avg_edit_distance > 0 ? `Edit-Distanz: ${stats.avg_edit_distance}` : null} color="text-amber-600" />
        </div>
      )}

      <div className="bg-white rounded-xl border border-surface-border p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
              <Fingerprint className="w-4 h-4 text-primary-600" />
              Die 12 Voice-Dimensionen
            </h2>
            <p className="text-xs text-ink-muted mt-0.5">Schiebe die Regler um dein Profil anzupassen. Hover fuer Details.</p>
          </div>
        </div>

        {Object.keys(dimensions).length > 0 ? (
          <div className="space-y-5">
            {VOICE_DIMENSIONS.map(dim => (
              <DimensionSlider
                key={dim.key}
                dim={dim}
                value={dimensions[dim.key]}
                defaultValue={defaults[dim.key]}
                onChange={v => handleChange(dim.key, v)}
                onReset={() => handleReset(dim.key)}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <AlertCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-ink-light">Voice-Profil noch nicht erstellt.</p>
          </div>
        )}
      </div>

      {stats?.top_angles?.length > 0 && (
        <div className="mt-6 bg-white rounded-xl border border-surface-border p-6">
          <h2 className="text-sm font-semibold text-ink mb-4">Deine besten Angles</h2>
          <div className="space-y-3">
            {stats.top_angles.map((a, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-primary-50 text-primary-700 text-xs font-bold flex items-center justify-center">{i + 1}</span>
                  <span className="text-sm text-ink">{a.angle}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-ink-muted">{a.count} Posts</span>
                  <span className="text-xs font-medium text-emerald-600">{((a.avg_engagement ?? 0) * 100).toFixed(1)}% Engagement</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Voice Profile Testmatrix */}
      <VoiceTestmatrix />
    </div>
  )
}

// Demo posts proving profile A/B/C produce distinctly different output for same input topic
const DEMO_POSTS = [
  {
    profile: 'A · Eric (SHK-Handwerk)',
    industry: 'SHK-Handwerk',
    score: 82,
    post: `Fachkräftemangel im Handwerk? Ich kenn das Problem seit 10 Jahren.

Wir haben bei wirsind1991 drei Dinge geändert, die wirklich geholfen haben:

1️⃣ Azubis früh einbinden — nicht nur Kaffee kochen lassen
2️⃣ Faire Bezahlung, klare Perspektive
3️⃣ Echtes Teamgefühl, nicht nur Sprüche an der Wand

Der Markt ist leer. Aber wer in seine Leute investiert, findet welche.

Was macht ihr, um gute Leute zu halten? 👇`,
  },
  {
    profile: 'B · Max (Tech-Startup)',
    industry: 'SaaS / IT',
    score: 78,
    post: `The "talent shortage" narrative is broken — here's what the data shows 📊

We analyzed 400+ hiring pipelines across EU SaaS companies.

Key finding: 73% of "unfillable" roles were filled within 60 days after teams fixed their async communication + remote setup.

The real bottleneck isn't talent supply — it's retention architecture.

3 levers that actually move the needle:
→ Async-first culture (kills context-switching overhead)
→ Transparent comp bands (no negotiation theater)
→ Ownership from day 1 (not 6 months)

What's your #1 hiring bottleneck right now? 🔽`,
  },
  {
    profile: 'C · Dr. Fischer (Steuerberater)',
    industry: 'Steuerberatung',
    score: 75,
    post: `Fachkräftemangel: Was viele Unternehmer steuerlich übersehen.

Mitarbeiterbindung beginnt nicht beim Gehalt — sondern bei der steuerlichen Gestaltung.

Folgende Instrumente werden regelmäßig unterschätzt:

• Betriebliche Altersvorsorge (bAV) — steuerfrei bis 604 €/Monat
• Inflationsausgleichsprämie — 3.000 € steuer- und sozialabgabenfrei
• Sachbezüge bis 50 €/Monat — voll anrechenbar

Gute Mitarbeiter bleiben, wenn sie merken: Hier denkt jemand mit.

Haben Sie Ihre Vergütungsstruktur zuletzt geprüft?`,
  },
]

function VoiceTestmatrix() {
  const [profiles, setProfiles] = useState([])
  const [comparing, setComparing] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [showDemo, setShowDemo] = useState(false)

  useEffect(() => {
    getVoiceProfilesList()
      .then(d => setProfiles(d?.profiles || []))
      .catch(() => {})
  }, [])

  const handleCompare = async () => {
    setComparing(true)
    setResults(null)
    setError(null)
    setShowDemo(false)
    try {
      const data = await runVoiceCompare()
      if (data.status === 'budget_exceeded') {
        setError(data.error)
        setShowDemo(true)
      } else if (data.status === 'error') {
        setError(data.error)
      } else {
        setResults(data)
      }
    } catch (e) {
      setError(e.message)
    }
    setComparing(false)
  }

  const configuredProfiles = profiles.filter(p => p.configured)

  return (
    <div className="mt-6 pt-6 border-t border-gray-100">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-primary-600" />
            Testmatrix: Profile vergleichen
          </h3>
          <p className="text-xs text-ink-muted mt-0.5">Gleiche Quelle, {configuredProfiles.length} Profile — Posts werden direkt verglichen</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setShowDemo(d => !d); setResults(null); setError(null) }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-700 border border-primary-300 bg-primary-50 rounded-lg hover:bg-primary-100"
          >
            <FlaskConical className="w-3.5 h-3.5" />
            Demo-Vorschau
          </button>
          <button
            onClick={handleCompare}
            disabled={comparing || configuredProfiles.length < 2}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-50"
          >
            {comparing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
            {comparing ? 'Generiere...' : 'Live-Vergleich starten'}
          </button>
        </div>
      </div>

      {/* Profile list */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {configuredProfiles.slice(0, 3).map((p, i) => (
          <div key={p.id} className={`rounded-lg border p-2.5 text-xs ${p.is_current ? 'border-primary-300 bg-primary-50' : 'border-gray-200 bg-gray-50'}`}>
            <div className="font-semibold text-ink">{['A', 'B', 'C'][i]} · {p.entrepreneur_name}</div>
            <div className="text-ink-muted mt-0.5">{p.industry}</div>
            <div className="text-[10px] text-ink-light mt-1 line-clamp-2">{p.tone}</div>
          </div>
        ))}
      </div>

      {configuredProfiles.length < 2 && (
        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Mindestens 2 konfigurierte Profile nötig. Aktuell: {configuredProfiles.length}
        </p>
      )}

      {error && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">{error}</div>
      )}

      {/* Demo preview — same topic, 3 profiles */}
      {showDemo && !results && (
        <div className="space-y-3 mt-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-primary-700 bg-primary-50 border border-primary-200 rounded px-2 py-0.5">Demo-Vorschau</span>
            <span className="text-xs text-ink-muted">Thema: "Fachkräftemangel" — gleicher Input, 3 verschiedene Stimmen</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {DEMO_POSTS.map((r, i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-white p-3 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold text-ink">{r.profile}</div>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${r.score >= 80 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                    {r.score}/100
                  </span>
                </div>
                <div className="text-[10px] text-ink-muted mb-2">{r.industry}</div>
                <pre className="whitespace-pre-wrap text-ink leading-relaxed max-h-52 overflow-y-auto text-[10px] font-sans">{r.post}</pre>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-ink-light text-center">Beispiel-Output — Live-Generierung startet nach Budget-Aufladung</p>
        </div>
      )}

      {results && (
        <div className="space-y-3 mt-3">
          <p className="text-xs text-ink-muted">Item: <span className="font-medium text-ink">{results.item_title}</span></p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {results.results.map((r, i) => (
              <div key={i} className={`rounded-lg border p-3 text-xs ${r.status === 'ok' ? 'border-gray-200' : 'border-red-200 bg-red-50'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold text-ink">{['A', 'B', 'C'][i]} · {r.entrepreneur_name}</div>
                  {r.quality_score != null && (
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${r.quality_score >= 80 ? 'bg-emerald-100 text-emerald-700' : r.quality_score >= 60 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                      {r.quality_score.toFixed(0)}/100
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-ink-muted mb-2">{r.industry} · {r.latency_ms}ms</div>
                {r.error ? (
                  <p className="text-red-600">{r.error}</p>
                ) : (
                  <pre className="whitespace-pre-wrap text-ink leading-relaxed max-h-48 overflow-y-auto text-[10px] font-sans">{r.post_text}</pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
