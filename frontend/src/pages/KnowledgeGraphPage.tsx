import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react'
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
  ReactFlowInstance,
  Handle,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'
import { getKnowledgeGraph, rebuildGraph, getFeatures } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { cn } from '@/lib/utils'
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
  Filter,
  Search,
  Grid,
  Eye,
  EyeOff,
  Maximize2,
  FolderTree,
  Compass,
  CheckCircle2,
  CheckCircle,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Node type styling configurations
const NODE_META: Record<
  string,
  { bg: string; border: string; text: string; icon: LucideIcon; label: string }
> = {
  module: {
    bg: 'rgba(37, 99, 235, 0.16)',
    border: '#3b82f6',
    text: '#93c5fd',
    icon: Boxes,
    label: 'Module',
  },
  feature: {
    bg: 'rgba(124, 58, 237, 0.16)',
    border: '#8b5cf6',
    text: '#c4b5fd',
    icon: Layers,
    label: 'Feature',
  },
  event: {
    bg: 'rgba(5, 150, 105, 0.16)',
    border: '#10b981',
    text: '#6ee7b7',
    icon: Calendar,
    label: 'Event',
  },
  document: {
    bg: 'rgba(217, 119, 6, 0.16)',
    border: '#f59e0b',
    text: '#fcd34d',
    icon: FileText,
    label: 'Document',
  },
  decision: {
    bg: 'rgba(225, 29, 72, 0.16)',
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
  is_isolated?: boolean
  degree?: number
  event_date?: string
  module_name?: string
  [key: string]: unknown
}

interface RawEdge {
  source: string
  target: string
  relationship_type: string
}

const NODE_WIDTH = 230
const NODE_HEIGHT = 80

type LayoutStructure =
  | 'clusters'
  | 'swimlanes'
  | 'concentric'
  | 'timeline'
  | 'hierarchical-tb'
  | 'hierarchical-lr'

/**
 * Custom ReactFlow Node for rich rendering
 */
function CustomKnowledgeNode({ data }: { data: any }) {
  const meta = data.meta || NODE_META.event
  const Icon = meta.icon || Calendar
  const targetPos = data.targetPosition || Position.Top
  const sourcePos = data.sourcePosition || Position.Bottom

  return (
    <div
      className={cn(
        'group relative rounded-xl border p-2.5 transition-all duration-200 select-none shadow-md backdrop-blur-md',
        'hover:shadow-lg hover:scale-[1.02] cursor-pointer'
      )}
      style={{
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        backgroundColor: meta.bg,
        borderColor: meta.border,
        boxShadow: `0 4px 16px rgba(0, 0, 0, 0.45), 0 0 10px ${meta.border}22`,
      }}
    >
      <Handle
        type="target"
        position={targetPos}
        className="!w-2.5 !h-2.5 !bg-purple-400 !border-2 !border-slate-900 transition-colors"
      />

      <div className="flex items-start justify-between gap-1 mb-1">
        <div className="flex items-center gap-1.5 overflow-hidden">
          <div
            className="p-1 rounded-md flex-shrink-0"
            style={{ backgroundColor: `${meta.border}25`, color: meta.text }}
          >
            <Icon size={12} />
          </div>
          <span
            className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded truncate"
            style={{ backgroundColor: `${meta.border}30`, color: meta.text }}
          >
            {meta.label}
          </span>
        </div>

        {data.decision_status && (
          <span
            className={cn(
              'text-[9px] font-bold px-1.5 py-0.5 rounded font-mono flex-shrink-0',
              data.decision_status === 'APPROVED'
                ? 'bg-emerald-500/25 text-emerald-300 border border-emerald-500/40'
                : data.decision_status === 'REJECTED'
                ? 'bg-rose-500/25 text-rose-300 border border-rose-500/40'
                : 'bg-amber-500/25 text-amber-300 border border-amber-500/40'
            )}
          >
            {data.decision_status}
          </span>
        )}

        {data.has_conflict && (
          <span className="p-0.5 text-rose-400 flex-shrink-0" title="Historical conflict">
            <AlertTriangle size={12} />
          </span>
        )}
      </div>

      <div className="text-xs font-semibold text-slate-100 leading-snug line-clamp-2">
        {data.label}
      </div>

      {(data.event_date || data.source_document_filename) && (
        <div className="mt-1.5 pt-1 border-t border-slate-700/50 flex items-center justify-between text-[10px] text-slate-400">
          {data.event_date ? (
            <span className="font-mono text-slate-300 truncate">{data.event_date}</span>
          ) : (
            <span />
          )}
          {data.source_document_filename && (
            <span
              className="truncate max-w-[110px] font-mono text-amber-300/80"
              title={data.source_document_filename}
            >
              {data.source_document_filename}
            </span>
          )}
        </div>
      )}

      <Handle
        type="source"
        position={sourcePos}
        className="!w-2.5 !h-2.5 !bg-purple-400 !border-2 !border-slate-900 transition-colors"
      />
    </div>
  )
}

const nodeTypes = {
  custom: CustomKnowledgeNode,
}

function createFlowNode(
  node: RawNode,
  x: number,
  y: number,
  targetPos: Position,
  sourcePos: Position
): Node {
  const type = node.node_type || 'event'
  const meta = NODE_META[type] || NODE_META.event

  return {
    id: node.id,
    type: 'custom',
    position: { x, y },
    targetPosition: targetPos,
    sourcePosition: sourcePos,
    data: {
      ...node,
      targetPosition: targetPos,
      sourcePosition: sourcePos,
      meta,
    },
  }
}

function formatEdges(edges: RawEdge[]): Edge[] {
  return edges.map((edge, i) => {
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
        strokeWidth: isSequential ? 2.0 : 1.4,
        strokeDasharray: isSequential ? '4 2' : undefined,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 14,
        height: 14,
      },
      labelStyle: { fill: '#94a3b8', fontSize: 8.5, fontWeight: 500 },
      labelBgStyle: { fill: '#090d1f', fillOpacity: 0.85, rx: 4, ry: 4 },
      labelBgPadding: [4, 2] as [number, number],
    }
  })
}

