import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { ToastProvider } from './components/ui/Toast'
import { UiModeProvider } from './hooks/useUiMode'
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
import Settings from './components/Settings'
import ExportImport from './components/ExportImport'
import Analytics from './components/Analytics'
import PublishQueue from './components/PublishQueue'
import Dialogue from './components/Dialogue'
import Memory from './components/Memory'
import CompanyProfile from './components/CompanyProfile'
import DataDeletion from './components/DataDeletion'
import MemoryViz from './components/MemoryViz'
import PipelineModels from './components/PipelineModels'
import AdminApp from './components/admin/AdminApp'

// Admin-SPA wird AUSSERHALB des Kunden-Layouts gerendert.
// Dazu teilen wir die App in zwei Äste: /admin/* und alles andere.
function CustomerApp() {
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
        <Route
          path="/brand-voice/wizard/start"
          element={<Navigate to="/brand-voice/wizard" replace />}
        />
        <Route path="/brand-voice/wizard/:sessionId" element={<WizardPage />} />
        <Route path="/brand-voice/insights" element={<VoiceInsights />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/publish" element={<PublishQueue />} />
        <Route path="/dialogue" element={<Dialogue />} />
        {/* Ins Admin-Tool (#98) ausgelagerte Screens → Redirect auf /admin (kein Kunden-Zugang, Admin-Session nötig) */}
        <Route path="/brand-voice/drift-review" element={<Navigate to="/admin/drift-quality" replace />} />
        <Route path="/brand-voice/review-queue" element={<Navigate to="/admin/drift-quality/review-queue" replace />} />
        <Route path="/settings/analytics" element={<Navigate to="/admin/llm-analytics" replace />} />
        <Route path="/settings/prompt-studio" element={<Navigate to="/admin/prompt-studio" replace />} />
        <Route path="/admin/models/backtest" element={<Navigate to="/admin/modelle" replace />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/export-import" element={<ExportImport />} />
        <Route path="/settings/pipeline-models" element={<PipelineModels />} />
        <Route path="/memory" element={<Memory />} />
        <Route path="/settings/company-profile" element={<CompanyProfile />} />
        <Route path="/settings/data-deletion" element={<DataDeletion />} />
        <Route path="/memory/viz" element={<MemoryViz />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}

function App() {
  const location = useLocation()
  const isAdmin = location.pathname.startsWith('/admin')

  return (
    <ToastProvider>
      <UiModeProvider>
        {isAdmin ? (
          // Admin-SPA: eigenes Layout, eigene Session, kein Kunden-Sidebar
          <Routes>
            <Route path="/admin/*" element={<AdminApp />} />
          </Routes>
        ) : (
          <CustomerApp />
        )}
      </UiModeProvider>
    </ToastProvider>
  )
}

export default App
