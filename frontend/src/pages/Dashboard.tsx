import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  FileText,
  Layers,
  Calendar,
  GitBranch,
  AlertTriangle,
  Activity,
  ArrowRight,
  Upload,
  Network,
  MessageSquare,
  Sparkles,
  RefreshCw,
} from 'lucide-react'
import { getDashboardStats } from '@/lib/api'
import StatCard from '@/components/StatCard'
import PageHeader from '@/components/PageHeader'
import { formatDateTime } from '@/lib/utils'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const CHART_COLORS = [
  '#8b5cf6',
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#06b6d4',
  '#ec4899',
  '#a855f7',
]

function formatEventTypeLabel(type: string): string {
  return type
    .replace(/^FEATURE_/, '')
    .replace(/^DECISION_/, '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

const SAMPLE_QUESTIONS = [
  'Why was Google Authentication introduced?',
  'When was the Auth module renamed?',
  'Which features were approved but not yet implemented?',
  'Were there any conflicting decisions?',
]

export default function Dashboard() {
  const navigate = useNavigate()
  const {
    data: stats,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: getDashboardStats,
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <RefreshCw size={28} className="animate-spin text-purple-400" />
        <div className="text-sm text-slate-400">Loading temporal product intelligence…</div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <div className="text-red-400 font-medium">Failed to connect to backend server.</div>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 rounded-lg bg-slate-800 text-sm text-slate-300 hover:text-white"
        >
          Retry Connection
        </button>
      </div>
    )
  }

  const formattedChartData = stats.event_type_distribution.map((item) => ({
    ...item,
    displayLabel: formatEventTypeLabel(item.event_type),
  }))

  return (
    <div className="px-6 py-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <PageHeader
        title="ChronoGraph AI"
        subtitle="AI-Powered Temporal Product Knowledge System — Historical Evolution & Grounded Intelligence"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-xs text-slate-300 transition-colors border border-slate-700/50"
            >
              <RefreshCw size={13} className={isFetching ? 'animate-spin text-purple-400' : ''} />
              <span>Refresh</span>
            </button>
            <button
              onClick={() => navigate('/documents')}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-xs font-medium text-white transition-colors shadow-sm"
            >
              <Upload size={13} />
              <span>Upload Records</span>
            </button>
          </div>
        }
      />

      {/* Quick Action Navigation Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Link
          to="/graph"
          className="flex items-center justify-between p-3.5 rounded-xl border border-purple-900/30 bg-gradient-to-r from-purple-950/30 to-[#0e1638]/60 hover:border-purple-500/40 transition-all group"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-600/20 text-purple-300 border border-purple-500/30">
              <Network size={16} />
            </div>
            <div>
              <div className="text-xs font-semibold text-white group-hover:text-purple-300 transition-colors">
                Temporal Knowledge Graph
              </div>
              <div className="text-[11px] text-slate-400">Dagre hierarchical layout</div>
            </div>
          </div>
          <ArrowRight
            size={14}
            className="text-slate-500 group-hover:text-purple-400 transition-transform group-hover:translate-x-0.5"
          />
        </Link>

        <Link
          to="/assistant"
          className="flex items-center justify-between p-3.5 rounded-xl border border-blue-900/30 bg-gradient-to-r from-blue-950/30 to-[#0e1638]/60 hover:border-blue-500/40 transition-all group"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-600/20 text-blue-300 border border-blue-500/30">
              <MessageSquare size={16} />
            </div>
            <div>
              <div className="text-xs font-semibold text-white group-hover:text-blue-300 transition-colors">
                AI Historical Assistant
              </div>
              <div className="text-[11px] text-slate-400">Evidence-grounded Q&A</div>
            </div>
          </div>
          <ArrowRight
            size={14}
            className="text-slate-500 group-hover:text-blue-400 transition-transform group-hover:translate-x-0.5"
          />
        </Link>

        <Link
          to="/timeline"
          className="flex items-center justify-between p-3.5 rounded-xl border border-emerald-900/30 bg-gradient-to-r from-emerald-950/30 to-[#0e1638]/60 hover:border-emerald-500/40 transition-all group"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-600/20 text-emerald-300 border border-emerald-500/30">
              <Calendar size={16} />
            </div>
            <div>
              <div className="text-xs font-semibold text-white group-hover:text-emerald-300 transition-colors">
                Feature Timelines
              </div>
              <div className="text-[11px] text-slate-400">Lifecycle & time-travel</div>
            </div>
          </div>
          <ArrowRight
            size={14}
            className="text-slate-500 group-hover:text-emerald-400 transition-transform group-hover:translate-x-0.5"
          />
        </Link>
      </div>

      {/* Primary KPI Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Link to="/documents" className="block hover:opacity-95 transition-opacity">
          <StatCard
            title="Documents"
            value={stats.total_documents}
            icon={FileText}
            color="text-blue-400"
            subtitle="Ingested records"
          />
        </Link>
        <Link to="/evidence" className="block hover:opacity-95 transition-opacity">
          <StatCard
            title="Events"
            value={stats.total_events}
            icon={Calendar}
            color="text-purple-400"
            subtitle="Extracted lifecycle points"
          />
        </Link>
        <Link to="/features" className="block hover:opacity-95 transition-opacity">
          <StatCard
            title="Features"
            value={stats.total_features}
            icon={Layers}
            color="text-emerald-400"
            subtitle="Canonical entities"
          />
        </Link>
        <Link to="/timeline" className="block hover:opacity-95 transition-opacity">
          <StatCard
            title="Decisions"
            value={stats.total_decisions}
            icon={GitBranch}
            color="text-yellow-400"
            subtitle="Proposals & approvals"
          />
        </Link>
        <Link to="/evidence" className="block hover:opacity-95 transition-opacity">
          <StatCard
            title="Conflicts"
            value={stats.total_conflicts}
            icon={AlertTriangle}
            color="text-red-400"
            subtitle="Contradictions flagged"
          />
        </Link>
      </div>

      {/* Main Charts & Analytics Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Event Type Distribution Chart */}
        <div className="rounded-xl border border-purple-900/30 bg-[#0d1530]/90 p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-200">Historical Event Breakdown</h2>
              <p className="text-xs text-slate-500">Distribution across feature lifecycle states</p>
            </div>
            <span className="text-[11px] font-mono text-purple-400 bg-purple-950/40 px-2 py-0.5 rounded border border-purple-800/40">
              {stats.total_events} total
            </span>
          </div>

          {stats.event_type_distribution.length === 0 ? (
            <div className="h-56 flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
              <Calendar size={28} className="opacity-30" />
              <span>No historical events extracted yet.</span>
              <Link to="/documents" className="text-xs text-purple-400 hover:underline">
                Upload documents to begin
              </Link>
            </div>
          ) : (
            <div className="h-60 w-full pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={formattedChartData}
                  margin={{ top: 10, right: 10, bottom: 45, left: -15 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2548" vertical={false} />
                  <XAxis
                    dataKey="displayLabel"
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    angle={-30}
                    textAnchor="end"
                    interval={0}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    allowDecimals={false}
                    stroke="#1a2548"
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#090e24',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      borderRadius: 8,
                      fontSize: '12px',
                    }}
                    labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
                    formatter={(val: number) => [`${val} events`, 'Count']}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {formattedChartData.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Recent Ingestion Batches */}
        <div className="rounded-xl border border-purple-900/30 bg-[#0d1530]/90 p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-200">Recent Ingestion Batches</h2>
              <p className="text-xs text-slate-500">Pipeline runs with AI extraction status</p>
            </div>
            <Link to="/ingestion" className="text-xs text-purple-400 hover:text-purple-300">
              View all
            </Link>
          </div>

          {stats.recent_batches.length === 0 ? (
            <div className="h-56 flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
              <FileText size={28} className="opacity-30" />
              <span>No document batches ingested yet.</span>
            </div>
          ) : (
            <div className="space-y-2.5 overflow-y-auto max-h-60 pr-1">
              {stats.recent_batches.map((batch) => (
                <div
                  key={batch.id}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition-colors"
                >
                  <div className="min-w-0 flex-1 mr-3">
                    <div className="text-xs font-medium text-slate-200 truncate">
                      {batch.label || `Batch ${batch.id.slice(0, 8)}`}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {formatDateTime(batch.started_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[11px] font-mono text-purple-300 bg-purple-950/50 px-2 py-0.5 rounded border border-purple-800/40">
                      +{batch.new_events_extracted} events
                    </span>
                    <span
                      className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${
                        batch.status === 'COMPLETED'
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : batch.status === 'FAILED'
                          ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                          : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                      }`}
                    >
                      {batch.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Suggested Historical Queries */}
      <div className="rounded-xl border border-purple-900/30 bg-[#0d1530]/80 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={16} className="text-purple-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Ask ChronoGraph AI — Instant Historical Verification
          </h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {SAMPLE_QUESTIONS.map((q, i) => (
            <button
              key={i}
              onClick={() => navigate(`/assistant?q=${encodeURIComponent(q)}`)}
              className="text-left p-3 rounded-lg bg-slate-900/70 hover:bg-purple-950/40 border border-slate-800/80 hover:border-purple-600/40 text-xs text-slate-300 hover:text-purple-200 transition-all flex items-start justify-between group"
            >
              <span>{q}</span>
              <ArrowRight
                size={12}
                className="opacity-0 group-hover:opacity-100 text-purple-400 mt-0.5 ml-2 flex-shrink-0 transition-opacity"
              />
            </button>
          ))}
        </div>
      </div>

      {/* System Status Banner */}
      <div className="rounded-xl border border-blue-900/30 bg-blue-950/20 p-4 flex items-start gap-3">
        <Activity size={16} className="text-blue-400 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-slate-400 leading-relaxed">
          <span className="text-blue-300 font-medium">Temporal Grounding Guarantee: </span>
          ChronoGraph AI strictly differentiates event occurrence dates from document ingestion
          dates. All answers are anchored in verified source excerpts. AI responses are cached for
          instant retrieval and automatically re-evaluated when new records are uploaded.
        </div>
      </div>
    </div>
  )
}