/**
 * 1. Component-Based 2D Shelf Grid Packing Layout
 * Partitions graph into connected subgraphs (components), lays out each individually with Dagre,
 * and packs them row-by-row into a balanced 16:9 canvas with zero overlap.
 */
function applyClusteredShelfLayout(
  nodes: RawNode[],
  edges: RawEdge[],
  targetRowWidth: number = 2200
): { nodes: Node[]; edges: Edge[] } {
  const nodeMap = new Map<string, RawNode>()
  nodes.forEach((n) => nodeMap.set(n.id, n))

  // Build undirected adjacency list for connected components
  const adj = new Map<string, Set<string>>()
  nodes.forEach((n) => adj.set(n.id, new Set()))
  edges.forEach((e) => {
    if (adj.has(e.source) && adj.has(e.target)) {
      adj.get(e.source)!.add(e.target)
      adj.get(e.target)!.add(e.source)
    }
  })

  // BFS to extract components
  const visited = new Set<string>()
  const connectedComps: {
    compNodes: RawNode[]
    compEdges: RawEdge[]
    width: number
    height: number
    positions: Map<string, { x: number; y: number }>
  }[] = []
  const isolatedNodes: RawNode[] = []

  nodes.forEach((n) => {
    if (!visited.has(n.id)) {
      const compIds: string[] = []
      const queue = [n.id]
      visited.add(n.id)

      while (queue.length > 0) {
        const curr = queue.shift()!
        compIds.push(curr)
        const neighbors = adj.get(curr) || new Set()
        neighbors.forEach((nbr) => {
          if (!visited.has(nbr)) {
            visited.add(nbr)
            queue.push(nbr)
          }
        })
      }

      if (compIds.length === 1 && (adj.get(compIds[0])?.size ?? 0) === 0) {
        const iso = nodeMap.get(compIds[0])
        if (iso) isolatedNodes.push(iso)
      } else {
        const compNodes = compIds.map((id) => nodeMap.get(id)!).filter(Boolean)
        const compIdSet = new Set(compIds)
        const compEdges = edges.filter(
          (e) => compIdSet.has(e.source) && compIdSet.has(e.target)
        )

        // Run Dagre locally on this component
        const g = new dagre.graphlib.Graph()
        g.setGraph({
          rankdir: 'TB',
          ranksep: 70,
          nodesep: 35,
          edgesep: 20,
          marginx: 10,
          marginy: 10,
        })
        g.setDefaultEdgeLabel(() => ({}))

        compNodes.forEach((node) => {
          g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
        })
        compEdges.forEach((edge) => {
          g.setEdge(edge.source, edge.target)
        })

        dagre.layout(g)

        let minX = Infinity
        let maxX = -Infinity
        let minY = Infinity
        let maxY = -Infinity

        const positions = new Map<string, { x: number; y: number }>()
        compNodes.forEach((node) => {
          const pos = g.node(node.id) || { x: 0, y: 0 }
          const left = pos.x - NODE_WIDTH / 2
          const top = pos.y - NODE_HEIGHT / 2
          minX = Math.min(minX, left)
          maxX = Math.max(maxX, left + NODE_WIDTH)
          minY = Math.min(minY, top)
          maxY = Math.max(maxY, top + NODE_HEIGHT)
          positions.set(node.id, { x: left, y: top })
        })

        const width = Math.max(NODE_WIDTH, maxX - minX)
        const height = Math.max(NODE_HEIGHT, maxY - minY)

        // Normalize positions to (0, 0) relative
        const normalizedPositions = new Map<string, { x: number; y: number }>()
        positions.forEach((pos, id) => {
          normalizedPositions.set(id, { x: pos.x - minX, y: pos.y - minY })
        })

        connectedComps.push({
          compNodes,
          compEdges,
          width,
          height,
          positions: normalizedPositions,
        })
      }
    }
  })

  // Sort connected components by node count descending
  connectedComps.sort((a, b) => b.compNodes.length - a.compNodes.length)

  // Shelf bin-packing
  const finalNodes: Node[] = []
  const COL_GAP = 70
  const ROW_GAP = 90

  let currentX = 0
  let currentY = 0
  let maxRowHeight = 0
  let rowCompsCount = 0

  connectedComps.forEach((comp) => {
    // If adding this component exceeds targetRowWidth and we already have components in this row, wrap
    if (rowCompsCount > 0 && currentX + comp.width > targetRowWidth) {
      currentX = 0
      currentY += maxRowHeight + ROW_GAP
      maxRowHeight = 0
      rowCompsCount = 0
    }

    comp.compNodes.forEach((n) => {
      const relPos = comp.positions.get(n.id) || { x: 0, y: 0 }
      finalNodes.push(
        createFlowNode(
          n,
          currentX + relPos.x,
          currentY + relPos.y,
          Position.Top,
          Position.Bottom
        )
      )
    })

    currentX += comp.width + COL_GAP
    maxRowHeight = Math.max(maxRowHeight, comp.height)
    rowCompsCount++
  })

  // Place isolated nodes neatly below the connected graph in a grid if any exist
  if (isolatedNodes.length > 0) {
    const isoStartY = connectedComps.length > 0 ? currentY + maxRowHeight + ROW_GAP * 1.4 : 0
    const ISO_COLS = 6
    isolatedNodes.forEach((iso, idx) => {
      const col = idx % ISO_COLS
      const row = Math.floor(idx / ISO_COLS)
      const x = col * (NODE_WIDTH + 30)
      const y = isoStartY + row * (NODE_HEIGHT + 25)
      finalNodes.push(createFlowNode(iso, x, y, Position.Top, Position.Bottom))
    })
  }

  return { nodes: finalNodes, edges: formatEdges(edges) }
}

