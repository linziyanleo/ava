import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExternalLink, GitBranch } from 'lucide-react'
import { api } from '../../api/client'
import { cn } from '../../lib/utils'
import type { DirectTaskMessage, DirectTaskStatus } from './types'
import type { WorkflowChain } from '../../stores/useWorkflowStore'
import {
  ACTIVE_TASK_STATUSES,
  ConversationTaskCard,
  RETRYABLE_TASK_STATUSES,
  TASK_STATUS_CONFIG,
  visibleTaskStatus,
} from './ConversationTaskCard'

function orderValue(task: DirectTaskMessage) {
  return task.started_at ?? Number.MAX_SAFE_INTEGER
}

function orderTasks(tasks: DirectTaskMessage[]) {
  return [...tasks].sort((a, b) => {
    const turnA = a.origin_turn_seq ?? Number.MAX_SAFE_INTEGER
    const turnB = b.origin_turn_seq ?? Number.MAX_SAFE_INTEGER
    if (turnA !== turnB) return turnA - turnB
    const startedDelta = orderValue(a) - orderValue(b)
    if (startedDelta !== 0) return startedDelta
    return a.task_id.localeCompare(b.task_id)
  })
}

function chainStatus(tasks: DirectTaskMessage[]): DirectTaskStatus {
  const statuses = new Set(tasks.map((task) => task.status))
  if (statuses.has('failed') || statuses.has('interrupted')) return 'failed'
  if (statuses.size > 0 && Array.from(statuses).every((status) => status === 'succeeded' || status === 'skipped')) return 'succeeded'
  if (statuses.size > 0 && Array.from(statuses).every((status) => status === 'cancelled' || status === 'skipped')) return 'cancelled'
  return 'running'
}

export function ChainBubble({
  chainId,
  tasks,
}: {
  chainId: string
  tasks: DirectTaskMessage[]
}) {
  const navigate = useNavigate()
  const [busyAction, setBusyAction] = useState<'cancel' | 'retry' | ''>('')
  const [actionError, setActionError] = useState('')
  const orderedTasks = useMemo(() => orderTasks(tasks), [tasks])
  const status = chainStatus(orderedTasks)
  const failed = status === 'failed'
  const succeeded = status === 'succeeded'
  const cancellable = orderedTasks.some((task) => ACTIVE_TASK_STATUSES.has(task.status))
  const retryable = orderedTasks.some((task) => RETRYABLE_TASK_STATUSES.has(task.status)) || failed
  const traceId = orderedTasks.find((task) => task.trace_id)?.trace_id || ''
  const virtualizedTaskWindow = orderedTasks.length > 10
  const skillTask = orderedTasks.find((task) => task.skill_name || task.matched_by === 'natural_language')

  const handleCancelChain = async () => {
    if (!window.confirm('Cancel this whole chain?')) return
    setBusyAction('cancel')
    setActionError('')
    try {
      await api<WorkflowChain>(`/workflows/${encodeURIComponent(chainId)}/cancel`, { method: 'POST' })
      navigate(`/?view=tasks&chain_id=${encodeURIComponent(chainId)}`)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to cancel chain')
    } finally {
      setBusyAction('')
    }
  }

  const handleRetryChain = async () => {
    setBusyAction('retry')
    setActionError('')
    try {
      const next = await api<WorkflowChain>(`/workflows/${encodeURIComponent(chainId)}/retry`, { method: 'POST' })
      const params = new URLSearchParams()
      params.set('view', 'tasks')
      params.set('chain_id', next.chain_id)
      if (next.trace_id || traceId) params.set('trace_id', next.trace_id || traceId)
      navigate({ pathname: '/', search: `?${params.toString()}` })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to retry chain')
    } finally {
      setBusyAction('')
    }
  }

  return (
    <div
      data-chain-id={chainId}
      data-skill-name={skillTask?.skill_name || undefined}
      data-match-kind={skillTask ? "matched_by: 'natural_language'" : undefined}
      className={cn(
        'max-w-full overflow-hidden rounded-lg border bg-[var(--bg-secondary)] text-xs',
        failed
          ? 'border-red-500/40'
          : succeeded
            ? 'border-emerald-500/30'
            : 'border-[var(--border)]',
      )}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-tertiary,var(--bg-secondary))] px-3 py-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--accent)]/10 text-[var(--accent)]">
          <GitBranch className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-[var(--text-primary)]">Task Chain</span>
            <span className="rounded bg-[var(--bg-primary)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-secondary)]">
              {chainId.slice(0, 12)}
            </span>
          </div>
          <p className="truncate text-[10px] text-[var(--text-secondary)]">
            {skillTask?.skill_name ? `Skill ${skillTask.skill_name}` : `${orderedTasks.length} task nodes`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate(`/?view=tasks&chain_id=${encodeURIComponent(chainId)}`)}
          className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          title="Open chain tasks"
        >
          <ExternalLink className="h-3 w-3" />
          Tasks
        </button>
        {cancellable && (
          <button
            type="button"
            onClick={handleCancelChain}
            disabled={busyAction !== ''}
            className="inline-flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-300 hover:bg-red-500/15 disabled:opacity-50"
          >
            Cancel Chain
          </button>
        )}
        {retryable && (
          <button
            type="button"
            onClick={handleRetryChain}
            disabled={busyAction !== ''}
            className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
          >
            Retry Chain
          </button>
        )}
      </div>
      {actionError && (
        <div className="border-b border-red-500/20 bg-red-500/10 px-3 py-1.5 text-[10px] text-red-300">
          {actionError}
        </div>
      )}
      <div className={cn('space-y-0 px-2 py-2 sm:px-3', virtualizedTaskWindow && 'max-h-[520px] overflow-y-auto')}>
        {orderedTasks.map((task, index) => {
          const statusConfig = TASK_STATUS_CONFIG[visibleTaskStatus(task.status)]
          return (
            <div
              key={task.task_id}
              className={cn('relative flex gap-2 pb-3 last:pb-0 sm:gap-3', virtualizedTaskWindow && '[content-visibility:auto] [contain-intrinsic-size:112px]')}
            >
              {index < orderedTasks.length - 1 && (
                <div className={cn('absolute left-[13px] top-9 h-[calc(100%-2.25rem)] border-l', statusConfig.line)} />
              )}
              <div className="min-w-0 flex-1">
                <ConversationTaskCard
                  task={task}
                  variant="chain"
                  actions={(
                    <>
                      {ACTIVE_TASK_STATUSES.has(task.status) && (
                        <button
                          type="button"
                          onClick={handleCancelChain}
                          disabled={busyAction !== ''}
                          className="text-[10px] text-red-300 hover:text-red-200 disabled:opacity-50"
                        >
                          Cancel Chain
                        </button>
                      )}
                      {RETRYABLE_TASK_STATUSES.has(task.status) && (
                        <button
                          type="button"
                          onClick={handleRetryChain}
                          disabled={busyAction !== ''}
                          className="text-[10px] text-[var(--text-secondary)] hover:text-[var(--accent)] disabled:opacity-50"
                        >
                          Retry Chain
                        </button>
                      )}
                      {task.artifact_uri && (
                        <button
                          type="button"
                          onClick={() => navigate(`/?view=tasks&task_view=artifacts&task_id=${encodeURIComponent(task.task_id)}`)}
                          className="text-[10px] text-[var(--text-secondary)] hover:text-[var(--accent)]"
                        >
                          Open Artifact
                        </button>
                      )}
                    </>
                  )}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
