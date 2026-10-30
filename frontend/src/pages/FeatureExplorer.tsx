import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Layers,
  Calendar,
  Hash,
  ArrowRight,
  Search,
  Filter,
  Boxes,
  X,
  Clock,
} from 'lucide-react'
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
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedModule, setSelectedModule] = useState('ALL')

  const { data, isLoading } = useQuery({
    queryKey: ['features'],
    queryFn: () => getFeatures(0, 200),
  })

  // Extract unique modules
  const modules = useMemo(() => {
    if (!data?.features) return []
    const set = new Set<string>()
    data.features.forEach((f) => {
      if (f.module_name) set.add(f.module_name)
    })
    return Array.from(set).sort()
  }, [data])

  // Filter features
  const filteredFeatures = useMemo(() => {
    if (!data?.features) return []
    const term = searchTerm.toLowerCase().trim()

    return data.features.filter((f) => {
      // Search term
      const matchesSearch =
        !term ||
        f.canonical_name.toLowerCase().includes(term) ||
        (f.module_name && f.module_name.toLowerCase().includes(term)) ||
        f.aliases.some((a) => a.alias.toLowerCase().includes(term))

      // Status
      const matchesStatus = statusFilter === 'ALL' || f.current_status === statusFilter

      // Module
      const matchesModule = selectedModule === 'ALL' || f.module_name === selectedModule

      return matchesSearch && matchesStatus && matchesModule
    })
  }, [data, searchTerm, statusFilter, selectedModule])

  return (
    <div className="px-6 py-6 space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Feature Explorer"
        subtitle="Canonical feature entities tracked across historical document mentions, renames, and lifecycles"
      />

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-[#0d1530]/80 p-3 rounded-xl border border-purple-900/30">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-3 text-slate-500" />
          <input
            type="text"
            placeholder="Search features or aliases (e.g., Google Login, Auth)..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#070b19] border border-slate-700/60 rounded-lg pl-9 pr-8 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500/70 transition-colors"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap text-xs">
          {/* Module Filter */}
          <div className="flex items-center gap-1.5 bg-[#070b19] border border-slate-700/60 rounded-lg px-2.5 py-1.5 text-slate-300">
            <Boxes size={13} className="text-blue-400" />
            <select
              value={selectedModule}
              onChange={(e) => setSelectedModule(e.target.value)}
              className="bg-transparent text-slate-300 focus:outline-none cursor-pointer text-xs"
            >
              <option value="ALL" className="bg-[#0d1530] text-slate-200">
                All Modules
              </option>
              {modules.map((m) => (
                <option key={m} value={m} className="bg-[#0d1530] text-slate-200">
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 bg-[#070b19] border border-slate-700/60 rounded-lg px-2.5 py-1.5 text-slate-300">
            <Filter size={13} className="text-purple-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-300 focus:outline-none cursor-pointer text-xs"
            >
              <option value="ALL" className="bg-[#0d1530] text-slate-200">
                All Statuses
              </option>
              <option value="ACTIVE" className="bg-[#0d1530] text-slate-200">
                Active
              </option>
              <option value="PROPOSED" className="bg-[#0d1530] text-slate-200">
                Proposed
              </option>
              <option value="DEPRECATED" className="bg-[#0d1530] text-slate-200">
                Deprecated
              </option>
              <option value="REMOVED" className="bg-[#0d1530] text-slate-200">
                Removed
              </option>
            </select>
          </div>

          <span className="text-slate-500 font-mono text-[11px] pl-1">
            {filteredFeatures.length} of {data?.total ?? 0}
          </span>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-slate-500">Loading features from database…</div>
      ) : filteredFeatures.length === 0 ? (
        <div className="text-center py-16 text-slate-500 bg-[#0d1530]/40 rounded-xl border border-purple-900/20">
          <Layers size={40} className="mx-auto mb-3 opacity-30 text-purple-400" />
          <div className="text-slate-300 font-medium">No matching features found.</div>
          <div className="text-xs text-slate-500 mt-1">
            Try adjusting your search query or status filter.
          </div>
          {(searchTerm || statusFilter !== 'ALL' || selectedModule !== 'ALL') && (
            <button
              onClick={() => {
                setSearchTerm('')
                setStatusFilter('ALL')
                setSelectedModule('ALL')
              }}
              className="mt-3 text-xs text-purple-400 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredFeatures.map((feature) => (
            <div
              key={feature.id}
              onClick={() => navigate(`/timeline?featureId=${feature.id}`)}
              className="rounded-xl border border-purple-900/30 bg-[#0d1530]/90 p-5 hover:border-purple-500/50 transition-all cursor-pointer hover:shadow-lg hover:shadow-purple-900/20 group backdrop-blur-md flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2.5">
                  <div className="text-base font-semibold text-white group-hover:text-purple-300 transition-colors flex items-center gap-1.5 leading-snug">
                    <span>{feature.canonical_name}</span>
                    <ArrowRight
                      size={14}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-purple-400 flex-shrink-0"
                    />
                  </div>
                  <span
                    className={cn(
                      'px-2 py-0.5 rounded-full text-[10px] font-semibold border flex-shrink-0 uppercase',
                      STATUS_COLORS[feature.current_status] || STATUS_COLORS.UNKNOWN
                    )}
                  >
                    {feature.current_status}
                  </span>
                </div>

                {feature.module_name && (
                  <div className="flex items-center gap-1.5 text-xs text-blue-400/90 mb-2.5 font-medium">
                    <Boxes size={12} />
                    <span>{feature.module_name}</span>
                  </div>
                )}

                {feature.aliases.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {feature.aliases
                      .filter((a) => !a.is_canonical)
                      .slice(0, 3)
                      .map((alias) => (
                        <span
                          key={alias.id}
                          className="px-2 py-0.5 rounded bg-slate-900/80 text-slate-400 text-[11px] border border-slate-800"
                          title="Known alias"
                        >
                          {alias.alias}
                        </span>
                      ))}
                    {feature.aliases.filter((a) => !a.is_canonical).length > 3 && (
                      <span className="text-[11px] text-slate-500 self-center">
                        +{feature.aliases.filter((a) => !a.is_canonical).length - 3} more
                      </span>
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800/60 text-xs text-slate-500">
                <div className="flex items-center gap-1.5 font-mono text-purple-400">
                  <Hash size={12} />
                  <span>{feature.event_count} events</span>
                </div>
                {feature.first_seen_date ? (
                  <div className="flex items-center gap-1.5">
                    <Calendar size={12} />
                    <span>Since {formatDate(feature.first_seen_date)}</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1 text-slate-600">
                    <Clock size={12} />
                    <span>Date unknown</span>
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
