import { useState, useEffect, useCallback } from 'react'
import { UserCog, RefreshCw, AlertCircle, Loader2, UserPlus, Check, Building2 } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import {
  adminListAccounts,
  adminListAgencies,
  adminCreateAgency,
  adminCreateAccount,
  adminUpdateAccount,
  adminDeleteAccount,
  adminListUsers as adminListTenants,
} from '../../api'

const ROLES = [
  { value: 'owner', label: 'Owner (alle Tenants der Agentur)' },
  { value: 'manager', label: 'Manager (zugewiesene Tenants)' },
  { value: 'member', label: 'Member (zugewiesene Tenants)' },
]

// Dialog: neue Agentur anlegen (nötig, jeder User braucht eine agency_id)
function CreateAgencyDialog({ onClose }) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleCreate() {
    if (!name.trim() || !slug.trim()) return
    setLoading(true)
    setError(null)
    try {
      await adminCreateAgency(name.trim(), slug.trim())
      onClose(true)
    } catch (e) {
      setError(e.message || 'Fehler beim Anlegen der Agentur')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title="Neue Agentur anlegen"
      titleIcon={Building2}
      maxWidth="md"
      closeOnBackdrop={false}
    >
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-ink mb-1.5">Name</label>
          <input
            type="text"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="z. B. Zukunftsbund"
            className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-ink mb-1.5">Slug</label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
            placeholder="z-b-zukunftsbund"
            className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink font-mono focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        {error && (
          <div className="flex items-start gap-2 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {error}
          </div>
        )}
        <button
          onClick={handleCreate}
          disabled={loading || !name.trim() || !slug.trim()}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 text-sm font-medium rounded-lg bg-primary-700 text-white hover:bg-primary-800 disabled:opacity-50 transition-colors"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Building2 className="w-4 h-4" />
          )}
          Agentur anlegen
        </button>
        <div className="flex justify-end">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg transition-colors"
          >
            Abbrechen
          </button>
        </div>
      </div>
    </Dialog>
  )
}

