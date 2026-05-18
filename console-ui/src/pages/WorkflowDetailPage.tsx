import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ChevronRight,
  Loader2,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  XCircle,
} from 'lucide-react'
import { api } from '../api/client'
import { cn } from '../lib/utils'
import { StatusBadge, type StatusKind } from '../components/ui/StatusBadge'
import { ArtifactPreview } from '../components/artifact/ArtifactPreview'
import {
  useWorkflowStore,
  type ArtifactRecord,
  type TaskNodeStatus,
  type WorkflowChain,
  type WorkflowNode,
} from '../stores/useWorkflowStore'

// Map TaskNodeStatus + ChainStatus → semantic StatusKind for badges.
function statusToKind(status: string): StatusKind {
  switch (status) {
    case 'running':
    case 'streaming':
      return 'running'
    case 'pending':
    case 'awaiting_deps':
      return 'waiting'
    case 'queued':
      return 'queued'
    case 'succeeded':
      return 'completed'
    case 'failed':
    case 'interrupted':
      return 'failed'
    case 'cancelled':
      return 'cancelled'
    case 'skipped':
      return 'paused'
    default:
      return 'idle'
  }
}

const NODE_STATUS_LABEL: Record<TaskNodeStatus, string> = {
  pending: '待解析',
  awaiting_deps: '等待前置',
  queued: '排队中',
  running: '运行中',
  streaming: '产出中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '中断',
  skipped: '已跳过',
}

const ACTIVE_CHAIN_STATUSES = new Set(['pending', 'running'])
const FAILED_CHAIN_STATUSES = new Set(['failed', 'interrupted'])

