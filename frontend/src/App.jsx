import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import SourceList from './components/SourceList'
import Pipeline from './components/Pipeline'
import Ideas from './components/Ideas'
import Feedback from './components/Feedback'
import Posts from './components/Posts'
import Calendar from './components/Calendar'
import BrandVoice from './components/BrandVoice'
import WizardPage from './components/WizardPage'
import VoiceInsights from './components/VoiceInsights'
import DriftReview from './components/DriftReview'
import ReviewQueue from './components/ReviewQueue'
import AdminModels from './components/AdminModels'
import Settings from './components/Settings'
import ExportImport from './components/ExportImport'
import Analytics from './components/Analytics'
import LLMAnalytics from './components/LLMAnalytics'
import PublishQueue from './components/PublishQueue'
import Dialogue from './components/Dialogue'
function App() {
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
        <Route path="/voice" element={<Navigate to="/brand-voice" replace />} />
        <Route path="/brand-voice" element={<BrandVoice />} />
        <Route path="/brand-voice/wizard" element={<WizardPage />} />
        <Route path="/brand-voice/wizard/start" element={<Navigate to="/brand-voice/wizard" replace />} />
        <Route path="/brand-voice/wizard/:sessionId" element={<WizardPage />} />
        <Route path="/brand-voice/insights" element={<VoiceInsights />} />
        <Route path="/brand-voice/drift-review" element={<DriftReview />} />
        <Route path="/brand-voice/review-queue" element={<ReviewQueue />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/publish" element={<PublishQueue />} />
        <Route path="/dialogue" element={<Dialogue />} />
        <Route path="/admin/models/backtest" element={<AdminModels />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/export-import" element={<ExportImport />} />
        <Route path="/settings/analytics" element={<LLMAnalytics />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}

export default App
