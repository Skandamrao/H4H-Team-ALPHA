import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileText, Layers, Calendar, GitBranch, AlertTriangle, Activity } from 'lucide-react'
import { getDashboardStats } from '@/lib/api'
import StatCard from '@/components/StatCard'
import PageHeader from '@/components/PageHeader'
import { formatDateTime } from '@/lib/utils'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'

const CHART_COLORS = [
  '#7c3aed', '#3b82f6', '#10b981', '#f59e0b',
  '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899',
]

export default function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: getDashboardStats,
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-slate-400">Loading dashboard…</div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-red-400">Failed to load stats. Is the backend running?</div>
      </div>
    )
  }

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="ChronoGraph AI"
        subtitle="Temporal Product Knowledge System — Powered by Groq AI"
      />

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Link to="/documents" className="block hover:opacity-90 transition-opacity">
          <StatCard title="Documents" value={stats.total_documents} icon={FileText} color="text-blue-400" />
        </Link>
        <Link to="/evidence" className="block hover:opacity-90 transition-opacity">
          <StatCard title="Events" value={stats.total_events} icon={Calendar} color="text-purple-400" />
        </Link>
        <Link to="/features" className="block hover:opacity-90 transition-opacity">
          <StatCard title="Features" value={stats.total_features} icon={Layers} color="text-emerald-400" />
        </Link>
        <Link to="/timeline" className="block hover:opacity-90 transition-opacity">
          <StatCard title="Decisions" value={stats.total_decisions} icon={GitBranch} color="text-yellow-400" />
        </Link>
        <Link to="/evidence" className="block hover:opacity-90 transition-opacity">
          <StatCard title="Conflicts" value={stats.total_conflicts} icon={AlertTriangle} color="text-red-400" />
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Event type chart */}
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Event Type Distribution</h2>
          {stats.event_type_distribution.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
              No events yet — upload documents to start.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats.event_type_distribution} margin={{ top: 0, right: 0, bottom: 40, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="event_type"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  angle={-35}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#0d1530', border: '1px solid #7c3aed33', borderRadius: 8 }}
                  labelStyle={{ color: '#e2e8f0', fontSize: 12 }}
                  itemStyle={{ color: '#a78bfa' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {stats.event_type_distribution.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent batches */}
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Recent Ingestion Batches</h2>
          {stats.recent_batches.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
              No ingestion batches yet.
            </div>
          ) : (
            <div className="space-y-3">
              {stats.recent_batches.map(batch => (
                <div key={batch.id} className="flex items-center justify-between py-2 border-b border-slate-800/50 last:border-0">
                  <div>
                    <div className="text-sm text-slate-200">{batch.label || `Batch ${batch.id.slice(0, 8)}`}</div>
                    <div className="text-xs text-slate-500">{formatDateTime(batch.started_at)}</div>
                  </div>
                  <div className="text-right">
                    <div className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      batch.status === 'COMPLETED' ? 'bg-green-500/20 text-green-400' :
                      batch.status === 'FAILED' ? 'bg-red-500/20 text-red-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>{batch.status}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{batch.new_events_extracted} events</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Info banner */}
      <div className="rounded-xl border border-blue-900/30 bg-blue-900/10 p-4 flex items-start gap-3">
        <Activity size={16} className="text-blue-400 mt-0.5 flex-shrink-0" />
        <div className="text-sm text-slate-400">
          <span className="text-blue-300 font-medium">Getting Started: </span>
          Upload project documents on the <span className="text-white">Documents</span> page.
          ChronoGraph AI extracts historical events, tracks feature identity across renames,
          detects conflicts, builds a temporal knowledge graph, and answers historical questions.
        </div>
      </div>
    </div>
  )
}

