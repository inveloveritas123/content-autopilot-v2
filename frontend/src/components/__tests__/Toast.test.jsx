/**
 * Toast-System Unit-Tests
 *
 * Voraussetzungen (falls noch nicht installiert):
 *   npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 *   vite.config.js → test: { environment: 'jsdom' }
 *
 * Ausführen: npx vitest run Toast.test.jsx
 */

import { act, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast } from '../ui/Toast'

// ─── Hilfs-Komponente ────────────────────────────────────────────────────────

function ToastTrigger({ message, variant }) {
  const toast = useToast()
  return <button onClick={() => toast.show(message, variant)}>Toast anzeigen</button>
}

function renderWithProvider(ui) {
  return render(<ToastProvider>{ui}</ToastProvider>)
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('Toast-System', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('zeigt Toast mit korrektem Text an', () => {
    renderWithProvider(<ToastTrigger message="Gespeichert!" variant="success" />)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /Toast anzeigen/i }))
    })
    expect(screen.getByText('Gespeichert!')).toBeInTheDocument()
  })

  it('dismisst success-Toast automatisch nach 4 Sekunden', () => {
    renderWithProvider(<ToastTrigger message="Kurze Nachricht" variant="success" />)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /Toast anzeigen/i }))
    })
    expect(screen.getByText('Kurze Nachricht')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(4001)
    })
    expect(screen.queryByText('Kurze Nachricht')).not.toBeInTheDocument()
  })

  it('dismisst error-Toast erst nach 8 Sekunden', () => {
    renderWithProvider(<ToastTrigger message="Fehler aufgetreten" variant="error" />)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /Toast anzeigen/i }))
    })

    act(() => {
      vi.advanceTimersByTime(4001)
    })
    // Nach 4s noch da (error = 8s)
    expect(screen.getByText('Fehler aufgetreten')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(4001)
    })
    expect(screen.queryByText('Fehler aufgetreten')).not.toBeInTheDocument()
  })

  it('stacked max 3 Toasts — ältester wird verdrängt', () => {
    function MultiTrigger() {
      const toast = useToast()
      return (
        <>
          <button onClick={() => toast.success('Toast 1')}>T1</button>
          <button onClick={() => toast.success('Toast 2')}>T2</button>
          <button onClick={() => toast.success('Toast 3')}>T3</button>
          <button onClick={() => toast.success('Toast 4')}>T4</button>
        </>
      )
    }
    renderWithProvider(<MultiTrigger />)

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'T1' }))
    })
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'T2' }))
    })
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'T3' }))
    })
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'T4' }))
    })

    // Max 3 — Toast 1 wurde verdrängt
    expect(screen.queryByText('Toast 1')).not.toBeInTheDocument()
    expect(screen.getByText('Toast 2')).toBeInTheDocument()
    expect(screen.getByText('Toast 3')).toBeInTheDocument()
    expect(screen.getByText('Toast 4')).toBeInTheDocument()
  })

  it('manuelles Schließen via X-Button funktioniert', () => {
    renderWithProvider(<ToastTrigger message="Schließbar" variant="info" />)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /Toast anzeigen/i }))
    })
    expect(screen.getByText('Schließbar')).toBeInTheDocument()

    const closeBtn = screen.getByRole('button', { name: /Schließen/i })
    act(() => {
      fireEvent.click(closeBtn)
    })
    expect(screen.queryByText('Schließbar')).not.toBeInTheDocument()
  })
})