/**
 * 2. Module Swimlanes Layout
 * Groups features and events into distinct vertical swimlanes.
 */
function applyModuleSwimlanesLayout(
  nodes: RawNode[],
  edges: RawEdge[]
): { nodes: Node[]; edges: Edge[] } {
  const modules = nodes.filter((n) => n.node_type === 'module')
  const features = nodes.filter((n) => n.node_type === 'feature')

  const featToModule = new Map<string, string>()
  edges.forEach((e) => {
    if (e.relationship_type === 'MODULE_CONTAINS_FEATURE') {
      featToModule.set(e.target, e.source)
    }
  })

  const featEvents = new Map<string, RawNode[]>()
  edges.forEach((e) => {
    if (
      e.relationship_type === 'FEATURE_HAS_EVENT' ||
      e.relationship_type === 'DECISION_RELATES_TO' ||
      e.relationship_type === 'EVENT_AFFECTS_FEATURE'
    ) {
      const ev = nodes.find((n) => n.id === e.target)
      if (ev) {
        const list = featEvents.get(e.source) || []
        list.push(ev)
        featEvents.set(e.source, list)
      }
    }
  })

  const finalNodes: Node[] = []
  const LANE_WIDTH = NODE_WIDTH + 60
  let laneIndex = 0

  // 1. Lanes for modules that exist
  modules.forEach((mod) => {
    const modFeatures = features.filter(
      (f) => featToModule.get(f.id) === mod.id || f.module_name === mod.label
    )

    const laneX = laneIndex * LANE_WIDTH
    let currentY = 0

    finalNodes.push(createFlowNode(mod, laneX, currentY, Position.Top, Position.Bottom))
    currentY += NODE_HEIGHT + 60

    modFeatures.forEach((feat) => {
      finalNodes.push(createFlowNode(feat, laneX, currentY, Position.Top, Position.Bottom))
      currentY += NODE_HEIGHT + 40

      const evs = featEvents.get(feat.id) || []
      evs.forEach((ev) => {
        finalNodes.push(createFlowNode(ev, laneX, currentY, Position.Top, Position.Bottom))
        currentY += NODE_HEIGHT + 35
      })
    })

    laneIndex++
  })

  // 2. Handle active features without modules (place each active feature in its own column)
  const handledFeatureIds = new Set(finalNodes.map((n) => n.id))
  const unhandledFeatures = features.filter((f) => !handledFeatureIds.has(f.id))
  unhandledFeatures.forEach((feat) => {
    const laneX = laneIndex * LANE_WIDTH
    let currentY = 0

    finalNodes.push(createFlowNode(feat, laneX, currentY, Position.Top, Position.Bottom))
    currentY += NODE_HEIGHT + 45

    const evs = featEvents.get(feat.id) || []
    evs.forEach((ev) => {
      finalNodes.push(createFlowNode(ev, laneX, currentY, Position.Top, Position.Bottom))
      currentY += NODE_HEIGHT + 35
    })
    laneIndex++
  })

  return { nodes: finalNodes, edges: formatEdges(edges) }
}

/**
 * 3. Concentric Radial Orbit Layout
 * Features arranged in inner orbit, Events/Decisions in outer orbit.
 */
