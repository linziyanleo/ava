import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, GitBranch, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { StatusBadge, type StatusKind } from '../ui/StatusBadge'
import {
  useWorkflowStore,
  type WorkflowChain,
  type WorkflowNode,
} from '../../stores/useWorkflowStore'
import { useTaskFloater } from '../../stores/taskFloater'

const ACTIVE_CHAIN = new Set(['pending', 'running'])
const FAILED_CHAIN = new Set(['failed', 'interrupted'])
const DONE_CHAIN = new Set(['succeeded', 'cancelled'])

const ACTIVE_NODE = new Set(['pending', 'awaiting_deps', 'queued', 'running', 'streaming'])
const FAILED_NODE = new Set(['failed', 'interrupted'])

function chainStatusKind(status: string): StatusKind {
  if (ACTIVE_CHAIN.has(status)) return status === 'pending' ? 'queued' : 'running'
  if (FAILED_CHAIN.has(status)) return 'failed'
  if (status === 'succeeded') return 'completed'
  if (status === 'cancelled') return 'cancelled'
  return 'idle'
}

function formatRelative(ts: number, nowMs: number): string {
  if (!ts) return '-'
  const deltaSec = Math.max(0, Math.round((nowMs - ts * 1000) / 1000))
  if (deltaSec < 60) return `${deltaSec}s 前`
  const min = Math.floor(deltaSec / 60)
  if (min < 60) return `${min}m 前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h 前`
  const day = Math.floor(hr / 24)
  return `${day}d 前`
}

function nodeCounts(nodes: WorkflowNode[]) {
  let active = 0
  let failed = 0
  let done = 0
  for (const node of nodes) {
    if (ACTIVE_NODE.has(node.status)) active += 1
    else if (FAILED_NODE.has(node.status)) failed += 1
    else done += 1
  }
  return { total: nodes.length, active, failed, done }
}

export type WorkflowView = 'all' | 'active' | 'failed' | 'done'

const VIEW_TABS: Array<{ id: WorkflowView; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'active', label: '进行中' },
  { id: 'failed', label: '失败' },
  { id: 'done', label: '已完成' },
]

export default function WorkflowsListPanel() {
  const navigate = useNavigate()
  const { workflowView, setWorkflowView, close } = useTaskFloater()
  const { chains, loading, error, fetchChains, connectTaskEvents } = useWorkflowStore()
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    void fetchChains()
    const disconnect = connectTaskEvents()
    return () => disconnect()
  }, [fetchChains, connectTaskEvents])

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const visibleChains = useMemo(() => {
    const filtered = chains.filter(chain => {
      if (workflowView === 'active') return ACTIVE_CHAIN.has(chain.status)
      if (workflowView === 'failed') return FAILED_CHAIN.has(chain.status)
      if (workflowView === 'done') return DONE_CHAIN.has(chain.status)
      return true
    })
    return [...filtered].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))
  }, [chains, workflowView])

  const handleOpen = (chain: WorkflowChain) => {
    navigate(`/workflows/${encodeURIComponent(chain.chain_id)}`)
    close()
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 overflow-x-auto scrollbar-none">
        {VIEW_TABS.map(item => (
          <button
            key={item.id}
            type="button"
            onClick={() => setWorkflowView(item.id)}
            className={cn(
              'h-8 shrink-0 rounded-md px-3 text-xs font-medium transition-colors',
              workflowView === item.id
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] p-3 text-sm text-[var(--ava-danger)]">
          {error}
        </div>
      )}

      {loading && chains.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-12 text-[var(--text-secondary)] text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          加载 workflow…
        </div>
      ) : visibleChains.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-12 text-[var(--text-secondary)] text-sm">
          <GitBranch className="w-8 h-8 opacity-40" />
          <p>{workflowView === 'all' ? '暂无 workflow' : `暂无${VIEW_TABS.find(v => v.id === workflowView)?.label}的 workflow`}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {visibleChains.map(chain => (
            <ChainRow key={chain.chain_id} chain={chain} onOpen={handleOpen} nowMs={nowMs} />
          ))}
        </ul>
      )}
    </div>
  )
}

function ChainRow({ chain, onOpen, nowMs }: { chain: WorkflowChain; onOpen: (chain: WorkflowChain) => void; nowMs: number }) {
  const counts = nodeCounts(chain.nodes ?? [])

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(chain)}
        className="group flex w-full items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3 text-left transition-colors hover:border-[var(--accent)]/40 hover:bg-[var(--bg-tertiary)]"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge kind={chainStatusKind(chain.status)} label={chain.status} size="sm" />
            <h3 className="text-sm font-medium text-[var(--text-primary)] truncate">
              {chain.title || `Workflow ${chain.chain_id.slice(0, 8)}`}
            </h3>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)]">
            <span className="font-mono">chain:{chain.chain_id.slice(0, 12)}</span>
            <span>共 {counts.total} step</span>
            {counts.active > 0 && (
              <span className="text-[var(--ava-running)]">{counts.active} 进行中</span>
            )}
            {counts.failed > 0 && (
              <span className="text-[var(--ava-danger)]">{counts.failed} 失败</span>
            )}
            {chain.updated_at > 0 && <span>{formatRelative(chain.updated_at, nowMs)}</span>}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 shrink-0 text-[var(--text-secondary)] group-hover:text-[var(--accent)] transition-colors" />
      </button>
    </li>
  )
}
