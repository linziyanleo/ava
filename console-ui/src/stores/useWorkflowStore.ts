import { create } from 'zustand'
import { api, wsUrl } from '../api/client'

export type TaskNodeStatus =
  | 'pending'
  | 'awaiting_deps'
  | 'queued'
  | 'running'
  | 'streaming'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'skipped'

export interface WorkflowNode {
  task_id: string
  chain_id: string
  status: TaskNodeStatus
  parent_task_ids: string[]
  node_kind: string
  title: string
  position: number
  metadata: Record<string, unknown>
}

export interface ArtifactRecord {
  artifact_id: string
  task_id: string
  chain_id: string
  trace_id: string
  artifact_type: string
  uri: string
  preview: string
  created_at: number
  metadata: Record<string, unknown>
}

export interface WorkflowChain {
  chain_id: string
  trace_id: string
  title: string
  status: string
  created_at: number
  updated_at: number
  metadata: Record<string, unknown>
  nodes: WorkflowNode[]
  artifacts?: ArtifactRecord[]
}

interface WorkflowFilters {
  traceId?: string | null
  status?: string | null
}

interface ArtifactFilters {
  taskId?: string | null
  chainId?: string | null
  traceId?: string | null
  artifactType?: string | null
}

interface WorkflowState {
  chains: WorkflowChain[]
  selectedChain: WorkflowChain | null
  artifacts: ArtifactRecord[]
  loading: boolean
  error: string
  fetchChains: (filters?: WorkflowFilters) => Promise<void>
  fetchChain: (chainId: string) => Promise<void>
  fetchArtifacts: (filters?: ArtifactFilters) => Promise<void>
  connectTaskEvents: (filters?: WorkflowFilters & ArtifactFilters) => () => void
}

interface WorkflowRealtimeEvent {
  type: 'workflow_events'
  chains: WorkflowChain[]
  artifacts: ArtifactRecord[]
}

function workflowQuery(filters: WorkflowFilters = {}) {
  const params = new URLSearchParams()
  if (filters.traceId) params.set('trace_id', filters.traceId)
  if (filters.status) params.set('status', filters.status)
  const query = params.toString()
  return `/workflows${query ? `?${query}` : ''}`
}

function artifactQuery(filters: ArtifactFilters = {}) {
  const params = new URLSearchParams()
  if (filters.taskId) params.set('task_id', filters.taskId)
  if (filters.chainId) params.set('chain_id', filters.chainId)
  if (filters.traceId) params.set('trace_id', filters.traceId)
  if (filters.artifactType) params.set('artifact_type', filters.artifactType)
  const query = params.toString()
  return `/artifacts${query ? `?${query}` : ''}`
}

function workflowRealtimeQuery(filters: WorkflowFilters & ArtifactFilters = {}) {
  const params = new URLSearchParams()
  if (filters.traceId) params.set('trace_id', filters.traceId)
  if (filters.chainId) params.set('chain_id', filters.chainId)
  if (filters.taskId) params.set('task_id', filters.taskId)
  if (filters.artifactType) params.set('artifact_type', filters.artifactType)
  const query = params.toString()
  return `/workflows/ws${query ? `?${query}` : ''}`
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  chains: [],
  selectedChain: null,
  artifacts: [],
  loading: false,
  error: '',

  async fetchChains(filters = {}) {
    set({ loading: true, error: '' })
    try {
      const response = await api<{ chains: WorkflowChain[] }>(workflowQuery(filters))
      set({ chains: response.chains || [], loading: false })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to load workflows', loading: false })
    }
  },

  async fetchChain(chainId) {
    set({ loading: true, error: '' })
    try {
      const chain = await api<WorkflowChain>(`/workflows/${encodeURIComponent(chainId)}`)
      set({ selectedChain: chain, artifacts: chain.artifacts || get().artifacts, loading: false })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to load workflow', loading: false })
    }
  },

  async fetchArtifacts(filters = {}) {
    try {
      const response = await api<{ artifacts: ArtifactRecord[] }>(artifactQuery(filters))
      set({ artifacts: response.artifacts || [] })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to load artifacts' })
    }
  },

  connectTaskEvents(filters = {}) {
    const socket = new WebSocket(wsUrl(workflowRealtimeQuery(filters)))
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as WorkflowRealtimeEvent
        if (payload.type === 'workflow_events') {
          const selectedChainId = get().selectedChain?.chain_id
          const selectedChain = selectedChainId
            ? payload.chains.find((chain) => chain.chain_id === selectedChainId) || get().selectedChain
            : get().selectedChain
          set({
            chains: payload.chains || [],
            artifacts: payload.artifacts || [],
            selectedChain,
          })
          return
        }
      } catch {
        // Fall back to the REST refresh below when an older gateway emits task snapshots.
      }
      void get().fetchChains(filters)
      void get().fetchArtifacts(filters)
    }
    socket.onerror = () => socket.close()
    return () => socket.close()
  },
}))
