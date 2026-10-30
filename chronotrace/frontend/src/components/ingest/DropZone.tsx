import { useState, useRef } from 'react';
import { Upload, FileText, X } from 'lucide-react';
import type { IngestBatchResponse } from '../../types';
import { ingestBatch } from '../../api/client';
import { useAppStore } from '../../stores/useAppStore';

interface DropZoneProps {
  onResult: (r: IngestBatchResponse) => void;
}

export default function DropZone({ onResult }: DropZoneProps) {
  const { projectId } = useAppStore();
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const processFiles = async (selected: File[]) => {
    setFiles(selected);
    setError(null);
    setLoading(true);
    try {
      const records: object[] = [];
      for (const file of selected) {
        const text = await file.text();
        if (file.name.endsWith('.json')) {
          const parsed = JSON.parse(text);
          if (Array.isArray(parsed)) records.push(...parsed);
          else records.push(parsed);
        } else {
          // Plain text / markdown — wrap as a generic record
          records.push({
            project_id: projectId,
            record_type: 'other',
            title: file.name,
            content: text,
          });
        }
      }
      // Ensure project_id is set on all records
      const stamped = records.map(r => ({ project_id: projectId, ...(r as object) }));
      const result = await ingestBatch(stamped);
      onResult(result);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Ingestion failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors
          ${dragging ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400 bg-gray-50'}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault(); setDragging(false);
          processFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <Upload className="mx-auto mb-3 text-indigo-400" size={32} />
        <p className="text-sm font-medium text-gray-700">Drop JSON batch files here</p>
        <p className="text-xs text-gray-400 mt-1">or click to browse — supports .json and .txt</p>
        <input
          ref={fileRef}
          type="file"
          accept=".json,.txt,.md"
          multiple
          className="hidden"
          onChange={e => processFiles(Array.from(e.target.files ?? []))}
        />
      </div>

      {files.length > 0 && (
        <div className="space-y-1">
          {files.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
              <FileText size={14} /> {f.name}
              <button onClick={() => setFiles(fs => fs.filter((_, j) => j !== i))}>
                <X size={12} className="text-gray-400 hover:text-red-500" />
              </button>
            </div>
          ))}
        </div>
      )}

      {loading && <p className="text-sm text-indigo-600 animate-pulse">⏳ Ingesting records…</p>}
      {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">{error}</p>}
    </div>
  );
}

