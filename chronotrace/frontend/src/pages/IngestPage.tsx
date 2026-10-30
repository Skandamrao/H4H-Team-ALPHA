import { useState } from 'react';
import DropZone from '../components/ingest/DropZone';
import type { IngestBatchResponse } from '../types';
import { CheckCircle2, AlertTriangle } from 'lucide-react';

export default function IngestPage() {
  const [result, setResult] = useState<IngestBatchResponse | null>(null);

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Ingest Records</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload JSON batch files (meeting notes, design specs, emails, changelogs, decision logs).
          Records are appended — existing history is never overwritten.
        </p>
      </div>

      <DropZone onResult={setResult} />

      {result && (
        <div className="border border-green-300 bg-green-50 rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-green-800 font-semibold">
            <CheckCircle2 size={18} />
            Ingestion complete — Batch <code className="text-xs bg-green-100 px-1 rounded">{result.batch_id.slice(0, 8)}…</code>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              ['Records', result.records_processed],
              ['Events', result.total_events_extracted],
              ['Features', result.total_features_identified],
            ].map(([label, val]) => (
              <div key={label as string} className="bg-white border border-green-200 rounded-lg py-3">
                <p className="text-xl font-bold text-green-800">{val}</p>
                <p className="text-xs text-green-600">{label}</p>
              </div>
            ))}
          </div>

          {result.total_conflicts_detected > 0 && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              <AlertTriangle size={14} />
              {result.total_conflicts_detected} conflict(s) detected — check the Events view.
            </div>
          )}

          {result.warnings.length > 0 && (
            <div className="space-y-1">
              {result.warnings.map((w, i) => (
                <p key={i} className="text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-2 py-1">⚠ {w}</p>
              ))}
            </div>
          )}

          <details>
            <summary className="text-xs font-semibold text-gray-600 cursor-pointer">Per-record details</summary>
            <div className="mt-2 space-y-2">
              {result.results.map((r, i) => (
                <div key={i} className="text-xs bg-white border border-gray-100 rounded p-3">
                  <code className="text-gray-500">{r.source_id.slice(0, 12)}…</code>
                  <span className="ml-2 text-gray-700">{r.events_extracted} events · {r.features_identified} features · {r.conflicts_detected} conflicts</span>
                  {r.warnings.map((w, j) => <p key={j} className="text-yellow-600 mt-0.5">⚠ {w}</p>)}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

