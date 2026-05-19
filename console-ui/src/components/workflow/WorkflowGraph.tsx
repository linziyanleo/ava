/**
 * AVA-48 P2c plan-step-11: read-only workflow graph.
 *
 * Renders a `WorkflowDefinitionDoc` as a react-flow graph with dagre
 * auto-layout. Node colour reflects run-step status; node accent colour
 * reflects agent kind (codex 蓝 / claude_code 紫 / image_gen 橙 / nanobot 灰).
 *
 * The component is read-only — edits go through the form/JSON dual-mode editor
 * elsewhere on the Detail page.
 */
import { useMemo } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import dagre from 'dagre'
import '@xyflow/react/dist/style.css'

import type { WorkflowDefinitionDoc } from '../../api/workflow-definitions'

export type StepRuntimeStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

const STATUS_COLOURS: Record<StepRuntimeStatus, { fill: string; border: string; label: string }> = {
  idle: { fill: '#f4f4f5', border: '#a1a1aa', label: 'Idle' },
  queued: { fill: '#dbeafe', border: '#2563eb', label: 'Queued' },
  running: { fill: '#2563eb', border: '#1e3a8a', label: 'Running' },
  succeeded: { fill: '#dcfce7', border: '#16a34a', label: 'Succeeded' },
  failed: { fill: '#fee2e2', border: '#dc2626', label: 'Failed' },
  cancelled: { fill: '#f4f4f5', border: '#52525b', label: 'Cancelled' },
}

const AGENT_COLOURS: Record<string, string> = {
  codex: '#2563eb',
  claude_code: '#7c3aed',
  image_gen: '#ea580c',
  nanobot: '#52525b',
}

function agentTone(agent: string): string {
  if (agent.startsWith('a2a://')) return '#94a3b8'
  return AGENT_COLOURS[agent] ?? '#71717a'
}

function statusOf(
  stepId: string,
  runStatuses: Record<string, StepRuntimeStatus> | undefined,
): StepRuntimeStatus {
  return (runStatuses && runStatuses[stepId]) || 'idle'
}

interface StepNodeData extends Record<string, unknown> {
  stepId: string
  agent: string
  status: StepRuntimeStatus
  promptPreview: string
  isSelected: boolean
}

function StepNode({ data }: NodeProps<Node<StepNodeData>>) {
  const status = STATUS_COLOURS[data.status]
  const tone = agentTone(data.agent)
  return (
    <div
      style={{
        background: status.fill,
        borderColor: status.border,
        borderStyle: data.status === 'cancelled' ? 'dashed' : 'solid',
        boxShadow: data.isSelected ? `0 0 0 2px ${tone}` : 'none',
        color: data.status === 'running' ? '#fff' : '#0f172a',
      }}
      className="min-w-[180px] rounded-md border-2 px-3 py-2 text-xs"
    >
      <Handle type="target" position={Position.Left} style={{ background: tone }} />
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono">{data.stepId}</span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-medium"
          style={{ background: tone, color: '#fff' }}
        >
          {data.agent}
        </span>
      </div>
      <div className="mt-1 line-clamp-2 text-[10px] opacity-80">{data.promptPreview}</div>
      <div className="mt-1 text-[10px] uppercase tracking-wide" style={{ color: status.border }}>
        {status.label}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: tone }} />
    </div>
  )
}

const NODE_TYPES = { workflowStep: StepNode }

interface DagreLayoutOptions {
  rankdir: 'LR' | 'TB'
  nodeWidth: number
  nodeHeight: number
}

const DEFAULT_LAYOUT: DagreLayoutOptions = { rankdir: 'LR', nodeWidth: 200, nodeHeight: 90 }

const STEP_INPUT_REF_RE = /^\$\.steps\.([^.]+)\.outputs\./

export function layoutWorkflow(
  definition: WorkflowDefinitionDoc,
  options: Partial<DagreLayoutOptions> = {},
): { nodes: Node<StepNodeData>[]; edges: Edge[] } {
  const layout: DagreLayoutOptions = { ...DEFAULT_LAYOUT, ...options }
  const dag = new dagre.graphlib.Graph()
  dag.setGraph({ rankdir: layout.rankdir, nodesep: 36, ranksep: 64 })
  dag.setDefaultEdgeLabel(() => ({}))

  for (const step of definition.steps) {
    dag.setNode(step.id, { width: layout.nodeWidth, height: layout.nodeHeight })
  }

  const edges: Edge[] = []
  let prevId: string | null = null
  for (const step of definition.steps) {
    if (step.next) {
      dag.setEdge(step.id, step.next)
      edges.push({ id: `${step.id}->${step.next}`, source: step.id, target: step.next })
    } else if (prevId) {
      dag.setEdge(prevId, step.id)
      edges.push({ id: `${prevId}->${step.id}`, source: prevId, target: step.id })
    }
    prevId = step.id
  }

  for (const step of definition.steps) {
    for (const expr of Object.values(step.inputs || {})) {
      const matched = STEP_INPUT_REF_RE.exec(expr)
      if (matched && matched[1] !== step.id) {
        const edgeId = `${matched[1]}->${step.id}#input`
        if (!edges.some((edge) => edge.id === edgeId)) {
          edges.push({
            id: edgeId,
            source: matched[1],
            target: step.id,
            animated: true,
            style: { strokeDasharray: '4 4' },
          })
          dag.setEdge(matched[1], step.id)
        }
      }
    }
  }

  dagre.layout(dag)

  const nodes: Node<StepNodeData>[] = definition.steps.map((step) => {
    const pos = dag.node(step.id)
    return {
      id: step.id,
      type: 'workflowStep',
      position: {
        x: (pos?.x ?? 0) - layout.nodeWidth / 2,
        y: (pos?.y ?? 0) - layout.nodeHeight / 2,
      },
      data: {
        stepId: step.id,
        agent: step.agent,
        status: 'idle',
        promptPreview: step.task.prompt_template.slice(0, 80),
        isSelected: false,
      },
    }
  })

  return { nodes, edges }
}

export interface WorkflowGraphProps {
  definition: WorkflowDefinitionDoc
  runStatuses?: Record<string, StepRuntimeStatus>
  selectedStepId?: string | null
  onStepClick?: (stepId: string) => void
  height?: number
}

export function WorkflowGraph({
  definition,
  runStatuses,
  selectedStepId,
  onStepClick,
  height = 440,
}: WorkflowGraphProps) {
  const { nodes, edges } = useMemo(() => {
    const laid = layoutWorkflow(definition)
    return {
      nodes: laid.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          status: statusOf(node.id, runStatuses),
          isSelected: node.id === selectedStepId,
        },
      })),
      edges: laid.edges,
    }
  }, [definition, runStatuses, selectedStepId])

  if (definition.steps.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border bg-zinc-50 text-xs text-zinc-500 dark:border-zinc-700 dark:bg-zinc-950"
        style={{ height }}
      >
        Definition 中没有 step；先在 Form 或 JSON 模式添加再回到此 tab 查看图。
      </div>
    )
  }

  return (
    <div
      style={{ height }}
      className="rounded border bg-white dark:border-zinc-700 dark:bg-zinc-900"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onStepClick?.(node.id)}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable style={{ height: 80 }} />
      </ReactFlow>
    </div>
  )
}

export default WorkflowGraph
