import type { EventType, AnswerStatus, DatePrecision } from '../types';

export const EVENT_TYPE_COLORS: Record<EventType, string> = {
  PROPOSED:         'bg-blue-100 text-blue-800 border-blue-300',
  APPROVED:         'bg-green-100 text-green-800 border-green-300',
  REJECTED:         'bg-red-100 text-red-800 border-red-300',
  IMPLEMENTED:      'bg-emerald-100 text-emerald-800 border-emerald-300',
  MODIFIED:         'bg-yellow-100 text-yellow-800 border-yellow-300',
  RENAMED:          'bg-purple-100 text-purple-800 border-purple-300',
  REMOVED:          'bg-gray-100 text-gray-600 border-gray-300',
  DEPENDENCY_ADDED: 'bg-orange-100 text-orange-800 border-orange-300',
  OTHER:            'bg-slate-100 text-slate-700 border-slate-300',
};

export const ANSWER_STATUS_COLORS: Record<AnswerStatus, string> = {
  SUPPORTED:             'bg-green-50 border-green-400 text-green-900',
  PARTIALLY_SUPPORTED:   'bg-yellow-50 border-yellow-400 text-yellow-900',
  CONFLICTED:            'bg-red-50 border-red-400 text-red-900',
  INSUFFICIENT_EVIDENCE: 'bg-gray-50 border-gray-400 text-gray-700',
};

export const DATE_PRECISION_LABEL: Record<DatePrecision, string> = {
  exact:        '📅 Exact',
  approximate:  '~️ Approx.',
  month:        '🗓 Month',
  quarter:      '📆 Quarter',
  year:         '📆 Year',
  unknown:      '❓ Unknown',
};

export function formatDate(d: string | null, raw: string | null): string {
  if (d) return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  if (raw) return raw;
  return 'Unknown date';
}

