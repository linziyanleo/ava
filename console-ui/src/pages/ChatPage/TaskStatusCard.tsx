import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ban, CheckCircle2, Clock, ExternalLink, Image as ImageIcon, Loader2, Terminal, XOctagon, Zap } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { DirectTaskMessage, DirectTaskStatus, DirectTaskType } from './types'
import { displayImagePath, extractImagePaths, imageUrl } from './utils'
import { ImageCarousel } from './ImageCarousel'

const TYPE_CONFIG: Record<DirectTaskType, {
  icon: typeof Terminal
  label: string
  accent: string
  bg: string
}> = {
  claude_code: {
    icon: Terminal,
    label: 'Claude Code',
    accent: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
  },
  codex: {
    icon: Zap,
    label: 'Codex',
    accent: 'text-sky-500',
    bg: 'bg-sky-500/10',
  },
  image_gen: {
    icon: ImageIcon,
    label: 'Image Gen',
    accent: 'text-fuchsia-500',
    bg: 'bg-fuchsia-500/10',
  },
}

const STATUS_CONFIG: Record<DirectTaskStatus, {
  icon: typeof Clock
  label: string
  color: string
  bg: string
}> = {
  queued: { icon: Clock, label: 'queued', color: 'text-yellow-500', bg: 'bg-yellow-500/10' },
  running: { icon: Loader2, label: 'running', color: 'text-blue-500', bg: 'bg-blue-500/10' },
  succeeded: { icon: CheckCircle2, label: 'succeeded', color: 'text-green-500', bg: 'bg-green-500/10' },
  failed: { icon: XOctagon, label: 'failed', color: 'text-red-500', bg: 'bg-red-500/10' },
  cancelled: { icon: Ban, label: 'cancelled', color: 'text-gray-400', bg: 'bg-gray-400/10' },
  interrupted: { icon: XOctagon, label: 'interrupted', color: 'text-orange-500', bg: 'bg-orange-500/10' },
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export function TaskStatusCard({ task }: { task: DirectTaskMessage }) {
  const navigate = useNavigate()
  const typeConfig = TYPE_CONFIG[task.task_type]
  const statusConfig = STATUS_CONFIG[task.status]
  const TypeIcon = typeConfig.icon
  const StatusIcon = statusConfig.icon
  const imagePaths = useMemo(
    () => task.task_type === 'image_gen' && task.result_preview ? extractImagePaths(task.result_preview) : [],
    [task.result_preview, task.task_type],
  )

  return (
    <div
      data-bg-task-id={task.task_id}
      className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-xs overflow-hidden"
    >
      <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-tertiary,var(--bg-secondary))] px-3 py-2">
        <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-md', typeConfig.bg, typeConfig.accent)}>
          <TypeIcon className="h-4 w-4" />
        </span>
        <span className="font-medium text-[var(--text-primary)]">{typeConfig.label}</span>
        <span className={cn('inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium', statusConfig.bg, statusConfig.color)}>
          <StatusIcon className={cn('h-3 w-3', task.status === 'running' && 'animate-spin')} />
          {statusConfig.label}
        </span>
        <button
          type="button"
          onClick={() => navigate(`/bg-tasks?task_id=${encodeURIComponent(task.task_id)}`)}
          className="ml-auto inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          title="Open background task"
        >
          <ExternalLink className="h-3 w-3" />
          Task
        </button>
      </div>
      <div className="space-y-2 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
          <span className="font-mono">{task.task_id}</span>
          <span>{formatDuration(task.elapsed_ms)}</span>
        </div>
        <div className="line-clamp-2 text-sm text-[var(--text-primary)]">{task.prompt_preview}</div>
        {task.error_message && (
          <div className="rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400">
            {task.error_message}
          </div>
        )}
        {imagePaths.length > 0 && (
          <div className="space-y-1.5">
            <ImageCarousel urls={imagePaths.map((path) => imageUrl(path))} alt="Generated image" maxHeight={180} />
            <div className="flex flex-wrap gap-1.5">
              {imagePaths.map((path) => (
                <span key={path} className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-secondary)]">
                  {displayImagePath(path)}
                </span>
              ))}
            </div>
          </div>
        )}
        {task.result_preview && imagePaths.length === 0 && (
          <div className="line-clamp-3 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-2 py-1.5 text-[11px] text-[var(--text-secondary)]">
            {task.result_preview}
          </div>
        )}
      </div>
    </div>
  )
}
