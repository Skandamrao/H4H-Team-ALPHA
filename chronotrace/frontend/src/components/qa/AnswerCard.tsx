import type { QuestionAnswer } from '../../types';
import { ANSWER_STATUS_COLORS } from '../../utils/dateUtils';
import Badge from '../shared/Badge';
import EventCard from '../timeline/EventCard';
import { AlertTriangle, CheckCircle2, HelpCircle, AlertCircle } from 'lucide-react';

const STATUS_ICONS: Record<string, any> = {
  SUPPORTED:             CheckCircle2,
  PARTIALLY_SUPPORTED:   HelpCircle,
  CONFLICTED:            AlertTriangle,
  INSUFFICIENT_EVIDENCE: AlertCircle,
};

interface AnswerCardProps {
  answer: QuestionAnswer;
}

export default function AnswerCard({ answer }: AnswerCardProps) {
  const statusColor = ANSWER_STATUS_COLORS[answer.status];
  const Icon = STATUS_ICONS[answer.status] ?? HelpCircle;

  return (
    <div className={`border-2 rounded-xl p-5 space-y-4 ${statusColor}`}>
      {/* Status + confidence */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon size={16} />
          <Badge label={answer.status.replace('_', ' ')} variant={
            answer.status === 'SUPPORTED' ? 'APPROVED' :
            answer.status === 'PARTIALLY_SUPPORTED' ? 'MODIFIED' :
            answer.status === 'CONFLICTED' ? 'REJECTED' : 'OTHER'
          } />
        </div>
        <span className="text-xs font-semibold">
          Confidence: {Math.round(answer.confidence * 100)}%
        </span>
      </div>

      {/* Question */}
      <p className="text-sm font-semibold italic">Q: {answer.question}</p>

      {/* Answer */}
      <div className="bg-white/60 rounded-lg p-4 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
        {answer.answer}
      </div>

      {/* Cited sources */}
      {answer.cited_source_ids.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-wide mb-1">📎 Cited Sources</p>
          <div className="flex flex-wrap gap-1">
            {answer.cited_source_ids.map(id => (
              <code key={id} className="text-xs bg-white/70 border border-gray-300 rounded px-2 py-0.5">{id.slice(0, 8)}…</code>
            ))}
          </div>
        </div>
      )}

      {/* Missing info / gaps */}
      {answer.missing_information.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-wide mb-1">🕳 Information Gaps</p>
          <ul className="space-y-1">
            {answer.missing_information.map((m, i) => (
              <li key={i} className="text-xs text-gray-700">• {m}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Supporting evidence */}
      {answer.supporting_evidence.length > 0 && (
        <details>
          <summary className="text-xs font-bold uppercase tracking-wide cursor-pointer select-none">
            📋 Supporting Evidence ({answer.supporting_evidence.length})
          </summary>
          <div className="mt-3 space-y-3">
            {answer.supporting_evidence.map(({ event, relevance_note }) => (
              <div key={event.id}>
                <EventCard event={event} />
                <p className="text-xs text-gray-500 mt-1 pl-2">↳ {relevance_note}</p>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Conflicting events */}
      {answer.conflicting_events.length > 0 && (
        <details>
          <summary className="text-xs font-bold text-red-700 uppercase tracking-wide cursor-pointer select-none">
            ⚔ Conflicting Events ({answer.conflicting_events.length})
          </summary>
          <div className="mt-3 space-y-3">
            {answer.conflicting_events.map(ev => (
              <EventCard key={ev.id} event={ev} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

