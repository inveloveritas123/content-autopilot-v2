import { useState, useEffect, useCallback } from 'react'
import {
  Users,
  RefreshCw,
  Key,
  Copy,
  Check,
  AlertCircle,
  Loader2,
  LogIn,
  UserPlus,
} from 'lucide-react'
import {
  adminListUsers,
  adminRegenerateApiKey,
  adminSetApiKey,
  adminCreateUser,
  setApiKey,
} from '../../api'
import { Dialog } from '../ui/Dialog'
import { CloseButton } from '../ui/CloseButton'

// localStorage-Key für den aktiven X-API-Key (gleicher Key wie main.jsx/tenant-init nutzt)
const API_KEY_STORAGE = 'apiKey'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback für ältere Browser
      const el = document.createElement('textarea')
      el.value = text
      el.style.position = 'fixed'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-accent-600 hover:bg-accent-500 text-white transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? 'Kopiert!' : 'Kopieren'}
    </button>
  )
}

// Einmaliger Klartext-Dialog für regenerierten API-Key
function NewKeyDialog({ userId, userName, onClose }) {
  const [loading, setLoading] = useState(true)
  const [key, setKey] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    adminRegenerateApiKey(userId)
      .then((data) => {
        if (!cancelled) setKey(data.api_key)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Fehler beim Generieren')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  function handleUseAsContext() {
    if (key) {
      setApiKey(key)
      // Token NICHT im DOM belassen — Dialog schliessen
      onClose(true)
    }
  }

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      maxWidth="md"
      closeOnBackdrop={false}
      contentClassName="p-0"
    >
      <>
        {/* Header — bewusst eigenes accent-Design statt Standard-Dialog-Header:
            hebt die einmalige Sichtbarkeit des Klartext-Keys visuell hervor. */}
        <div className="px-5 py-4 bg-accent-50 border-b border-accent-200 flex items-center gap-3">
          <Key className="w-5 h-5 text-accent-600 shrink-0" />
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-accent-900">
              Neuer API-Key — einmalig sichtbar
            </h2>
            <p className="text-xs text-accent-700 mt-0.5">Nutzer: {userName}</p>
          </div>
          <CloseButton onClick={() => onClose(false)} />
        </div>

        <div className="p-5 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-ink-muted py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              Generiere neuen Key…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {key && !loading && (
            <>
              {/* Warnung */}
              <div className="p-3 bg-status-aktiv-bg border border-status-aktiv-border rounded-lg text-xs text-status-aktiv-text">
                <strong>Jetzt kopieren!</strong> Dieser Key wird nicht erneut angezeigt und ist ab
                sofort aktiv.
              </div>

              {/* Key-Anzeige + Copy */}
              <div className="flex items-center gap-2 p-3 bg-surface-bg border border-surface-border rounded-lg">
                <code className="flex-1 text-xs font-mono text-ink break-all select-all">
                  {key}
                </code>
                <CopyButton text={key} />
              </div>

              {/* Als aktiven Kontext verwenden */}
              <button
                onClick={handleUseAsContext}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 text-sm font-medium rounded-lg border border-primary-200 text-primary-700 hover:bg-primary-50 transition-colors"
              >
                <LogIn className="w-4 h-4" />
                Als aktiven Kontext verwenden (setzt diesen Tenant-Key)
              </button>
            </>
          )}
        </div>

        <div className="px-5 pb-4 flex justify-end">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg transition-colors"
          >
            Schließen
          </button>
        </div>
      </>
    </Dialog>
  )
}

// Dialog zum manuellen Setzen eines API-Keys
function SetKeyDialog({ userId, userName, onClose }) {
  const [keyInput, setKeyInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [masked, setMasked] = useState(null)

  async function handleSet() {
    if (!keyInput.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await adminSetApiKey(userId, keyInput.trim())
      setMasked(data.api_key_masked)
      setKeyInput('') // Key sofort aus dem State löschen
    } catch (e) {
      setError(e.message || 'Fehler beim Setzen des Keys')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open onClose={onClose} title="API-Key setzen" maxWidth="md" closeOnBackdrop={false}>
      <>
        <p className="text-xs text-ink-muted -mt-2 mb-4">Nutzer: {userName}</p>
        <div className="space-y-4">
          {!masked ? (
            <>
              <div>
                <label className="block text-xs font-medium text-ink mb-1.5">Neuer API-Key</label>
                <input
                  type="password"
                  autoComplete="off"
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSet()
                  }}
                  placeholder="cap_live_…"
                  className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  {error}
                </div>
              )}

              <button
                onClick={handleSet}
                disabled={loading || !keyInput.trim()}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 text-sm font-medium rounded-lg bg-primary-700 text-white hover:bg-primary-800 disabled:opacity-50 transition-colors"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Key className="w-4 h-4" />
                )}
                Key setzen
              </button>
            </>
          ) : (
            <div className="p-3 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-sm text-status-fertig-text">
              <Check className="inline w-4 h-4 mr-1" />
              Key gesetzt. Maskiert: <code className="font-mono">{masked}</code>
            </div>
          )}
        </div>

        <div className="pt-4 mt-4 border-t border-surface-border flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg transition-colors"
          >
            Schließen
          </button>
        </div>
      </>
    </Dialog>
  )
}

