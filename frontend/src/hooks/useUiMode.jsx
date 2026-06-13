/**
 * useUiMode — zentraler Hook für den Oberflächen-Modus MVP vs Features (#90).
 *
 * Lädt den Modus einmal vom Backend (GET /tenants/me/ui-mode) und hält ihn
 * im React-Context bereit.  Komponenten rufen useUiMode() auf und bekommen:
 *   - mode: "mvp" | "features" (Default "features" beim Laden — fail-open)
 *   - loading: true solange der erste Fetch noch läuft
 *   - setMode(newMode): ruft PUT /tenants/me/ui-mode auf und aktualisiert
 *     sofort den Context-State → Nav und alle Abonnenten reagieren ohne Reload.
 *
 * Fail-open-Strategie: Schlägt der Fetch fehl, bleibt mode="features" (Voll-
 * ansicht) — kein Funktionsverlust durch Netzwerkfehler.
 */
import { createContext, useContext, useEffect, useState } from 'react'
import { getUiMode, setUiMode as apiSetUiMode } from '../api'

// Default "features" beim ersten Render — fail-open: zeige alles, bis Modus geladen
const UiModeContext = createContext({ mode: 'features', loading: true, setMode: () => {} })

export function UiModeProvider({ children }) {
  const [mode, setModeState] = useState('features') // fail-open default
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getUiMode()
      .then((res) => {
        if (!cancelled) setModeState(res.mode ?? 'features')
      })
      .catch(() => {
        // Netzwerkfehler → behalte "features" (fail-open), kein Crash
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  /**
   * Persistiert den Modus im Backend und aktualisiert sofort den lokalen State.
   * Wirft einen Fehler wenn der API-Call fehlschlägt — Aufrufer muss fangen.
   */
  async function setMode(newMode) {
    await apiSetUiMode(newMode)
    setModeState(newMode)
  }

  return (
    <UiModeContext.Provider value={{ mode, loading, setMode }}>
      {children}
    </UiModeContext.Provider>
  )
}

/**
 * Hook für Komponenten:  const { mode, loading, setMode } = useUiMode()
 */
export function useUiMode() {
  return useContext(UiModeContext)
}
