import { useEffect, useState, useMemo, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  BackgroundVariant,
  Position,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'
import { getKnowledgeGraph, rebuildGraph, getFeatures } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import {
  RefreshCw,
  Info,
  ExternalLink,
  X,
  Layers,
  Calendar,
  FileText,
  Boxes,
  AlertTriangle,
  ArrowDownUp,
  ArrowLeftRight,
  Eye,
  EyeOff,
  Filter,
} from 'lucide-react'

// Node type styling configurations
const NODE_META: Record<
  string,
  { bg: string; border: string; text: string; icon: any; label: string }
> = {
  module: {
    bg: 'rgba(37, 99, 235, 0.12)',
    border: '#3b82f6',
    text: '#93c5fd',
    icon: Boxes,
    label: 'Module',
  },
  feature: {
    bg: 'rgba(124, 58, 237, 0.14)',
    border: '#8b5cf6',
    text: '#c4b5fd',
    icon: Layers,
    label: 'Feature',
  },
  event: {
    bg: 'rgba(5, 150, 105, 0.12)',
    border: '#10b981',
    text: '#6ee7b7',
    icon: Calendar,
    label: 'Event',
  },
  document: {
    bg: 'rgba(217, 119, 6, 0.12)',
    border: '#f59e0b',
    text: '#fcd34d',
    icon: FileText,
    label: 'Document',
  },
  decision: {
    bg: 'rgba(225, 29, 72, 0.12)',
    border: '#f43f5e',
    text: '#fda4af',
    icon: AlertTriangle,
    label: 'Decision',
  },
}

const EDGE_COLORS: Record<string, string> = {
  MODULE_CONTAINS_FEATURE: '#3b82f6',
  FEATURE_HAS_EVENT: '#8b5cf6',
  EVENT_FOLLOWS_EVENT: '#10b981',
  EVENT_SUPPORTED_BY: '#f59e0b',
  DECISION_RELATES_TO: '#f43f5e',
  FEATURE_RENAMED_FROM: '#ec4899',
}

interface RawNode {
  id: string
  label: string
  node_type: string
  feature_id?: string
  status?: string
  decision_status?: string
  has_conflict?: boolean
  source_document_filename?: string
  [key: string]: unknown
}

interface RawEdge {
  source: string
  target: string
  relationship_type: string
}

const NODE_WIDTH = 210
const NODE_HEIGHT = 70

/**
 * Applies Dagre directed acyclic graph layout to nodes and edges.
 */
function applyDagreLayout(
  rawNodes: RawNode[],
  rawEdges: RawEdge[],
  direction: 'TB' | 'LR' = 'TB',
  showDocuments: boolean = false
): { nodes: Node[]; edges: Edge[] } {
  // Filter out document nodes if showDocuments is false
  const filteredRawNodes = showDocuments
    ? rawNodes
    : rawNodes.filter((n) => n.node_type !== 'document')

  const validNodeIds = new Set(filteredRawNodes.map((n) => n.id))

  const filteredRawEdges = rawEdges.filter(
    (e) => validNodeIds.has(e.source) && validNodeIds.has(e.target)
  )

  const g = new dagre.graphlib.Graph()
  g.setGraph({
    rankdir: direction,
    ranksep: direction === 'TB' ? 85 : 120,
    nodesep: direction === 'TB' ? 45 : 35,
    edgesep: 25,
    marginx: 30,
    marginy: 30,
  })
  g.setDefaultEdgeLabel(() => ({}))

  filteredRawNodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })

  filteredRawEdges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  const isTB = direction === 'TB'

  const nodes: Node[] = filteredRawNodes.map((node) => {
    const dagreNode = g.node(node.id) || { x: 0, y: 0 }
    const type = node.node_type || 'event'
    const meta = NODE_META[type] || NODE_META.event

    const truncatedLabel =
      node.label && node.label.length > 28
        ? node.label.slice(0, 26) + '…'
        : node.label || node.id

    return {
      id: node.id,
      position: {
        x: dagreNode.x - NODE_WIDTH / 2,
        y: dagreNode.y - NODE_HEIGHT / 2,
      },
      targetPosition: isTB ? Position.Top : Position.Left,
      sourcePosition: isTB ? Position.Bottom : Position.Right,
      data: {
        ...node,
        rawLabel: node.label,
        truncatedLabel,
        meta,
      },
      style: {
        background: meta.bg,
        border: `1.5px solid ${meta.border}`,
        borderRadius: '10px',
        padding: '8px 12px',
        color: '#e2e8f0',
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        boxShadow: `0 4px 16px rgba(0, 0, 0, 0.4), 0 0 12px ${meta.border}22`,
        backdropFilter: 'blur(8px)',
        cursor: 'pointer',
      },
    }
  })

  const edges: Edge[] = filteredRawEdges.map((edge, i) => {
    const strokeColor = EDGE_COLORS[edge.relationship_type] || '#7c3aed66'
    const isSequential = edge.relationship_type === 'EVENT_FOLLOWS_EVENT'

    return {
      id: `edge-${edge.source}-${edge.target}-${i}`,
      source: edge.source,
      target: edge.target,
      label: edge.relationship_type.replace(/_/g, ' ').toLowerCase(),
      type: 'smoothstep',
      animated: isSequential,
      style: {
        stroke: strokeColor,
        strokeWidth: isSequential ? 1.8 : 1.4,
        strokeDasharray: isSequential ? '4 2' : undefined,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 14,
        height: 14,
      },
      labelStyle: {
        fill: '#94a3b8',
        fontSize: 8.5,
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: '#090d1f',
        fillOpacity: 0.85,
        rx: 4,
        ry: 4,
      },
      labelBgPadding: [4, 2] as [number, number],
    }
  })

  return { nodes, edges }
}

