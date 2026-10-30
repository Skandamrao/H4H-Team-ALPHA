import { useEffect, useState, useCallback } from 'react';
import { listFeatures, listEvents } from '../api/client';
import { useAppStore } from '../stores/useAppStore';
import ReactFlow, {
  Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState,
  type Connection, type Edge, type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { Feature, TemporalEvent } from '../types';

function buildGraph(features: Feature[], events: TemporalEvent[]) {
  const nodes: Node[] = features.map((f, i) => ({
    id: f.id,
    data: {
      label: (
        <div className="text-xs font-semibold text-center px-1">
          <div>{f.canonical_name}</div>
          {f.is_implemented && <div className="text-emerald-600 text-[10px]">✓ Impl.</div>}
          {f.is_removed && <div className="text-gray-400 text-[10px]">✗ Removed</div>}
        </div>
      ),
    },
    position: {
      x: 120 + (i % 4) * 220,
      y: 80 + Math.floor(i / 4) * 160,
    },
    style: {
      background: f.is_implemented ? '#d1fae5' : f.is_removed ? '#f3f4f6' : '#eff6ff',
      border: `1.5px solid ${f.is_implemented ? '#6ee7b7' : f.is_removed ? '#d1d5db' : '#a5b4fc'}`,
      borderRadius: 10,
      fontSize: 12,
      minWidth: 140,
    },
  }));

  const edgeMap = new Map<string, Edge>();
  events.filter(e => e.event_type === 'DEPENDENCY_ADDED' && e.feature_id && e.related_event_ids.length).forEach(e => {
    e.related_event_ids.forEach(rel => {
      const edgeId = `${e.feature_id}-${rel}`;
      if (!edgeMap.has(edgeId)) {
        edgeMap.set(edgeId, {
          id: edgeId,
          source: e.feature_id!,
          target: rel,
          label: 'depends on',
          style: { stroke: '#6366f1' },
          labelStyle: { fontSize: 10 },
          animated: true,
        });
      }
    });
  });

  return { nodes, edges: Array.from(edgeMap.values()) };
}

export default function GraphPage() {
  const { projectId } = useAppStore();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);

  const onConnect = useCallback(
    (params: Connection) => setEdges(eds => addEdge(params, eds)),
    [setEdges],
  );

  useEffect(() => {
    setLoading(true);
    Promise.all([listFeatures(projectId), listEvents(projectId, { limit: 500 })]).then(([f, e]) => {
      const { nodes: n, edges: ed } = buildGraph(f, e);
      setNodes(n);
      setEdges(ed);
    }).finally(() => setLoading(false));
  }, [projectId]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Feature Entity Graph</h1>
        <p className="text-sm text-gray-500 mt-1">Interactive graph of features and dependencies.</p>
      </div>

      {loading ? (
        <p className="text-sm text-indigo-600 animate-pulse">Building graph…</p>
      ) : (
        <div className="border border-gray-200 rounded-xl overflow-hidden" style={{ height: 520 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
          >
            <Background gap={16} size={1} />
            <Controls />
            <MiniMap nodeColor={n => (n.style?.background as string) ?? '#eff6ff'} />
          </ReactFlow>
        </div>
      )}

      {!loading && nodes.length === 0 && (
        <p className="text-sm text-gray-400">No features found. Ingest some records first.</p>
      )}
    </div>
  );
}

