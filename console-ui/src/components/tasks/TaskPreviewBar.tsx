import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, Loader2, Timer } from 'lucide-react'
import { api } from '../../api/client'
import { cn } from '../../lib/utils'
import { useAuth } from '../../stores/auth'

interface ActiveTask {
  task_id: string
  task_type: string
  status: string
  prompt_preview: string
  started_at: number | null
}

interface ActiveTasksResponse {
  tasks: ActiveTask[]
}

interface TaskPreviewBarProps {
  onOpenTask: (taskId: string) => void
  onOpenList: () => void
  density?: 'topbar' | 'inline'
}

const ACTIVE_STATUSES = new Set(['pending', 'awaiting_deps', 'queued', 'running', 'streaming'])

function statusClass(status: string) {
  if (status === 'failed') return 'border-red-500/30 bg-red-500/10 text-red-300'
  if (status === 'awaiting_deps') return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  if (status === 'queued' || status === 'pending') return 'border-blue-500/25 bg-blue-500/10 text-blue-300'
  if (status === 'streaming' || status === 'running') return 'border-blue-400/40 bg-blue-500/15 text-blue-200'
  return 'border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
}

export function TaskPreviewBar({ onOpenTask, onOpenList, density = 'inline' }: TaskPreviewBarProps) {
  const { isMockTester } = useAuth()
  const mockMode = isMockTester()
  const [tasks, setTasks] = useState<ActiveTask[]>([])

  useEffect(() => {
    if (mockMode) return

    let disposed = false
    const loadTasks = () => {
      api<ActiveTasksResponse>('/bg-tasks?include_finished=false')
        .then((response) => {
          if (!disposed) setTasks(response.tasks || [])
        })
        .catch(() => {
          if (!disposed) setTasks([])
        })
    }

    loadTasks()
    const timer = window.setInterval(loadTasks, 3000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [mockMode])

  const activeTasks = useMemo(
    () => mockMode ? [] : tasks.filter((task) => ACTIVE_STATUSES.has(task.status)).slice(0, 8),
    [mockMode, tasks],
  )

  return (
    <div
      className={cn(
        'flex items-center gap-2 bg-[var(--bg-secondary)] px-3',
        density === 'topbar'
          ? 'h-14 min-w-0 border-x border-[var(--border)]'
          : 'min-h-11 border-b border-[var(--border)]',
      )}
    >
      <div className="flex shrink-0 items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
        <Timer className="h-4 w-4" />
        Tasks
      </div>
      <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto py-2 scrollbar-none">
        {activeTasks.length > 0 ? (
          activeTasks.map((task) => (
            <button
              key={task.task_id}
              type="button"
              onClick={() => onOpenTask(task.task_id)}
              className={cn('inline-flex max-w-64 shrink-0 items-center gap-2 rounded-md border px-2.5 py-1 text-xs', statusClass(task.status))}
              title={task.prompt_preview || task.task_id}
            >
              {(task.status === 'running' || task.status === 'streaming') && <Loader2 className="h-3 w-3 animate-spin" />}
              <span className="font-mono">{task.task_type}</span>
              <span className="truncate">{task.prompt_preview || task.task_id}</span>
            </button>
          ))
        ) : (
          <span className="inline-flex items-center rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
            No active tasks
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onOpenList}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[var(--border)] px-2.5 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
      >
        <ExternalLink className="h-3.5 w-3.5" />
        展开
      </button>
    </div>
  )
}
