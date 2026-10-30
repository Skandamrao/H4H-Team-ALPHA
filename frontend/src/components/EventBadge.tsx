import { cn } from '@/lib/utils'
import { EVENT_TYPE_COLORS } from '@/lib/utils'

interface EventBadgeProps {
  eventType: string
  className?: string
}

function humanise(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function EventBadge({ eventType, className }: EventBadgeProps) {
  const colorClass = EVENT_TYPE_COLORS[eventType] || 'bg-slate-500/20 text-slate-300 border-slate-500/30'
  return (
    <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border', colorClass, className)}>
      {humanise(eventType)}
    </span>
  )
}

