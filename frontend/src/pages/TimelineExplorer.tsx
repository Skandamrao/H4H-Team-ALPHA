import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Clock, FileText, AlertTriangle, Calendar, Search, RotateCcw, ShieldCheck } from 'lucide-react'
import { getFeatures, getFeatureTimeline } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import EventBadge from '@/components/EventBadge'
import { formatDate, EVENT_TYPE_DOTS, cn } from '@/lib/utils'

export default function TimelineExplorer() {
  const [searchParams] = useSearchParams()
  const initialFeatureId = searchParams.get('featureId')
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(initialFeatureId)
  const [featureSearch, setFeatureSearch] = useState('')
  const [asOfDate, setAsOfDate] = useState<string>('')

  const { data: featuresData } = useQuery({
    queryKey: ['features'],
    queryFn: () => getFeatures(),
  })

  useEffect(() => {
    if (featuresData?.features.length && !selectedFeatureId) {
      const paramId = searchParams.get('featureId')
      const target = paramId ? featuresData.features.find(f => f.id === paramId) : null
      setSelectedFeatureId(target ? target.id : featuresData.features[0].id)
    }
  }, [featuresData, searchParams, selectedFeatureId])

  const { data: timeline, isLoading: timelineLoading } = useQuery({
    queryKey: ['timeline', selectedFeatureId, asOfDate],
    queryFn: () => getFeatureTimeline(selectedFeatureId!, asOfDate ? asOfDate : undefined),
    enabled: !!selectedFeatureId,
  })

  const filteredFeatures = useMemo(() => {
    if (!featuresData?.features) return []
    if (!featureSearch.trim()) return featuresData.features
    const q = featureSearch.toLowerCase()
    return featuresData.features.filter(f =>
      f.canonical_name.toLowerCase().includes(q) ||
      f.aliases.some(a => a.alias.toLowerCase().includes(q))
    )
  }, [featuresData, featureSearch])

  // Infer reconstructed state as of date
  const reconstructedState = useMemo(() => {
    if (!timeline?.events || timeline.events.length === 0) return null
    const sorted = [...timeline.events].sort((a, b) => {
      const da = a.event_date ? new Date(a.event_date).getTime() : 0
      const db = b.event_date ? new Date(b.event_date).getTime() : 0
      return da - db
    })
    const lastEvent = sorted[sorted.length - 1]
    let state = 'PROPOSED'
    if (sorted.some(e => e.event_type === 'FEATURE_REMOVED')) {
      state = 'REMOVED'
    } else if (sorted.some(e => e.event_type === 'FEATURE_DEPRECATED')) {
      state = 'DEPRECATED'
    } else if (sorted.some(e => e.event_type === 'FEATURE_IMPLEMENTED')) {
      state = 'IMPLEMENTED'
    } else if (sorted.some(e => e.decision_status === 'APPROVED' || e.event_type === 'DECISION_APPROVED')) {
      state = 'APPROVED'
    }
    return { state, lastEvent }
  }, [timeline])

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Timeline & Historical State Reconstruction"
        subtitle="Explore feature history or time-travel to reconstruct exact feature state at any past date"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Feature list */}
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 overflow-hidden flex flex-col h-[680px]">
          <div className="p-3 border-b border-slate-800/50 space-y-2">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Features ({filteredFeatures.length})</div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search features..."
                value={featureSearch}
                onChange={e => setFeatureSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-slate-900/60 border border-slate-700/50 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500/50"
              />
            </div>
          </div>
          <div className="divide-y divide-slate-800/30 overflow-y-auto flex-1">
            {!filteredFeatures.length ? (
              <div className="p-6 text-center text-slate-500 text-xs">No matching features found.</div>
            ) : (
              filteredFeatures.map(f => (
                <button
                  key={f.id}
                  className={cn(
                    'w-full text-left px-4 py-3 hover:bg-slate-800/30 transition-colors',
                    selectedFeatureId === f.id && 'bg-purple-900/20 border-l-2 border-purple-500'
                  )}
                  onClick={() => setSelectedFeatureId(f.id)}
                >
                  <div className="text-sm font-medium text-slate-200">{f.canonical_name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{f.event_count} events</div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Timeline */}
        <div className="lg:col-span-2 rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5 flex flex-col h-[680px]">
          {/* Header controls: Date filter for Historical State Reconstruction */}
          <div className="pb-4 border-b border-slate-800/50 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">{timeline?.feature_name || 'Feature Timeline'}</h2>
              {timeline?.aliases && timeline.aliases.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  <span className="text-[11px] text-slate-500">Aliases:</span>
                  {timeline.aliases.map((a, i) => (
                    <span key={i} className="text-[11px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/50">{a}</span>
                  ))}
                </div>
              )}
            </div>

            {/* Time travel picker */}
            <div className="flex items-center gap-2 bg-slate-900/70 border border-purple-900/40 rounded-lg p-1.5">
              <Calendar size={14} className="text-purple-400 ml-1" />
              <label className="text-xs text-slate-400 whitespace-nowrap">As of date:</label>
              <input
                type="date"
                value={asOfDate}
                onChange={e => setAsOfDate(e.target.value)}
                className="bg-slate-800 border border-slate-700/60 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-purple-400"
              />
              {asOfDate && (
                <button
                  onClick={() => setAsOfDate('')}
                  className="p-1 text-slate-400 hover:text-slate-200 text-xs rounded hover:bg-slate-800"
                  title="Reset to full timeline"
                >
                  <RotateCcw size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Historical State Banner */}
          {asOfDate && reconstructedState && (
            <div className="mt-3 p-3 rounded-lg border border-purple-500/30 bg-purple-950/30 flex items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2 text-purple-300">
                <ShieldCheck size={16} className="text-purple-400 flex-shrink-0" />
                <div>
                  <span className="font-semibold">Historical State on {asOfDate}: </span>
                  <span className={cn(
                    'px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider',
                    reconstructedState.state === 'IMPLEMENTED' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' :
                    reconstructedState.state === 'APPROVED' ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40' :
                    reconstructedState.state === 'REMOVED' ? 'bg-red-500/20 text-red-300 border border-red-500/40' :
                    'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40'
                  )}>
                    {reconstructedState.state}
                  </span>
                  <span className="text-slate-400 ml-2">
                    (Reconstructed strictly using events on or before this date)
                  </span>
                </div>
              </div>
              <span className="text-slate-500">{timeline?.events.length} event(s) recorded</span>
            </div>
          )}

          {/* Scrollable event list */}
          <div className="flex-1 overflow-y-auto mt-4 pr-1">
            {!selectedFeatureId ? (
              <div className="h-64 flex items-center justify-center text-slate-500">
                <div className="text-center">
                  <Clock size={32} className="mx-auto mb-2 opacity-30" />
                  <div>Select a feature to see its timeline</div>
                </div>
              </div>
            ) : timelineLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-500 animate-pulse">Loading timeline…</div>
            ) : !timeline ? (
              <div className="h-64 flex items-center justify-center text-red-400">Failed to load timeline</div>
            ) : timeline.events.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-sm">
                {asOfDate ? `No events recorded for this feature on or before ${asOfDate}.` : 'No events recorded for this feature.'}
              </div>
            ) : (
              <div className="relative pl-6">
                {/* Timeline vertical track */}
                <div className="absolute left-2.5 top-2 bottom-2 w-px bg-slate-700/50" />

                <div className="space-y-4">
                  {timeline.events.map((event) => (
                    <div key={event.event_id} className="relative">
                      {/* Dot */}
                      <div className={cn(
                        'absolute -left-[19px] top-4 w-3 h-3 rounded-full border-2 border-[#111b40]',
                        EVENT_TYPE_DOTS[event.event_type] || 'bg-slate-500'
                      )} />

                      <div className={cn(
                        'rounded-lg border p-4 transition-colors',
                        event.has_conflict
                          ? 'border-red-500/40 bg-red-900/10'
                          : 'border-slate-700/50 bg-slate-800/30 hover:bg-slate-800/50'
                      )}>
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span className="text-xs font-mono text-purple-300">
                            {event.event_date ? formatDate(event.event_date) : 'Unknown date'}
                            {event.event_date_confidence !== 'HIGH' && (
                              <span className="ml-1 text-slate-500 text-[10px]">({event.event_date_confidence.toLowerCase()})</span>
                            )}
                          </span>
                          <EventBadge eventType={event.event_type} />
                          {event.decision_status && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                              Status: {event.decision_status}
                            </span>
                          )}
                          {event.has_conflict && (
                            <div className="flex items-center gap-1 text-xs text-red-400 font-medium">
                              <AlertTriangle size={12} />
                              Conflict Flagged
                            </div>
                          )}
                        </div>
                        <div className="text-sm font-medium text-white">{event.title}</div>
                        {event.description && (
                          <div className="text-xs text-slate-300 mt-1 leading-relaxed">{event.description}</div>
                        )}
                        {event.reason && (
                          <div className="text-xs text-slate-400 mt-1.5 italic bg-slate-900/40 p-2 rounded border border-slate-800/60">
                            <span className="text-slate-500 font-medium not-italic">Reason: </span>{event.reason}
                          </div>
                        )}
                        {event.source_document_filename && (
                          <div className="flex items-center gap-1 mt-2 text-xs text-slate-500">
                            <FileText size={11} className="text-slate-500" />
                            Source: <span className="text-slate-400">{event.source_document_filename}</span>
                          </div>
                        )}
                        {event.evidence?.map(ev => (
                          <div key={ev.id} className="mt-2 p-2 rounded bg-slate-900/50 text-xs text-slate-300 font-mono border-l-2 border-purple-500/50">
                            "{ev.excerpt.slice(0, 220)}{ev.excerpt.length > 220 ? '…' : ''}"
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

