import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

/**
 * Tenant-Init-Flow (Issue #157):
 * 1. Kein hardcodierter API-Key mehr im Bundle.
 * 2. Im Dev-Modus: VITE_DEFAULT_TENANT_KEY aus .env als Fallback.
 * 3. Prod: Key muss in localStorage stehen (gesetzt via Login/Tenant-Picker)
 *    und wird gegen GET /api/tenant-init validiert.
 */

const STORAGE_KEY = 'apiKey'

async function validateStoredKey(key) {
  try {
    const resp = await fetch('/api/tenant-init', {
      headers: { 'X-API-Key': key },
    })
    if (resp.ok) {
      const data = await resp.json()
      // Refresh stored key in case secondary key rotated to primary
      if (data.tenant_key && data.tenant_key !== key) {
        localStorage.setItem(STORAGE_KEY, data.tenant_key)
      }
      return true
    }
    return false
  } catch {
    // Network error — keep existing key, app will surface 401 errors inline
    return true
  }
}

async function initTenantKey() {
  const stored = localStorage.getItem(STORAGE_KEY)

  if (stored) {
    // Validate existing key against backend; on 401 clear it
    const valid = await validateStoredKey(stored)
    if (!valid) {
      localStorage.removeItem(STORAGE_KEY)
    }
    return
  }

  // Dev-only fallback: VITE_DEFAULT_TENANT_KEY (never bundled in prod builds
  // because Vite replaces import.meta.env.DEV with `false` during production build)
  if (import.meta.env.DEV && import.meta.env.VITE_DEFAULT_TENANT_KEY) {
    localStorage.setItem(STORAGE_KEY, import.meta.env.VITE_DEFAULT_TENANT_KEY)
  }
  // Prod ohne Key: App rendert, API-Calls liefern 401, Login-Flow greift
}

// Starte Init asynchron, render App unabhaengig davon.
// React suspense/login-guard im App-Layer behandelt den 401-Fall.
initTenantKey().catch(() => {})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
