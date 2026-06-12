import { useState, useEffect } from 'react'
import { useToast } from './ui/Toast'
import { request } from '../api'

function ColorSwatch({ color }) {
  return (
    <div
      className="w-6 h-6 rounded border border-gray-200 shrink-0"
      style={{ background: color }}
    />
  )
}

export default function BrandingSettings() {
  const { toast } = useToast()
  const [form, setForm] = useState({
    primary_color: '#0F766E',
    secondary_color: '#F59E0B',
    font_family: 'Helvetica',
    logo_url: '',
    watermark_text: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    request('/carousels/branding')
      .then((d) => {
        setForm((f) => ({ ...f, ...d }))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  async function handleSave() {
    setSaving(true)
    try {
      await request('/carousels/branding', { method: 'PUT', body: form })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      toast.error('Fehler beim Speichern: ' + (e?.detail || e?.message || 'Unbekannter Fehler'))
    }
    setSaving(false)
  }

  if (loading) return <div className="text-sm text-ink-muted py-4">Lade Branding...</div>

  return (
    <div className="max-w-lg space-y-5">
      <h2 className="text-lg font-bold text-ink">Carousel-Branding</h2>
      <p className="text-sm text-ink-muted">Farben und Schrift für deine LinkedIn-Carousels.</p>

      <div className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-ink-muted mb-1">Primärfarbe</label>
          <div className="flex items-center gap-2">
            <ColorSwatch color={form.primary_color} />
            <input
              type="text"
              value={form.primary_color}
              onChange={(e) => setForm((f) => ({ ...f, primary_color: e.target.value }))}
              placeholder="#0F766E"
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-400"
            />
            <input
              type="color"
              value={form.primary_color}
              onChange={(e) => setForm((f) => ({ ...f, primary_color: e.target.value }))}
              className="w-8 h-8 rounded cursor-pointer"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-muted mb-1">Akzentfarbe</label>
          <div className="flex items-center gap-2">
            <ColorSwatch color={form.secondary_color} />
            <input
              type="text"
              value={form.secondary_color}
              onChange={(e) => setForm((f) => ({ ...f, secondary_color: e.target.value }))}
              placeholder="#F59E0B"
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-400"
            />
            <input
              type="color"
              value={form.secondary_color}
              onChange={(e) => setForm((f) => ({ ...f, secondary_color: e.target.value }))}
              className="w-8 h-8 rounded cursor-pointer"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-muted mb-1">Schrift</label>
          <select
            value={form.font_family}
            onChange={(e) => setForm((f) => ({ ...f, font_family: e.target.value }))}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-400"
          >
            <option value="Helvetica">Helvetica (Standard)</option>
            <option value="Helvetica-Bold">Helvetica Bold</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-muted mb-1">
            Wasserzeichen-Text (optional)
          </label>
          <input
            type="text"
            value={form.watermark_text || ''}
            onChange={(e) => setForm((f) => ({ ...f, watermark_text: e.target.value }))}
            placeholder="z.B. @dein-linkedin-profil"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-400"
          />
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-4 py-2 bg-primary-600 text-white text-sm font-semibold rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
      >
        {saved ? 'Gespeichert' : saving ? 'Speichere...' : 'Branding speichern'}
      </button>
    </div>
  )
}