function formatDuration(ms: number): string {
  if (ms < 0) return '-'
  if (ms < 1000) return `${ms}ms`
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  if (min < 60) return `${min}m ${remSec}s`
  const hr = Math.floor(min / 60)
  return `${hr}h ${min % 60}m`
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function chainCoordinator(chain: WorkflowChain): string | null {
  const meta = chain.metadata ?? {}
  const value = meta.coordinator ?? meta.agent ?? meta.runner
  return typeof value === 'string' ? value : null
}

function nodeAgent(node: WorkflowNode): string | null {
  const value = node.metadata?.agent ?? node.metadata?.tool ?? node.node_kind
  return typeof value === 'string' && value.length > 0 ? value : null
}

function nodeInputSummary(node: WorkflowNode): string | null {
  const value = node.metadata?.input_summary ?? node.metadata?.input ?? node.metadata?.prompt
  return typeof value === 'string' ? value : null
}

function nodeOutputSummary(node: WorkflowNode): string | null {
  const value = node.metadata?.output_summary ?? node.metadata?.output ?? node.metadata?.result
  return typeof value === 'string' ? value : null
}

function nodeError(node: WorkflowNode): string | null {
  const value = node.metadata?.error ?? node.metadata?.error_message
  return typeof value === 'string' ? value : null
}

function nodeRetryCount(node: WorkflowNode): number {
  const value = node.metadata?.retry_count
  return typeof value === 'number' ? value : 0
}

export default function WorkflowDetailPage() {
  const { chainId } = useParams<{ chainId: string }>()
  const navigate = useNavigate()
  const { selectedChain, loading, error, fetchChain, connectTaskEvents } = useWorkflowStore()
  const [busyAction, setBusyAction] = useState<'cancel' | 'retry' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState<number>(() => Date.now())

  useEffect(() => {
    if (!chainId) return
    void fetchChain(chainId)
    const disconnect = connectTaskEvents({ chainId })
    return () => disconnect()
  }, [chainId, fetchChain, connectTaskEvents])

  // Tick once per second so running duration ages live.
  useEffect(() => {
    if (!selectedChain) return
    if (!ACTIVE_CHAIN_STATUSES.has(selectedChain.status)) return
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [selectedChain])

  const sortedNodes = useMemo<WorkflowNode[]>(() => {
    if (!selectedChain) return []
    return [...selectedChain.nodes].sort((a, b) => a.position - b.position)
  }, [selectedChain])

  const selectedNode = useMemo<WorkflowNode | null>(() => {
    if (!selectedNodeId) return sortedNodes[0] ?? null
    return sortedNodes.find(n => n.task_id === selectedNodeId) ?? sortedNodes[0] ?? null
  }, [selectedNodeId, sortedNodes])

  const nodeArtifacts = useMemo<ArtifactRecord[]>(() => {
    if (!selectedNode || !selectedChain) return []
    const all = selectedChain.artifacts ?? []
    return all.filter(a => a.task_id === selectedNode.task_id)
  }, [selectedChain, selectedNode])

  if (!chainId) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-secondary)] text-sm">
        缺少 chain_id
      </div>
    )
  }

  if (loading && !selectedChain) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        加载 workflow…
      </div>
    )
  }

  if (error && !selectedChain) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] p-4 text-sm text-[var(--ava-danger)]">
          {error}
        </div>
      </div>
    )
  }

  if (!selectedChain) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-secondary)] text-sm">
        未找到该 workflow
      </div>
    )
  }

  const isActive = ACTIVE_CHAIN_STATUSES.has(selectedChain.status)
  const isFailed = FAILED_CHAIN_STATUSES.has(selectedChain.status)
  const startedAtMs = (selectedChain.created_at || 0) * 1000
  const endedAtMs = isActive ? nowMs : (selectedChain.updated_at || selectedChain.created_at || 0) * 1000
  const durationMs = startedAtMs ? Math.max(0, endedAtMs - startedAtMs) : 0
  const coordinator = chainCoordinator(selectedChain)

  const handleCancel = async () => {
    setBusyAction('cancel')
    setActionError(null)
    try {
      await api(`/workflows/${encodeURIComponent(selectedChain.chain_id)}/cancel`, { method: 'POST' })
      await fetchChain(selectedChain.chain_id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '取消失败')
    } finally {
      setBusyAction(null)
    }
  }

  const handleRetry = async () => {
    setBusyAction('retry')
    setActionError(null)
    try {
      await api(`/workflows/${encodeURIComponent(selectedChain.chain_id)}/retry`, { method: 'POST' })
      await fetchChain(selectedChain.chain_id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '重试失败')
    } finally {
      setBusyAction(null)
    }
  }

  const handleRefresh = () => {
    void fetchChain(selectedChain.chain_id)
  }

  return (
    <div className="flex flex-col h-full">
      {/* DESIGN_DETAILS §8.4 Header — overall status + duration + coordinator + primary action */}
      <header className="flex items-start gap-3 px-6 py-4 border-b border-[var(--border)]">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mt-1 inline-flex items-center justify-center w-8 h-8 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          aria-label="返回"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge kind={statusToKind(selectedChain.status)} label={selectedChain.status} />
            <h1 className="text-lg font-semibold text-[var(--text-primary)] truncate">
              {selectedChain.title || `Workflow ${selectedChain.chain_id.slice(0, 8)}`}
            </h1>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-[var(--text-secondary)]">
            <span>开始 <span className="text-[var(--text-primary)]">{formatTimestamp(selectedChain.created_at)}</span></span>
            <span>耗时 <span className="text-[var(--text-primary)]">{formatDuration(durationMs)}</span></span>
            {coordinator && (
              <span>协调者 <span className="text-[var(--text-primary)]">{coordinator}</span></span>
            )}
            <span className="font-mono">chain:{selectedChain.chain_id.slice(0, 12)}</span>
            {selectedChain.trace_id && <span className="font-mono">trace:{selectedChain.trace_id.slice(0, 12)}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            刷新
          </button>
          {isActive && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] text-[var(--ava-danger)] hover:opacity-90 disabled:opacity-50 transition-colors"
            >
              {busyAction === 'cancel' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
              取消整链
            </button>
          )}
          {isFailed && (
            <button
              type="button"
              onClick={handleRetry}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--ava-running-border)] bg-[var(--ava-running-soft)] text-[var(--ava-running)] hover:opacity-90 disabled:opacity-50 transition-colors"
            >
              {busyAction === 'retry' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              重试
            </button>
          )}
        </div>
      </header>

      {actionError && (
        <div className="mx-6 mt-3 rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] p-3 text-sm text-[var(--ava-danger)]">
          {actionError}
        </div>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(300px,380px)_1fr]">
        {/* Timeline · vertical chain rail with numbered status nodes */}
        <aside className="border-r border-[var(--border)] overflow-y-auto px-4 py-5">
          {sortedNodes.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)] text-center py-8">该 workflow 暂无 step</p>
          ) : (
            <ol className="flex flex-col">
              {sortedNodes.map((node, index) => (
                <ChainStep
                  key={node.task_id}
                  node={node}
                  index={index}
                  total={sortedNodes.length}
                  isSelected={selectedNode?.task_id === node.task_id}
                  onSelect={setSelectedNodeId}
                />
              ))}
            </ol>
          )}
        </aside>

        {/* Detail panel */}
        <section className="overflow-y-auto p-6">
          {selectedNode ? (
            <NodeDetail node={selectedNode} artifacts={nodeArtifacts} />
          ) : (
            <p className="text-sm text-[var(--text-secondary)] text-center py-8">选择一个 step 查看详情</p>
          )}
        </section>
      </div>
    </div>
  )
}

