/**
 * Data-Deletion (DSGVO Art. 17 — Right-to-be-forgotten).
 * Issue #148, Welle E.
 *
 * 4 Modi: full / memory_selective / telegram_purge / audit_selective
 * Soft-Delete mit 30-Tage Recovery-Cooldown.
 */
import { useState, useEffect } from 'react'
import { Trash2, AlertTriangle, RotateCcw, Loader2, ShieldOff } from 'lucide-react'
import { Button } from './ui/Button'
import { requestDataDeletion, listDataDeletions, recoverDataDeletion } from '../api'

const MODE_LABELS = {
  full: 'Vollständige Konto-Löschung',
  memory_selective: 'Nur Gedächtnis (memory_chunks)',
  telegram_purge: 'Nur Telegram-Daten',
  audit_selective: 'Einzelne Inhalte (mit IDs)',
}

const STATUS_BADGES = {
  pending: { label: 'Ausstehend', color: '#a16207' },
  soft_deleted: { label: 'Soft-Deleted', color: '#dc2626' },
  hard_deleted: { label: 'Hard-Deleted', color: '#7f1d1d' },
  recovered: { label: 'Wiederhergestellt', color: '#16a34a' },
  expired: { label: 'Abgelaufen', color: '#6b7280' },
  rejected: { label: 'Abgelehnt', color: '#6b7280' },
}

