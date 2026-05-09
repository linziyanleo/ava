import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ban, Check, CheckCircle2, Clock, Copy, ExternalLink, Image as ImageIcon, Loader2, Puzzle, Terminal, XOctagon, Zap } from 'lucide-react'
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer'
import { cn } from '../../lib/utils'
import { buildTokenStatsNavUrl } from '../../lib/tokenStatsNav'
import { useTaskFloater } from '../../stores/taskFloater'
import type { DirectTaskMessage, DirectTaskStatus, DirectTaskType } from './types'
import { displayImagePath, extractImagePaths, formatTimestamp, imageUrl } from './utils'
import { ImageCarousel } from './ImageCarousel'

type VisibleTaskStatus = Exclude<DirectTaskStatus, 'interrupted'>

export const ACTIVE_TASK_STATUSES = new Set<DirectTaskStatus>(['pending', 'awaiting_deps', 'queued', 'running', 'streaming'])
export const RETRYABLE_TASK_STATUSES = new Set<DirectTaskStatus>(['failed', 'cancelled', 'skipped'])

export const TASK_TYPE_CONFIG: Record<DirectTaskType, {
  icon: typeof Terminal
  label: string
  accent: string
  bg: string
}> = {
  claude_code: { icon: Terminal, label: 'Claude Code', accent: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  codex: { icon: Zap, label: 'Codex', accent: 'text-sky-500', bg: 'bg-sky-500/10' },
  image_gen: { icon: ImageIcon, label: 'Image Gen', accent: 'text-fuchsia-500', bg: 'bg-fuchsia-500/10' },
  skill: { icon: Puzzle, label: 'Skill', accent: 'text-amber-500', bg: 'bg-amber-500/10' },
}

export const TASK_STATUS_CONFIG: Record<VisibleTaskStatus, {
  icon: typeof Clock
  label: string
  color: string
  bg: string
  line: string
}> = {
  pending: { icon: Loader2, label: 'pending', color: 'text-gray-400', bg: 'bg-gray-400/10', line: 'border-gray-500/40 border-dashed' },
  awaiting_deps: { icon: Clock, label: 'awaiting deps', color: 'text-amber-400', bg: 'bg-amber-500/10', line: 'border-amber-500/40 border-dashed' },
  queued: { icon: Clock, label: 'queued', color: 'text-blue-300', bg: 'bg-blue-500/10', line: 'border-blue-500/40 border-dashed' },
  running: { icon: Loader2, label: 'running', color: 'text-blue-400', bg: 'bg-blue-500/10', line: 'border-blue-500/60' },
  streaming: { icon: Loader2, label: 'streaming', color: 'text-sky-300', bg: 'bg-sky-500/10', line: 'border-sky-500/60' },
  succeeded: { icon: CheckCircle2, label: 'succeeded', color: 'text-emerald-400', bg: 'bg-emerald-500/10', line: 'border-emerald-500/60' },
  failed: { icon: XOctagon, label: 'failed', color: 'text-red-400', bg: 'bg-red-500/10', line: 'border-red-500/60' },
  cancelled: { icon: Ban, label: 'cancelled', color: 'text-gray-400', bg: 'bg-gray-400/10', line: 'border-gray-500/40' },
  skipped: { icon: Ban, label: 'skipped', color: 'text-gray-500', bg: 'bg-gray-500/10', line: 'border-gray-500/40 border-dashed' },
}

export function visibleTaskStatus(status: DirectTaskStatus): VisibleTaskStatus {
  if (status === 'interrupted') return 'failed'
  return status
}

export function taskProgress(task: DirectTaskMessage) {
  if (typeof task.progress_percent === 'number') return Math.max(0, Math.min(100, Math.round(task.progress_percent)))
  if (task.status === 'succeeded') return 100
  if (task.status === 'streaming') return 65
  if (task.status === 'running') return 40
  if (task.status === 'queued') return 15
  if (task.status === 'pending' || task.status === 'awaiting_deps') return 5
  return 0
}

export function formatTaskDuration(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return 'unknown'
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

interface TaskDetails {
  body?: string
  timestamp?: string
  defaultExpanded?: boolean
}

interface ConversationTaskCardProps {
  task: DirectTaskMessage
  variant?: 'standalone' | 'chain' | 'result'
  highlighted?: boolean
  details?: TaskDetails
  actions?: ReactNode
  showTraceActions?: boolean
}

export function ConversationTaskCard({
  task,
  variant = 'standalone',
  highlighted = false,
  details,
  actions,
  showTraceActions = variant !== 'chain',
}: ConversationTaskCardProps) {
  const navigate = useNavigate()
  const { open: openTaskFloater } = useTaskFloater()
  const [traceCopied, setTraceCopied] = useState(false)
  const [expanded, setExpanded] = useState(() => details?.defaultExpanded ?? false)
  const [actionMenuOpen, setActionMenuOpen] = useState(false)
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const typeConfig = TASK_TYPE_CONFIG[task.task_type]
  const statusConfig = TASK_STATUS_CONFIG[visibleTaskStatus(task.status)]
  const TypeIcon = typeConfig.icon
  const StatusIcon = statusConfig.icon
  const progress = taskProgress(task)
  const active = ACTIVE_TASK_STATUSES.has(task.status)
  const body = details?.body || ''
  const preview = task.artifact_preview || task.result_preview || ''
  const imagePaths = useMemo(() => {
    if (task.task_type !== 'image_gen') return []
    return extractImagePaths([preview, body].filter(Boolean).join('\n'))
  }, [body, preview, task.task_type])

  const clearLongPressTimer = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  useEffect(() => clearLongPressTimer, [])

  const handleOpenTask = () => {
    openTaskFloater({ panel: 'background', bgView: 'all', taskId: task.task_id })
  }

  const handleOpenTrace = () => {
    if (!task.trace_id) return
    navigate(buildTokenStatsNavUrl({ traceId: task.trace_id, sessionKey: task.session_key }))
  }

  const handleCopyTraceLink = () => {
    if (!task.trace_id) return
    navigator.clipboard.writeText(`${window.location.origin}/?trace_id=${encodeURIComponent(task.trace_id)}`)
    setTraceCopied(true)
    setTimeout(() => setTraceCopied(false), 1500)
  }

  const startLongPress = () => {
    if (variant === 'chain') return
    clearLongPressTimer()
    longPressTimer.current = setTimeout(() => {
      setActionMenuOpen(true)
      longPressTimer.current = null
    }, 500)
  }

  return (
    <div
      data-bg-task-id={task.task_id}
      id={variant === 'result' ? `bg-task-result-${task.task_id}` : undefined}
      onTouchStart={startLongPress}
      onTouchMove={clearLongPressTimer}
      onTouchEnd={clearLongPressTimer}
      onContextMenu={(event) => {
        if (variant === 'chain') return
        event.preventDefault()
        setActionMenuOpen(true)
      }}
      className={cn(
        'max-w-full overflow-hidden rounded-lg border bg-[var(--bg-secondary)] text-xs transition-all duration-500',
        highlighted
          ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]/30 bg-[var(--accent)]/5'
          : 'border-[var(--border)]',
      )}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-tertiary,var(--bg-secondary))] px-3 py-2">
        <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-md', typeConfig.bg, typeConfig.accent)}>
          <TypeIcon className="h-4 w-4" />
        </span>
        <span className="font-medium text-[var(--text-primary)]">{typeConfig.label}</span>
        <span className={cn('inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium', statusConfig.bg, statusConfig.color)}>
          <StatusIcon className={cn('h-3 w-3', active && 'animate-spin')} />
          {statusConfig.label}
        </span>
        {task.chain_id && variant !== 'chain' && (
          <span className="rounded bg-[var(--bg-primary)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-secondary)]">
            chain:{task.chain_id.slice(0, 8)}
          </span>
        )}
        <button
          type="button"
          onClick={handleOpenTask}
          className="ml-auto inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          title="查看完整日志"
        >
          <ExternalLink className="h-3 w-3" />
          任务
        </button>
        {showTraceActions && task.trace_id && (
          <>
            <button
              type="button"
              onClick={handleOpenTrace}
              className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              title={task.trace_id}
            >
              <ExternalLink className="h-3 w-3" />
              Trace
            </button>
            <button
              type="button"
              onClick={handleCopyTraceLink}
              className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              title="Copy trace link"
            >
              {traceCopied ? <Check className="h-3 w-3 text-[var(--success)]" /> : <Copy className="h-3 w-3" />}
              Link
            </button>
          </>
        )}
      </div>

      <div className="space-y-2 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
          <span className="font-mono">{task.task_id}</span>
          {task.trace_id && <span className="font-mono">trace:{task.trace_id.slice(0, 8)}</span>}
          {task.origin_turn_seq != null && <span>turn {task.origin_turn_seq}</span>}
          <span>{formatTaskDuration(task.elapsed_ms)}</span>
          {details?.timestamp && <span>{formatTimestamp(details.timestamp)}</span>}
        </div>

        <p className="line-clamp-2 text-sm text-[var(--text-primary)]">{task.prompt_preview || task.task_id}</p>

        {(task.status === 'streaming' || typeof task.progress_percent === 'number') && (
          <div className="flex items-center gap-2">
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
              <div className="h-full rounded-full bg-sky-400 transition-[width]" style={{ width: `${progress}%` }} />
            </div>
            <span className="w-8 text-right font-mono text-[10px] text-[var(--text-secondary)]">{progress}%</span>
          </div>
        )}

        {task.error_message && (
          <div className="rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400">
            {task.error_message}
          </div>
        )}

        {imagePaths.length > 0 && (
          <div className="space-y-1.5">
            <ImageCarousel urls={imagePaths.map((path) => imageUrl(path))} alt="Generated image" maxHeight={variant === 'chain' ? 160 : 220} />
            <div className="flex flex-wrap gap-1.5">
              {imagePaths.map((path) => (
                <span key={path} className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-secondary)]">
                  {displayImagePath(path)}
                </span>
              ))}
            </div>
          </div>
        )}

        {preview && imagePaths.length === 0 && (
          <div className="line-clamp-3 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-2 py-1.5 text-[11px] text-[var(--text-secondary)]">
            {task.status === 'streaming' ? '实时产物预览: ' : ''}{preview}
          </div>
        )}

        {body && (
          <div>
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="text-[11px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              {expanded ? '收起详情' : '展开详情'}
            </button>
            {expanded && (
              <div className="mt-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)]">
                <MarkdownRenderer content={body} />
              </div>
            )}
          </div>
        )}

        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>

      {actionMenuOpen && (
        <div className="fixed inset-0 z-[70] flex items-end bg-black/40 p-3 sm:items-center sm:justify-center" onClick={() => setActionMenuOpen(false)}>
          <div className="w-full max-w-sm rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-2 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              onClick={() => {
                setActionMenuOpen(false)
                handleOpenTask()
              }}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            >
              <ExternalLink className="h-4 w-4" />
              Open Task
            </button>
            {task.trace_id && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setActionMenuOpen(false)
                    handleOpenTrace()
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                >
                  <ExternalLink className="h-4 w-4" />
                  Open Trace
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleCopyTraceLink()
                    setActionMenuOpen(false)
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                >
                  <Copy className="h-4 w-4" />
                  Copy Trace Link
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
