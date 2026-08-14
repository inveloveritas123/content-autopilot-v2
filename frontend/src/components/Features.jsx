import { Link } from 'react-router-dom'
import { Card, CardContent } from './ui/Card'
import { featureRouteItems } from './featureRoutes'

// #90-Fortsetzung (docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md, D4): Route-Guard
// bleibt NUR Nav-Gating (Robert-Entscheid, Layout.jsx) — mvp:false-Seiten
// verschwinden aus der Sidebar, sind aber weiterhin per Direktlink erreichbar.
// Diese Seite ist der fehlende dritte Baustein: eine zentrale Sammelansicht,
// damit "ausgeblendet" nicht "unauffindbar" bedeutet, solange man im
// MVP-Modus ist. Referenzvorbild: /admin-Kachel-Struktur (Admin-Tool #98).
export default function Features() {
  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-display font-semibold text-ink">Weitere Funktionen</h1>
        <p className="text-ink-light text-sm mt-1">
          Diese Seiten sind in der schlanken MVP-Ansicht ausgeblendet, aber jederzeit nutzbar.
          Wechsle oben links auf „Features&quot;, um sie dauerhaft in der Navigation zu sehen.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {featureRouteItems.map((item) => (
          <Link key={item.to} to={item.to} className="block">
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardContent className="flex items-start gap-3">
                <item.icon
                  className="w-5 h-5 text-primary-600 shrink-0 mt-0.5"
                  strokeWidth={1.75}
                />
                <div>
                  <p className="font-medium text-ink text-sm">{item.label}</p>
                  <p className="text-ink-muted text-xs mt-0.5">{item.description}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
