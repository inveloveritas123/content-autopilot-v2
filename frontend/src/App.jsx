import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import SourceList from './components/SourceList'
import Pipeline from './components/Pipeline'
import Ideas from './components/Ideas'
import Posts from './components/Posts'
import VoiceProfile from './components/VoiceProfile'
import Settings from './components/Settings'
import { setApiKey } from './api'

function App() {
  // Set default API key if not configured
  useEffect(() => {
    if (!localStorage.getItem('apiKey')) {
      setApiKey('***REMOVED-TENANT-KEY***')
    }
  }, [])

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sources" element={<SourceList />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/ideas" element={<Ideas />} />
        <Route path="/posts" element={<Posts />} />
        <Route path="/voice" element={<VoiceProfile />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}

export default App
