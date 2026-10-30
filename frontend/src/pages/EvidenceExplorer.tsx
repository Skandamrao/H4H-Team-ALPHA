import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getEvents } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import EventBadge from '@/components/EventBadge'
import { formatDate } from '@/lib/utils'
import { Search, FileText, AlertTriangle } from 'lucide-react'

export default function EvidenceExplorer() {
  const [searchTerm, setSearchTerm] = useState('')
  const [onlyConflicts, setOnlyConflicts] = useState(false)
  const [selectedType, setSelectedType] = useState<string>('ALL')

  const { data, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => getEvents(),
  })

  const filteredEvents = useMemo(() => {
    if (!data?.events) return []
    return data.events.filter(e => {
      if (onlyConflicts && !e.has_conflict) return false
      if (selectedType !== 'ALL' && e.event_type !== selectedType) return false
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase()
        const text = `${e.title} ${e.description || ''} ${e.feature_name || ''} ${e.reason || ''} ${e.supporting_text || ''}`.toLowerCase()
        if (!text.includes(term)) return false
      }
      return true
    })
  }, [data?.events, searchTerm, onlyConflicts, selectedType])

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Evidence Explorer"
        subtitle="Browse extracted events with their source evidence, confidence scores, and conflict flags"
      />

      {/* Filter toolbar */}
      <div className="flex flex-wrap items-center gap-3 p-3.5 rounded-xl border border-purple-900/30 bg-[#111b40]/80">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search evidence by keyword or feature..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full bg-slate-900/60 border border-slate-700/60 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        <button
          onClick={() => setOnlyConflicts(c => !c)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            onlyConflicts
              ? 'bg-red-500/20 text-red-300 border-red-500/40'
              : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:text-slate-200'
          }`}
        >
          <AlertTriangle size={13} className={onlyConflicts ? 'text-red-400' : 'text-slate-500'} />
          Only Conflicts
        </button>

        <select
          value={selectedType}
          onChange={e => setSelectedType(e.target.value)}
          className="bg-slate-900/60 border border-slate-700/60 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-purple-500"
        >
          <option value="ALL">All Event Types</option>
          <option value="FEATURE_INTRODUCED">Feature Introduced</option>
          <option value="FEATURE_MODIFIED">Feature Modified</option>
          <option value="FEATURE_IMPLEMENTED">Feature Implemented</option>
          <option value="FEATURE_RENAMED">Feature Renamed</option>
          <option value="FEATURE_DEPRECATED">Feature Deprecated</option>
          <option value="FEATURE_REMOVED">Feature Removed</option>
          <option value="DECISION_PROPOSED">Decision Proposed</option>
          <option value="DECISION_APPROVED">Decision Approved</option>
          <option value="DECISION_REJECTED">Decision Rejected</option>
          <option value="MODULE_CREATED">Module Created</option>
          <option value="MODULE_MODIFIED">Module Modified</option>
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-slate-500">Loading events…</div>
      ) : !filteredEvents.length ? (
        <div className="text-center py-16 text-slate-500">
          <Search size={40} className="mx-auto mb-3 opacity-30" />
          <div>No events matching your filters.</div>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredEvents.map(event => (
            <div
              key={event.id}
              className={`rounded-xl border p-5 ${
                event.has_conflict
                  ? 'border-red-500/30 bg-red-950/10'
                  : 'border-purple-900/30 bg-[#111b40]/80'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <EventBadge eventType={event.event_type} />
                {event.decision_status && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400 border border-slate-600/30">
                    {event.decision_status}
                  </span>
                )}
                {event.has_conflict && (
                  <span className="flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-red-500/20 text-red-300 border border-red-500/40 font-semibold">
                    <AlertTriangle size={12} />
                    Conflict Detected
                  </span>
                )}
                <span className="text-xs font-mono text-slate-500">
                  {event.event_date ? formatDate(event.event_date) : 'Unknown date'}
                </span>
                <span className="text-xs text-slate-600">confidence: {(event.confidence_score * 100).toFixed(0)}%</span>
              </div>

              <div className="text-sm font-semibold text-white mb-1">{event.title}</div>
              {event.feature_name && (
                <div className="text-xs text-purple-400 mb-2">Feature: {event.feature_name}</div>
              )}
              {event.description && (
                <div className="text-xs text-slate-400 mb-2">{event.description}</div>
              )}
              {event.reason && (
                <div className="text-xs text-slate-500 italic mb-2">Reason: {event.reason}</div>
              )}

              {event.evidence.map(ev => (
                <div key={ev.id} className="mt-2 p-3 rounded-lg bg-slate-900/60 border-l-2 border-purple-600/40">
                  <div className="flex items-center gap-1.5 mb-1">
                    <FileText size={11} className="text-slate-600" />
                    <span className="text-xs text-slate-500">{ev.document_filename}</span>
                  </div>
                  <div className="text-xs font-mono text-slate-400">
                    "{ev.excerpt}"
                  </div>
                </div>
              ))}

              {event.source_document_filename && (
                <div className="mt-2 text-xs text-slate-600 flex items-center gap-1">
                  <FileText size={10} />
                  Source: {event.source_document_filename}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

