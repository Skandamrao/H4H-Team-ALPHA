import { cn } from '@/lib/utils'
import { LucideIcon } from 'lucide-react'

interface StatCardProps {
  title: string
  value: number | string
  icon: LucideIcon
  color?: string
  subtitle?: string
}

export default function StatCard({ title, value, icon: Icon, color = 'text-purple-400', subtitle }: StatCardProps) {
  return (
    <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-400">{title}</span>
        <div className={cn('p-2 rounded-lg bg-slate-800/60', color.replace('text-', 'bg-').replace('400', '400/10'))}>
          <Icon size={16} className={color} />
        </div>
      </div>
      <div className="text-3xl font-bold text-white">{value}</div>
      {subtitle && <div className="text-xs text-slate-500">{subtitle}</div>}
    </div>
  )
}

