// AUDITED-2026-08-14 (D6): Tiefen-Audit, Datei vollstaendig gelesen.
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
import { Bot, Circle, Eye, EyeOff, Users, UserX, UserCheck, UserPlus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { useToast } from './ui/Toast'
import { useApi } from '../hooks/useApi'
import {
  getTelegramBot,
  setTelegramBot,
  revokeTelegramBot,
  getTelegramUsers,
  blockTelegramUser,
  unblockTelegramUser,
  removeTelegramUser,
  manualLinkTelegramUser,
} from '../api'

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
        className={`w-2.5 h-2.5 fill-current ${online ? 'text-status-fertig-text' : 'text-ink-light'}`}
        aria-hidden="true"
      />
      {online ? (
        <span className="text-status-fertig-text dark:text-status-fertig-text font-medium">
          online
        </span>
      ) : (
        <span className="text-ink-light dark:text-ink-muted">
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
          <p className="text-sm text-ink-light dark:text-ink-muted animate-pulse">Lade Status…</p>
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
          <p className="text-sm text-status-fehler-text dark:text-status-fehler-text">
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
                    ? 'bg-status-fertig-bg text-status-fertig-text dark:bg-status-fertig-bg/30 dark:text-status-fertig-text'
                    : data.status === 'error'
                      ? 'bg-status-fehler-bg text-status-fehler-text dark:bg-status-fehler-bg/30 dark:text-status-fehler-text'
                      : 'bg-surface-bg text-ink-light dark:bg-surface-card dark:text-ink-muted'
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
              <p className="text-sm text-ink-light dark:text-ink-muted">
                Verbinde einen eigenen Telegram-Bot mit diesem Projekt. Der Bot-Token bleibt
                verschlüsselt gespeichert und wird nie wieder angezeigt.
              </p>

              {/* Help text */}
              <div className="bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg p-3 text-xs text-primary-800 dark:text-primary-200 space-y-1">
                <p className="font-medium">Token von @BotFather holen:</p>
                <ol className="list-decimal list-inside space-y-0.5 text-primary-700 dark:text-primary-300">
                  <li>
                    Öffne Telegram und schreibe <code className="font-mono">@BotFather</code>
                  </li>
                  <li>
                    Neuer Bot: <code className="font-mono">/newbot</code> — folge den Anweisungen
                  </li>
                  <li>
                    Vorhandener Bot: <code className="font-mono">/mybots</code> → Bot wählen →{' '}
                    <em>API Token</em>
                  </li>
                  <li>Token hier einfügen und speichern</li>
                </ol>
              </div>

              <form onSubmit={handleConnect} className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-ink dark:text-ink-muted mb-1">
                    Bot-Token
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type={showToken ? 'text' : 'password'}
                      value={tokenInput}
                      onChange={(e) => setTokenInput(e.target.value)}
                      placeholder="123456789:ABCDefGhIjKlmNoPQRsTUVwxyz"
                      autoComplete="off"
                      className="flex-1 px-3 py-2 rounded-lg border border-surface-border dark:border-surface-border bg-white dark:bg-surface-card text-ink dark:text-ink-muted placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken((s) => !s)}
                      className="p-2 rounded-md text-ink-light hover:bg-surface-bg dark:hover:bg-surface-card transition-colors"
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
                  <p
                    className="text-sm text-status-fehler-text dark:text-status-fehler-text"
                    role="alert"
                  >
                    {connectError}
                  </p>
                )}

                <Button type="submit" disabled={connecting || !tokenInput.trim()} size="sm">
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
                    <p className="text-base font-semibold text-ink dark:text-ink-muted">
                      @{data.bot_username}
                    </p>
                  )}
                  {data?.bot_id && (
                    <p className="text-xs text-ink-light dark:text-ink-muted font-mono">
                      Bot-ID: {data.bot_id}
                    </p>
                  )}
                  <OnlineIndicator online={data?.online} lastActiveAt={data?.last_active_at} />
                </div>
              </div>

              {/* Error row */}
              {data?.status === 'error' && data?.last_error && (
                <div className="bg-status-fehler-bg dark:bg-status-fehler-bg/20 border border-status-fehler-border dark:border-status-fehler-border rounded-lg p-3">
                  <p className="text-xs font-medium text-status-fehler-text dark:text-status-fehler-text mb-0.5">
                    Bot-Fehler
                  </p>
                  <p className="text-xs text-status-fehler-text dark:text-status-fehler-text font-mono break-all">
                    {data.last_error}
                  </p>
                </div>
              )}

              {/* Validation timestamp */}
              {data?.validated_at && (
                <p className="text-xs text-ink-light dark:text-ink-muted">
                  Token validiert:{' '}
                  {relativeTime(data.validated_at) ??
                    new Date(data.validated_at).toLocaleString('de-DE')}
                </p>
              )}

              {/* Revoke button */}
              <div className="pt-1 border-t border-surface-border dark:border-surface-border">
                <Button variant="danger" size="sm" onClick={() => setShowRevokeDialog(true)}>
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
          <p className="text-sm text-ink dark:text-ink-muted">
            Der Token wird hier entfernt und der Bot gestoppt. Diese Aktion kann nicht rückgängig
            gemacht werden.
          </p>

          <div className="bg-accent-50 dark:bg-accent-900/20 border border-accent-200 dark:border-accent-800 rounded-lg p-3 text-xs text-accent-800 dark:text-accent-200">
            <p className="font-medium mb-1">Sicherheitshinweis</p>
            <p>
              Für vollständige Invalidierung den Token zusätzlich in <strong>@BotFather</strong>{' '}
              über <code className="font-mono">/revoke</code> neu generieren. Nur so wird der alte
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
            <Button variant="danger" size="sm" onClick={handleRevoke} disabled={revoking}>
              {revoking ? 'Widerrufe…' : 'Ja, widerrufen'}
            </Button>
          </div>
        </div>
      </Dialog>

      {configured && <TelegramUsersPanel tenantConfigured={configured} />}
    </>
  )
}

