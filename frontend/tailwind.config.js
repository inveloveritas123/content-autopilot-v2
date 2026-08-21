/** @type {import('tailwindcss').Config} */
// Drei-Tier-Token-Architektur (Redesign 2026-08-14, docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md):
// Tier 1 Primitive (Zahlen/Hex, unten) -> Tier 2 Semantic (bedeutungstragende Aliase,
// z.B. `status.*`) -> Tier 3 Component (in den ui/-Komponenten selbst, referenziert nur
// Tier 2). Component-Code darf NIE einen Primitive-Wert direkt zitieren.
//
// Dark-Mode entfernt (Owner-Entscheid 2026-08-14): war eine tote Halb-Implementierung
// (nur ui/-Komponenten hatten dark:-Varianten, der Rest der App nicht) — schlechter als
// beides. Kann bei Bedarf sauber als Token-Override nachgerüstet werden.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tier 1 — Primitive. Teal/Amber-Grundidee aus dem Vorgänger-System behalten
        // (kein Blue-Purple-Gradient-Klischee), aber jetzt als klar benannte Basis.
        primary: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          950: '#042f2e',
        },
        accent: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
        },
        surface: {
          bg: '#F8FAFC',
          card: '#FFFFFF',
          border: '#E2E8F0',
        },
        ink: {
          DEFAULT: '#1E293B',
          light: '#64748B',
          muted: '#94A3B8',
        },

        // Tier 2 — Semantic: Status-Vokabular. Vorher pro Komponente neu erfunden
        // (Posts.jsx allein nutzte 10 Farbfamilien für Status/Kategorie). Jetzt EIN
        // projektweites Set mit 5 Bedeutungen — jede Komponente referenziert nur noch
        // `status-{neu,aktiv,fertig,fehler,archiviert}-*`, nie eine rohe Tailwind-Farbe.
        'status-neu': {
          bg: '#dbeafe',
          text: '#1d4ed8',
          border: '#93c5fd',
        },
        'status-aktiv': {
          bg: '#fef3c7',
          text: '#b45309',
          border: '#fcd34d',
        },
        'status-fertig': {
          bg: '#d1fae5',
          text: '#047857',
          border: '#6ee7b7',
        },
        'status-fehler': {
          bg: '#fee2e2',
          text: '#b91c1c',
          border: '#fca5a5',
        },
        'status-archiviert': {
          bg: '#f1f5f9',
          text: '#64748b',
          border: '#cbd5e1',
        },
      },
      fontFamily: {
        // Display: Fraunces (variable Serif, Charakter statt Neutralität — passt zu
        // einem Redaktions-/Content-Werkzeug, ohne steif zu wirken).
        // Body: IBM Plex Sans (neutral, sehr gut lesbar, kein Slop-Tell wie Inter).
        // Mono: IBM Plex Mono (Zeitstempel, IDs, Zahlen — konsistent zur Body-Familie).
        // 'Fraunces Variable' ist der Familienname aus @fontsource-variable/fraunces
        // (gemessen in dessen index.css) — 'Fraunces' allein trifft NICHTS.
        display: ['"Fraunces Variable"', 'Fraunces', 'Georgia', 'serif'],
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      spacing: {
        // Tier-1-Raster-Ergänzung: 4px-Rhythmus als benannte Zwischenwerte, wo
        // Tailwinds Default-Skala (0,1,2,3,4,5,6,8...) Lücken lässt, die sonst zu
        // Hand-getippten Arbitrary-Values verleiten.
        18: '4.5rem',
      },
      borderRadius: {
        // Tier-2-Vorgabe: EIN Radius pro Komponenten-Tier statt fünf freier Skalen.
        // card = rounded-xl, control (Button/Input) = rounded-lg, pill (Badge) = full.
        card: '0.75rem',
        control: '0.5rem',
      },
    },
  },
  plugins: [],
}