// Dialog: Login-Account anlegen oder bearbeiten (editUser === null → anlegen)
function AccountDialog({ editUser, agencies, tenants, onClose }) {
  const isEdit = !!editUser
  const [email, setEmail] = useState(editUser?.email || '')
  const [displayName, setDisplayName] = useState(editUser?.display_name || '')
  const [agencyId, setAgencyId] = useState(editUser?.agency_id || agencies[0]?.id || '')
  const [role, setRole] = useState(editUser?.role || 'member')
  const [password, setPassword] = useState('')
  const [tenantIds, setTenantIds] = useState(editUser?.tenants?.map((t) => t.id) || [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function toggleTenant(id) {
    setTenantIds((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]))
  }

  async function handleSave() {
    setLoading(true)
    setError(null)
    try {
      if (isEdit) {
        const patch = { display_name: displayName, role, tenant_ids: tenantIds }
        if (password.trim()) patch.password = password.trim()
        await adminUpdateAccount(editUser.id, patch)
      } else {
        if (!email.trim() || !password.trim() || !agencyId) {
          setError('E-Mail, Passwort und Agentur sind Pflicht.')
          setLoading(false)
          return
        }
        await adminCreateAccount({
          email: email.trim(),
          display_name: displayName.trim() || null,
          agency_id: agencyId,
          role,
          password: password.trim(),
          tenant_ids: tenantIds,
        })
      }
      onClose(true)
    } catch (e) {
      setError(e.message || 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={isEdit ? `Account bearbeiten — ${editUser.email}` : 'Neuen Login-Account anlegen'}
      titleIcon={UserCog}
      maxWidth="lg"
      closeOnBackdrop={false}
      contentClassName="p-5 space-y-4"
    >
      <>
        <div className="space-y-4">
          {!isEdit && (
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">E-Mail</label>
              <input
                type="email"
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="kunde@firma.de"
                className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-ink mb-1.5">
              Anzeigename (optional)
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Vor- und Nachname"
              className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {!isEdit && (
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">Agentur</label>
              <select
                value={agencyId}
                onChange={(e) => setAgencyId(e.target.value)}
                className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                {agencies.length === 0 && <option value="">Keine Agentur vorhanden</option>}
                {agencies.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-ink mb-1.5">Rolle</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-ink mb-1.5">
              {isEdit ? 'Neues Passwort (leer lassen = unverändert)' : 'Passwort'}
            </label>
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="mindestens 8 Zeichen"
              className="w-full border border-surface-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {role !== 'owner' && (
            <div>
              <label className="block text-xs font-medium text-ink mb-1.5">
                Zugewiesene Tenants
              </label>
              <div className="border border-surface-border rounded-lg divide-y divide-surface-border max-h-40 overflow-y-auto">
                {tenants.length === 0 && (
                  <p className="text-xs text-ink-muted p-3">Keine Tenants vorhanden.</p>
                )}
                {tenants.map((t) => (
                  <label
                    key={t.id}
                    className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-surface-bg"
                  >
                    <input
                      type="checkbox"
                      checked={tenantIds.includes(t.id)}
                      onChange={() => toggleTenant(t.id)}
                      className="rounded border-surface-border text-primary-700 focus:ring-primary-500"
                    />
                    {t.name}
                  </label>
                ))}
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                Bei Rolle "Owner" sind automatisch alle Tenants der Agentur sichtbar — hier keine
                Auswahl nötig.
              </p>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-status-fehler-bg border border-status-fehler-border rounded-lg text-xs text-status-fehler-text">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}
        </div>

        <div className="pt-4 mt-4 border-t border-surface-border flex justify-end gap-2">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg transition-colors"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSave}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary-700 text-white hover:bg-primary-800 disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            {isEdit ? 'Speichern' : 'Account anlegen'}
          </button>
        </div>
      </>
    </Dialog>
  )
}

export default function AccountManagement() {
  const [users, setUsers] = useState([])
  const [agencies, setAgencies] = useState([])
  const [tenants, setTenants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [editTarget, setEditTarget] = useState(undefined) // undefined = geschlossen, null = neu, {} = bearbeiten
  const [createAgencyOpen, setCreateAgencyOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  const loadAll = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([adminListAccounts(), adminListAgencies(), adminListTenants()])
      .then(([usersRes, agenciesRes, tenantsRes]) => {
        setUsers(usersRes.users || [])
        setAgencies(agenciesRes.agencies || [])
        setTenants(tenantsRes.users || [])
      })
      .catch((e) => setError(e.message || 'Fehler beim Laden'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  async function handleDelete(user) {
    setDeleteTarget(null)
    try {
      await adminDeleteAccount(user.id)
      loadAll()
    } catch (e) {
      setError(e.message || 'Fehler beim Löschen')
    }
  }

  return (
    <div>
      {editTarget !== undefined && (
        <AccountDialog
          editUser={editTarget}
          agencies={agencies}
          tenants={tenants}
          onClose={(didSave) => {
            setEditTarget(undefined)
            if (didSave) loadAll()
          }}
        />
      )}

      {createAgencyOpen && (
        <CreateAgencyDialog
          onClose={(didCreate) => {
            setCreateAgencyOpen(false)
            if (didCreate) loadAll()
          }}
        />
      )}

      <Dialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        maxWidth="sm"
        closeOnBackdrop={false}
      >
        <p className="text-sm text-ink mb-4">
          Account <strong>{deleteTarget?.email}</strong> wirklich löschen? Das kann nicht rückgängig
          gemacht werden.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setDeleteTarget(null)}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-surface-border text-ink-muted hover:bg-surface-bg"
          >
            Abbrechen
          </button>
          <button
            onClick={() => handleDelete(deleteTarget)}
            // rot bewusst behalten: kräftiger Destruktiv-Button-Ton, status-fehler-*-
            // Tokens sind für Badges/Borders auf hellem Grund gedacht, nicht kräftig
            // genug als Volltonfläche für einen Löschen-Button.
            className="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700"
          >
            Löschen
          </button>
        </div>
      </Dialog>

      {/* bewusst behalten: bg-slate-800, bg-slate-700, text-slate-400, text-slate-300,
          text-slate-500 = dunkle Admin-Seitenkörper-Oberfläche (Tabelle, Buttons) —
          kein Dark-Surface-Token vorhanden, Tier-2-Palette ist bewusst Light-only
          (Dark-Mode am 2026-08-14 entfernt, siehe tailwind.config.js). amber und teal
          sind primitive-identisch zu accent und primary und deshalb migriert. Ebenso
          bewusst behalten: bg-amber-900/30, bg-red-900/30|40, border-amber-700/50,
          border-red-700/50, text-amber-300, text-red-300, text-red-400 = Warn-/Fehler-
          Banner UND Destruktiv-Button auf dunklem Grund — die status-aktiv- und
          status-fehler-Tokens sind helle Tier-2-Tokens (für Badges auf weißem Grund
          konzipiert) und auf der dunklen Admin-Fläche nicht kontraststark genug. */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <UserCog className="w-5 h-5 text-accent-400" strokeWidth={1.75} />
            Login-Accounts
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            E-Mail+Passwort-Zugänge für Kunden verwalten (getrennt von Tenant-API-Keys).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreateAgencyOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors"
          >
            <Building2 className="w-3.5 h-3.5" />
            Neue Agentur
          </button>
          <button
            onClick={() => setEditTarget(null)}
            disabled={agencies.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-primary-700 text-white hover:bg-primary-600 disabled:opacity-40 transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5" />
            Neuer Account
          </button>
          <button
            onClick={loadAll}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </button>
        </div>
      </div>

      {agencies.length === 0 && !loading && (
        <div className="mb-4 flex items-start gap-2 p-3 bg-amber-900/30 border border-amber-700/50 rounded-lg text-xs text-amber-300">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          Noch keine Agentur vorhanden — lege zuerst eine an, bevor du Accounts erstellst.
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-start gap-2 p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-xs text-red-300">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {loading && !error && (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-8">
          <Loader2 className="w-4 h-4 animate-spin" />
          Lade Accounts…
        </div>
      )}

      {!loading && !error && users.length === 0 && (
        <p className="text-sm text-slate-400 py-8">Noch keine Login-Accounts angelegt.</p>
      )}

      {!loading && users.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left">
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  E-Mail
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Rolle
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Tenants
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Letzter Login
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
                      <span className="font-medium text-white">{u.email}</span>
                      {!u.is_active && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-900/40 border border-red-700/50 text-red-300">
                          Deaktiviert
                        </span>
                      )}
                    </div>
                    {u.display_name && (
                      <p className="text-xs text-slate-500 mt-0.5">{u.display_name}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-300">{u.role}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {u.role === 'owner'
                      ? 'alle (Agentur-weit)'
                      : u.tenants.map((t) => t.name).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {u.last_login_at
                      ? new Date(u.last_login_at).toLocaleString('de-DE')
                      : 'noch nie'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => setEditTarget(u)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors"
                      >
                        Bearbeiten
                      </button>
                      <button
                        onClick={() => setDeleteTarget(u)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-red-700/50 text-red-400 hover:bg-red-900/30 transition-colors"
                      >
                        Löschen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
