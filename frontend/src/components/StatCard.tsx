import { LucideIcon } from 'lucide-react'

interface StatCardProps {
  title: string
  value: number | string
  icon: LucideIcon
  color?: string
  subtitle?: string
}

export default function StatCard({
  title,
  value,
  icon: Icon,
  color = 'text-purple-400',
  subtitle,
}: StatCardProps) {
  return (
    <div className="group relative rounded-xl border border-purple-900/30 bg-gradient-to-br from-[#111b40]/90 via-[#0d1636]/90 to-[#0a102a]/95 p-5 backdrop-blur-md transition-all duration-300 hover:border-purple-500/40 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-purple-900/20 overflow-hidden">
      {/* Top subtle highlight line */}
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-purple-500/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {title}
        </span>
        <div
          className={`p-2 rounded-lg bg-slate-800/60 border border-slate-700/40 transition-transform group-hover:scale-105 ${color}`}
        >
          <Icon size={16} />
        </div>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-3xl font-bold tracking-tight text-white">{value}</span>
      </div>

      {subtitle && <div className="mt-1 text-xs text-slate-500">{subtitle}</div>}
    </div>
  )
}