// DESIGN_DETAILS §8.4: each step lives on a vertical "chain rail". The rail
// segment between two steps takes the upstream step's status colour so the
// chain's flow is readable at a glance. Failed-after-success shows a red
// segment leaving a green node, etc.
const NODE_STATUS_TONE: Record<string, { dotBg: string; dotBorder: string; numText: string; rail: string; railDashed: boolean }> = {
  succeeded:     { dotBg: 'bg-[var(--ava-success)]',  dotBorder: 'border-[var(--ava-success-border)]',  numText: 'text-white',                  rail: 'bg-[var(--ava-success-border)]',  railDashed: false },
  running:       { dotBg: 'bg-[var(--ava-running)]',  dotBorder: 'border-[var(--ava-running-border)]',  numText: 'text-white',                  rail: 'bg-[var(--ava-running-border)]',  railDashed: false },
  streaming:     { dotBg: 'bg-[var(--ava-running)]',  dotBorder: 'border-[var(--ava-running-border)]',  numText: 'text-white',                  rail: 'bg-[var(--ava-running-border)]',  railDashed: false },
  failed:        { dotBg: 'bg-[var(--ava-danger)]',   dotBorder: 'border-[var(--ava-danger-border)]',   numText: 'text-white',                  rail: 'bg-[var(--ava-danger-border)]',   railDashed: false },
  interrupted:   { dotBg: 'bg-[var(--ava-danger)]',   dotBorder: 'border-[var(--ava-danger-border)]',   numText: 'text-white',                  rail: 'bg-[var(--ava-danger-border)]',   railDashed: false },
  cancelled:     { dotBg: 'bg-[var(--ava-idle)]',     dotBorder: 'border-[var(--ava-idle-border)]',     numText: 'text-white',                  rail: 'bg-[var(--ava-idle-border)]',     railDashed: false },
  skipped:       { dotBg: 'bg-[var(--ava-idle)]',     dotBorder: 'border-[var(--ava-idle-border)]',     numText: 'text-white',                  rail: 'bg-[var(--ava-idle-border)]',     railDashed: true  },
  awaiting_deps: { dotBg: 'bg-[var(--ava-warning-soft)]', dotBorder: 'border-[var(--ava-warning-border)]', numText: 'text-[var(--ava-warning)]', rail: 'bg-[var(--border)]',              railDashed: true  },
  queued:        { dotBg: 'bg-[var(--ava-queued-soft)]',  dotBorder: 'border-[var(--ava-queued-border)]',  numText: 'text-[var(--ava-queued)]',  rail: 'bg-[var(--border)]',              railDashed: true  },
  pending:       { dotBg: 'bg-[var(--bg-tertiary)]',  dotBorder: 'border-[var(--border)]',              numText: 'text-[var(--text-secondary)]', rail: 'bg-[var(--border)]',             railDashed: true  },
}

function nodeTone(status: string) {
  return NODE_STATUS_TONE[status] ?? NODE_STATUS_TONE.pending
}

interface ChainStepProps {
  node: WorkflowNode
  index: number
  total: number
  isSelected: boolean
  onSelect: (taskId: string) => void
}

