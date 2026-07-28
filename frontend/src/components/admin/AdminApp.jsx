import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { adminSession } from '../../api'
import AdminLogin from './AdminLogin'
import AdminLayout from './AdminLayout'
import AdminOverview from './AdminOverview'
import UserManagement from './UserManagement'

// Bestehende Komponenten werden wiederverwendet — kein Neu-Schreiben
import LLMAnalytics from '../LLMAnalytics'
import DriftReview from '../DriftReview'
import ReviewQueue from '../ReviewQueue'
import AdminModels from '../AdminModels'
import PromptStudio from '../PromptStudio'

// Setzt apiKey für tenant-scopte Komponenten (LLMAnalytics, PromptStudio etc.)
// Nutzt den ersten Tenant aus VITE_TEST_TENANTS (= Standard/ZKG)
function setDefaultTenantKey() {
  if (localStorage.getItem('apiKey')) return // bereits gesetzt
  try {
    const tenants = JSON.parse(import.meta.env.VITE_TEST_TENANTS || '[]')
    if (tenants.length > 0) localStorage.setItem('apiKey', tenants[0].key)
  } catch {}
}

export default function AdminApp() {
  // null = noch nicht geprüft, true = eingeloggt, false = ausgeloggt
  const [authenticated, setAuthenticated] = useState(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    adminSession()
      .then((data) => {
        if (data.authenticated) setDefaultTenantKey()
        setAuthenticated(!!data.authenticated)
      })
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false))
  }, [])

  // Session-Check läuft noch
  if (checking) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    )
  }

  // Nicht eingeloggt → Login-Maske
  if (!authenticated) {
    return (
      <AdminLogin
        onAuthenticated={() => {
          setDefaultTenantKey()
          setAuthenticated(true)
        }}
      />
    )
  }

  // Eingeloggt → Admin-SPA mit eigenem Layout + Routen
  return (
    <Routes>
      <Route element={<AdminLayout onLogout={() => setAuthenticated(false)} />}>
        <Route index element={<Navigate to="uebersicht" replace />} />
        <Route path="uebersicht" element={<AdminOverview />} />
        <Route path="llm-analytics" element={<LLMAnalytics />} />
        {/* Drift + Review-Queue gemeinsam unter einem Prefix */}
        <Route path="drift-quality" element={<DriftReview />} />
        <Route path="drift-quality/review-queue" element={<ReviewQueue />} />
        <Route path="users" element={<UserManagement />} />
        <Route path="modelle" element={<AdminModels />} />
        <Route path="prompt-studio" element={<PromptStudio />} />
        {/* Fallback innerhalb /admin */}
        <Route path="*" element={<Navigate to="uebersicht" replace />} />
      </Route>
    </Routes>
  )
}
