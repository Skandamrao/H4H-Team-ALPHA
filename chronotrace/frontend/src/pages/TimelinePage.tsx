import { useEffect, useState } from 'react';
import { listFeatures, getFeatureTimeline } from '../api/client';
import { useAppStore } from '../stores/useAppStore';
import TimelineView from '../components/timeline/TimelineView';
import type { Feature, FeatureTimeline } from '../types';

export default function TimelinePage() {
  const { projectId } = useAppStore();
  const [features, setFeatures] = useState<Feature[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [timeline, setTimeline] = useState<FeatureTimeline | null>(null);
  const [asOf, setAsOf] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listFeatures(projectId).then(f => {
      setFeatures(f);
      if (f.length > 0 && !selectedId) setSelectedId(f[0].id);
    });
  }, [projectId]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    getFeatureTimeline(selectedId, asOf || undefined)
      .then(setTimeline)
      .finally(() => setLoading(false));
  }, [selectedId, asOf]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Feature Timeline</h1>
        <p className="text-sm text-gray-500 mt-1">Chronological event history for any feature.</p>
      </div>

      <div className="flex gap-3 flex-wrap items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-gray-600">Feature</label>
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
          >
            <option value="">— Select —</option>
            {features.map(f => (
              <option key={f.id} value={f.id}>{f.canonical_name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-gray-600">As of date (optional)</label>
          <input
            type="date"
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            value={asOf}
            onChange={e => setAsOf(e.target.value)}
          />
        </div>

        {asOf && (
          <button
            className="text-xs text-gray-500 hover:text-red-500 underline pb-2"
            onClick={() => setAsOf('')}
          >Clear filter</button>
        )}
      </div>

      {loading && <p className="text-sm text-indigo-600 animate-pulse">Loading timeline…</p>}

      {!loading && timeline && <TimelineView timeline={timeline} />}

      {!loading && !timeline && selectedId && (
        <p className="text-sm text-gray-400">No timeline data available.</p>
      )}

      {features.length === 0 && !loading && (
        <p className="text-sm text-gray-400">No features found. Ingest some records first.</p>
      )}
    </div>
  );
}

