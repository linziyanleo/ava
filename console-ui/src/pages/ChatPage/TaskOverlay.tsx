import { useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'
import BgTasksPage from '../BgTasksPage'
import MediaPage from '../MediaPage'
import ScheduledTasksPage from '../ScheduledTasksPage'
import { cn } from '../../lib/utils'

export type TaskOverlaySection = 'current' | 'history' | 'scheduled' | 'artifacts'

const SECTIONS: Array<{ id: TaskOverlaySection; label: string }> = [
  { id: 'current', label: '当前进行中' },
  { id: 'history', label: '历史' },
  { id: 'scheduled', label: '定时任务' },
  { id: 'artifacts', label: '产物视图' },
]

function normalizeSection(value: string | null): TaskOverlaySection {
  if (value === 'history' || value === 'scheduled' || value === 'artifacts') return value
  return 'current'
}

function overlaySubtitle({
  taskId,
  chainId,
  traceId,
  section,
}: {
  taskId: string | null
  chainId: string | null
  traceId: string | null
  section: TaskOverlaySection
}) {
  if (taskId) return `task_id=${taskId}`
  if (chainId) return `chain_id=${chainId}`
  if (traceId) return `trace_id=${traceId}`
  return SECTIONS.find((item) => item.id === section)?.label ?? '任务页'
}

export function TaskOverlay({
  taskId,
  chainId,
  traceId,
  taskView,
  isMobile,
  onClose,
}: {
  taskId: string | null
  chainId: string | null
  traceId: string | null
  taskView: string | null
  isMobile?: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const section = useMemo(() => normalizeSection(taskView), [taskView])
  const subtitle = overlaySubtitle({ taskId, chainId, traceId, section })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const setSection = (nextSection: TaskOverlaySection) => {
    const next = new URLSearchParams(searchParams)
    next.set('view', 'tasks')
    next.set('task_view', nextSection)
    if (nextSection === 'scheduled' || nextSection === 'artifacts') {
      next.delete('task_id')
      next.delete('chain_id')
    }
    navigate({ pathname: '/', search: `?${next.toString()}` })
  }

  return (
    <section className={cn(
      'flex flex-col bg-[var(--bg-primary)] animate-task-overlay-in',
      isMobile ? 'fixed inset-0 z-[60]' : 'absolute inset-0 z-30',
    )}>
      <header className={cn(
        'flex shrink-0 flex-col gap-2 border-b border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3',
        isMobile && 'safe-area-inset-top',
      )}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-[var(--text-primary)]">任务页</h1>
            <p className="truncate text-[10px] text-[var(--text-secondary)]">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            title="关闭任务页"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex gap-1 overflow-x-auto scrollbar-none">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                'h-8 shrink-0 rounded-md px-3 text-xs font-medium transition-colors',
                section === item.id
                  ? 'bg-[var(--accent)] text-white'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>
      <div className={cn('min-h-0 flex-1 overflow-y-auto p-4 md:p-6', isMobile && 'mobile-task-overlay-body')}>
        {section === 'scheduled' ? (
          <ScheduledTasksPage />
        ) : section === 'artifacts' ? (
          <MediaPage />
        ) : (
          <BgTasksPage embedded taskView={section} traceId={traceId} chainId={chainId} />
        )}
      </div>
    </section>
  )
}