function applyConcentricOrbitLayout(
  nodes: RawNode[],
  edges: RawEdge[]
): { nodes: Node[]; edges: Edge[] } {
  const modules = nodes.filter((n) => n.node_type === 'module')
  const features = nodes.filter((n) => n.node_type === 'feature')
  const events = nodes.filter((n) => n.node_type === 'event' || n.node_type === 'decision')
  const documents = nodes.filter((n) => n.node_type === 'document')

  const finalNodes: Node[] = []
  const centerX = 1000
  const centerY = 1000

  // 1. Modules at Radius = 240 (if modules present)
  if (modules.length > 0) {
    const R_MODULE = Math.max(220, modules.length * 40)
    modules.forEach((m, i) => {
      const angle = (2 * Math.PI * i) / (modules.length || 1)
      const x = centerX + R_MODULE * Math.cos(angle) - NODE_WIDTH / 2
      const y = centerY + R_MODULE * Math.sin(angle) - NODE_HEIGHT / 2
      finalNodes.push(createFlowNode(m, x, y, Position.Top, Position.Bottom))
    })
  }

  // 2. Features at Radius = 440
  const R_FEATURE = Math.max(modules.length > 0 ? 520 : 360, features.length * 18)
  features.forEach((f, i) => {
    const angle = (2 * Math.PI * i) / (features.length || 1)
    const x = centerX + R_FEATURE * Math.cos(angle) - NODE_WIDTH / 2
    const y = centerY + R_FEATURE * Math.sin(angle) - NODE_HEIGHT / 2
    finalNodes.push(createFlowNode(f, x, y, Position.Top, Position.Bottom))
  })

  // 3. Events & Decisions at Radius = 780
  const R_EVENT = Math.max(R_FEATURE + 320, events.length * 28)
  events.forEach((e, i) => {
    const angle = (2 * Math.PI * i) / (events.length || 1)
    const x = centerX + R_EVENT * Math.cos(angle) - NODE_WIDTH / 2
    const y = centerY + R_EVENT * Math.sin(angle) - NODE_HEIGHT / 2
    finalNodes.push(createFlowNode(e, x, y, Position.Top, Position.Bottom))
  })

  // 4. Documents at Radius = 1100
  if (documents.length > 0) {
    const R_DOC = Math.max(R_EVENT + 320, documents.length * 35)
    documents.forEach((d, i) => {
      const angle = (2 * Math.PI * i) / (documents.length || 1)
      const x = centerX + R_DOC * Math.cos(angle) - NODE_WIDTH / 2
      const y = centerY + R_DOC * Math.sin(angle) - NODE_HEIGHT / 2
      finalNodes.push(createFlowNode(d, x, y, Position.Top, Position.Bottom))
    })
  }

  return { nodes: finalNodes, edges: formatEdges(edges) }
}

/**
 * 4. Chronological Timeline Flow Layout
 * Arranges events sequentially along horizontal lanes by time and feature.
 */
function applyTimelineFlowLayout(
  nodes: RawNode[],
  edges: RawEdge[]
): { nodes: Node[]; edges: Edge[] } {
  const finalNodes: Node[] = []

  const modules = nodes.filter((n) => n.node_type === 'module')
  const features = nodes.filter((n) => n.node_type === 'feature')
  const events = nodes.filter((n) => n.node_type === 'event' || n.node_type === 'decision')
  const documents = nodes.filter((n) => n.node_type === 'document')

  // Column 1: Modules (x = 40)
  modules.forEach((m, idx) => {
    finalNodes.push(createFlowNode(m, 40, idx * 110, Position.Left, Position.Right))
  })

  // Column 2: Features (x = 340)
  features.forEach((f, idx) => {
    finalNodes.push(createFlowNode(f, 340, idx * 95, Position.Left, Position.Right))
  })

  // Columns 3+: Events arranged by chronological index
  const sortedEvents = [...events].sort((a, b) => {
    const da = a.event_date ? new Date(a.event_date).getTime() : 0
    const db = b.event_date ? new Date(b.event_date).getTime() : 0
    return da - db
  })

  const EVENTS_PER_COL = 8
  sortedEvents.forEach((ev, idx) => {
    const col = Math.floor(idx / EVENTS_PER_COL)
    const row = idx % EVENTS_PER_COL
    const x = 680 + col * (NODE_WIDTH + 50)
    const y = row * 110
    finalNodes.push(createFlowNode(ev, x, y, Position.Left, Position.Right))
  })

  // Rightmost column: Documents
  documents.forEach((doc, idx) => {
    const x = 680 + Math.ceil(sortedEvents.length / EVENTS_PER_COL) * (NODE_WIDTH + 50) + 60
    finalNodes.push(createFlowNode(doc, x, idx * 90, Position.Left, Position.Right))
  })

  return { nodes: finalNodes, edges: formatEdges(edges) }
}

/**
 * 5. Standard Dagre Hierarchical Layout (Top-to-Bottom or Left-to-Right)
 */
