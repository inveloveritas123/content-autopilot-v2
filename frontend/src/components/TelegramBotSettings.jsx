/**
 * TelegramBotSettings — Panel „Telegram-Bot (pro Projekt)"
 *
 * Allows a tenant to configure a single Telegram bot token, see live status,
 * and revoke the token when needed.
 *
 * API contract (implemented in parallel by backend):
 *   GET    /api/tenants/me/telegram-bot  → { configured, bot_username, bot_id,
 *                                            status, online, last_active_at,
 *                                            validated_at, last_error }
 *   POST   /api/tenants/me/telegram-bot  body { token }  → same shape (201)
 *   DELETE /api/tenants/me/telegram-bot  → { status: "revoked" }
 *
 * Token is NEVER echoed back from the API and is cleared from state immediately
 * after the POST response is received — it does not persist in the DOM.
 */

import { useState } from 'react'
import { Bot, Circle, Eye, EyeOff } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { useToast } from './ui/Toast'
import { useApi } from '../hooks/useApi'
import { getTelegramBot, setTelegramBot, revokeTelegramBot } from '../api'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Returns a human-readable relative time string for a given ISO timestamp.
 * E.g. "vor 3 Min", "vor 2 Std", "vor 5 Tagen"
 */
function relativeTime(isoString) {
  if (!isoString) return null
  const diffMs = Date.now() - new Date(isoString).getTime()
  if (diffMs < 0) return null

  const secs = Math.floor(diffMs / 1000)
  if (secs < 60) return 'gerade eben'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `vor ${mins} Min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `vor ${hours} Std`
  const days = Math.floor(hours / 24)
  return `vor ${days} ${days === 1 ? 'Tag' : 'Tagen'}`
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function OnlineIndicator({ online, lastActiveAt }) {
  const relTime = relativeTime(lastActiveAt)
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <Circle
        className={`w-2.5 h-2.5 fill-current ${online ? 'text-emerald-500' : 'text-gray-400'}`}
        aria-hidden="true"
      />
      {online ? (
        <span className="text-emerald-700 dark:text-emerald-400 font-medium">online</span>
      ) : (
        <span className="text-gray-500 dark:text-gray-400">
          offline{relTime ? ` · zuletzt aktiv ${relTime}` : ''}
        </span>
      )}
    </span>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function TelegramBotSettings() {
  const toast = useToast()
  const { data, loading, error, refetch } = useApi(getTelegramBot)

  // Connect form state
  const [tokenInput, setTokenInput] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [connectError, setConnectError] = useState(null)

  // Revoke dialog
  const [showRevokeDialog, setShowRevokeDialog] = useState(false)
  const [revoking, setRevoking] = useState(false)

  const handleConnect = async (e) => {
    e.preventDefault()
    if (!tokenInput.trim()) return
    setConnecting(true)
    setConnectError(null)
    const tokenToSend = tokenInput.trim()
    // Clear the input immediately — token must not linger in state
    setTokenInput('')
    setShowToken(false)
    try {
      await setTelegramBot(tokenToSend)
      toast.success('Telegram-Bot erfolgreich verbunden!')
      refetch()
    } catch (err) {
      // Backend guarantees the error message never contains the token
      setConnectError(err.message || 'Verbindung fehlgeschlagen.')
    } finally {
      setConnecting(false)
    }
  }

  const handleRevoke = async () => {
    setRevoking(true)
    try {
      await revokeTelegramBot()
      toast.success('Token widerrufen. Der Bot ist jetzt gestoppt.')
      setShowRevokeDialog(false)
      refetch()
    } catch (err) {
      toast.error('Fehler beim Widerrufen: ' + (err.message || 'Unbekannter Fehler'))
    } finally {
      setRevoking(false)
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-primary-600" aria-hidden="true" />
            Telegram-Bot
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-400 dark:text-gray-500 animate-pulse">Lade Status…</p>
        </CardContent>
      </Card>
    )
  }

  // ── Fetch error ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-primary-600" aria-hidden="true" />
            Telegram-Bot
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-red-600 dark:text-red-400">
            Fehler beim Laden: {error}
          </p>
          <Button size="sm" variant="secondary" className="mt-3" onClick={refetch}>
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    )
  }

  const configured = data?.configured ?? false

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-primary-600" aria-hidden="true" />
              Telegram-Bot
            </CardTitle>
            {configured && data?.status && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  data.status === 'active'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : data.status === 'error'
                      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                }`}
              >
                {data.status === 'active'
                  ? 'Aktiv'
                  : data.status === 'revoked'
                    ? 'Widerrufen'
                    : data.status === 'error'
                      ? 'Fehler'
                      : data.status}
              </span>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {!configured ? (
            /* ── Not configured: connect form ──────────────────────────────── */
            <>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Verbinde einen eigenen Telegram-Bot mit diesem Projekt. Der Bot-Token bleibt
                verschlüsselt gespeichert und wird nie wieder angezeigt.
              </p>

              {/* Help text */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-xs text-blue-800 dark:text-blue-200 space-y-1">
                <p className="font-medium">Token von @BotFather holen:</p>
                <ol className="list-decimal list-inside space-y-0.5 text-blue-700 dark:text-blue-300">
                  <li>
                    Öffne Telegram und schreibe <code className="font-mono">@BotFather</code>
                  </li>
                  <li>
                    Neuer Bot: <code className="font-mono">/newbot</code> — folge den Anweisungen
                  </li>
                  <li>
                    Vorhandener Bot:{' '}
                    <code className="font-mono">/mybots</code> → Bot wählen →{' '}
                    <em>API Token</em>
                  </li>
                  <li>Token hier einfügen und speichern</li>
                </ol>
              </div>

              <form onSubmit={handleConnect} className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Bot-Token
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type={showToken ? 'text' : 'password'}
                      value={tokenInput}
                      onChange={(e) => setTokenInput(e.target.value)}
                      placeholder="123456789:ABCDefGhIjKlmNoPQRsTUVwxyz"
                      autoComplete="off"
                      className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken((s) => !s)}
                      className="p-2 rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      title={showToken ? 'Verbergen' : 'Anzeigen'}
                      aria-label={showToken ? 'Token verbergen' : 'Token anzeigen'}
                    >
                      {showToken ? (
                        <EyeOff className="w-4 h-4" aria-hidden="true" />
                      ) : (
                        <Eye className="w-4 h-4" aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>

                {connectError && (
                  <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                    {connectError}
                  </p>
                )}

                <Button
                  type="submit"
                  disabled={connecting || !tokenInput.trim()}
                  size="sm"
                >
                  {connecting ? 'Verbinde…' : 'Bot verbinden'}
                </Button>
              </form>
            </>
          ) : (
            /* ── Configured: status view ───────────────────────────────────── */
            <div className="space-y-4">
              {/* Bot identity + online indicator */}
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  {data?.bot_username && (
                    <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
                      @{data.bot_username}
                    </p>
                  )}
                  {data?.bot_id && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                      Bot-ID: {data.bot_id}
                    </p>
                  )}
                  <OnlineIndicator online={data?.online} lastActiveAt={data?.last_active_at} />
                </div>
              </div>

              {/* Error row */}
              {data?.status === 'error' && data?.last_error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                  <p className="text-xs font-medium text-red-700 dark:text-red-300 mb-0.5">
                    Bot-Fehler
                  </p>
                  <p className="text-xs text-red-600 dark:text-red-400 font-mono break-all">
                    {data.last_error}
                  </p>
                </div>
              )}

              {/* Validation timestamp */}
              {data?.validated_at && (
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  Token validiert: {relativeTime(data.validated_at) ?? new Date(data.validated_at).toLocaleString('de-DE')}
                </p>
              )}

              {/* Revoke button */}
              <div className="pt-1 border-t border-gray-100 dark:border-gray-800">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setShowRevokeDialog(true)}
                >
                  Token widerrufen
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Revoke confirmation dialog */}
      <Dialog
        open={showRevokeDialog}
        onClose={() => !revoking && setShowRevokeDialog(false)}
        title="Token widerrufen?"
        className="max-w-md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-700 dark:text-gray-300">
            Der Token wird hier entfernt und der Bot gestoppt. Diese Aktion kann nicht rückgängig
            gemacht werden.
          </p>

          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 text-xs text-amber-800 dark:text-amber-200">
            <p className="font-medium mb-1">Sicherheitshinweis</p>
            <p>
              Für vollständige Invalidierung den Token zusätzlich in{' '}
              <strong>@BotFather</strong> über{' '}
              <code className="font-mono">/revoke</code> neu generieren. Nur so wird der alte
              Token serverseitig bei Telegram ungültig.
            </p>
          </div>

          <div className="flex gap-3 justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowRevokeDialog(false)}
              disabled={revoking}
            >
              Abbrechen
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleRevoke}
              disabled={revoking}
            >
              {revoking ? 'Widerrufe…' : 'Ja, widerrufen'}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  )
}
