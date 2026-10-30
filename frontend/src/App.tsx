import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import DocumentManager from './pages/DocumentManager'
import FeatureExplorer from './pages/FeatureExplorer'
import TimelineExplorer from './pages/TimelineExplorer'
import KnowledgeGraphPage from './pages/KnowledgeGraphPage'
import AIAssistant from './pages/AIAssistant'
import EvidenceExplorer from './pages/EvidenceExplorer'
import IngestionMonitor from './pages/IngestionMonitor'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/documents" element={<DocumentManager />} />
        <Route path="/features" element={<FeatureExplorer />} />
        <Route path="/timeline" element={<TimelineExplorer />} />
        <Route path="/graph" element={<KnowledgeGraphPage />} />
        <Route path="/assistant" element={<AIAssistant />} />
        <Route path="/evidence" element={<EvidenceExplorer />} />
        <Route path="/ingestion" element={<IngestionMonitor />} />
      </Routes>
    </Layout>
  )
}

