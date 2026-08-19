import { clsx } from 'clsx'

// Status-Vokabular auf die 5 projektweiten Bedeutungen reduziert (SSOT D2):
// neu/aktiv/fertig/fehler/archiviert. `color`-Prop bleibt als direkter
// Status-Token-Name nutzbar (z.B. color="status-fertig"), `colors` unten
// bildet zusätzlich Kurzformen ab, die im Repo noch als Prop-Wert vorkommen
// könnten (blue/green/... wurden 1:1 auf ihre Status-Bedeutung gemappt).
const colors = {
  neu: 'bg-status-neu-bg text-status-neu-text',
  aktiv: 'bg-status-aktiv-bg text-status-aktiv-text',
  fertig: 'bg-status-fertig-bg text-status-fertig-text',
  fehler: 'bg-status-fehler-bg text-status-fehler-text',
  archiviert: 'bg-status-archiviert-bg text-status-archiviert-text',
}

const borderColors = {
  neu: 'border-status-neu-border',
  aktiv: 'border-status-aktiv-border',
  fertig: 'border-status-fertig-border',
  fehler: 'border-status-fehler-border',
  archiviert: 'border-status-archiviert-border',
}

const sizes = {
  xs: 'px-1.5 py-0.5 text-[10px]',
  sm: 'px-2 py-0.5 text-[11px]',
  md: 'px-2.5 py-0.5 text-xs',
}

// Rückwärtskompatible Aliase: einige Feature-Komponenten (außerhalb des
// Migrations-Scopes dieser Welle, z.B. PromptStudio.jsx, ContentCalendar.jsx)
// übergeben noch alte Rohfarbnamen als `color`-Prop. Bis diese in Welle D6
// migriert sind, auf die nächstliegende Status-Bedeutung abbilden statt
// stillschweigend zu brechen.
const legacyColorAliases = {
  gray: 'archiviert',
  blue: 'neu',
  green: 'fertig',
  yellow: 'aktiv',
  red: 'fehler',
  orange: 'aktiv',
  purple: 'aktiv',
}

// Zuordnung Roh-Status -> die 5 Bedeutungen (neu/aktiv/fertig/fehler/archiviert):
// new/transcribed/reviewed (Info, wartet) -> neu
// transcribing/analyzing/generating (läuft gerade) -> aktiv
// analyzed/scheduled (Zwischenschritt, aber grundsätzlich positiv) -> aktiv
// content_ready/approved (fertig, freigegeben) -> fertig
// needs_voicescriptor/transcription_failed (Fehler) -> fehler
// published/draft (abgeschlossen/inaktiv, keine Aktion nötig) -> archiviert
const statusColors = {
  new: 'neu',
  transcribing: 'aktiv',
  transcribed: 'neu',
  analyzing: 'aktiv',
  analyzed: 'aktiv',
  generating: 'aktiv',
  content_ready: 'fertig',
  approved: 'fertig',
  published: 'archiviert',
  needs_voicescriptor: 'fehler',
  transcription_failed: 'fehler',
  draft: 'archiviert',
  reviewed: 'neu',
  scheduled: 'aktiv',
}

export function Badge({ color, status, className, children, border = false, size = 'md' }) {
  const resolvedColor =
    (colors[color] && color) || legacyColorAliases[color] || statusColors[status] || 'archiviert'
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full font-medium',
        sizes[size] || sizes.md,
        colors[resolvedColor],
        border && 'border',
        border && (borderColors[resolvedColor] || borderColors.archiviert),
        className
      )}
    >
      {children || status}
    </span>
  )
}