// Dialog zum Anlegen eines neuen Tenant-Benutzers
function CreateUserDialog({ onClose }) {
  const [nameInput, setNameInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  // newKey wird nur einmalig angezeigt und danach aus dem State entfernt
  const [newKey, setNewKey] = useState(null)
  const [newUser, setNewUser] = useState(null)

  async function handleCreate() {
    const name = nameInput.trim()
    if (!name) return
    setLoading(true)
    setError(null)
    try {
      const data = await adminCreateUser(name)
      // api_key einmalig aus der Response holen, dann nie wieder
      setNewKey(data.api_key)
      setNewUser({ id: data.id, name: data.name, slug: data.slug })
      setNameInput('')
    } catch (e) {
      setError(e.message || 'Fehler beim Anlegen des Benutzers')
    } finally {
      setLoading(false)
    }
  }

  function handleDone() {
    setNewKey(null) // Key aus dem State entfernen
    onClose(true) // Liste neu laden
  }

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title="Neuen Benutzer anlegen"
      titleIcon={UserPlus}
      maxWidth="md"
      closeOnBackdrop={false}
    >
      <>
        <div className="space-y-4">
          {/* Phase 1: Name eingeben */}
          {!newKey && (
            <>
              <div>
                <label className="block text-xs font-medium text-ink mb-1.5">
                  Name des Tenants <span className="text-status-fehler-text">*</span>
                </label>
                <input
                  type="text"
                  autoFocus
                  autoComplete="off"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreate()
                  }}
                  placeholder="z.B. Acme GmbH"
                  maxLength={255}
                  className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <p className="mt-1 text-xs text-ink-muted">
                  Slug und API-Key werden automatisch generiert.
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-2 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  {error}
                </div>
              )}

              <button
                onClick={handleCreate}
                disabled={loading || !nameInput.trim()}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 text-sm font-medium rounded-lg bg-primary-700 text-white hover:bg-primary-800 disabled:opacity-50 transition-colors"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <UserPlus className="w-4 h-4" />
                )}
                Benutzer anlegen
              </button>
            </>
          )}

          {/* Phase 2: API-Key einmalig anzeigen */}
          {newKey && newUser && (
            <>
              <div className="p-3 bg-status-fertig-bg border border-status-fertig-border rounded-lg text-sm text-status-fertig-text">
                <Check className="inline w-4 h-4 mr-1" />
                <strong>{newUser.name}</strong> wurde angelegt (Slug:{' '}
                <code className="font-mono">{newUser.slug}</code>).
              </div>

              {/* Warnung */}
              <div className="p-3 bg-status-aktiv-bg border border-status-aktiv-border rounded-lg text-xs text-status-aktiv-text">
                <strong>Jetzt kopieren!</strong> Dieser API-Key wird nicht erneut angezeigt und ist
                ab sofort aktiv.
              </div>

              {/* Key-Anzeige + Copy */}
              <div className="flex items-center gap-2 p-3 bg-surface-bg border border-surface-border rounded-lg">
                <code className="flex-1 text-xs font-mono text-ink break-all select-all">
                  {newKey}
                </code>
                <CopyButton text={newKey} />
              </div>

              <button
                onClick={handleDone}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 text-sm font-medium rounded-lg bg-primary-700 text-white hover:bg-primary-800 transition-colors"
              >
                <Check className="w-4 h-4" />
                Fertig — Key wurde gesichert
              </button>
            </>
          )}
        </div>

        {!newKey && (
          <div className="pt-4 mt-4 border-t border-surface-border flex justify-end">
            <button
              onClick={() => onClose(false)}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg transition-colors"
            >
              Abbrechen
            </button>
          </div>
        )}
      </>
    </Dialog>
  )
}

