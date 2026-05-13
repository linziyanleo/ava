import { useEffect, useRef } from 'react'
import { wsUrl } from '../api/client'
import { setTaskFloaterBadgeCount } from '../stores/taskFloater'

interface AvaDesktopApi {
  showNotification?: (payload: { title: string; body?: string; taskId?: string }) => Promise<{ ok: boolean }>
  setBadgeCount?: (count: number) => Promise<{ ok: boolean; error?: string }>
}

interface BgTaskSnapshot {
  task_id: string
  status: string
  task_type?: string
  prompt_preview?: string
}

interface BgTaskUpdate {
  type: 'update'
  tasks: BgTaskSnapshot[]
}

const NOTIFIABLE_STATUSES = new Set(['completed', 'succeeded', 'failed'])
const ACTIVE_BADGE_STATUSES = new Set(['queued', 'running', 'streaming', 'pending', 'awaiting_deps'])

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

function notificationTitle(status: string) {
  return status === 'failed' ? 'Ava task failed' : 'Ava task completed'
}

function activeBadgeCount(tasks: BgTaskSnapshot[]) {
  return tasks.filter((task) => ACTIVE_BADGE_STATUSES.has(task.status)).length
}

export function useBgTaskNotifications() {
  const previousStatusesRef = useRef<Map<string, string>>(new Map())

  useEffect(() => {
    const api = desktopApi()
    if (!api?.showNotification && !api?.setBadgeCount) return
    const showNotification = api.showNotification

    const socket = new WebSocket(wsUrl('/bg-tasks/ws'))
    socket.onmessage = (event) => {
      let payload: BgTaskUpdate
      try {
        payload = JSON.parse(event.data) as BgTaskUpdate
      } catch {
        return
      }
      if (payload.type !== 'update' || !Array.isArray(payload.tasks)) return

      setTaskFloaterBadgeCount(activeBadgeCount(payload.tasks))
      for (const task of payload.tasks) {
        const previousStatus = previousStatusesRef.current.get(task.task_id)
        if (
          showNotification
          && previousStatus
          && !NOTIFIABLE_STATUSES.has(previousStatus)
          && NOTIFIABLE_STATUSES.has(task.status)
        ) {
          void showNotification({
            title: notificationTitle(task.status),
            body: task.prompt_preview || task.task_type || task.task_id,
            taskId: task.task_id,
          })
        }
        previousStatusesRef.current.set(task.task_id, task.status)
      }
    }
    socket.onerror = () => socket.close()

    return () => socket.close()
  }, [])
}
