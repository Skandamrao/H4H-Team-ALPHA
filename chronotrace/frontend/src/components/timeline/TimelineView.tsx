import type { FeatureTimeline } from '../../types';
import EventCard from './EventCard';
import { AlertTriangle, Info } from 'lucide-react';

interface TimelineViewProps {
  timeline: FeatureTimeline;
}

export default function TimelineView({ timeline }: TimelineViewProps) {
  return (
    <div className="space-y-4">
      {/* Feature header */}
      <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4">
        <h2 className="text-lg font-bold text-indigo-900">{timeline.feature.canonical_name}</h2>
        <div className="flex gap-3 mt-2 flex-wrap text-xs">
          {timeline.feature.is_implemented && <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 rounded-full px-2 py-0.5 font-semibold">✓ Implemented</span>}
          {timeline.feature.is_approved && <span className="bg-green-100 text-green-800 border border-green-300 rounded-full px-2 py-0.5 font-semibold">✓ Approved</span>}
          {timeline.feature.is_removed && <span className="bg-gray-200 text-gray-600 border border-gray-300 rounded-full px-2 py-0.5 font-semibold">✗ Removed</span>}
          {timeline.feature.aliases.length > 1 && (
            <span className="bg-purple-100 text-purple-800 border border-purple-300 rounded-full px-2 py-0.5">
              Also known as: {timeline.feature.aliases.map(a => a.alias).filter(a => a !== timeline.feature.canonical_name).join(', ')}
            </span>
          )}
        </div>
      </div>

      {/* Gaps */}
      {timeline.gaps.length > 0 && (
        <div className="space-y-1">
          {timeline.gaps.map((gap, i) => (
            <div key={i} className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
              <Info size={14} className="mt-0.5 shrink-0" />
              <span>{gap}</span>
            </div>
          ))}
        </div>
      )}

      {/* Conflicts */}
      {timeline.conflicts.length > 0 && (
        <div className="space-y-1">
          {timeline.conflicts.map((conflict, i) => (
            <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-300 rounded-lg p-3 text-sm text-red-800">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{conflict}</span>
            </div>
          ))}
        </div>
      )}

      {/* Events */}
      {timeline.events.length === 0 ? (
        <p className="text-center text-gray-400 py-8">No events found for this feature.</p>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-indigo-200" />
          <div className="space-y-4 pl-10">
            {timeline.events.map(({ event, milestone_label }) => (
              <div key={event.id} className="relative">
                <div className={`absolute -left-6 top-4 w-3 h-3 rounded-full border-2 border-white ${event.event_date ? 'bg-indigo-500' : 'bg-gray-400'}`} />
                <EventCard event={event} milestoneLabel={milestone_label} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

