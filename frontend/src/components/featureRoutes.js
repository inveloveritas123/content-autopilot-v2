import {
  MessagesSquare,
  Send,
  CalendarDays,
  PieChart,
  BarChart3,
  Sparkles,
  Settings,
  ShieldAlert,
  FileStack,
  SlidersHorizontal,
} from 'lucide-react'

// Geteilte Datenquelle für die "Weitere Funktionen"-Sammelansicht (Features.jsx).
// Ergänzt navItems/brandVoiceNavItems aus Layout.jsx (dort bleibt mvp:true/false
// die Single Source of Truth für die Sidebar) um eine Kurzbeschreibung je Route
// UND die zwei Routen, die in App.jsx existieren, aber nie einen Sidebar-Link
// hatten (/settings/export-import, /settings/pipeline-models — #90/#98).
//
// Robert-Freigabe der mvp:false-Zuordnung: 2026-06-13 (#90, siehe Layout.jsx).
export const featureRouteItems = [
  {
    to: '/dialogue',
    label: 'Dialogue',
    icon: MessagesSquare,
    description: 'Ideen per Frage-Antwort-Dialog verfeinern, bevor daraus ein Post wird.',
  },
  {
    to: '/publish',
    label: 'Posten',
    icon: Send,
    description: 'Übersicht geplanter und veröffentlichter Posts (Backoffice-Ansicht).',
  },
  {
    to: '/calendar',
    label: 'Kalender',
    icon: CalendarDays,
    description: 'Content-Kalender über alle geplanten und veröffentlichten Posts.',
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: PieChart,
    description: 'Performance-Auswertung veröffentlichter Posts.',
  },
  {
    to: '/feedback',
    label: 'Feedback',
    icon: BarChart3,
    description: 'Rückmeldungen und Reaktionen zu veröffentlichten Posts einsehen.',
  },
  {
    to: '/memory/viz',
    label: 'Gedächtnis-Karte',
    icon: Sparkles,
    description: 'Visuelle Exploration des gespeicherten Gedächtnisses.',
  },
  {
    to: '/settings/company-profile',
    label: 'Firmen-Profil',
    icon: Settings,
    description: 'Detaillierte Firmen-Angaben für Content-Kontext pflegen.',
  },
  {
    to: '/settings/data-deletion',
    label: 'Recht auf Vergessen',
    icon: ShieldAlert,
    description: 'DSGVO-Löschanfragen stellen und den Status verfolgen.',
  },
  {
    to: '/settings/export-import',
    label: 'Export/Import',
    icon: FileStack,
    description: 'Daten exportieren oder importieren.',
  },
  {
    to: '/settings/pipeline-models',
    label: 'Pipeline-Modelle',
    icon: SlidersHorizontal,
    description: 'Modellzuordnung je Pipeline-Schritt einsehen.',
  },
]