function applyStandardDagre(
  nodes: RawNode[],
  edges: RawEdge[],
  direction: 'TB' | 'LR' = 'TB'
): { nodes: Node[]; edges: Edge[] } {
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

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)

  const isTB = direction === 'TB'
  const flowNodes: Node[] = nodes.map((node) => {
    const pos = g.node(node.id) || { x: 0, y: 0 }
    return createFlowNode(
      node,
      pos.x - NODE_WIDTH / 2,
      pos.y - NODE_HEIGHT / 2,
      isTB ? Position.Top : Position.Left,
      isTB ? Position.Bottom : Position.Right
    )
  })

  return { nodes: flowNodes, edges: formatEdges(edges) }
}

export default function KnowledgeGraphPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const currentFeatureFilter = searchParams.get('featureId') || ''

  // View state: 'canvas' or 'explorer'
  const [activeView, setActiveView] = useState<'canvas' | 'explorer'>('canvas')

  // Layout method switcher
  const [layoutStructure, setLayoutStructure] = useState<LayoutStructure>('clusters')

  // Filters: onlyWithEvents is TRUE by default to hide entities with 0 events
  const [onlyWithEvents, setOnlyWithEvents] = useState<boolean>(true)
  const [showDocuments, setShowDocuments] = useState<boolean>(false)
  const [nodeSearch, setNodeSearch] = useState<string>('')
  const [selectedNode, setSelectedNode] = useState<RawNode | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null)

  // Fetch list of features for focus selector
  const { data: featuresData } = useQuery({
    queryKey: ['features-list'],
    queryFn: () => getFeatures(0, 200),
  })

  // Fetch graph data
  const {
    data: graphData,
    isLoading,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ['knowledge-graph', currentFeatureFilter, onlyWithEvents],
    queryFn: () => getKnowledgeGraph(currentFeatureFilter || undefined, onlyWithEvents),
  })

  const rebuildMutation = useMutation({
    mutationFn: rebuildGraph,
    onSuccess: () => refetch(),
  })

  // Filter raw graph data based on user controls: IF NO EVENTS, DON'T SHOW
  const filteredData = useMemo(() => {
    if (!graphData || !(graphData as any).nodes) return { nodes: [], edges: [] }
    const raw = graphData as { nodes: RawNode[]; edges: RawEdge[] }

    // 1. Identify all event and decision nodes
    const eventNodeIds = new Set(
      raw.nodes
        .filter((n) => n.node_type === 'event' || n.node_type === 'decision')
        .map((n) => n.id)
    )

    // 2. Identify all features that actually have events
    const featuresWithEvents = new Set<string>()
    raw.edges.forEach((e) => {
      if (
        e.relationship_type === 'FEATURE_HAS_EVENT' ||
        e.relationship_type === 'DECISION_RELATES_TO' ||
        e.relationship_type === 'EVENT_AFFECTS_FEATURE'
      ) {
        if (eventNodeIds.has(e.target) && e.source.startsWith('feature:')) {
          featuresWithEvents.add(e.source)
        }
        if (eventNodeIds.has(e.source) && e.target.startsWith('feature:')) {
          featuresWithEvents.add(e.target)
        }
      }
    })

    // 3. Identify modules that contain features with events
    const modulesWithEvents = new Set<string>()
    raw.edges.forEach((e) => {
      if (e.relationship_type === 'MODULE_CONTAINS_FEATURE') {
        if (featuresWithEvents.has(e.target) && e.source.startsWith('module:')) {
          modulesWithEvents.add(e.source)
        }
      }
    })

    // 4. Identify documents connected to those events
    const documentsWithEvents = new Set<string>()
    raw.edges.forEach((e) => {
      if (e.relationship_type === 'EVENT_SUPPORTED_BY') {
        if (eventNodeIds.has(e.source) && e.target.startsWith('document:')) {
          documentsWithEvents.add(e.target)
        }
      }
    })

    let nList = raw.nodes || []

    // If onlyWithEvents is TRUE (default): Strictly exclude entities with 0 events!
    if (onlyWithEvents) {
      nList = nList.filter((n) => {
        if (n.node_type === 'event' || n.node_type === 'decision') return true
        if (n.node_type === 'feature') return featuresWithEvents.has(n.id)
        if (n.node_type === 'module') return modulesWithEvents.has(n.id)
        if (n.node_type === 'document') return showDocuments && documentsWithEvents.has(n.id)
        return false
      })
    } else {
      if (!showDocuments) {
        nList = nList.filter((n) => n.node_type !== 'document')
      }
    }

    // Filter by text search if provided
    if (nodeSearch.trim()) {
      const q = nodeSearch.toLowerCase()
      nList = nList.filter(
        (n) => n.label?.toLowerCase().includes(q) || n.node_type?.toLowerCase().includes(q)
      )
    }

    const validIds = new Set(nList.map((n) => n.id))
    const eList = (raw.edges || []).filter(
      (e) => validIds.has(e.source) && validIds.has(e.target)
    )

    return { nodes: nList, edges: eList }
  }, [graphData, showDocuments, onlyWithEvents, nodeSearch])

  // Apply chosen layout algorithm
  useEffect(() => {
    if (filteredData.nodes.length === 0) {
      setNodes([])
      setEdges([])
      return
    }

    let result: { nodes: Node[]; edges: Edge[] }

    switch (layoutStructure) {
      case 'clusters':
        result = applyClusteredShelfLayout(filteredData.nodes, filteredData.edges, 2200)
        break
      case 'swimlanes':
        result = applyModuleSwimlanesLayout(filteredData.nodes, filteredData.edges)
        break
      case 'concentric':
        result = applyConcentricOrbitLayout(filteredData.nodes, filteredData.edges)
        break
      case 'timeline':
        result = applyTimelineFlowLayout(filteredData.nodes, filteredData.edges)
        break
      case 'hierarchical-tb':
        result = applyStandardDagre(filteredData.nodes, filteredData.edges, 'TB')
        break
      case 'hierarchical-lr':
        result = applyStandardDagre(filteredData.nodes, filteredData.edges, 'LR')
        break
      default:
        result = applyClusteredShelfLayout(filteredData.nodes, filteredData.edges, 2200)
    }

    setNodes(result.nodes)
    setEdges(result.edges)

    // Trigger smooth fitView after layout calculation
    setTimeout(() => {
      reactFlowInstance.current?.fitView({ padding: 0.18, duration: 400 })
    }, 120)
  }, [filteredData, layoutStructure, setNodes, setEdges])

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

  const resetZoomAndCenter = () => {
    reactFlowInstance.current?.fitView({ padding: 0.18, duration: 500 })
  }

  // Grouped structure for the Structural Explorer view (Only showing entities with events)
  const structuredHierarchy = useMemo(() => {
    if (!graphData || !(graphData as any).nodes) return []
    const raw = graphData as { nodes: RawNode[]; edges: RawEdge[] }

    const modules = raw.nodes.filter((n) => n.node_type === 'module')
    const features = raw.nodes.filter((n) => n.node_type === 'feature')

    // Map features to modules
    const featToModule = new Map<string, string>()
    raw.edges.forEach((e) => {
      if (e.relationship_type === 'MODULE_CONTAINS_FEATURE') {
        featToModule.set(e.target, e.source)
      }
    })

    // Map events to features
    const featEvents = new Map<string, RawNode[]>()
    raw.edges.forEach((e) => {
      if (
        e.relationship_type === 'FEATURE_HAS_EVENT' ||
        e.relationship_type === 'DECISION_RELATES_TO' ||
        e.relationship_type === 'EVENT_AFFECTS_FEATURE'
      ) {
        const evNode = raw.nodes.find((n) => n.id === e.target)
        if (evNode) {
          const list = featEvents.get(e.source) || []
          list.push(evNode)
          featEvents.set(e.source, list)
        }
      }
    })

    const groups: {
      id: string
      groupTitle: string
      groupType: 'module' | 'core'
      features: { feature: RawNode; events: RawNode[] }[]
    }[] = []

    // 1. Process standard modules: ONLY keep if they have active features with events
    modules.forEach((mod) => {
      const modFeatures = features.filter(
        (f) => featToModule.get(f.id) === mod.id || f.module_name === mod.label
      )
      const activeFeatures = modFeatures
        .map((f) => ({ feature: f, events: featEvents.get(f.id) || [] }))
        .filter((item) => item.events.length > 0)

      if (activeFeatures.length > 0) {
        groups.push({
          id: mod.id,
          groupTitle: mod.label,
          groupType: 'module',
          features: activeFeatures,
        })
      }
    })

    // 2. Process features with events that have no module assigned
    const handledFeatureIds = new Set(
      groups.flatMap((g) => g.features.map((f) => f.feature.id))
    )
    const unhandledWithEvents = features
      .filter((f) => !handledFeatureIds.has(f.id))
      .map((f) => ({ feature: f, events: featEvents.get(f.id) || [] }))
      .filter((item) => item.events.length > 0)

    if (unhandledWithEvents.length > 0) {
      groups.push({
        id: 'core-active-features',
        groupTitle: 'Active Feature Milestones & Decisions',
        groupType: 'core',
        features: unhandledWithEvents,
      })
    }

    return groups
  }, [graphData])

  return (
    <div className="flex flex-col h-screen">
      {/* Top Header & Interactive Controls */}
      <div className="px-6 pt-5 pb-3 flex-shrink-0 border-b border-purple-900/20 bg-[#0a0f1e]/90 backdrop-blur-md">
        <PageHeader
          title="Temporal Knowledge Graph"
          subtitle="Explore features, decisions, and sequential milestones with modular 2D clustering, radial orbits, swimlanes, and multi-structure layouts"
          actions={
            <div className="flex items-center gap-2">
              {/* View Switcher: Canvas vs. Explorer */}
              <div className="flex bg-slate-900/90 rounded-lg p-0.5 border border-slate-700/60 text-xs">
                <button
                  onClick={() => setActiveView('canvas')}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all',
                    activeView === 'canvas'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  )}
                >
                  <Grid size={13} />
                  <span>Graph Canvas</span>
                </button>
                <button
                  onClick={() => setActiveView('explorer')}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all',
                    activeView === 'explorer'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  )}
                >
                  <FolderTree size={13} />
                  <span>Hierarchy Matrix</span>
                </button>
              </div>

              <button
                onClick={() => rebuildMutation.mutate()}
                disabled={rebuildMutation.isPending || isRefetching}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/40 text-xs font-medium text-purple-300 border border-purple-500/30 transition-all disabled:opacity-50"
                title="Rebuild graph from current database records"
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

        {/* Toolbar Controls */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Left filters & search */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Search in graph */}
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search nodes in graph..."
                value={nodeSearch}
                onChange={(e) => setNodeSearch(e.target.value)}
                className="bg-slate-900/80 border border-slate-700/60 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500/70 w-48"
              />
              {nodeSearch && (
                <button
                  onClick={() => setNodeSearch('')}
                  className="absolute right-2 top-2 text-slate-500 hover:text-slate-300"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Feature Focus Filter - only showing features that have events */}
            <div className="flex items-center gap-1.5 bg-slate-900/70 border border-slate-700/60 rounded-lg px-2.5 py-1.5 text-slate-300">
              <Filter size={13} className="text-purple-400" />
              <span className="text-slate-400 font-medium">Focus:</span>
              <select
                value={currentFeatureFilter}
                onChange={(e) => handleFeatureFilterChange(e.target.value)}
                className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer max-w-[170px] truncate"
              >
                <option value="" className="bg-[#0d1530] text-slate-200">
                  All Active Features
                </option>
                {featuresData?.features
                  .filter((f) => !onlyWithEvents || f.event_count > 0)
                  .map((f) => (
                    <option key={f.id} value={f.id} className="bg-[#0d1530] text-slate-200">
                      {f.canonical_name} ({f.event_count} events)
                    </option>
                  ))}
              </select>
            </div>

            {/* Layout Structure Switcher (Canvas View) */}
            {activeView === 'canvas' && (
              <div className="flex items-center gap-1.5 bg-slate-900/70 border border-slate-700/60 rounded-lg px-2.5 py-1 text-slate-300">
                <Compass size={13} className="text-purple-400" />
                <span className="text-slate-400 font-medium">Structure:</span>
                <select
                  value={layoutStructure}
                  onChange={(e) => setLayoutStructure(e.target.value as LayoutStructure)}
                  className="bg-transparent text-purple-300 font-medium text-xs focus:outline-none cursor-pointer"
                >
                  <option value="clusters" className="bg-[#0d1530] text-slate-200">
                    Modular Clusters (2D Shelf Grid)
                  </option>
                  <option value="swimlanes" className="bg-[#0d1530] text-slate-200">
                    Module Swimlanes
                  </option>
                  <option value="concentric" className="bg-[#0d1530] text-slate-200">
                    Concentric Radial Orbit
                  </option>
                  <option value="timeline" className="bg-[#0d1530] text-slate-200">
                    Chronological Flow
                  </option>
                  <option value="hierarchical-tb" className="bg-[#0d1530] text-slate-200">
                    Hierarchical (Top-Down)
                  </option>
                  <option value="hierarchical-lr" className="bg-[#0d1530] text-slate-200">
                    Hierarchical (Left-to-Right)
                  </option>
                </select>
              </div>
            )}

            {/* Toggle Show Documents */}
            <button
              onClick={() => setShowDocuments((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors ${
                showDocuments
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-slate-900/70 text-slate-400 border-slate-700/60 hover:text-slate-200'
              }`}
              title="Toggle source document leaf nodes"
            >
              {showDocuments ? <Eye size={13} /> : <EyeOff size={13} />}
              <span>{showDocuments ? 'Documents Visible' : 'Hide Documents'}</span>
            </button>

            {/* Filter Toggle: Only Features With Events (active by default) */}
            <button
              onClick={() => setOnlyWithEvents((v) => !v)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors',
                onlyWithEvents
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm'
                  : 'bg-slate-900/70 text-slate-400 border-slate-700/60 hover:text-slate-200'
              )}
              title={
                onlyWithEvents
                  ? 'Showing strictly entities with events. Click to include 0-event features.'
                  : 'Showing all entities. Click to show only features with events.'
              }
            >
              <CheckCircle2
                size={13}
                className={onlyWithEvents ? 'text-emerald-400' : 'text-slate-500'}
              />
              <span>{onlyWithEvents ? 'Only Features With Events' : 'All Entities (Inc. 0 Events)'}</span>
            </button>
          </div>

          {/* Right Stats & Fit-view Button */}
          <div className="flex items-center gap-3">
            <span className="text-slate-400 font-mono text-[11px]">
              {nodes.length} Visible Nodes ({onlyWithEvents ? 'Only With Events' : 'All Entities'}) •{' '}
              {edges.length} Edges
            </span>
            {activeView === 'canvas' && (
              <button
                onClick={resetZoomAndCenter}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition-colors"
                title="Fit entire graph to screen"
              >
                <Maximize2 size={12} />
                <span>Fit View</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 mx-6 my-4 rounded-xl border border-purple-900/30 overflow-hidden bg-[#070b19] relative shadow-inner flex flex-col">
        {isLoading ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw size={28} className="animate-spin text-purple-400" />
            <div className="text-sm">Calculating graph layout and clustering…</div>
          </div>
        ) : activeView === 'explorer' ? (
          /* Structural Hierarchy Matrix View */
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-purple-900/30 pb-3">
              <div>
                <h3 className="text-base font-semibold text-white">
                  Product Architecture & Historical Matrix
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Showing active features with recorded sequential lifecycle events and decisions
                </p>
              </div>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-950/40 px-3 py-1 rounded-lg border border-emerald-800/40 flex items-center gap-1.5">
                <CheckCircle size={12} />
                {structuredHierarchy.reduce((acc, g) => acc + g.features.length, 0)} Active Features With Events
              </span>
            </div>

            {structuredHierarchy.length === 0 ? (
              <div className="py-12 text-center text-slate-500">
                <Info size={32} className="mx-auto mb-2 opacity-40 text-purple-400" />
                <div className="text-slate-300 font-medium">No Features with Events Found</div>
                <div className="text-xs text-slate-500 mt-1">
                  Upload project documents to record events and populate the knowledge graph.
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {structuredHierarchy.map((group) => (
                  <div
                    key={group.id}
                    className="rounded-xl border border-blue-900/30 bg-[#0d1636]/90 p-5 space-y-4 shadow-lg backdrop-blur-md"
                  >
                    <div className="flex items-center justify-between border-b border-blue-900/40 pb-3">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-blue-600/20 text-blue-300 border border-blue-500/30">
                          <Boxes size={16} />
                        </div>
                        <h4 className="text-sm font-bold text-white tracking-wide">
                          {group.groupTitle}
                        </h4>
                      </div>
                      <span className="text-[11px] font-mono text-slate-400">
                        {group.features.length} active features
                      </span>
                    </div>

                    <div className="space-y-3">
                      {group.features.map((item) => (
                        <div
                          key={item.feature.id}
                          className="rounded-lg bg-slate-900/60 border border-slate-800/80 p-3 space-y-2 hover:border-purple-500/40 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-purple-200">
                              {item.feature.label}
                            </span>
                            <button
                              onClick={() =>
                                navigate(
                                  `/timeline?featureId=${
                                    item.feature.feature_id || item.feature.id.replace('feature:', '')
                                  }`
                                )
                              }
                              className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium"
                            >
                              <ExternalLink size={10} />
                              Timeline
                            </button>
                          </div>

                          <div className="space-y-1.5 pt-1">
                            {item.events.map((ev, i) => (
                              <div
                                key={i}
                                className="flex items-start gap-2 text-[11px] text-slate-300 pl-2 border-l-2 border-emerald-500/40"
                              >
                                <span className="text-[10px] uppercase font-mono px-1 rounded bg-slate-800 text-slate-400">
                                  {ev.decision_status || ev.node_type}
                                </span>
                                <span className="truncate">{ev.label}</span>
                                {ev.event_date && (
                                  <span className="ml-auto text-[10px] text-slate-500 font-mono flex-shrink-0">
                                    {ev.event_date}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : nodes.length === 0 ? (
          /* Empty State */
          <div className="h-full flex items-center justify-center text-slate-500">
            <div className="text-center max-w-sm">
              <Info size={36} className="mx-auto mb-2 opacity-40 text-purple-400" />
              <div className="text-slate-300 font-medium">No Graph Data to Display</div>
              <div className="text-xs text-slate-500 mt-1">
                {currentFeatureFilter
                  ? 'No events or relationships found for this feature.'
                  : 'No features with events found. Upload project documents to build the temporal knowledge graph.'}
              </div>
            </div>
          </div>
        ) : (
          /* Interactive ReactFlow Graph Canvas */
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            onInit={(instance) => {
              reactFlowInstance.current = instance
              instance.fitView({ padding: 0.18 })
            }}
            fitView
            minZoom={0.12}
            maxZoom={2.0}
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

        {/* Selected Node Details Side Drawer */}
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
                  <span className="text-slate-500">Status:</span>
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

            <div className="pt-1 flex gap-2">
              {selectedNode.node_type === 'feature' && (
                <>
                  <button
                    onClick={() =>
                      navigate(
                        `/timeline?featureId=${
                          selectedNode.feature_id || selectedNode.id.replace('feature:', '')
                        }`
                      )
                    }
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 text-xs font-medium text-purple-200 border border-purple-500/30 transition-all hover:shadow"
                  >
                    <ExternalLink size={12} />
                    View Timeline
                  </button>
                  <button
                    onClick={() =>
                      handleFeatureFilterChange(
                        selectedNode.feature_id || selectedNode.id.replace('feature:', '')
                      )
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
