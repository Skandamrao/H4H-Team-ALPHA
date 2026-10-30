import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import Dashboard from './pages/Dashboard';
import IngestPage from './pages/IngestPage';
import TimelinePage from './pages/TimelinePage';
import GraphPage from './pages/GraphPage';
import QAPage from './pages/QAPage';

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-gray-50 font-sans">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <TopBar />
          <main className="flex-1 p-6 overflow-auto">
            <Routes>
              <Route path="/"         element={<Dashboard />} />
              <Route path="/ingest"   element={<IngestPage />} />
              <Route path="/timeline" element={<TimelinePage />} />
              <Route path="/graph"    element={<GraphPage />} />
              <Route path="/ask"      element={<QAPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
