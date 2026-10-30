import { useEffect, useState } from 'react';
import { listFeatures, listEvents, listConflicts, getInfo } from '../api/client';
import { useAppStore } from '../stores/useAppStore';
import Badge from '../components/shared/Badge';
import type { Feature, TemporalEvent } from '../types';

export default function Dashboard() {
  const { projectId, setFeatures, setConflicts } = useAppStore();
  const [features, setLocalFeatures] = useState<Feature[]>([]);
  const [recentEvents, setRecentEvents] = useState<TemporalEvent[]>([]);
  const [conflictCount, setConflictCount] = useState(0);
  const [info, setInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listFeatures(projectId),
      listEvents(projectId, { limit: 10 }),
      listConflicts(projectId, false),
      getInfo(),
    ]).then(([f, e, c, i]) => {
      setLocalFeatures(f); setFeatures(f);
      setRecentEvents(e);
      setConflictCount(c.length); setConflicts(c);
      setInfo(i);
    }).finally(() => setLoading(false));
  }, [projectId]);

  const implemented = features.filter(f => f.is_implemented).length;
  const approved = features.filter(f => f.is_approved && !f.is_implemented).length;
  const removedCount = features.filter(f => f.is_removed).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Project: <code className="bg-gray-100 px-1 rounded">{projectId}</code>
          {info && <span className="ml-3 text-gray-400">· {info.llm_provider} / {info.llm_model}</span>}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Total Features', value: features.length, color: 'bg-indigo-50 border-indigo-200 text-indigo-900' },
          { label: 'Implemented', value: implemented, color: 'bg-emerald-50 border-emerald-200 text-emerald-900' },
          { label: 'Approved (pending)', value: approved, color: 'bg-green-50 border-green-200 text-green-900' },
          { label: 'Removed', value: removedCount, color: 'bg-gray-100 border-gray-300 text-gray-800' },
          { label: 'Conflicts', value: conflictCount, color: conflictCount > 0 ? 'bg-red-50 border-red-200 text-red-900' : 'bg-gray-50 border-gray-200 text-gray-600' },
        ].map(({ label, value, color }) => (
          <div key={label} className={`border rounded-xl p-4 ${color}`}>
            <p className="text-2xl font-bold">{loading ? '…' : value}</p>
            <p className="text-xs font-medium mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Features list */}
      <div>
        <h2 className="text-base font-semibold text-gray-800 mb-3">Known Features</h2>
        {loading ? <p className="text-sm text-gray-400">Loading…</p> : features.length === 0 ? (
          <p className="text-sm text-gray-400">No features yet. Ingest some records to get started.</p>
        ) : (
          <div className="grid gap-2">
            {features.map(f => (
              <div key={f.id} className="border border-gray-200 rounded-lg px-4 py-3 bg-white flex items-center justify-between gap-3 hover:bg-gray-50">
                <div>
                  <p className="text-sm font-medium text-gray-900">{f.canonical_name}</p>
                  {f.aliases.length > 1 && (
                    <p className="text-xs text-gray-400">
                      aka: {f.aliases.filter(a => a.alias !== f.canonical_name).map(a => a.alias).join(', ')}
                    </p>
                  )}
                </div>
                <div className="flex gap-1 flex-wrap">
                  {f.is_implemented && <Badge label="Implemented" variant="IMPLEMENTED" />}
                  {f.is_approved && !f.is_implemented && <Badge label="Approved" variant="APPROVED" />}
                  {f.is_removed && <Badge label="Removed" variant="REMOVED" />}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent events */}
      <div>
        <h2 className="text-base font-semibold text-gray-800 mb-3">Recent Events</h2>
        {loading ? <p className="text-sm text-gray-400">Loading…</p> : recentEvents.length === 0 ? (
          <p className="text-sm text-gray-400">No events yet.</p>
        ) : (
          <div className="space-y-2">
            {recentEvents.map(ev => (
              <div key={ev.id} className="border border-gray-100 rounded-lg px-4 py-2 bg-white flex items-start gap-3 text-sm">
                <Badge label={ev.event_type} variant={ev.event_type} size="sm" />
                <p className="text-gray-700 flex-1 line-clamp-1">{ev.description}</p>
                <span className="text-xs text-gray-400 shrink-0">{ev.event_date ?? '?'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

