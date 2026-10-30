import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import ReactFlow, {
  Background, Controls, MiniMap, useNodesState, useEdgesState,
  Node, Edge, BackgroundVariant
} from 'reactflow'
import 'reactflow/dist/style.css'
import { getKnowledgeGraph, rebuildGraph } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { RefreshCw, Info, ExternalLink, X } from 'lucide-react'

const NODE_COLORS: Record<string, string> = {
  feature: '#7c3aed',
  module: '#2563eb',
  event: '#059669',
  document: '#d97706',
  person: '#dc2626',
}

function buildFlowElements(rawGraph: { nodes: unknown[]; edges: unknown[] }) {
  const typeCount: Record<string, number> = {}
  const typeOrder = ['module', 'feature', 'event', 'document', 'person']

  const nodes: Node[] = (rawGraph.nodes as Array<{
    id: string; label: string; node_type: string; [key: string]: unknown
  }>).map((n) => {
    const type = n.node_type || 'event'
    typeCount[type] = (typeCount[type] || 0) + 1
    const indexInType = typeCount[type] - 1

    // Arrange nodes in 2-3 wrapped columns per category so the graph stays compact
    const maxRows = 12
    const subCol = Math.floor(indexInType / maxRows)
    const row = indexInType % maxRows

    const baseTypeIndex = Math.max(0, typeOrder.indexOf(type))
    const x = baseTypeIndex * 380 + subCol * 170
    const y = row * 72 + (subCol % 2 === 1 ? 25 : 0)

    return {
      id: n.id,
      position: { x, y },
      data: { ...n, label: n.label, node_type: type },
      style: {
        background: `${NODE_COLORS[type] || '#334155'}26`,
        border: `1.5px solid ${NODE_COLORS[type] || '#334155'}`,
        borderRadius: 8,
        padding: '5px 10px',
        color: '#e2e8f0',
        fontSize: 11,
        maxWidth: 160,
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      },
    }
  })

  const edges: Edge[] = (rawGraph.edges as Array<{
    source: string; target: string; relationship_type: string
  }>).map((e, i) => ({
    id: `edge-${i}`,
    source: e.source,
    target: e.target,
    label: e.relationship_type,
    style: { stroke: '#7c3aed44', strokeWidth: 1.2 },
    labelStyle: { fill: '#94a3b8', fontSize: 9 },
    animated: false,
  }))

  return { nodes, edges }
}

export default function KnowledgeGraphPage() {
  const navigate = useNavigate()
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNode, setSelectedNode] = useState<{
    id?: string; label?: string; node_type?: string; feature_id?: string; status?: string; [key: string]: unknown
  } | null>(null)

  const { data: graphData, isLoading, refetch } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: getKnowledgeGraph,
  })

  const rebuildMutation = useMutation({
    mutationFn: rebuildGraph,
    onSuccess: () => refetch(),
  })

  useEffect(() => {
    if (graphData) {
      const { nodes: n, edges: e } = buildFlowElements(graphData as { nodes: unknown[]; edges: unknown[] })
      setNodes(n)
      setEdges(e)
    }
  }, [graphData, setNodes, setEdges])

  const legend = Object.entries(NODE_COLORS).map(([type, color]) => (
    <div key={type} className="flex items-center gap-1.5">
      <div className="w-3 h-3 rounded" style={{ background: color + '55', border: `1.5px solid ${color}` }} />
      <span className="text-xs text-slate-400 capitalize">{type}</span>
    </div>
  ))

  return (
    <div className="flex flex-col h-screen">
      <div className="px-6 pt-6 pb-4 flex-shrink-0">
        <PageHeader
          title="Knowledge Graph"
          subtitle="Interactive temporal knowledge graph — features, events, decisions, and their relationships"
          actions={
            <button
              onClick={() => rebuildMutation.mutate()}
              disabled={rebuildMutation.isPending}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-700/30 hover:bg-purple-700/50 text-sm text-purple-300 border border-purple-600/30 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={rebuildMutation.isPending ? 'animate-spin' : ''} />
              Rebuild Graph
            </button>
          }
        />
        {/* Legend */}
        <div className="flex flex-wrap gap-4 px-6">{legend}</div>
      </div>

      <div className="flex-1 mx-6 mb-6 rounded-xl border border-purple-900/30 overflow-hidden bg-[#0d1530] relative">
        {isLoading ? (
          <div className="h-full flex items-center justify-center text-slate-500">Building graph…</div>
        ) : nodes.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-500">
            <div className="text-center">
              <Info size={32} className="mx-auto mb-2 opacity-30" />
              <div>No graph data yet. Upload documents first.</div>
            </div>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => setSelectedNode(node.data as any)}
            fitView
            minZoom={0.1}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
            <Controls style={{ background: '#111b40', borderColor: '#7c3aed44' }} />
            <MiniMap
              style={{ background: '#0d1530', borderColor: '#7c3aed44' }}
              nodeColor={(n) => {
                const type = (n.data as { node_type?: string }).node_type || 'event'
                return NODE_COLORS[type] || '#334155'
              }}
            />
          </ReactFlow>
        )}

        {/* Selected Node Drawer */}
        {selectedNode && (
          <div className="absolute bottom-4 right-4 z-10 w-80 rounded-xl border border-purple-800/50 bg-[#111b40]/95 p-4 backdrop-blur shadow-2xl space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {selectedNode.node_type}
                </span>
                <h4 className="text-sm font-semibold text-white mt-1.5">{selectedNode.label}</h4>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            {Boolean(selectedNode.status) && (
              <div className="text-xs text-slate-400">
                Status: <span className="text-emerald-400 font-medium">{String(selectedNode.status)}</span>
              </div>
            )}

            {selectedNode.node_type === 'feature' && selectedNode.feature_id && (
              <button
                onClick={() => navigate(`/timeline?featureId=${selectedNode.feature_id}`)}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 text-xs font-medium text-purple-200 border border-purple-500/30 transition-colors"
              >
                <ExternalLink size={12} />
                Open Feature Timeline
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

