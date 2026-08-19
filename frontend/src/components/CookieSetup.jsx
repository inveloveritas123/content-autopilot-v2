import { useState } from 'react'
import { useToast } from './ui/Toast'
import { Dialog } from './ui/Dialog'
import { Button } from './ui/Button'
import { Textarea } from './ui/Input'
import { Badge } from './ui/Badge'
import { saveCookies } from '../api'

export default function CookieSetup({ open, onClose, onSaved }) {
  const { toast } = useToast()
  const [cookieText, setCookieText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    if (!cookieText.trim()) return
    setSaving(true)
    try {
      await saveCookies(cookieText)
      setSaved(true)
      setTimeout(() => {
        onSaved?.()
        onClose()
        setSaved(false)
        setCookieText('')
      }, 1500)
    } catch (e) {
      toast.error('Fehler beim Speichern: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="YouTube Cookies einrichten" className="max-w-xl">
      <div className="space-y-4">
        {/* Why */}
        <div className="bg-status-aktiv-bg border border-status-aktiv-border rounded-lg p-3">
          <p className="text-sm font-medium text-status-aktiv-text">
            Warum braucht der Autopilot Cookies?
          </p>
          <p className="text-xs text-status-aktiv-text mt-1">
            YouTube blockiert automatische Transkript-Anfragen nach kurzer Zeit (Rate-Limit). Mit
            einem Cookie aus deinem Browser erkennt YouTube die Anfragen als eingeloggt und erlaubt
            deutlich mehr Zugriffe.
          </p>
        </div>

        {/* Steps */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-ink">3 einfache Schritte:</h4>

          {/* Step 1 */}
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 bg-primary-100 text-primary-700 rounded-full flex items-center justify-center text-xs font-bold">
              1
            </span>
            <div>
              <p className="text-sm text-ink-light">Browser-Extension installieren:</p>
              <div className="flex gap-2 mt-1.5">
                <a
                  href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-surface-card border border-surface-border rounded px-2.5 py-1.5 text-ink-light hover:bg-surface-bg"
                >
                  Chrome: Get cookies.txt LOCALLY
                </a>
                <a
                  href="https://addons.mozilla.org/de/firefox/addon/cookies-txt/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-surface-card border border-surface-border rounded px-2.5 py-1.5 text-ink-light hover:bg-surface-bg"
                >
                  Firefox: cookies.txt
                </a>
              </div>
            </div>
          </div>

          {/* Step 2 */}
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 bg-primary-100 text-primary-700 rounded-full flex items-center justify-center text-xs font-bold">
              2
            </span>
            <div>
              <p className="text-sm text-ink-light">
                Oeffne{' '}
                <a
                  href="https://www.youtube.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:underline"
                >
                  youtube.com
                </a>{' '}
                im Browser (eingeloggt), klicke auf die Extension und exportiere die Cookies.
              </p>
            </div>
          </div>

          {/* Step 3 */}
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 bg-primary-100 text-primary-700 rounded-full flex items-center justify-center text-xs font-bold">
              3
            </span>
            <div>
              <p className="text-sm text-ink-light">
                Oeffne die exportierte Datei mit einem Texteditor, kopiere den gesamten Inhalt und
                fuege ihn hier ein:
              </p>
            </div>
          </div>
        </div>

        {/* Paste field */}
        <Textarea
          label="Cookie-Inhalt hier einfuegen"
          value={cookieText}
          onChange={(e) => setCookieText(e.target.value)}
          rows={6}
          placeholder={
            '# Netscape HTTP Cookie File\n# https://curl.se/docs/http-cookies.html\n.youtube.com\tTRUE\t/\tTRUE\t...'
          }
          className="font-mono text-xs"
        />

        {cookieText && (
          <p className="text-xs text-ink-light">
            {cookieText.split('\n').filter((l) => l.trim() && !l.startsWith('#')).length}{' '}
            Cookie-Eintraege erkannt
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          <div>{saved && <Badge color="green">Gespeichert!</Badge>}</div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              Abbrechen
            </Button>
            <Button onClick={handleSave} disabled={saving || !cookieText.trim()}>
              {saving ? 'Speichern...' : 'Cookies speichern'}
            </Button>
          </div>
        </div>

        {/* Alternative: SCP */}
        <details className="text-xs text-ink-muted">
          <summary className="cursor-pointer hover:text-ink-light">
            Alternativ: Per Terminal hochladen
          </summary>
          <div className="mt-2 bg-surface-bg p-2 rounded font-mono select-all">
            scp -P 10022 cookies.txt
            meister@152.53.142.163:/opt/content-autopilot-v2/data/youtube_cookies.txt
          </div>
        </details>
      </div>
    </Dialog>
  )
}