export default function UserManagement() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Dialog-State
  const [regenerateTarget, setRegenerateTarget] = useState(null) // { id, name }
  const [setKeyTarget, setSetKeyTarget] = useState(null) // { id, name }
  const [createUserOpen, setCreateUserOpen] = useState(false)

  const loadUsers = useCallback(() => {
    setLoading(true)
    setError(null)
    adminListUsers()
      .then((data) => setUsers(data.users || []))
      .catch((e) => setError(e.message || 'Fehler beim Laden der Nutzer'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  function handleRegenerateClose(didUseAsContext) {
    setRegenerateTarget(null)
    loadUsers() // Refresh masked key in table
    if (didUseAsContext) {
      window.location.reload() // Neustart damit Kunden-App den neuen Key nutzt
    }
  }

  function handleSetKeyClose() {
    setSetKeyTarget(null)
    loadUsers()
  }

  function handleCreateUserClose(didCreate) {
    setCreateUserOpen(false)
    if (didCreate) loadUsers()
  }

  function handleUseAsContext(maskedKey, userId) {
    // Wir haben nur den masked Key hier — User muss regenerate nutzen für Klartext.
    // Daher nur Hinweis; echte Nutzung läuft über den Regenerate-Dialog.
    alert(
      `Um diesen Tenant-Key als aktiven Kontext zu verwenden, nutze "Key neu generieren" — ` +
        `dann kannst du den Klartext-Key direkt als Kontext setzen.`
    )
  }

  return (
    <div>
      {/* Create-User-Dialog */}
      {createUserOpen && <CreateUserDialog onClose={handleCreateUserClose} />}

      {/* Regenerate-Dialog */}
      {regenerateTarget && (
        <NewKeyDialog
          userId={regenerateTarget.id}
          userName={regenerateTarget.name}
          onClose={handleRegenerateClose}
        />
      )}

      {/* Set-Key-Dialog */}
      {setKeyTarget && (
        <SetKeyDialog
          userId={setKeyTarget.id}
          userName={setKeyTarget.name}
          onClose={handleSetKeyClose}
        />
      )}

      {/* bewusst behalten: bg-slate-800, bg-slate-700, text-slate-400, text-slate-300,
          text-slate-500 = dunkle Admin-Seitenkörper-Oberfläche (Tabelle, Buttons) —
          kein Dark-Surface-Token vorhanden, Tier-2-Palette ist bewusst Light-only
          (Dark-Mode am 2026-08-14 entfernt, siehe tailwind.config.js). amber und teal
          sind primitive-identisch zu accent und primary und deshalb migriert. Ebenso
          bewusst behalten: bg-red-900/30|40, border-red-700/50, text-red-300 = Fehler-
          Banner und "Deaktiviert"-Badge auf dunklem Grund — das status-fehler-Token ist
          ein helles Tier-2-Token (für Badges auf weißem Grund konzipiert) und auf der
          dunklen Admin-Fläche nicht kontraststark genug. */}
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-accent-400" strokeWidth={1.75} />
            Nutzer &amp; API-Keys
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Tenant-Nutzer verwalten und API-Keys rotieren.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreateUserOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-primary-700 text-white hover:bg-primary-600 transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5" />
            Neuer Benutzer
          </button>
          <button
            onClick={loadUsers}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-xs text-red-300">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && !error && (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-8">
          <Loader2 className="w-4 h-4 animate-spin" />
          Lade Nutzer…
        </div>
      )}

      {/* Table */}
      {!loading && !error && users.length === 0 && (
        <p className="text-sm text-slate-400 py-8">Keine Nutzer gefunden.</p>
      )}

      {!loading && users.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left">
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  API-Key (maskiert)
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Erstellt
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Aktionen
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-750">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white">{u.name}</span>
                      {u.enabled === false && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-900/40 border border-red-700/50 text-red-300">
                          Deaktiviert
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">ID: {u.id}</p>
                  </td>
                  <td className="px-4 py-3">
                    <code className="text-xs font-mono text-slate-300">
                      {u.api_key_masked || '—'}
                    </code>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString('de-DE') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => setRegenerateTarget({ id: u.id, name: u.name })}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-accent-600/50 text-accent-400 hover:bg-accent-900/30 transition-colors"
                      >
                        <Key className="w-3.5 h-3.5" />
                        Key neu generieren
                      </button>
                      <button
                        onClick={() => setSetKeyTarget({ id: u.id, name: u.name })}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors"
                      >
                        API-Key setzen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-slate-500">
        Tipp: Nach "Key neu generieren" kannst du den Klartext-Key direkt als aktiven Kontext setzen
        — dann zeigen LLM Analytics und Drift-Review die Daten dieses Tenants.
      </p>
    </div>
  )
}
