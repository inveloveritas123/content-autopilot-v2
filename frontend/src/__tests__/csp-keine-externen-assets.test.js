// Beweis-Test zum Befund 'zubu-google-fonts-per-csp-blockiert-redesign-wirkungslos'
// (2026-08-21). Vorher ROT: index.css importierte Fraunces/IBM Plex von
// fonts.googleapis.com, die nginx-CSP erlaubt aber nur 'self' — die Schriften
// luden bei KEINEM Kunden, der Browser fiel auf Georgia/system-ui zurueck.
//
// Der Test prueft die KLASSE, nicht den Einzelfall: er liest die CSP aus der
// echten nginx-Config und haelt jede Stylesheet-/Font-Quelle im CSS dagegen.
// Kommt morgen ein anderer externer @import dazu, faellt er hier auf — auch
// wenn es nicht Google Fonts ist.
//
// ⛔ Der Fix ist LOKAL BUENDELN (@fontsource), nicht die CSP oeffnen:
// ein externer Google-Fonts-Request sendet die Nutzer-IP an Google in die USA
// und ist in DE abmahnfaehig (LG Muenchen I, 3 O 17493/20).

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../..')

const indexCss = readFileSync(resolve(repoRoot, 'frontend/src/index.css'), 'utf-8')
const nginxConf = readFileSync(resolve(repoRoot, 'nginx/nginx.v2.conf'), 'utf-8')

/** Liest eine Direktive aus dem Content-Security-Policy-Header der nginx-Config. */
function cspDirective(name) {
  const header = nginxConf.match(/add_header\s+Content-Security-Policy\s+"([^"]+)"/)
  expect(header, 'Content-Security-Policy-Header in nginx/nginx.v2.conf').not.toBeNull()
  const found = header[1]
    .split(';')
    .map((d) => d.trim())
    .find((d) => d.startsWith(`${name} `))
  return found ? found.slice(name.length).trim().split(/\s+/) : null
}

describe('CSP vs. Frontend-Assets', () => {
  it('index.css laedt kein Stylesheet von einem fremden Host', () => {
    // @import url(https://…) oder @import 'https://…' — beide Schreibweisen.
    const externe = [
      ...indexCss.matchAll(/@import\s+(?:url\(\s*)?['"]?(https?:\/\/[^'")\s]+)/g),
    ].map((m) => m[1])
    expect(externe, `externe @import-Quellen in index.css: ${externe.join(', ')}`).toEqual([])
  })

  it('die CSP erlaubt Styles und Fonts weiterhin nur von self — sie wurde NICHT aufgeweicht', () => {
    // Waechter gegen den bequemen Ruecksturz: wer den Font-Fehler durch
    // Oeffnen der CSP "loest", faellt hier auf.
    for (const direktive of ['style-src', 'font-src']) {
      const quellen = cspDirective(direktive)
      expect(quellen, `${direktive} fehlt in der CSP`).not.toBeNull()
      const fremde = quellen.filter((q) => q.startsWith('http') || q.includes('.'))
      expect(fremde, `${direktive} erlaubt fremde Hosts: ${fremde.join(', ')}`).toEqual([])
    }
  })

  it('die Display-Schrift nennt den Familiennamen, den @fontsource-variable wirklich registriert', () => {
    // 'Fraunces' allein trifft NICHTS — das Paket registriert 'Fraunces Variable'.
    // Ohne diesen Namen ist der CSP-Fehler weg, die Schrift aber immer noch Georgia.
    const displayRegel = indexCss.match(/font-family:\s*([^;]+);/g) || []
    const nenntVariable = displayRegel.some((r) => r.includes('Fraunces Variable'))
    expect(nenntVariable, 'keine font-family nennt "Fraunces Variable"').toBe(true)
  })
})
