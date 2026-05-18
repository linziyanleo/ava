import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Box, CalendarClock, GitBranch, ListChecks, X } from 'lucide-react'
import BgTasksPage, { type BgTaskView } from '../../pages/BgTasksPage'
import MediaPage from '../../pages/MediaPage'
import ScheduledTasksPage from '../../pages/ScheduledTasksPage'
import WorkflowsListPanel from './WorkflowsListPanel'
import { cn } from '../../lib/utils'
import { useTaskFloater } from '../../stores/taskFloater'
import type { TaskFloaterPanel } from '../../stores/taskFloater'

const PANEL_TABS: Array<{ id: TaskFloaterPanel; label: string; icon: typeof ListChecks }> = [
  { id: 'background', label: '后台任务', icon: ListChecks },
  { id: 'workflows', label: '工作流', icon: GitBranch },
  { id: 'scheduled', label: '定时任务', icon: CalendarClock },
  { id: 'artifacts', label: '产物', icon: Box },
]

const BG_VIEW_TABS: Array<{ id: BgTaskView; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'current', label: '当前进行中' },
  { id: 'history', label: '历史' },
]

export default function TaskFloater() {
  const {
    isOpen,
    panel,
    bgView,
    selectedTaskId,
    traceId,
    chainId,
    close,
    setPanel,
    setBgView,
  } = useTaskFloater()

  useEffect(() => {
    if (!isOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [close, isOpen])

  if (!isOpen) return null

  const subtitle = panel === 'scheduled'
    ? 'cron / heartbeat'
    : panel === 'artifacts'
      ? 'media artifacts'
      : panel === 'workflows'
        ? 'workflow chains'
        : selectedTaskId
        ? `task_id=${selectedTaskId}`
        : chainId
          ? `chain_id=${chainId}`
          : traceId
            ? `trace_id=${traceId}`
            : BG_VIEW_TABS.find((item) => item.id === bgView)?.label ?? '全部'

  return createPortal(
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/40" onClick={close}>
      <aside
        className="flex h-full w-full max-w-[760px] flex-col border-l border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex shrink-0 flex-col gap-3 border-b border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-sm font-semibold text-[var(--text-primary)]">任务</h1>
              <p className="truncate text-[10px] text-[var(--text-secondary)]">{subtitle}</p>
            </div>
            <button
              type="button"
              onClick={close}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
              title="关闭任务浮窗"
              aria-label="关闭任务浮窗"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1 rounded-lg bg-[var(--bg-primary)] p-1">
              {PANEL_TABS.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setPanel(item.id)}
                    className={cn(
                      'inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors',
                      panel === item.id
                        ? 'bg-[var(--accent)] text-white'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </button>
                )
              })}
            </div>
            {panel === 'background' && (
              <div className="flex gap-1 overflow-x-auto scrollbar-none">
                {BG_VIEW_TABS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setBgView(item.id)}
                    className={cn(
                      'h-8 shrink-0 rounded-md px-3 text-xs font-medium transition-colors',
                      bgView === item.id
                        ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {panel === 'scheduled' ? (
            <ScheduledTasksPage embedded />
          ) : panel === 'artifacts' ? (
            <MediaPage />
          ) : panel === 'workflows' ? (
            <WorkflowsListPanel />
          ) : (
            <BgTasksPage
              embedded
              taskView={bgView}
              taskId={selectedTaskId}
              traceId={traceId}
              chainId={chainId}
            />
          )}
        </div>
      </aside>
    </div>,
    document.body,
  )
}