function ChainStep({ node, index, total, isSelected, onSelect }: ChainStepProps) {
  const tone = nodeTone(node.status)
  const isRunning = node.status === 'running' || node.status === 'streaming'
  const isLast = index === total - 1
  const agent = nodeAgent(node)
  const retry = nodeRetryCount(node)

  return (
    <li className="flex gap-3">
      {/* Rail column */}
      <div className="flex flex-col items-center w-7 shrink-0">
        <div className="relative pt-1">
          <span
            className={cn(
              'flex items-center justify-center w-7 h-7 rounded-full border-2 text-[11px] font-semibold shadow-sm',
              tone.dotBg,
              tone.dotBorder,
              tone.numText,
              isRunning && 'motion-safe:animate-pulse',
            )}
          >
            {index + 1}
          </span>
          {isRunning && (
            <span
              className={cn(
                'absolute inset-0 rounded-full motion-safe:animate-ping opacity-40',
                tone.dotBg,
              )}
              aria-hidden
            />
          )}
        </div>
        {!isLast && (
          <span
            className={cn(
              'flex-1 w-0.5 my-1.5 min-h-[20px]',
              tone.railDashed ? 'bg-transparent border-l-2 border-dashed border-[var(--border)] w-0' : tone.rail,
            )}
            aria-hidden
          />
        )}
      </div>

      {/* Card column */}
      <button
        type="button"
        onClick={() => onSelect(node.task_id)}
        className={cn(
          'group flex-1 text-left rounded-xl border px-3 py-2.5 mb-3 transition-colors',
          isSelected
            ? 'border-[var(--ava-primary-border)] bg-[var(--ava-primary-soft)] shadow-sm'
            : 'border-[var(--border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] hover:border-[var(--accent)]/40',
        )}
      >
        <div className="flex items-center gap-2">
          <StatusBadge kind={statusToKind(node.status)} label={NODE_STATUS_LABEL[node.status] ?? node.status} size="sm" />
          <ChevronRight className="w-3 h-3 text-[var(--text-secondary)] ml-auto shrink-0 group-hover:text-[var(--accent)] transition-colors" />
        </div>
        <p className="mt-1.5 text-sm font-medium text-[var(--text-primary)] truncate">
          {node.title || `Step ${node.position}`}
        </p>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          {agent && <span className="truncate">{agent}</span>}
          {retry > 0 && (
            <span className="text-[var(--ava-warning)] shrink-0">已重试 {retry} 次</span>
          )}
        </div>
      </button>
    </li>
  )
}

function NodeDetail({ node, artifacts }: { node: WorkflowNode; artifacts: ArtifactRecord[] }) {
  const agent = nodeAgent(node)
  const input = nodeInputSummary(node)
  const output = nodeOutputSummary(node)
  const error = nodeError(node)
  const retry = nodeRetryCount(node)
  const isFailed = node.status === 'failed' || node.status === 'interrupted'
  const isActive = node.status === 'running' || node.status === 'streaming'

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <StatusBadge kind={statusToKind(node.status)} label={NODE_STATUS_LABEL[node.status] ?? node.status} size="md" />
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          {node.title || `Step ${node.position}`}
        </h2>
        {isActive && (
          <span className="inline-flex items-center gap-1.5 text-xs text-[var(--ava-running)]">
            <PlayCircle className="w-3.5 h-3.5" />
            正在执行
          </span>
        )}
      </div>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-[var(--text-secondary)]">Agent</dt>
        <dd className="text-[var(--text-primary)]">{agent ?? '—'}</dd>
        <dt className="text-[var(--text-secondary)]">Task ID</dt>
        <dd className="font-mono text-xs text-[var(--text-secondary)]">{node.task_id}</dd>
        <dt className="text-[var(--text-secondary)]">Position</dt>
        <dd className="text-[var(--text-primary)]">{node.position}</dd>
        {retry > 0 && (
          <>
            <dt className="text-[var(--text-secondary)]">Retry</dt>
            <dd className="text-[var(--ava-warning)]">{retry} 次</dd>
          </>
        )}
        {node.parent_task_ids.length > 0 && (
          <>
            <dt className="text-[var(--text-secondary)]">前置</dt>
            <dd className="font-mono text-xs text-[var(--text-secondary)]">
              {node.parent_task_ids.map(p => p.slice(0, 8)).join(', ')}
            </dd>
          </>
        )}
      </dl>

      {/* Failed step: reason + next action surfaced first (§8.4). */}
      {isFailed && (
        <div className="rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] p-4">
          <p className="text-sm font-medium text-[var(--ava-danger)] mb-1">失败原因</p>
          <p className="text-sm text-[var(--ava-danger)] whitespace-pre-wrap break-words">
            {error ?? '未提供 reason'}
          </p>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            下一步：从顶部「重试」按钮重新跑整链，或在父任务页查看更细 trace。
          </p>
        </div>
      )}

      {input && (
        <section>
          <h3 className="text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-2">输入摘要</h3>
          <p className="text-sm text-[var(--text-primary)] whitespace-pre-wrap break-words">{input}</p>
        </section>
      )}

      {output && (
        <section>
          <h3 className="text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-2">输出摘要</h3>
          <p className="text-sm text-[var(--text-primary)] whitespace-pre-wrap break-words">{output}</p>
        </section>
      )}

      {artifacts.length > 0 && (
        <section>
          <h3 className="text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-2">
            Artifacts ({artifacts.length})
          </h3>
          <div className="space-y-3">
            {artifacts.map(artifact => (
              <ArtifactPreview key={artifact.artifact_id} artifact={artifact} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