export default function KnowledgeGraphPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const currentFeatureFilter = searchParams.get('featureId') || ''

  const [direction, setDirection] = useState<'TB' | 'LR'>('TB')
  const [showDocuments, setShowDocuments] = useState<boolean>(false)
  const [selectedNode, setSelectedNode] = useState<RawNode | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Fetch list of features for the filter dropdown
  const { data: featuresData } = useQuery({
    queryKey: ['features-list'],
    queryFn: () => getFeatures(0, 200),
  })

  // Fetch graph data (filtered by featureId if specified)
  const {
    data: graphData,
    isLoading,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ['knowledge-graph', currentFeatureFilter],
    queryFn: () => getKnowledgeGraph(currentFeatureFilter || undefined),
  })

  const rebuildMutation = useMutation({
    mutationFn: rebuildGraph,
    onSuccess: () => refetch(),
  })

  // Re-run Dagre layout when graphData, direction, or showDocuments change
  useEffect(() => {
    if (graphData && (graphData as any).nodes) {
      const raw = graphData as { nodes: RawNode[]; edges: RawEdge[] }
      const { nodes: layoutNodes, edges: layoutEdges } = applyDagreLayout(
        raw.nodes || [],
        raw.edges || [],
        direction,
        showDocuments
      )
      setNodes(layoutNodes)
      setEdges(layoutEdges)
    }
  }, [graphData, direction, showDocuments, setNodes, setEdges])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node.data as RawNode)
  }, [])

  const handleFeatureFilterChange = (featId: string) => {
    if (featId) {
      setSearchParams({ featureId: featId })
    } else {
      setSearchParams({})
    }
  }

  const nodeStats = useMemo(() => {
    return {
      totalNodes: nodes.length,
      totalEdges: edges.length,
    }
  }, [nodes, edges])

  return (
    <div className="flex flex-col h-screen">
      {/* Top Header & Controls */}
      <div className="px-6 pt-5 pb-3 flex-shrink-0 border-b border-purple-900/20 bg-[#0a0f1e]/90 backdrop-blur-md">
        <PageHeader
          title="Temporal Knowledge Graph"
          subtitle="Hierarchical view of Modules, Features, Decisions, and Sequential Events with Dagre layout"
          actions={
            <div className="flex items-center gap-2">
              <button
                onClick={() => rebuildMutation.mutate()}
                disabled={rebuildMutation.isPending || isRefetching}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/40 text-xs font-medium text-purple-300 border border-purple-500/30 transition-all disabled:opacity-50"
                title="Re-evaluate all relationships and rebuild graph"
              >
                <RefreshCw
                  size={13}
                  className={rebuildMutation.isPending || isRefetching ? 'animate-spin' : ''}
                />
                Rebuild Graph
              </button>
            </div>
          }
        />

        {/* Toolbar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Left filters: Feature selection & Document toggle */}
          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Feature selector */}
            <div className="flex items-center gap-1.5 bg-slate-900/70 border border-slate-700/60 rounded-lg px-2.5 py-1 text-slate-300">
              <Filter size={13} className="text-purple-400" />
              <span className="text-slate-400 font-medium">Focus:</span>
              <select
                value={currentFeatureFilter}
                onChange={(e) => handleFeatureFilterChange(e.target.value)}
                className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer max-w-[180px] truncate"
              >
                <option value="" className="bg-[#0d1530] text-slate-200">
                  All Features (Global View)
                </option>
                {featuresData?.features.map((f) => (
                  <option key={f.id} value={f.id} className="bg-[#0d1530] text-slate-200">
                    {f.canonical_name} ({f.event_count})
                  </option>
                ))}
              </select>
              {currentFeatureFilter && (
                <button
                  onClick={() => handleFeatureFilterChange('')}
                  className="hover:text-white text-slate-400 p-0.5"
                  title="Clear focus"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Layout Direction Toggle */}
            <button
              onClick={() => setDirection((d) => (d === 'TB' ? 'LR' : 'TB'))}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/70 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors"
              title="Toggle graph orientation"
            >
              {direction === 'TB' ? (
                <>
                  <ArrowDownUp size={13} className="text-emerald-400" />
                  <span>Top-Down</span>
                </>
              ) : (
                <>
                  <ArrowLeftRight size={13} className="text-blue-400" />
                  <span>Left-to-Right</span>
                </>
              )}
            </button>

            {/* Show Documents Leaf Nodes Toggle */}
            <button
              onClick={() => setShowDocuments((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border transition-colors ${
                showDocuments
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-slate-900/70 text-slate-400 border-slate-700/60 hover:text-slate-200'
              }`}
              title="Toggle source document leaf nodes"
            >
              {showDocuments ? <Eye size={13} /> : <EyeOff size={13} />}
              <span>{showDocuments ? 'Hide Documents' : 'Show Documents'}</span>
            </button>
          </div>

          {/* Right: Graph counts & Legend */}
          <div className="flex items-center gap-3">
            <span className="text-slate-500 font-mono text-[11px]">
              {nodeStats.totalNodes} Nodes • {nodeStats.totalEdges} Edges
            </span>
            <div className="h-3 w-px bg-slate-800" />
            <div className="flex items-center gap-2">
              {Object.entries(NODE_META).map(([type, meta]) => {
                if (!showDocuments && type === 'document') return null
                const Icon = meta.icon
                return (
                  <div key={type} className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    <Icon size={12} style={{ color: meta.border }} />
                    <span>{meta.label}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Main Graph Canvas */}
      <div className="flex-1 mx-6 my-4 rounded-xl border border-purple-900/30 overflow-hidden bg-[#070b19] relative shadow-inner">
        {isLoading ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw size={28} className="animate-spin text-purple-400" />
            <div className="text-sm">Calculating hierarchical layout with Dagre…</div>
          </div>
        ) : nodes.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-500">
            <div className="text-center max-w-sm">
              <Info size={36} className="mx-auto mb-2 opacity-40 text-purple-400" />
              <div className="text-slate-300 font-medium">No Graph Data to Display</div>
              <div className="text-xs text-slate-500 mt-1">
                {currentFeatureFilter
                  ? 'No events or relationships found for this feature. Clear the focus filter to view all.'
                  : 'Upload project documents on the Documents page to build the temporal knowledge graph.'}
              </div>
            </div>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            fitView
            minZoom={0.08}
            maxZoom={1.8}
            attributionPosition="bottom-left"
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1.2} color="#1e293b" />
            <Controls
              style={{
                background: '#0d1530',
                borderColor: '#7c3aed33',
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            />
            <MiniMap
              style={{
                background: '#070b19',
                borderColor: '#7c3aed33',
                borderRadius: '8px',
              }}
              nodeColor={(n) => {
                const type = (n.data as any)?.node_type || 'event'
                return NODE_META[type]?.border || '#64748b'
              }}
              maskColor="rgba(5, 8, 22, 0.75)"
            />
          </ReactFlow>
        )}

        {/* Selected Node Details Drawer */}
        {selectedNode && (
          <div className="absolute bottom-5 right-5 z-20 w-88 max-w-sm rounded-xl border border-purple-500/40 bg-[#0d1530]/95 p-4 backdrop-blur-md shadow-2xl space-y-3 transition-all animate-in fade-in slide-in-from-bottom-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span
                  className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border"
                  style={{
                    backgroundColor: NODE_META[selectedNode.node_type]?.bg || '#1e293b',
                    borderColor: NODE_META[selectedNode.node_type]?.border || '#475569',
                    color: NODE_META[selectedNode.node_type]?.text || '#e2e8f0',
                  }}
                >
                  {selectedNode.node_type}
                </span>
                <h4 className="text-sm font-semibold text-white mt-1.5 leading-snug break-words">
                  {selectedNode.label}
                </h4>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800/60 transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            {/* Node Metadata Details */}
            <div className="space-y-1.5 text-xs text-slate-300 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
              {selectedNode.decision_status && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Decision:</span>
                  <span
                    className={`font-semibold px-1.5 py-0.5 rounded text-[10px] ${
                      selectedNode.decision_status === 'APPROVED'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : selectedNode.decision_status === 'REJECTED'
                        ? 'bg-red-500/20 text-red-400'
                        : 'bg-yellow-500/20 text-yellow-400'
                    }`}
                  >
                    {selectedNode.decision_status}
                  </span>
                </div>
              )}

              {selectedNode.status && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Lifecycle Status:</span>
                  <span className="text-emerald-400 font-medium">{String(selectedNode.status)}</span>
                </div>
              )}

              {selectedNode.source_document_filename && (
                <div className="flex items-start justify-between gap-2">
                  <span className="text-slate-500 whitespace-nowrap">Source Doc:</span>
                  <span className="text-amber-400 font-mono text-[11px] truncate max-w-[180px]">
                    {selectedNode.source_document_filename}
                  </span>
                </div>
              )}

              {selectedNode.has_conflict && (
                <div className="flex items-center gap-1.5 text-red-400 bg-red-900/20 p-1.5 rounded border border-red-500/30 text-[11px]">
                  <AlertTriangle size={12} className="flex-shrink-0" />
                  <span>Historical conflict recorded for this event</span>
                </div>
              )}
            </div>

            {/* Actions depending on node type */}
            <div className="pt-1 flex gap-2">
              {selectedNode.node_type === 'feature' && (
                <>
                  <button
                    onClick={() =>
                      navigate(
                        `/timeline?featureId=${selectedNode.feature_id || selectedNode.id}`
                      )
                    }
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 text-xs font-medium text-purple-200 border border-purple-500/30 transition-all hover:shadow"
                  >
                    <ExternalLink size={12} />
                    View Timeline
                  </button>
                  <button
                    onClick={() =>
                      handleFeatureFilterChange(selectedNode.feature_id || selectedNode.id)
                    }
                    className="flex items-center justify-center gap-1 py-2 px-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition-colors"
                    title="Focus on this feature's subgraph"
                  >
                    <Filter size={12} />
                    Focus
                  </button>
                </>
              )}

              {selectedNode.node_type === 'document' && (
                <button
                  onClick={() => navigate('/documents')}
                  className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-amber-600/30 hover:bg-amber-600/50 text-xs font-medium text-amber-200 border border-amber-500/30 transition-colors"
                >
                  <FileText size={12} />
                  Open in Document Manager
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