// ─── TelegramUsersPanel ───────────────────────────────────────────────────────

function TelegramUsersPanel({ tenantConfigured }) {
  const toast = useToast()
  const { data, loading, error, refetch } = useApi(getTelegramUsers)
  const [actionLoading, setActionLoading] = useState(null) // user_id being actioned
  const [removeDialog, setRemoveDialog] = useState(null) // user to remove
  const [showManualAdd, setShowManualAdd] = useState(false)
  const [manualUserId, setManualUserId] = useState('')
  const [manualChatId, setManualChatId] = useState('')
  const [addingManual, setAddingManual] = useState(false)

  // tenantConfigured prop used to conditionally render from parent
  void tenantConfigured

  const users = data?.users ?? []

  const handleBlock = async (userId) => {
    setActionLoading(userId)
    try {
      await blockTelegramUser(userId)
      toast.success('Nutzer blockiert.')
      refetch()
    } catch (err) {
      toast.error(err.message || 'Fehler beim Blockieren')
    } finally {
      setActionLoading(null)
    }
  }

  const handleUnblock = async (userId) => {
    setActionLoading(userId)
    try {
      await unblockTelegramUser(userId)
      toast.success('Nutzer freigeschaltet.')
      refetch()
    } catch (err) {
      toast.error(err.message || 'Fehler beim Freischalten')
    } finally {
      setActionLoading(null)
    }
  }

  const handleRemove = async (userId) => {
    setActionLoading(userId)
    try {
      await removeTelegramUser(userId)
      toast.success('Nutzer entfernt.')
      setRemoveDialog(null)
      refetch()
    } catch (err) {
      toast.error(err.message || 'Fehler beim Entfernen')
    } finally {
      setActionLoading(null)
    }
  }

  const handleManualAdd = async (e) => {
    e.preventDefault()
    const uid = parseInt(manualUserId.trim(), 10)
    if (!uid || uid <= 0) return
    setAddingManual(true)
    try {
      const body = { telegram_user_id: uid }
      if (manualChatId.trim()) body.telegram_chat_id = parseInt(manualChatId.trim(), 10)
      await manualLinkTelegramUser(body)
      toast.success('Nutzer manuell hinzugefügt.')
      setManualUserId('')
      setManualChatId('')
      setShowManualAdd(false)
      refetch()
    } catch (err) {
      toast.error(err.message || 'Fehler beim Hinzufügen')
    } finally {
      setAddingManual(false)
    }
  }

  const statusBadge = (status) => {
    const map = {
      active:
        'bg-status-fertig-bg text-status-fertig-text dark:bg-status-fertig-bg/30 dark:text-status-fertig-text',
      blocked:
        'bg-status-fehler-bg text-status-fehler-text dark:bg-status-fehler-bg/30 dark:text-status-fehler-text',
      pending: 'bg-accent-100 text-accent-700 dark:bg-accent-900/30 dark:text-accent-300',
    }
    const label = { active: 'Aktiv', blocked: 'Blockiert', pending: 'Ausstehend' }
    return (
      <span
        className={`text-xs font-medium px-2 py-0.5 rounded-full ${map[status] ?? map.pending}`}
      >
        {label[status] ?? status}
      </span>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Users className="w-4 h-4 text-primary-600" aria-hidden="true" />
              Verbundene Nutzer
            </CardTitle>
            <Button size="sm" variant="secondary" onClick={() => setShowManualAdd((s) => !s)}>
              <UserPlus className="w-3.5 h-3.5 mr-1.5" />
              Manuell hinzufügen
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Manual add form */}
          {showManualAdd && (
            <form
              onSubmit={handleManualAdd}
              className="bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg p-3 space-y-3"
            >
              <p className="text-xs text-primary-800 dark:text-primary-200 font-medium">
                Telegram-User-ID hinzufügen (ohne /start-Flow)
              </p>
              <p className="text-xs text-primary-700 dark:text-primary-300">
                Die User-ID findest du z.B. über <code className="font-mono">@userinfobot</code> in
                Telegram. Chat-ID ist identisch mit User-ID bei Direktnachrichten.
              </p>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={manualUserId}
                  onChange={(e) => setManualUserId(e.target.value)}
                  placeholder="Telegram User-ID"
                  required
                  className="flex-1 px-3 py-1.5 rounded-lg border border-surface-border dark:border-surface-border bg-white dark:bg-surface-card text-sm font-mono"
                />
                <input
                  type="number"
                  value={manualChatId}
                  onChange={(e) => setManualChatId(e.target.value)}
                  placeholder="Chat-ID (optional)"
                  className="w-36 px-3 py-1.5 rounded-lg border border-surface-border dark:border-surface-border bg-white dark:bg-surface-card text-sm font-mono"
                />
                <Button type="submit" size="sm" disabled={addingManual || !manualUserId.trim()}>
                  {addingManual ? 'Füge hinzu…' : 'Hinzufügen'}
                </Button>
              </div>
            </form>
          )}

          {/* Rate limit info */}
          <div className="text-xs text-ink-light dark:text-ink-muted bg-surface-bg dark:bg-surface-card/50 rounded-lg px-3 py-2">
            Rate-Limit: max. 20 Nachrichten pro 10 Minuten pro Nutzer
          </div>

          {loading && <p className="text-sm text-ink-light animate-pulse">Lade Nutzer…</p>}

          {error && (
            <p className="text-sm text-status-fehler-text dark:text-status-fehler-text">
              Fehler: {error}
            </p>
          )}

          {!loading && !error && users.length === 0 && (
            <p className="text-sm text-ink-light dark:text-ink-muted">
              Noch keine verbundenen Nutzer. Nutze <code className="font-mono text-xs">/start</code>{' '}
              im Telegram-Bot oder füge eine User-ID manuell hinzu.
            </p>
          )}

          {!loading && users.length > 0 && (
            <div className="space-y-2">
              {users.map((user) => {
                const displayName = user.telegram_first_name
                  ? `${user.telegram_first_name}${user.telegram_username ? ` (@${user.telegram_username})` : ''}`
                  : user.telegram_username
                    ? `@${user.telegram_username}`
                    : '—'
                const isActioning = actionLoading === user.telegram_user_id
                return (
                  <div
                    key={user.telegram_user_id}
                    className="flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-lg border border-surface-border dark:border-surface-border bg-white dark:bg-surface-card"
                  >
                    {/* Identity */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-ink dark:text-ink-muted truncate">
                          {displayName}
                        </span>
                        {statusBadge(user.status)}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-ink-light dark:text-ink-muted flex-wrap">
                        <span className="font-mono">ID: {user.telegram_user_id}</span>
                        {user.linked_at && <span>Verbunden {relativeTime(user.linked_at)}</span>}
                        {user.last_active && <span>Aktiv {relativeTime(user.last_active)}</span>}
                      </div>
                    </div>

                    {/* Stats */}
                    <div className="flex items-center gap-4 text-xs text-ink-light dark:text-ink-muted shrink-0">
                      <div className="text-center">
                        <div className="font-semibold text-ink dark:text-ink-muted">
                          {user.total_messages}
                        </div>
                        <div>Gesamt</div>
                      </div>
                      <div className="text-center">
                        <div className="font-semibold text-ink dark:text-ink-muted">
                          {user.messages_24h}
                        </div>
                        <div>24h</div>
                      </div>
                      <div
                        className={`text-center ${user.messages_10min > 15 ? 'text-accent-600 dark:text-accent-400' : ''}`}
                      >
                        <div className="font-semibold">{user.messages_10min}</div>
                        <div>10min</div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      {user.status === 'blocked' ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleUnblock(user.telegram_user_id)}
                          disabled={isActioning}
                          title="Nutzer freischalten"
                        >
                          <UserCheck className="w-3.5 h-3.5 mr-1" />
                          {isActioning ? '…' : 'Freischalten'}
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleBlock(user.telegram_user_id)}
                          disabled={isActioning}
                          title="Nutzer blockieren"
                        >
                          <UserX className="w-3.5 h-3.5 mr-1" />
                          {isActioning ? '…' : 'Blockieren'}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => setRemoveDialog(user)}
                        disabled={isActioning}
                        title="Verbindung trennen"
                      >
                        Trennen
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Remove confirmation dialog */}
      <Dialog
        open={!!removeDialog}
        onClose={() => actionLoading !== removeDialog?.telegram_user_id && setRemoveDialog(null)}
        title="Verbindung trennen?"
        className="max-w-md"
      >
        <div className="space-y-4">
          <p className="text-sm text-ink dark:text-ink-muted">
            Der Nutzer{' '}
            <strong>
              {removeDialog?.telegram_first_name ??
                removeDialog?.telegram_username ??
                `ID ${removeDialog?.telegram_user_id}`}
            </strong>{' '}
            wird getrennt und kann keine Nachrichten mehr senden.
          </p>
          <div className="flex gap-3 justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setRemoveDialog(null)}
              disabled={!!actionLoading}
            >
              Abbrechen
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => handleRemove(removeDialog?.telegram_user_id)}
              disabled={!!actionLoading}
            >
              {actionLoading ? 'Trenne…' : 'Ja, trennen'}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  )
}
