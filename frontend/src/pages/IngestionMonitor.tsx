import { useQuery } from '@tanstack/react-query'
import { Activity, CheckCircle, AlertCircle, Clock, Copy } from 'lucide-react'
import { getIngestionBatches } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { formatDateTime, cn } from '@/lib/utils'

export default function IngestionMonitor() {
  const { data: batches, isLoading } = useQuery({
    queryKey: ['ingestion-batches'],
    queryFn: getIngestionBatches,
    refetchInterval: 5000,
  })

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Ingestion Monitor"
        subtitle="Track document processing batches and incremental ingestion status"
      />

      {isLoading ? (
        <div className="text-center py-12 text-slate-500">Loading batches…</div>
      ) : !batches?.length ? (
        <div className="text-center py-16 text-slate-500">
          <Activity size={40} className="mx-auto mb-3 opacity-30" />
          <div>No ingestion batches yet.</div>
        </div>
      ) : (
        <div className="space-y-4">
          {batches.map(batch => (
            <div key={batch.id} className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="text-base font-semibold text-white">
                    {batch.label || `Batch ${batch.id.slice(0, 8)}`}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">Started: {formatDateTime(batch.started_at)}</div>
                  {batch.completed_at && (
                    <div className="text-xs text-slate-500">Completed: {formatDateTime(batch.completed_at)}</div>
                  )}
                </div>
                <div className={cn(
                  'px-3 py-1 rounded-full text-xs font-medium border',
                  batch.status === 'COMPLETED' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
                  batch.status === 'FAILED' ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                  'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                )}>
                  {batch.status}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {[
                  { label: 'Total Files', value: batch.total_files, icon: Activity, color: 'text-slate-400' },
                  { label: 'Processed', value: batch.processed_files, icon: CheckCircle, color: 'text-green-400' },
                  { label: 'Failed', value: batch.failed_files, icon: AlertCircle, color: 'text-red-400' },
                  { label: 'Duplicates', value: batch.duplicate_files, icon: Copy, color: 'text-yellow-400' },
                  { label: 'New Events', value: batch.new_events_extracted, icon: Clock, color: 'text-purple-400' },
                ].map(({ label, value, icon: Icon, color }) => (
                  <div key={label} className="rounded-lg bg-slate-800/40 p-3 text-center">
                    <Icon size={14} className={cn('mx-auto mb-1', color)} />
                    <div className={cn('text-xl font-bold', color)}>{value}</div>
                    <div className="text-xs text-slate-500">{label}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

