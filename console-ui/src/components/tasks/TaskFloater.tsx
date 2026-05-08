import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import BgTasksPage from '../../pages/BgTasksPage'
import { useTaskFloater } from '../../stores/taskFloater'

export default function TaskFloater() {
  const { isOpen, selectedTaskId, close } = useTaskFloater()

  useEffect(() => {
    if (!isOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [close, isOpen])

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/40" onClick={close}>
      <aside
        className="flex h-full w-full max-w-[520px] flex-col border-l border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-[var(--text-primary)]">任务</h1>
            <p className="truncate text-[10px] text-[var(--text-secondary)]">
              {selectedTaskId ? `task_id=${selectedTaskId}` : '当前进行中'}
            </p>
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
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <BgTasksPage embedded taskView="all" taskId={selectedTaskId} />
        </div>
      </aside>
    </div>,
    document.body,
  )
}
