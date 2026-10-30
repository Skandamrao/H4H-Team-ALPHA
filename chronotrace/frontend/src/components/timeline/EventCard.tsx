import type { TemporalEvent } from '../../types';
import { DATE_PRECISION_LABEL, formatDate } from '../../utils/dateUtils';
import Badge from '../shared/Badge';

interface EventCardProps {
  event: TemporalEvent;
  milestoneLabel?: string | null;
}

export default function EventCard({ event, milestoneLabel }: EventCardProps) {
  return (
    <div className={`relative border rounded-xl p-4 bg-white shadow-sm hover:shadow-md transition-shadow ${event.needs_review ? 'border-yellow-400' : 'border-gray-200'}`}>
      {milestoneLabel && (
        <div className="absolute -top-3 left-4">
          <span className="bg-indigo-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
            {milestoneLabel}
          </span>
        </div>
      )}

      <div className="flex items-start justify-between gap-3 mt-1">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge label={event.event_type} variant={event.event_type} />
          {event.needs_review && <Badge label="⚠ Review" variant="warning" />}
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs font-semibold text-gray-700">
            {formatDate(event.event_date, event.event_date_raw)}
          </p>
          <p className="text-xs text-gray-400">{DATE_PRECISION_LABEL[event.event_date_precision]}</p>
        </div>
      </div>

      <p className="mt-2 text-sm text-gray-800 font-medium">{event.description}</p>

      {event.event_type === 'RENAMED' && event.previous_name && event.new_name && (
        <p className="mt-1 text-xs text-purple-700">
          <span className="line-through">{event.previous_name}</span>
          {' → '}
          <span className="font-semibold">{event.new_name}</span>
        </p>
      )}

      {event.actor && (
        <p className="mt-1 text-xs text-gray-500">👤 {event.actor}</p>
      )}

      <blockquote className="mt-2 text-xs text-gray-500 italic border-l-2 border-gray-300 pl-2 line-clamp-2">
        "{event.evidence_excerpt}"
      </blockquote>

      <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
        <span>Source: <code className="bg-gray-100 px-1 rounded">{event.source_id.slice(0, 8)}…</code></span>
        {event.extraction_confidence != null && (
          <span>Confidence: {Math.round(event.extraction_confidence * 100)}%</span>
        )}
      </div>
    </div>
  );
}

