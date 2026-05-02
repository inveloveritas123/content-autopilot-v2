import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import SourceList from './components/SourceList'
import Pipeline from './components/Pipeline'
import Ideas from './components/Ideas'
import Feedback from './components/Feedback'
import Posts from './components/Posts'
import Calendar from './components/Calendar'
import VoiceProfile from './components/VoiceProfile'
import BrandVoice from './components/BrandVoice'
import WizardPage from './components/WizardPage'
import VoiceInsights from './components/VoiceInsights'
import DriftReview from './components/DriftReview'
import Settings from './components/Settings'
import Analytics from './components/Analytics'
import PublishQueue from './components/PublishQueue'
import Dialogue from './components/Dialogue'
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
        <Route path="/feedback" element={<Feedback />} />
        <Route path="/posts" element={<Posts />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/voice" element={<VoiceProfile />} />
        <Route path="/brand-voice" element={<BrandVoice />} />
        <Route path="/brand-voice/wizard" element={<WizardPage />} />
        <Route path="/brand-voice/wizard/:sessionId" element={<WizardPage />} />
        <Route path="/brand-voice/insights" element={<VoiceInsights />} />
        <Route path="/brand-voice/drift-review" element={<DriftReview />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/publish" element={<PublishQueue />} />
        <Route path="/dialogue" element={<Dialogue />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}

export default App
