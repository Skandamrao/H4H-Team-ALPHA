import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Layers, Calendar, Hash, ArrowRight } from 'lucide-react'
import { getFeatures } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { formatDate, cn } from '@/lib/utils'

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  DEPRECATED: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  REMOVED: 'bg-red-500/20 text-red-400 border-red-500/30',
  PROPOSED: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  UNKNOWN: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

export default function FeatureExplorer() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['features'],
    queryFn: () => getFeatures(),
  })

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Feature Explorer"
        subtitle={`${data?.total ?? 0} features identified across all documents`}
      />
      {isLoading ? (
        <div className="text-center py-12 text-slate-500">Loading features…</div>
      ) : !data?.features.length ? (
        <div className="text-center py-16 text-slate-500">
          <Layers size={40} className="mx-auto mb-3 opacity-30" />
          <div>No features extracted yet.</div>
          <div className="text-sm mt-1">Upload documents on the Documents page to begin.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {data.features.map(feature => (
            <div
              key={feature.id}
              onClick={() => navigate(`/timeline?featureId=${feature.id}`)}
              className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5 hover:border-purple-500/60 transition-all cursor-pointer hover:shadow-lg hover:shadow-purple-900/20 group"
            >
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="text-base font-semibold text-white group-hover:text-purple-300 transition-colors flex items-center gap-1.5">
                  {feature.canonical_name}
                  <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity text-purple-400" />
                </div>
                <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border flex-shrink-0', STATUS_COLORS[feature.current_status] || STATUS_COLORS.UNKNOWN)}>
                  {feature.current_status}
                </span>
              </div>

              {feature.module_name && (
                <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-2">
                  <Layers size={11} />
                  <span>{feature.module_name}</span>
                </div>
              )}

              {feature.aliases.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {feature.aliases.filter(a => !a.is_canonical).slice(0, 4).map(alias => (
                    <span key={alias.id} className="px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 text-xs border border-slate-700/50">
                      {alias.alias}
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800/50 text-xs text-slate-500">
                <div className="flex items-center gap-1.5">
                  <Hash size={11} />
                  <span>{feature.event_count} events</span>
                </div>
                {feature.first_seen_date && (
                  <div className="flex items-center gap-1.5">
                    <Calendar size={11} />
                    <span>Since {formatDate(feature.first_seen_date)}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

