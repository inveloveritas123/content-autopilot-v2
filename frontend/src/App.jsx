import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import SourceList from './components/SourceList'
import Pipeline from './components/Pipeline'
import ContentPreview from './components/ContentPreview'
import ContentCalendar from './components/ContentCalendar'
import Settings from './components/Settings'
import { setApiKey } from './api'

function App() {
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('darkMode') === 'true')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    localStorage.setItem('darkMode', darkMode)
  }, [darkMode])

  // Set default API key if not configured
  useEffect(() => {
    if (!localStorage.getItem('apiKey')) {
      setApiKey('***REMOVED-TENANT-KEY***')
    }
  }, [])

  return (
    <Layout darkMode={darkMode} onToggleDark={() => setDarkMode(!darkMode)}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sources" element={<SourceList />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/content" element={<ContentPreview />} />
        <Route path="/calendar" element={<ContentCalendar />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}

export default App
