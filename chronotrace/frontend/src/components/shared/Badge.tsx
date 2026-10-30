import type { EventType } from '../../types';
import { EVENT_TYPE_COLORS } from '../../utils/dateUtils';

interface BadgeProps {
  label: string;
  variant?: EventType | 'info' | 'warning' | 'error' | 'success';
  size?: 'sm' | 'md';
}

const EXTRA: Record<string, string> = {
  info:    'bg-blue-100 text-blue-800 border-blue-300',
  warning: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  error:   'bg-red-100 text-red-800 border-red-300',
  success: 'bg-green-100 text-green-800 border-green-300',
};

export default function Badge({ label, variant = 'OTHER', size = 'sm' }: BadgeProps) {
  const color = EVENT_TYPE_COLORS[variant as EventType] ?? EXTRA[variant] ?? EXTRA.info;
  const sz = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1';
  return (
    <span className={`inline-block rounded-full border font-semibold ${sz} ${color}`}>
      {label}
    </span>
  );
}

