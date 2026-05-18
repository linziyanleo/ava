import { create } from 'zustand'

export type TaskFloaterPanel = 'background' | 'scheduled' | 'artifacts' | 'workflows'
export type TaskFloaterBgView = 'all' | 'current' | 'history'
export type TaskFloaterWorkflowView = 'all' | 'active' | 'failed' | 'done'

interface TaskFloaterOpenOptions {
  panel?: TaskFloaterPanel
  bgView?: TaskFloaterBgView
  workflowView?: TaskFloaterWorkflowView
  taskId?: string | null
  traceId?: string | null
  chainId?: string | null
}

interface TaskFloaterState {
  isOpen: boolean
  panel: TaskFloaterPanel
  bgView: TaskFloaterBgView
  workflowView: TaskFloaterWorkflowView
  selectedTaskId: string | null
  traceId: string | null
  chainId: string | null
  open: (options?: string | TaskFloaterOpenOptions) => void
  setPanel: (panel: TaskFloaterPanel) => void
  setBgView: (bgView: TaskFloaterBgView) => void
  setWorkflowView: (workflowView: TaskFloaterWorkflowView) => void
  close: () => void
}

export const useTaskFloater = create<TaskFloaterState>((set) => ({
  isOpen: false,
  panel: 'background',
  bgView: 'all',
  workflowView: 'all',
  selectedTaskId: null,
  traceId: null,
  chainId: null,
  open: (options) => {
    if (typeof options === 'string') {
      set({
        isOpen: true,
        panel: 'background',
        bgView: 'all',
        workflowView: 'all',
        selectedTaskId: options,
        traceId: null,
        chainId: null,
      })
      return
    }
    set({
      isOpen: true,
      panel: options?.panel ?? 'background',
      bgView: options?.bgView ?? 'all',
      workflowView: options?.workflowView ?? 'all',
      selectedTaskId: options?.taskId ?? null,
      traceId: options?.traceId ?? null,
      chainId: options?.chainId ?? null,
    })
  },
  setPanel: (panel) => set({ panel }),
  setBgView: (bgView) => set({ bgView }),
  setWorkflowView: (workflowView) => set({ workflowView }),
  close: () => set({
    isOpen: false,
    panel: 'background',
    bgView: 'all',
    workflowView: 'all',
    selectedTaskId: null,
    traceId: null,
    chainId: null,
  }),
}))

interface AvaDesktopApi {
  onOpenTaskFloater?: (callback: (payload?: { taskId?: string | null }) => void) => () => void
  setBadgeCount?: (count: number) => Promise<{ ok: boolean; error?: string }>
}

let uninstallDesktopBridge: (() => void) | null = null

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

export function installTaskFloaterDesktopBridge() {
  if (uninstallDesktopBridge) return uninstallDesktopBridge

  const api = desktopApi()
  if (!api?.onOpenTaskFloater) return () => {}

  uninstallDesktopBridge = api.onOpenTaskFloater((payload) => {
    useTaskFloater.getState().open({
      panel: 'background',
      bgView: 'all',
      taskId: payload?.taskId ?? null,
    })
  })

  return () => {
    uninstallDesktopBridge?.()
    uninstallDesktopBridge = null
  }
}

export function setTaskFloaterBadgeCount(count: number) {
  const api = desktopApi()
  if (!api?.setBadgeCount) return
  void api.setBadgeCount(count)
}
