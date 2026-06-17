import { useState } from 'react'

const RAW = import.meta.env.VITE_TEST_TENANTS || ''
let TEST_TENANTS = []
try {
  if (RAW) TEST_TENANTS = JSON.parse(RAW)
} catch {
  /* invalid JSON — ignore */
}

export default function TenantSwitcher() {
  if (!TEST_TENANTS.length) return null

  const currentKey = localStorage.getItem('apiKey') || ''
  const [selected, setSelected] = useState(
    TEST_TENANTS.find((t) => t.key === currentKey)?.name || ''
  )

  function handleChange(e) {
    const tenant = TEST_TENANTS.find((t) => t.name === e.target.value)
    if (!tenant) return
    setSelected(tenant.name)
    localStorage.setItem('apiKey', tenant.key)
    // Tenant-spezifische Keys löschen damit neuer Tenant frisch startet
    localStorage.removeItem('activeProjectId')
    localStorage.removeItem('activeProjectName')
    window.location.reload()
  }

  return (
    <select
      value={selected}
      onChange={handleChange}
      className="text-xs border border-surface-border rounded-lg px-2 py-1.5 bg-white text-ink hover:border-primary-400 transition-colors"
      title="Instanz wechseln"
    >
      <option value="" disabled>
        Instanz wählen
      </option>
      {TEST_TENANTS.map((t) => (
        <option key={t.name} value={t.name}>
          {t.name}
        </option>
      ))}
    </select>
  )
}