export default function DataDeletion() {
  const [history, setHistory] = useState([])
  const [mode, setMode] = useState('memory_selective')
  const [olderThanDays, setOlderThanDays] = useState('')
  const [classification, setClassification] = useState('')
  const [recordIds, setRecordIds] = useState('')
  const [notes, setNotes] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function loadHistory() {
    try {
      const r = await listDataDeletions()
      setHistory(r.history || [])
    } catch (e) {
      setError(e.message)
    }
  }
  useEffect(() => {
    loadHistory()
  }, [])

  async function handleSubmit() {
    setSubmitting(true)
    setError(null)
    try {
      const payload = { mode }
      if (olderThanDays) payload.older_than_days = parseInt(olderThanDays, 10)
      if (classification) payload.classification = classification
      if (mode === 'audit_selective' && recordIds) {
        payload.record_ids = recordIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      }
      if (notes) payload.notes = notes
      const r = await requestDataDeletion(payload)
      setResult(r)
      setConfirming(false)
      await loadHistory()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRecover(id) {
    if (
      !confirm(
        'Wirklich wiederherstellen? Alle soft-gelöschten Daten dieser Anfrage werden zurückgeholt.'
      )
    )
      return
    try {
      await recoverDataDeletion(id)
      await loadHistory()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
        <ShieldOff size={22} style={{ display: 'inline', marginRight: 8 }} />
        Recht auf Vergessen (DSGVO Art. 17)
      </h1>
      <p style={{ color: '#6b7280', marginBottom: 16, fontSize: 14 }}>
        Du kannst gespeicherte Daten in 4 Modi löschen. Soft-Delete mit 30 Tagen Recovery-Frist —
        danach unwiderruflich. Audit-Logs (Lösch-Anfragen) bleiben gemäß §147 AO erhalten.
      </p>

      {error && (
        <div
          style={{
            padding: 12,
            background: '#fee2e2',
            color: '#991b1b',
            borderRadius: 6,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}
      {result && (
        <div
          style={{
            padding: 12,
            background: '#fef3c7',
            color: '#78350f',
            borderRadius: 6,
            marginBottom: 12,
          }}
        >
          ✓ Lösch-Anfrage angelegt:{' '}
          {Object.entries(result.affected || {})
            .map(([k, v]) => `${k}: ${v}`)
            .join(', ')}
          <br />
          Recovery möglich bis: {new Date(result.recovery_until).toLocaleDateString('de-DE')}
        </div>
      )}

      <div
        style={{
          marginBottom: 24,
          padding: 16,
          border: '1px solid #fca5a5',
          borderRadius: 6,
          background: '#fef2f2',
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
          <AlertTriangle
            size={16}
            style={{ display: 'inline', marginRight: 4, color: '#dc2626' }}
          />
          Neue Lösch-Anfrage
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              Modus
            </label>
            <select
              data-testid="deletion-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              style={{ width: '100%', padding: 8, border: '1px solid #d1d5db', borderRadius: 4 }}
            >
              {Object.entries(MODE_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          {(mode === 'memory_selective' || mode === 'telegram_purge') && (
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Älter als (Tage, optional)
              </label>
              <input
                type="number"
                min="0"
                max="3650"
                value={olderThanDays}
                onChange={(e) => setOlderThanDays(e.target.value)}
                data-testid="deletion-older-than"
                style={{ width: '100%', padding: 8, border: '1px solid #d1d5db', borderRadius: 4 }}
              />
            </div>
          )}
          {mode === 'memory_selective' && (
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Klassifikation (optional)
              </label>
              <select
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
                style={{ width: '100%', padding: 8, border: '1px solid #d1d5db', borderRadius: 4 }}
              >
                <option value="">— alle —</option>
                <option value="werte">werte</option>
                <option value="stories">stories</option>
                <option value="konflikte">konflikte</option>
              </select>
            </div>
          )}
          {mode === 'audit_selective' && (
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Record-IDs (komma-getrennt)
              </label>
              <input
                type="text"
                value={recordIds}
                onChange={(e) => setRecordIds(e.target.value)}
                placeholder="uuid1, uuid2, ..."
                style={{ width: '100%', padding: 8, border: '1px solid #d1d5db', borderRadius: 4 }}
              />
            </div>
          )}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              Notiz (optional)
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={1000}
              style={{ width: '100%', padding: 8, border: '1px solid #d1d5db', borderRadius: 4 }}
            />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          {!confirming ? (
            <Button
              data-testid="btn-deletion-start"
              onClick={() => setConfirming(true)}
              variant="ghost"
            >
              <Trash2 size={14} /> Lösch-Anfrage prüfen
            </Button>
          ) : (
            <>
              <span style={{ marginRight: 12, color: '#991b1b', fontWeight: 600 }}>
                Sicher? {mode === 'full' && '⚠️ Löscht alle Daten + deaktiviert Konto.'}
              </span>
              <Button
                data-testid="btn-deletion-confirm"
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                {submitting ? ' Lösche…' : ' Endgültig anfordern'}
              </Button>
              <Button
                onClick={() => setConfirming(false)}
                variant="ghost"
                style={{ marginLeft: 8 }}
              >
                Abbrechen
              </Button>
            </>
          )}
        </div>
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>Verlauf</h2>
      {history.length === 0 ? (
        <p style={{ color: '#6b7280' }}>Keine Lösch-Anfragen.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>Datum</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Modus</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Status</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Betroffen</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Recovery bis</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Aktion</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => {
              const badge = STATUS_BADGES[h.status] || { label: h.status, color: '#6b7280' }
              const recoverable =
                h.status === 'soft_deleted' &&
                h.recovery_until &&
                new Date(h.recovery_until) > new Date()
              return (
                <tr key={h.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: 8 }}>
                    {new Date(h.requested_at).toLocaleDateString('de-DE')}
                  </td>
                  <td style={{ padding: 8 }}>{MODE_LABELS[h.mode] || h.mode}</td>
                  <td style={{ padding: 8 }}>
                    <span
                      style={{
                        background: badge.color,
                        color: 'white',
                        padding: '2px 8px',
                        borderRadius: 12,
                        fontSize: 11,
                      }}
                    >
                      {badge.label}
                    </span>
                  </td>
                  <td style={{ padding: 8 }}>
                    {Object.entries(h.affected || {})
                      .filter(([, v]) => v > 0)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(', ') || '—'}
                  </td>
                  <td style={{ padding: 8 }}>
                    {h.recovery_until
                      ? new Date(h.recovery_until).toLocaleDateString('de-DE')
                      : '—'}
                  </td>
                  <td style={{ padding: 8 }}>
                    {recoverable && (
                      <Button
                        data-testid={`btn-recover-${h.id}`}
                        onClick={() => handleRecover(h.id)}
                        variant="ghost"
                      >
                        <RotateCcw size={12} /> Wiederherstellen
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
