import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

// Synchron vor React-Mount: API-Key initialisieren
if (!localStorage.getItem('apiKey')) {
  localStorage.setItem('apiKey', '***REMOVED-TENANT-KEY-ZKG***')
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
