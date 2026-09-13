import { useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, Position, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import type { ArchitectureGraph } from '../types'

export function ArchitectureFlow({ graph }: { graph: ArchitectureGraph }) {
  const nodes = useMemo<Node[]>(() => graph.nodes.map((node) => ({
    id: node.id,
    position: { x: node.x, y: node.y },
    data: { label: <div className="flow-node-label"><strong>{node.label}</strong>{node.subtitle ? <small>{node.subtitle}</small> : null}</div> },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    className: `flow-node flow-${node.kind}`,
  })), [graph])

  const edges = useMemo<Edge[]>(() => graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label,
    animated: edge.label === 'imports',
  })), [graph])

  return (
    <div className="architecture-flow">
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.2} maxZoom={1.8} proOptions={{ hideAttribution: true }}>
        <MiniMap pannable zoomable />
        <Controls />
        <Background gap={18} size={1} />
      </ReactFlow>
    </div>
  )
}
